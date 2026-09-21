from fastapi import APIRouter

from app.models.post_services import PostServicesRequest, PostServicesResponse
from app.services import post_services as post_services_service

router = APIRouter(prefix="/api/v1", tags=["aggregated"])


@router.post("/post-services", response_model=PostServicesResponse)
def post_services(request: PostServicesRequest) -> PostServicesResponse:
    return post_services_service.execute_actions(request)
