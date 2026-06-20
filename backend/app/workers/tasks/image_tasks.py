from app.workers.celery_app import celery_app


@celery_app.task(name="app.workers.tasks.image_tasks.generate_images", bind=True, max_retries=2)
def generate_images(self, listing_id: str) -> dict:
    # Implementado na Fase 3
    raise NotImplementedError("Fase 3")


@celery_app.task(name="app.workers.tasks.image_tasks.upload_images_to_ml", bind=True, max_retries=3)
def upload_images_to_ml(self, listing_id: str) -> dict:
    # Implementado na Fase 3
    raise NotImplementedError("Fase 3")
