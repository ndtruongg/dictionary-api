import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException

from app.dictionary import SupabaseDictionary, create_http_client
from app.config import Settings
from app.errors import APIError
from app.routes import STATIC_DIR, router

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        application.state.settings = settings
        async with create_http_client(settings) as client:
            application.state.dictionary = SupabaseDictionary(settings, client)
            yield

    application = FastAPI(
        title="Dictionary API", version="0.4.0", lifespan=lifespan,
        description="Tra từ tiếng Anh trong bảng Supabase public.dictionary, không gọi dịch vụ AI.",
    )
    if settings.cors_origins:
        application.add_middleware(CORSMiddleware, allow_origins=list(settings.cors_origins),
                                   allow_methods=["GET"], allow_headers=["Accept"], allow_credentials=False)

    @application.exception_handler(APIError)
    async def handle_api_error(request: Request, exc: APIError):
        return JSONResponse(status_code=exc.status, content=exc.payload(), headers={"Cache-Control": "no-store"})

    @application.exception_handler(RequestValidationError)
    async def handle_validation_error(request: Request, exc: RequestValidationError):
        return JSONResponse(status_code=422, content={"code": "INVALID_INPUT", "message": "Query word bắt buộc là chuỗi không quá 512 ký tự trước chuẩn hóa.", "retryable": False})

    @application.exception_handler(HTTPException)
    async def handle_http_error(request: Request, exc: HTTPException):
        return JSONResponse(status_code=exc.status_code, content={"code": "HTTP_ERROR", "message": "Đường dẫn hoặc phương thức không được hỗ trợ.", "retryable": False}, headers=exc.headers)

    @application.exception_handler(Exception)
    async def handle_unexpected(request: Request, exc: Exception):
        # Không đưa dữ liệu nội bộ hoặc traceback ra client/log công khai.
        logger.error("application_failure code=INTERNAL_ERROR")
        return JSONResponse(status_code=500, content={"code": "INTERNAL_ERROR", "message": "Ứng dụng gặp lỗi nội bộ.", "retryable": False})

    application.include_router(router)
    application.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    return application


# Vercel import main:app. Không gọi uvicorn.run() khi import.
app = create_app()
