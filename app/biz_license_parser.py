import re


def _box_center(box: list) -> tuple[float, float]:
    xs = [p[0] for p in box]
    ys = [p[1] for p in box]
    return sum(xs) / len(xs), sum(ys) / len(ys)


def _compact(text: str) -> str:
    return re.sub(r"\s+", "", text)


def _join_text(items: list[dict]) -> str:
    return _compact("".join(item["text"] for item in items))


def _ordered_items(items: list[dict]) -> list[dict]:
    return sorted(items, key=lambda x: (_box_center(x["box"])[1], _box_center(x["box"])[0]))


def _find_after_label(items: list[dict], labels: str | list[str]) -> str | None:
    if isinstance(labels, str):
        labels = [labels]
    ordered = _ordered_items(items)
    for idx, item in enumerate(ordered):
        text = item["text"]
        for label in labels:
            if label not in text:
                continue
            inline = text.split(label, 1)[-1].strip()
            if inline and not any(l in inline for l in labels):
                return inline
            for nxt in ordered[idx + 1 : idx + 4]:
                candidate = nxt["text"].strip()
                if candidate and not any(l in candidate for l in labels):
                    return candidate
    return None


def _collect_multiline_field(items: list[dict], start_labels: list[str], stop_labels: list[str]) -> str | None:
    ordered = _ordered_items(items)
    parts: list[str] = []
    collecting = False
    for item in ordered:
        text = item["text"].strip()
        if not collecting:
            for label in start_labels:
                if label in text:
                    collecting = True
                    inline = text.split(label, 1)[-1].strip()
                    if inline:
                        parts.append(inline)
                    break
            continue
        if any(stop in text for stop in stop_labels):
            inline_parts = []
            for stop in stop_labels:
                if stop in text:
                    before = text.split(stop, 1)[0].strip()
                    if before:
                        inline_parts.append(before)
            if inline_parts:
                parts.append("".join(inline_parts))
            break
        parts.append(text)
    if parts:
        return _compact("".join(parts)) or None
    return None


def _extract_credit_code(full: str, items: list[dict]) -> str | None:
    patterns = [
        r"统一社会信用代码[：:]?\s*([0-9A-HJ-NP-RTUW-Y]{18})",
        r"社会信用代码[：:]?\s*([0-9A-HJ-NP-RTUW-Y]{18})",
        r"([0-9A-HJ-NP-RTUW-Y]{18})",
    ]
    for pattern in patterns:
        match = re.search(pattern, full, re.IGNORECASE)
        if match:
            return match.group(1).upper()
    for item in items:
        match = re.search(r"([0-9A-HJ-NP-RTUW-Y]{18})", _compact(item["text"]), re.IGNORECASE)
        if match:
            return match.group(1).upper()
    return None


def _extract_company_name(full: str, items: list[dict]) -> str | None:
    for pattern in [
        r"(?:名称|企业名称)[：:]?([\u4e00-\u9fa5（）()A-Za-z0-9·]{2,80}?)(?:类型|法定代表人|注册资本|成立日期|住所|统一社会信用代码|$)",
        r"(?:名称|企业名称)([\u4e00-\u9fa5（）()A-Za-z0-9·]{2,80})",
    ]:
        match = re.search(pattern, full)
        if match:
            return match.group(1).strip()
    value = _find_after_label(items, ["名称", "企业名称"])
    if value:
        value = re.sub(r"^(名称|企业名称)[：:]?", "", value).strip()
        value = re.split(r"(类型|法定代表人|注册资本|成立日期|住所)", value)[0].strip()
        if value:
            return value
    return None


def _extract_company_type(full: str, items: list[dict]) -> str | None:
    match = re.search(
        r"(?:类型|公司类型|企业类型)[：:]?([\u4e00-\u9fa5（）()A-Za-z0-9·]{2,40}?)(?:法定代表人|注册资本|成立日期|营业期限|经营范围|住所|$)",
        full,
    )
    if match:
        return match.group(1).strip()
    value = _find_after_label(items, ["类型", "公司类型", "企业类型"])
    if value:
        value = re.sub(r"^(类型|公司类型|企业类型)[：:]?", "", value).strip()
        value = re.split(r"(法定代表人|注册资本|成立日期|营业期限|经营范围|住所)", value)[0].strip()
        if value:
            return value
    return None


def _extract_legal_representative(full: str, items: list[dict]) -> str | None:
    match = re.search(
        r"法定代表人[：:]?([\u4e00-\u9fa5·]{2,20}?)(?:注册资本|成立日期|营业期限|经营范围|住所|登记机关|$)",
        full,
    )
    if match:
        return match.group(1).strip()
    value = _find_after_label(items, "法定代表人")
    if value:
        value = re.sub(r"^法定代表人[：:]?", "", value).strip()
        value = re.split(r"(注册资本|成立日期|营业期限|经营范围|住所|登记机关)", value)[0].strip()
        if value:
            return value
    return None


def _extract_registered_capital(full: str, items: list[dict]) -> str | None:
    match = re.search(
        r"注册资本[：:]?([\u4e00-\u9fa5\d.,·（）()万元整]+?)(?:成立日期|营业期限|经营范围|住所|登记机关|$)",
        full,
    )
    if match:
        return match.group(1).strip()
    value = _find_after_label(items, "注册资本")
    if value:
        value = re.sub(r"^注册资本[：:]?", "", value).strip()
        value = re.split(r"(成立日期|营业期限|经营范围|住所|登记机关)", value)[0].strip()
        if value:
            return value
    return None


