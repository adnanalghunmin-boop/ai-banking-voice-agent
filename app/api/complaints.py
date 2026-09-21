from fastapi import APIRouter, status

from app.models.complaint import ComplaintCreateRequest, ComplaintResponse
from app.services import complaints as complaints_service

router = APIRouter(prefix="/api/v1/complaints", tags=["complaints"])


@router.post("", response_model=ComplaintResponse, status_code=status.HTTP_201_CREATED)
def create_complaint(request: ComplaintCreateRequest) -> ComplaintResponse:
    return complaints_service.create_complaint(request)
