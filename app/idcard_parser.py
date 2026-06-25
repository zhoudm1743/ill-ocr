import re
from typing import Literal

Side = Literal["front", "back"]


def _box_center(box: list) -> tuple[float, float]:
    xs = [p[0] for p in box]
    ys = [p[1] for p in box]
    return sum(xs) / len(xs), sum(ys) / len(ys)


def _compact(text: str) -> str:
    return re.sub(r"\s+", "", text)


def _join_text(items: list[dict]) -> str:
    return _compact("".join(item["text"] for item in items))


def detect_side(items: list[dict]) -> Side:
    full = _join_text(items)
    if re.search(r"公民身份号码|身份号码|\d{17}[\dXx]", full):
        return "front"
    if "签发机关" in full or "有效期限" in full:
        return "back"
    if re.search(r"\d{4}\.\d{2}\.\d{2}-\d{4}\.\d{2}\.\d{2}", full):
        return "back"
    return "front"


def _find_after_label(items: list[dict], label: str) -> str | None:
    ordered = sorted(items, key=lambda x: (_box_center(x["box"])[1], _box_center(x["box"])[0]))
    for idx, item in enumerate(ordered):
        text = item["text"]
        if label not in text:
            continue
        inline = text.split(label, 1)[-1].strip()
        if inline and not inline.startswith(label):
            return inline
        for nxt in ordered[idx + 1 : idx + 4]:
            candidate = nxt["text"].strip()
            if candidate and label not in candidate:
                return candidate
    return None


def _extract_id_number(full: str, items: list[dict]) -> str | None:
    match = re.search(r"(?:公民身份号码|身份号码)(\d{17}[\dXx])", full)
    if match:
        return match.group(1).upper()
    for item in items:
        match = re.search(r"(\d{17}[\dXx])", _compact(item["text"]))
        if match:
            return match.group(1).upper()
    return None


def _extract_birth(full: str) -> dict | None:
    match = re.search(r"(\d{4})年(\d{1,2})月(\d{1,2})日", full)
    if not match:
        return None
    year, month, day = match.groups()
    return {
        "year": int(year),
        "month": int(month),
        "day": int(day),
        "text": f"{year}年{month}月{day}日",
        "iso": f"{year}-{int(month):02d}-{int(day):02d}",
    }


def _extract_gender(full: str) -> str | None:
    match = re.search(r"性别(男|女)", full)
    if match:
        return match.group(1)
    match = re.search(r"性别\s*(男|女)", full)
    return match.group(1) if match else None


def _extract_ethnicity(full: str) -> str | None:
    match = re.search(r"民族([\u4e00-\u9fa5]{1,6})", full)
    if not match:
        return None
    value = match.group(1)
    value = re.split(r"出生|性别|住址", value)[0]
    return value or None


def _extract_name(full: str, items: list[dict]) -> str | None:
    match = re.search(r"姓名([\u4e00-\u9fa5]{2,4})", full)
    if match:
        return match.group(1)
    value = _find_after_label(items, "姓名")
    if value:
        value = re.sub(r"^姓名", "", value).strip()
        match = re.match(r"([\u4e00-\u9fa5]{2,4})", value)
        if match:
            return match.group(1)
    return None


def _clean_address(value: str) -> str:
    value = re.sub(r"[A-Za-z].*$", "", value)
    value = re.sub(r"公民身份号码.*$", "", value)
    value = re.sub(r"GUNGHMINZ.*$", "", value, flags=re.IGNORECASE)
    return value.strip()


def _extract_address(full: str, items: list[dict]) -> str | None:
    match = re.search(
        r"住址([\u4e00-\u9fa5\d\-号组弄巷里]+?)(?:公民身份号码|身份号码|GUNGHMINZ|\d{17}[\dXx]|$)",
        full,
    )
    if match:
        return _clean_address(match.group(1))

    ordered = sorted(items, key=lambda x: (_box_center(x["box"])[1], _box_center(x["box"])[0]))
    parts: list[str] = []
    collecting = False
    for item in ordered:
        text = item["text"].strip()
        if re.fullmatch(r"[A-Za-z\s]+", text):
            if collecting:
                break
            continue
        if "住址" in text:
            collecting = True
            inline = text.split("住址", 1)[-1].strip()
            if inline:
                parts.append(inline)
            continue
        if collecting:
            if "公民身份号码" in text or re.search(r"\d{17}[\dXx]", text):
                break
            if re.fullmatch(r"[A-Za-z\s]+", text):
                break
            parts.append(text)
    if parts:
        return _clean_address("".join(parts))
    return None


