import asyncio
import base64
import binascii
import io
import logging
from contextlib import asynccontextmanager
from typing import Literal

import numpy as np
from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from PIL import Image
from pydantic import BaseModel

from biz_license_parser import parse_biz_license
from idcard_parser import parse_idcard
from response import (
    register_exception_handlers,
    success,
    HealthResponse,
    OCRUploadResponse,
    IDCardFrontResponse,
    IDCardBackResponse,
    IDCardAutoResponse,
    BizLicenseResponse,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("rapid-ocr")

ocr_engine = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global ocr_engine
    from rapidocr_onnxruntime import RapidOCR

    logger.info("Initializing RapidOCR engine...")
    ocr_engine = RapidOCR()
    logger.info("RapidOCR engine ready.")
    yield
    ocr_engine = None


app = FastAPI(title="OCR Service (RapidOCR)", version="1.3.0", lifespan=lifespan)
register_exception_handlers(app)


class OCRBase64Request(BaseModel):
    image: str


class IDCardBase64Request(BaseModel):
    image: str
    side: Literal["front", "back", "auto"] = "auto"


class BizLicenseBase64Request(BaseModel):
    image: str


def _parse_result(result) -> list[dict]:
    items: list[dict] = []
    if not result:
        return items
    for item in result:
        box, text, score = item[0], item[1], item[2]
        items.append(
            {
                "text": text,
                "confidence": float(score) if score is not None else 0.0,
                "box": box.tolist() if hasattr(box, "tolist") else box,
            }
        )
    return items


def _bytes_to_ndarray(data: bytes) -> np.ndarray:
    try:
        img = Image.open(io.BytesIO(data)).convert("RGB")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"无法解析图片: {exc}") from exc
    return np.array(img)


def _run_ocr(img: np.ndarray) -> list[dict]:
    if ocr_engine is None:
        raise HTTPException(status_code=503, detail="OCR 引擎尚未就绪")
    result, _ = ocr_engine(img)
    return _parse_result(result)


async def _ocr_async(img: np.ndarray) -> list[dict]:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _run_ocr, img)


def _build_idcard_response(items: list[dict], side: Literal["front", "back", "auto"], include_raw: bool):
    parsed = parse_idcard(items, side=side)
    if include_raw:
        return {**parsed, "raw": items}
    return parsed


def _build_biz_license_response(items: list[dict], include_raw: bool):
    parsed = parse_biz_license(items)
    if include_raw:
        return {**parsed, "raw": items}
    return parsed


@app.get("/health", response_model=HealthResponse)
async def health():
    return success({"status": "ok", "ready": ocr_engine is not None})


@app.post("/ocr/upload", response_model=OCRUploadResponse)
async def ocr_upload(file: UploadFile = File(...)):
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="上传文件为空")
    img = _bytes_to_ndarray(data)
    results = await _ocr_async(img)
    return success({"count": len(results), "results": results})


@app.post("/ocr/base64", response_model=OCRUploadResponse)
async def ocr_base64(req: OCRBase64Request):
    raw = req.image.split(",", 1)[-1].strip()
    try:
        data = base64.b64decode(raw, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"base64 解码失败: {exc}") from exc
    img = _bytes_to_ndarray(data)
    results = await _ocr_async(img)
    return success({"count": len(results), "results": results})


@app.post("/ocr/idcard", response_model=IDCardAutoResponse)
async def ocr_idcard(
    file: UploadFile = File(...),
    side: Literal["front", "back", "auto"] = Query("auto", description="身份证面：front/back/auto"),
    include_raw: bool = Query(False, description="是否返回原始 OCR 结果"),
):
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="上传文件为空")
    img = _bytes_to_ndarray(data)
    items = await _ocr_async(img)
    if not items:
        raise HTTPException(status_code=422, detail="未识别到文字，请检查图片是否清晰")
    return success(_build_idcard_response(items, side, include_raw))


@app.post("/ocr/idcard/front", response_model=IDCardFrontResponse)
async def ocr_idcard_front(
    file: UploadFile = File(...),
    include_raw: bool = Query(False),
):
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="上传文件为空")
    img = _bytes_to_ndarray(data)
    items = await _ocr_async(img)
    if not items:
        raise HTTPException(status_code=422, detail="未识别到文字，请检查图片是否清晰")
    return success(_build_idcard_response(items, "front", include_raw))


@app.post("/ocr/idcard/back", response_model=IDCardBackResponse)
async def ocr_idcard_back(
    file: UploadFile = File(...),
    include_raw: bool = Query(False),
):
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="上传文件为空")
    img = _bytes_to_ndarray(data)
    items = await _ocr_async(img)
    if not items:
        raise HTTPException(status_code=422, detail="未识别到文字，请检查图片是否清晰")
    return success(_build_idcard_response(items, "back", include_raw))


@app.post("/ocr/idcard/base64", response_model=IDCardAutoResponse)
async def ocr_idcard_base64(
    req: IDCardBase64Request,
    include_raw: bool = Query(False),
):
    raw = req.image.split(",", 1)[-1].strip()
    try:
        data = base64.b64decode(raw, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"base64 解码失败: {exc}") from exc
    img = _bytes_to_ndarray(data)
    items = await _ocr_async(img)
    if not items:
        raise HTTPException(status_code=422, detail="未识别到文字，请检查图片是否清晰")
    return success(_build_idcard_response(items, req.side, include_raw))


@app.post("/ocr/biz-license", response_model=BizLicenseResponse)
async def ocr_biz_license(
    file: UploadFile = File(...),
    include_raw: bool = Query(False, description="是否返回原始 OCR 结果"),
):
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="上传文件为空")
    img = _bytes_to_ndarray(data)
    items = await _ocr_async(img)
    if not items:
        raise HTTPException(status_code=422, detail="未识别到文字，请检查图片是否清晰")
    return success(_build_biz_license_response(items, include_raw))


@app.post("/ocr/biz-license/base64", response_model=BizLicenseResponse)
async def ocr_biz_license_base64(
    req: BizLicenseBase64Request,
    include_raw: bool = Query(False, description="是否返回原始 OCR 结果"),
):
    raw = req.image.split(",", 1)[-1].strip()
    try:
        data = base64.b64decode(raw, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"base64 解码失败: {exc}") from exc
    img = _bytes_to_ndarray(data)
    items = await _ocr_async(img)
    if not items:
        raise HTTPException(status_code=422, detail="未识别到文字，请检查图片是否清晰")
    return success(_build_biz_license_response(items, include_raw))
