import sys
from app.workers.tasks.category_tasks import predict_category

listing_id = sys.argv[1]
result = predict_category.delay(listing_id)
print(f"Task disparada: {result.id}")
