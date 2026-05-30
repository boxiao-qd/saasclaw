from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from app.responses import UnicodeJSONResponse


class AppError(Exception):
    def __init__(self, error_code: str, message: str, status_code: int, detail: dict | None = None):
        self.error_code = error_code
        self.message = message
        self.status_code = status_code
        self.detail = detail


def register_error_handlers(app: FastAPI):
    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError):
        return UnicodeJSONResponse(
            status_code=exc.status_code,
            content={"error_code": exc.error_code, "message": exc.message, "detail": exc.detail},
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError):
        errors = []
        for err in exc.errors():
            sanitized = dict(err)
            if "ctx" in sanitized:
                sanitized["ctx"] = {k: str(v) for k, v in sanitized["ctx"].items()}
            errors.append(sanitized)
        return UnicodeJSONResponse(
            status_code=422,
            content={
                "error_code": "BX_1002",
                "message": "Request validation failed",
                "detail": {"errors": errors},
            },
        )