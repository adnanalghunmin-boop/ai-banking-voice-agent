from fastapi import APIRouter, status

from app.models.common import ServiceRequestResponse
from app.models.customer_request import CustomerDetailChangeRequest
from app.services import customer_requests as customer_requests_service

router = APIRouter(prefix="/api/v1/customers", tags=["customers"])


@router.post(
    "/detail-change-request",
    response_model=ServiceRequestResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_customer_detail_change_request(
    request: CustomerDetailChangeRequest,
) -> ServiceRequestResponse:
    return customer_requests_service.create_customer_detail_change_request(request)
