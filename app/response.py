from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel


# ---------- 统一响应模型 ----------

class OCRItem(BaseModel):
    text: str
    confidence: float
    box: list[list[float]]


class OCRUploadData(BaseModel):
    count: int
    results: list[OCRItem]


class HealthData(BaseModel):
    status: str
    ready: bool


class IDCardFrontFields(BaseModel):
    name: str | None = None
    gender: str | None = None
    ethnicity: str | None = None
    birth_date: str | None = None
    birth_date_iso: str | None = None
    address: str | None = None
    id_number: str | None = None


class IDCardFrontData(BaseModel):
    side: str
    fields: IDCardFrontFields
    confidence: dict[str, float | None]
    raw_count: int
    raw: list[OCRItem] | None = None


class IDCardBackFields(BaseModel):
    issue_authority: str | None = None
    valid_period: str | None = None
    valid_start: str | None = None
    valid_end: str | None = None
    is_long_term: bool | None = None


class IDCardBackData(BaseModel):
    side: str
    fields: IDCardBackFields
    confidence: dict[str, float | None]
    raw_count: int
    raw: list[OCRItem] | None = None


class IDCardAutoData(BaseModel):
    side: str
    fields: IDCardFrontFields | IDCardBackFields | dict[str, None]
    confidence: dict[str, float | None]
    raw_count: int
    raw: list[OCRItem] | None = None


class BizLicenseFields(BaseModel):
    company_name: str | None = None
    credit_code: str | None = None
    company_type: str | None = None
    legal_representative: str | None = None
    registered_capital: str | None = None
    establishment_date: str | None = None
    establishment_date_iso: str | None = None
    business_term: str | None = None
    business_scope: str | None = None
    registered_address: str | None = None
    registration_authority: str | None = None


class BizLicenseData(BaseModel):
    doc_type: str
    fields: BizLicenseFields
    confidence: dict[str, float | None]
    raw_count: int
    raw: list[OCRItem] | None = None


# ---------- 响应包装模型（用于 Swagger 文档）----------

class ApiResponse(BaseModel):
    code: int = 200
    data: Any = None
    message: str = "ok"


class OCRUploadResponse(BaseModel):
    code: int = 200
    data: OCRUploadData
    message: str = "ok"


class HealthResponse(BaseModel):
    code: int = 200
    data: HealthData
    message: str = "ok"


class IDCardFrontResponse(BaseModel):
    code: int = 200
    data: IDCardFrontData
    message: str = "ok"


class IDCardBackResponse(BaseModel):
    code: int = 200
    data: IDCardBackData
    message: str = "ok"


class IDCardAutoResponse(BaseModel):
    code: int = 200
    data: IDCardAutoData
    message: str = "ok"


class BizLicenseResponse(BaseModel):
    code: int = 200
    data: BizLicenseData
    message: str = "ok"


# ---------- 工具函数 ----------

def success(data: Any = None, message: str = "ok", code: int = 200) -> dict:
    """返回 dict，由 FastAPI 通过 response_model 序列化并生成 schema"""
    return {"code": code, "data": data, "message": message}


def fail(message: str, code: int = 400, data: Any = None) -> JSONResponse:
    """异常处理器仍需 JSONResponse 以设置非 200 状态码"""
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
