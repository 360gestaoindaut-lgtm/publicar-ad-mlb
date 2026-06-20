from app.workers.celery_app import celery_app


@celery_app.task(name="app.workers.tasks.ai_tasks.generate_title", bind=True, max_retries=3)
def generate_title(self, listing_id: str) -> dict:
    # Implementado na Fase 2
    raise NotImplementedError("Fase 2")


@celery_app.task(name="app.workers.tasks.ai_tasks.generate_description", bind=True, max_retries=3)
def generate_description(self, listing_id: str) -> dict:
    # Implementado na Fase 4
    raise NotImplementedError("Fase 4")
