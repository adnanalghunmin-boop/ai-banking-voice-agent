from fastapi import APIRouter, status

from app.models.document import DocumentRequestCreateRequest, DocumentRequestResponse
from app.services import documents as documents_service

router = APIRouter(prefix="/api/v1/document-requests", tags=["document-requests"])


@router.post(
    "", response_model=DocumentRequestResponse, status_code=status.HTTP_201_CREATED
)
def create_document_request(
    request: DocumentRequestCreateRequest,
) -> DocumentRequestResponse:
    return documents_service.create_document_request(request)
