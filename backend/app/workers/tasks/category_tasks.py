from app.workers.celery_app import celery_app


@celery_app.task(name="app.workers.tasks.category_tasks.predict_category", bind=True, max_retries=3)
def predict_category(self, listing_id: str) -> dict:
    # Implementado na Fase 2
    raise NotImplementedError("Fase 2")
