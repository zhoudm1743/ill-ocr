from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


def success(data: Any = None, message: str = "ok", code: int = 200) -> JSONResponse:
    return JSONResponse(
        status_code=200,
        content={"code": code, "data": data, "message": message},
    )


def fail(message: str, code: int = 400, data: Any = None) -> JSONResponse:
    return JSONResponse(
        status_code=code,
        content={"code": code, "data": data, "message": message},
    )


def _normalize_message(detail: Any) -> str:
    if isinstance(detail, str):
        return detail
    if isinstance(detail, dict):
        return detail.get("message") or detail.get("msg") or str(detail)
    if isinstance(detail, list):
        parts: list[str] = []
        for item in detail:
            if isinstance(item, dict):
                loc = ".".join(str(x) for x in item.get("loc", []))
                msg = item.get("msg", "")
                parts.append(f"{loc}: {msg}" if loc else str(msg))
            else:
                parts.append(str(item))
        return "; ".join(parts) if parts else "请求参数错误"
    return str(detail)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(HTTPException)
    async def http_exception_handler(_: Request, exc: HTTPException) -> JSONResponse:
        return fail(message=_normalize_message(exc.detail), code=exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        _: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return fail(message=_normalize_message(exc.errors()), code=422)

    @app.exception_handler(Exception)
    async def generic_exception_handler(_: Request, exc: Exception) -> JSONResponse:
        return fail(message=str(exc) or "服务器内部错误", code=500)
