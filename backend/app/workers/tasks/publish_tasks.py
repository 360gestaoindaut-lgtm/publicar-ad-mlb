from app.workers.celery_app import celery_app


@celery_app.task(name="app.workers.tasks.publish_tasks.publish_listing", bind=True, max_retries=2)
def publish_listing(self, listing_id: str) -> dict:
    # Implementado na Fase 4
    raise NotImplementedError("Fase 4")