def _extract_date(full: str, label: str) -> dict | None:
    match = re.search(rf"{label}[：:]?(\d{{4}})年(\d{{1,2}})月(\d{{1,2}})日", full)
    if not match:
        return None
    year, month, day = match.groups()
    return {
        "text": f"{year}年{month}月{day}日",
        "iso": f"{year}-{int(month):02d}-{int(day):02d}",
    }


def _extract_establishment_date(full: str, items: list[dict]) -> dict | None:
    date = _extract_date(full, "成立日期")
    if date:
        return date
    value = _find_after_label(items, "成立日期")
    if value:
        match = re.search(r"(\d{4})年(\d{1,2})月(\d{1,2})日", value)
        if match:
            year, month, day = match.groups()
            return {
                "text": f"{year}年{month}月{day}日",
                "iso": f"{year}-{int(month):02d}-{int(day):02d}",
            }
    return None


def _extract_business_term(full: str, items: list[dict]) -> str | None:
    match = re.search(
        r"营业期限[：:]?([\u4e00-\u9fa5\d年月日至\-长期]+?)(?:经营范围|住所|登记机关|$)",
        full,
    )
    if match:
        return match.group(1).strip()
    value = _find_after_label(items, "营业期限")
    if value:
        value = re.sub(r"^营业期限[：:]?", "", value).strip()
        value = re.split(r"(经营范围|住所|登记机关)", value)[0].strip()
        if value:
            return value
    if "长期" in full and "营业期限" in full:
        return "长期"
    return None


def _extract_business_scope(full: str, items: list[dict]) -> str | None:
    match = re.search(
        r"经营范围[：:]?(.+?)(?:住所|登记机关|国家企业信用信息公示系统|$)",
        full,
    )
    if match:
        value = match.group(1).strip()
        if value:
            return value
    value = _collect_multiline_field(
        items,
        start_labels=["经营范围"],
        stop_labels=["住所", "登记机关", "国家企业信用信息公示系统"],
    )
    return value


def _extract_registered_address(full: str, items: list[dict]) -> str | None:
    match = re.search(
        r"住所[：:]?([\u4e00-\u9fa5\d\-号组弄巷里路街道区市县镇村（）()A-Za-z0-9·#]+?)(?:登记机关|国家企业信用信息公示系统|$)",
        full,
    )
    if match:
        return match.group(1).strip()
    value = _collect_multiline_field(
        items,
        start_labels=["住所"],
        stop_labels=["登记机关", "国家企业信用信息公示系统"],
    )
    return value


def _extract_registration_authority(full: str, items: list[dict]) -> str | None:
    match = re.search(
        r"登记机关[：:]?([\u4e00-\u9fa5]{2,30}(?:局|厅|委|处|所)?)",
        full,
    )
    if match:
        return match.group(1).strip()
    value = _find_after_label(items, "登记机关")
    if value:
        value = re.sub(r"^登记机关[：:]?", "", value).strip()
        match = re.match(r"([\u4e00-\u9fa5]{2,30}(?:局|厅|委|处|所)?)", value)
        if match:
            return match.group(1)
    return None


def _field_confidences(items: list[dict], fields: dict) -> dict[str, float | None]:
    mapping: dict[str, list[str]] = {
        "company_name": ["名称", "企业名称"],
        "credit_code": ["统一社会信用代码", "社会信用代码"],
        "company_type": ["类型", "公司类型", "企业类型"],
        "legal_representative": ["法定代表人"],
        "registered_capital": ["注册资本"],
        "establishment_date": ["成立日期"],
        "establishment_date_iso": ["成立日期"],
        "business_term": ["营业期限", "长期"],
        "business_scope": ["经营范围"],
        "registered_address": ["住所"],
        "registration_authority": ["登记机关"],
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
        elif key == "credit_code":
            matched = [
                item["confidence"]
                for item in items
                if re.search(r"[0-9A-HJ-NP-RTUW-Y]{18}", item["text"], re.IGNORECASE)
            ]
            scores[key] = round(max(matched), 4) if matched else None
        else:
            scores[key] = round(sum(item["confidence"] for item in items) / len(items), 4) if items else None
    return scores


def parse_biz_license(items: list[dict]) -> dict:
    full = _join_text(items)
    establishment = _extract_establishment_date(full, items)
    data = {
        "company_name": _extract_company_name(full, items),
        "credit_code": _extract_credit_code(full, items),
        "company_type": _extract_company_type(full, items),
        "legal_representative": _extract_legal_representative(full, items),
        "registered_capital": _extract_registered_capital(full, items),
        "establishment_date": establishment["text"] if establishment else None,
        "establishment_date_iso": establishment["iso"] if establishment else None,
        "business_term": _extract_business_term(full, items),
        "business_scope": _extract_business_scope(full, items),
        "registered_address": _extract_registered_address(full, items),
        "registration_authority": _extract_registration_authority(full, items),
    }
    confidences = _field_confidences(items, data)
    return {
        "doc_type": "biz_license",
        "fields": data,
        "confidence": confidences,
        "raw_count": len(items),
    }