def parse_idcard_front(items: list[dict]) -> dict:
    full = _join_text(items)
    birth = _extract_birth(full)
    data = {
        "name": _extract_name(full, items),
        "gender": _extract_gender(full),
        "ethnicity": _extract_ethnicity(full),
        "birth_date": birth["text"] if birth else None,
        "birth_date_iso": birth["iso"] if birth else None,
        "address": _extract_address(full, items),
        "id_number": _extract_id_number(full, items),
    }
    confidences = _field_confidences(items, data)
    return {
        "side": "front",
        "fields": data,
        "confidence": confidences,
        "raw_count": len(items),
    }


def _extract_issue_authority(full: str, items: list[dict]) -> str | None:
    match = re.search(r"签发机关([\u4e00-\u9fa5]{2,30}(?:公安局|分局|派出所)?)", full)
    if match:
        return match.group(1)
    value = _find_after_label(items, "签发机关")
    if value:
        value = re.sub(r"^签发机关", "", value).strip()
        match = re.match(r"([\u4e00-\u9fa5]{2,30}(?:公安局|分局|派出所)?)", value)
        if match:
            return match.group(1)
    return None


def _extract_valid_period(full: str) -> dict | None:
    match = re.search(
        r"有效期限(\d{4}\.\d{2}\.\d{2})-(\d{4}\.\d{2}\.\d{2}|长期)",
        full,
    )
    if not match:
        match = re.search(r"(\d{4}\.\d{2}\.\d{2})-(\d{4}\.\d{2}\.\d{2}|长期)", full)
    if not match:
        return None
    start, end = match.groups()
    return {
        "start": start,
        "end": end,
        "text": f"{start}-{end}",
        "is_long_term": end == "长期",
    }


def parse_idcard_back(items: list[dict]) -> dict:
    full = _join_text(items)
    period = _extract_valid_period(full)
    data = {
        "issue_authority": _extract_issue_authority(full, items),
        "valid_period": period["text"] if period else None,
        "valid_start": period["start"] if period else None,
        "valid_end": period["end"] if period else None,
        "is_long_term": period["is_long_term"] if period else None,
    }
    confidences = _field_confidences(items, data)
    return {
        "side": "back",
        "fields": data,
        "confidence": confidences,
        "raw_count": len(items),
    }


def _field_confidences(items: list[dict], fields: dict) -> dict[str, float | None]:
    full = _join_text(items)
    mapping: dict[str, list[str]] = {
        "name": ["姓名"],
        "gender": ["性别"],
        "ethnicity": ["民族"],
        "birth_date": ["出生", "年", "月", "日"],
        "address": ["住址"],
        "id_number": ["公民身份号码", "身份号码"],
        "issue_authority": ["签发机关", "公安局"],
        "valid_period": ["有效期限"],
        "valid_start": ["有效期限"],
        "valid_end": ["有效期限", "长期"],
        "is_long_term": ["长期"],
    }

    scores: dict[str, float | None] = {}
    for key, value in fields.items():
        if value is None or value == "":
            scores[key] = None
            continue
        keywords = mapping.get(key, [str(value)])
        matched = [
            item["confidence"]
            for item in items
            if any(k in item["text"] for k in keywords) or str(value) in item["text"]
        ]
        if matched:
            scores[key] = round(max(matched), 4)
        elif key == "id_number":
            matched = [item["confidence"] for item in items if re.search(r"\d{17}[\dXx]", item["text"])]
            scores[key] = round(max(matched), 4) if matched else None
        else:
            scores[key] = round(sum(item["confidence"] for item in items) / len(items), 4) if items else None
    return scores


def parse_idcard(items: list[dict], side: Side | Literal["auto"] = "auto") -> dict:
    resolved = detect_side(items) if side == "auto" else side
    if resolved == "front":
        return parse_idcard_front(items)
    return parse_idcard_back(items)
