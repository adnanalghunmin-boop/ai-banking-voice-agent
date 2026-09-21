from fastapi import APIRouter

from app.models.verification import VerificationRequest, VerificationResponse
from app.services.verification import verify_customer

router = APIRouter(prefix="/api/v1/verification", tags=["verification"])


@router.post("/verify", response_model=VerificationResponse)
def verify(request: VerificationRequest) -> VerificationResponse:
    return verify_customer(request)
