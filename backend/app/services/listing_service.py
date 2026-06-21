from uuid import UUID
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, func
from app.models.listing import Listing
from app.models.listing_title import ListingTitle
from app.models.listing_attribute import ListingAttribute
from app.models.listing_description import ListingDescription
from app.models.listing_image import ListingImage
from app.models.listing_job import ListingJob
from app.models.user import User
from app.models.seller import Seller
from app.schemas.listing import ListingCreate, ListingPage, ListingSummary


class ListingService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(self, data: ListingCreate, user: User, seller: Seller) -> Listing:
        listing = Listing(
            seller_id=seller.id,
            created_by=user.id,
            **data.model_dump(),
        )
        self.db.add(listing)
        await self.db.commit()
        await self.db.refresh(listing)
        return listing

    async def get_or_404(self, listing_id: UUID, seller_id: UUID) -> Listing:
        result = await self.db.execute(
            select(Listing).where(Listing.id == listing_id, Listing.seller_id == seller_id)
        )
        listing = result.scalar_one_or_none()
        if not listing:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Anúncio não encontrado")
        return listing

    async def list_listings(
        self,
        seller_id: UUID,
        filter_status: str | None,
        page: int,
        page_size: int,
    ) -> ListingPage:
        query = select(Listing).where(Listing.seller_id == seller_id)
        if filter_status:
            query = query.where(Listing.status == filter_status)

        count_result = await self.db.execute(
            select(func.count()).select_from(query.subquery())
        )
        total = count_result.scalar_one()

        query = query.order_by(Listing.created_at.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)
        result = await self.db.execute(query)
        items = result.scalars().all()

        return ListingPage(
            items=[ListingSummary.model_validate(i) for i in items],
            total=total,
            page=page,
            page_size=page_size,
        )

    async def delete(self, listing_id: UUID, seller_id: UUID) -> None:
        listing = await self.get_or_404(listing_id, seller_id)
        if listing.status not in ("draft", "failed"):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Somente anúncios em rascunho ou com falha podem ser excluídos",
            )
        await self.db.delete(listing)
        await self.db.commit()

    async def start_pipeline(self, listing: Listing) -> None:
        if listing.status != "draft":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Pipeline não pode ser iniciado no status '{listing.status}'",
            )
        listing.status = "generating_title"
        await self.db.commit()
        from app.workers.tasks.ai_tasks import generate_title
        generate_title.delay(str(listing.id))

    async def retry_pipeline(self, listing: Listing) -> None:
        if listing.status != "failed":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Retry disponível apenas para anúncios com falha",
            )
        listing.error_message = None
        # Se a categoria já foi prevista, basta o seller corrigir os atributos;
        # não é necessário reger todo o pipeline desde o início.
        if listing.ml_category_id:
            listing.status = "pending_seller_attributes"
            await self.db.commit()
            return
        listing.status = "generating_title"
        await self.db.commit()
        from app.workers.tasks.ai_tasks import generate_title
        generate_title.delay(str(listing.id))

    async def select_title(self, listing: Listing, title_id: UUID) -> None:
        if listing.status != "pending_title_approval":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Seleção de título disponível apenas no status 'pending_title_approval'",
            )
        result = await self.db.execute(
            select(ListingTitle).where(
                ListingTitle.id == title_id, ListingTitle.listing_id == listing.id
            )
        )
        title = result.scalar_one_or_none()
        if not title:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Título não encontrado")

        await self.db.execute(
            update(ListingTitle)
            .where(ListingTitle.listing_id == listing.id)
            .values(selected=False)
        )
        title.selected = True
        listing.selected_title = title.title_text
        listing.status = "predicting_category"
        await self.db.commit()

        from app.workers.tasks.category_tasks import predict_category
        predict_category.delay(str(listing.id))

    async def submit_attributes(self, listing: Listing, submitted: list[dict]) -> None:
        if listing.status != "pending_seller_attributes":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Atributos só podem ser enviados no status 'pending_seller_attributes'",
            )
        for item in submitted:
            result = await self.db.execute(
                select(ListingAttribute).where(
                    ListingAttribute.listing_id == listing.id,
                    ListingAttribute.attribute_id == item["attribute_id"],
                )
            )
            attr = result.scalar_one_or_none()
            if attr:
                attr.value_id = item.get("value_id")
                attr.value_name = item.get("value_name")
                attr.source = "seller"

        # Se imagens aprovadas e descrição já existem (retry após erro de publicação),
        # pula direto para ready_to_publish sem regenerar tudo.
        approved_img = (await self.db.execute(
            select(ListingImage).where(
                ListingImage.listing_id == listing.id,
                ListingImage.approved == True,
            )
        )).scalars().first()
        description = (await self.db.execute(
            select(ListingDescription).where(ListingDescription.listing_id == listing.id)
        )).scalar_one_or_none()

        new_status = "ready_to_publish" if (approved_img and description) else "pending_description"
        listing.status = new_status
        await self.db.commit()

        # Batch: avança automaticamente sem esperar o seller clicar
        if listing.created_via == "batch":
            if new_status == "pending_description":
                listing.status = "generating_images"
                await self.db.commit()
                from app.workers.tasks.image_tasks import generate_images
                generate_images.delay(str(listing.id))
            elif new_status == "ready_to_publish":
                listing.status = "publishing"
                await self.db.commit()
                from app.workers.tasks.publish_tasks import publish_listing
                publish_listing.delay(str(listing.id))

    async def trigger_image_generation(self, listing: Listing) -> None:
        if listing.status != "pending_description":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Geração de imagens indisponível no status '{listing.status}'",
            )
        listing.status = "generating_images"
        await self.db.commit()
        from app.workers.tasks.image_tasks import generate_images
        generate_images.delay(str(listing.id))

    async def approve_images(self, listing: Listing, approved_ids: list[UUID]) -> None:
        if listing.status != "pending_image_approval":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Aprovação de imagens disponível apenas no status 'pending_image_approval'",
            )
        if not approved_ids:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Pelo menos uma imagem deve ser aprovada",
            )
        result = await self.db.execute(
            select(ListingImage).where(ListingImage.listing_id == listing.id)
        )
        images = result.scalars().all()

        approved_set = set(approved_ids)
        order_map = {uid: i for i, uid in enumerate(approved_ids)}
        approved_ml_ids = []

        for img in images:
            if img.id in approved_set:
                img.approved = True
                img.sort_order = order_map[img.id]
                img.status = "approved"
                if img.ml_picture_id:
                    approved_ml_ids.append(img.ml_picture_id)
            else:
                img.approved = False
                img.status = "rejected"

        # Marca as imagens aprovadas no índice SKU→imagem
        if approved_ml_ids and listing.sku_external_id:
            from app.models.product_image import ProductImage
            from sqlalchemy import update as sa_update
            await self.db.execute(
                sa_update(ProductImage)
                .where(
                    ProductImage.seller_id == listing.seller_id,
                    ProductImage.sku == listing.sku_external_id,
                    ProductImage.ml_picture_id.in_(approved_ml_ids),
                )
                .values(is_approved=True)
            )

        listing.status = "generating_description"
        await self.db.commit()

        from app.workers.tasks.ai_tasks import generate_description
        generate_description.delay(str(listing.id))

    async def trigger_publish(self, listing: Listing) -> None:
        if listing.status != "ready_to_publish":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Publicação indisponível no status '{listing.status}'",
            )
        listing.status = "publishing"
        await self.db.commit()

        from app.workers.tasks.publish_tasks import publish_listing
        publish_listing.delay(str(listing.id))
