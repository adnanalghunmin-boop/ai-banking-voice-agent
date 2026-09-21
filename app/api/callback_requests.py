from fastapi import APIRouter, status

from app.models.callback import CallbackCreateRequest, CallbackResponse
from app.services import callbacks as callbacks_service

router = APIRouter(prefix="/api/v1/callback-requests", tags=["callback-requests"])


@router.post("", response_model=CallbackResponse, status_code=status.HTTP_201_CREATED)
def create_callback_request(request: CallbackCreateRequest) -> CallbackResponse:
    return callbacks_service.create_callback_request(request)
