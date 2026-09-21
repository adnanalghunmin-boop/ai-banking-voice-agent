from fastapi import APIRouter

from app.models.get_services import GetServicesRequest, GetServicesResponse
from app.services import aggregated as aggregated_service

router = APIRouter(prefix="/api/v1", tags=["aggregated"])


@router.post(
    "/get-services",
    response_model=GetServicesResponse,
    response_model_exclude_none=True,
)
def get_services(request: GetServicesRequest) -> GetServicesResponse:
    return aggregated_service.get_services(request)
