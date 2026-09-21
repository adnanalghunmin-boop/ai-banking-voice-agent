from pydantic import BaseModel, Field


class CallbackCreateRequest(BaseModel):
    customer_id: int | None = Field(default=None, gt=0)
    account_id: int | None = Field(default=None, gt=0)
    request_type: str = Field(..., min_length=1, max_length=100)
    request_summary: str | None = Field(default=None, max_length=1000)
    reason_for_callback: str = Field(..., min_length=1, max_length=500)


class CallbackResponse(BaseModel):
    callback_id: int
    callback_status: str
