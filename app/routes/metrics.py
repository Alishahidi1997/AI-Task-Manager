from fastapi import APIRouter

from app.metrics.prometheus import metrics_response

router = APIRouter(tags=["metrics"])


@router.get("/metrics")
def prometheus_metrics():
    return metrics_response()
