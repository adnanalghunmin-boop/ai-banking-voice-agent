import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api import (
    accounts,
    callback_requests,
    cards,
    complaints,
    customers,
    document_requests,
    get_services,
    health,
    post_services,
    verification,
)
from app.db.connection import close_pool, init_pool
from app.utils.exceptions import (
    BusinessRuleError,
    DatabaseUnavailableError,
    InvalidSessionError,
    NotFoundError,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_pool()
    yield
    close_pool()


app = FastAPI(title="Banking Voice Agent Backend", lifespan=lifespan)

app.include_router(health.router)
app.include_router(health.database_router)
app.include_router(verification.router)
app.include_router(accounts.router)
app.include_router(cards.router)
app.include_router(customers.router)
app.include_router(complaints.router)
app.include_router(callback_requests.router)
app.include_router(document_requests.router)
app.include_router(get_services.router)
app.include_router(post_services.router)


@app.exception_handler(DatabaseUnavailableError)
async def database_unavailable_handler(
    request: Request, exc: DatabaseUnavailableError
) -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={"detail": "Service temporarily unavailable. Please try again later."},
    )


@app.exception_handler(NotFoundError)
async def not_found_handler(request: Request, exc: NotFoundError) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": exc.message})


@app.exception_handler(BusinessRuleError)
async def business_rule_handler(request: Request, exc: BusinessRuleError) -> JSONResponse:
    return JSONResponse(status_code=400, content={"detail": exc.message})


@app.exception_handler(InvalidSessionError)
async def invalid_session_handler(
    request: Request, exc: InvalidSessionError
) -> JSONResponse:
    return JSONResponse(status_code=401, content={"detail": exc.message})


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled exception")
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error."},
    )
