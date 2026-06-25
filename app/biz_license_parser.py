import re

_ROW_OVERLAP_RATIO = 0.45
_LABEL_TOKENS = frozenset({"名", "称", "类", "型", "住", "所", "法定代表人", "经营范围"})


def _box_center(box: list) -> tuple[float, float]:
    xs = [p[0] for p in box]
    ys = [p[1] for p in box]
    return sum(xs) / len(xs), sum(ys) / len(ys)


def _box_edges(box: list) -> tuple[float, float, float, float]:
    xs = [p[0] for p in box]
    ys = [p[1] for p in box]
    return min(xs), min(ys), max(xs), max(ys)


def _compact(text: str) -> str:
    return re.sub(r"\s+", "", text)


def _join_text(items: list[dict]) -> str:
    return _compact("".join(item["text"] for item in items))


def _ordered_items(items: list[dict]) -> list[dict]:
    return sorted(items, key=lambda x: (_box_center(x["box"])[1], _box_center(x["box"])[0]))


def _column_split_x(items: list[dict]) -> float:
    centers = sorted(_box_center(item["box"])[0] for item in items)
    if len(centers) < 2:
        return 500.0
    best_gap = 0.0
    split = (centers[0] + centers[-1]) / 2
    for left, right in zip(centers, centers[1:]):
        gap = right - left
        if gap > best_gap and left < (centers[0] + centers[-1]) / 2 < right:
            best_gap = gap
            split = (left + right) / 2
    return split


def _vertical_overlap_ratio(box_a: list, box_b: list) -> float:
    _, top_a, _, bottom_a = _box_edges(box_a)
    _, top_b, _, bottom_b = _box_edges(box_b)
    overlap = min(bottom_a, bottom_b) - max(top_a, top_b)
    if overlap <= 0:
        return 0.0
    min_height = min(bottom_a - top_a, bottom_b - top_b)
    return overlap / min_height if min_height else 0.0


def _same_row(item_a: dict, item_b: dict, min_ratio: float = _ROW_OVERLAP_RATIO) -> bool:
    return _vertical_overlap_ratio(item_a["box"], item_b["box"]) >= min_ratio


def _items_on_row(items: list[dict], ref_item: dict, min_ratio: float = _ROW_OVERLAP_RATIO) -> list[dict]:
    row = [item for item in items if _same_row(item, ref_item, min_ratio)]
    return sorted(row, key=lambda x: _box_center(x["box"])[0])


def _is_label_text(text: str) -> bool:
    compact = _compact(text)
    if compact in _LABEL_TOKENS:
        return True
    return compact in {"名称", "类型", "住所", "企业名称", "公司类型", "企业类型"}


def _inline_after_label(text: str, labels: str | list[str]) -> str:
    if isinstance(labels, str):
        labels = [labels]
    for label in labels:
        if label in text:
            return text.split(label, 1)[-1].strip("：: ")
    return ""


def _values_right_of_label(items: list[dict], label_item: dict) -> list[str]:
    _, _, label_right, _ = _box_edges(label_item["box"])
    values: list[str] = []
    for item in _items_on_row(items, label_item):
        if item is label_item:
            continue
        left, _, _, _ = _box_edges(item["box"])
        if left + 5 < label_right:
            continue
        text = item["text"].strip()
        if text and not _is_label_text(text):
            values.append(text)
    return values


def _find_label_item(items: list[dict], labels: str | list[str], column: str | None = None) -> dict | None:
    if isinstance(labels, str):
        labels = [labels]
    split_x = _column_split_x(items) if column else None
    for item in items:
        text = item["text"]
        if not any(label in text for label in labels):
            continue
        if column == "left" and _box_center(item["box"])[0] >= split_x:
            continue
        if column == "right" and _box_center(item["box"])[0] < split_x:
            continue
        return item
    return None


def _clean_company_name(value: str) -> str:
    value = re.sub(r"^(名称|企业名称|名)[：:]?", "", value).strip()
    value = re.split(r"(类型|法定代表人|注册资本|成立日期|住所)", value)[0].strip()
    value = re.sub(r"^.{1,2}(?=陕西|北京|上海|天津|重庆|河北|山西|辽宁|吉林|黑龙江|江苏|浙江|安徽|福建|江西|山东|河南|湖北|湖南|广东|海南|四川|贵州|云南|甘肃|青海|台湾|内蒙古|广西|西藏|宁夏|新疆|香港|澳门)", "", value)
    return value.strip()


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
    label = _find_label_item(items, ["名称", "企业名称", "名"], column="left")
    if label:
        inline = _inline_after_label(label["text"], ["名称", "企业名称", "名"])
        if inline:
            cleaned = _clean_company_name(inline)
            if cleaned:
                return cleaned
        row_values = _values_right_of_label(items, label)
        if row_values:
            cleaned = _clean_company_name("".join(row_values))
            if cleaned:
                return cleaned

    match = re.search(
        r"(?:名称|企业名称)[：:]?([\u4e00-\u9fa5（）()A-Za-z0-9·]{2,80}?)(?:类型|法定代表人|注册资本|成立日期|住所|统一社会信用代码|$)",
        full,
    )
    if match:
        return _clean_company_name(match.group(1))
    return None


def _extract_company_type(full: str, items: list[dict]) -> str | None:
    label = _find_label_item(items, ["类型", "公司类型", "企业类型", "类"], column="left")
    if label:
        inline = _inline_after_label(label["text"], ["类型", "公司类型", "企业类型"])
        if inline:
            value = re.split(r"(法定代表人|注册资本|成立日期|营业期限|经营范围|住所)", inline)[0].strip()
            if value:
                return value
        row_items = _items_on_row(items, label)
        parts: list[str] = []
        started = False
        for item in row_items:
            text = item["text"].strip()
            if item is label or text in {"类", "型"} or "类型" in text:
                started = True
                tail = _inline_after_label(text, ["类型", "公司类型", "企业类型"])
                if tail:
                    parts.append(tail)
                continue
            if started and text and not _is_label_text(text):
                parts.append(text)
        if parts:
            return _compact("".join(parts))

    match = re.search(
        r"(?:类型|公司类型|企业类型)[：:]?([\u4e00-\u9fa5（）()A-Za-z0-9·]{2,40}?)(?:法定代表人|注册资本|成立日期|营业期限|经营范围|住所|$)",
        full,
    )
    if match:
        return match.group(1).strip()
    return None


def _extract_legal_representative(full: str, items: list[dict]) -> str | None:
    label = _find_label_item(items, "法定代表人", column="left")
    if label:
        inline = _inline_after_label(label["text"], "法定代表人")
        if inline:
            value = re.split(r"(注册资本|成立日期|营业期限|经营范围|住所|登记机关)", inline)[0].strip()
            if value:
                return value
        row_values = _values_right_of_label(items, label)
        if row_values:
            value = re.split(r"(注册资本|成立日期|营业期限|经营范围|住所|登记机关)", row_values[0])[0].strip()
            if value:
                return value

    match = re.search(
        r"法定代表人[：:]?([\u4e00-\u9fa5·]{2,20}?)(?:注册资本|成立日期|营业期限|经营范围|住所|登记机关|$)",
        full,
    )
    if match:
        return match.group(1).strip()
    return None


def _normalize_capital(value: str) -> str:
    value = re.split(r"(成立日期|营业期限|经营范围|住所|登记机关|名称|名)", value)[0].strip()
    match = re.search(r"([\u4e00-\u9fa5\d.,·（）()]+?(?:万元(?:人民币)?|万(?:元)?|元整|人民币))", value)
    if match:
        return match.group(1).strip()
    return value.strip()


def _extract_registered_capital(full: str, items: list[dict]) -> str | None:
    label = _find_label_item(items, "注册资本", column="right")
    if label:
        inline = _inline_after_label(label["text"], "注册资本")
        if inline:
            normalized = _normalize_capital(inline)
            if normalized:
                return normalized

    match = re.search(
        r"注册资本[：:]?([\u4e00-\u9fa5\d.,·（）()]+?(?:万元(?:人民币)?|万(?:元)?|元整|人民币))",
        full,
    )
    if match:
        return match.group(1).strip()
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
    label = _find_label_item(items, "成立日期", column="right")
    if label:
        inline = _inline_after_label(label["text"], "成立日期")
        match = re.search(r"(\d{4})年(\d{1,2})月(\d{1,2})日", inline or label["text"])
        if match:
            year, month, day = match.groups()
            return {
                "text": f"{year}年{month}月{day}日",
                "iso": f"{year}-{int(month):02d}-{int(day):02d}",
            }

    date = _extract_date(full, "成立日期")
    if date:
        return date
    return None


def _normalize_business_term(value: str) -> str | None:
    value = value.strip("：: ")
    if not value:
        return None
    match = re.match(
        r"(长期|\d{4}年\d{1,2}月\d{1,2}日至(?:长期|\d{4}年\d{1,2}月\d{1,2}日))",
        value,
    )
    if match:
        return match.group(1)
    if value.startswith("长期"):
        return "长期"
    return value.split("法定代表人")[0].split("住")[0].strip() or None


def _extract_business_term(full: str, items: list[dict]) -> str | None:
    label = _find_label_item(items, "营业期限", column="right")
    if label:
        inline = _inline_after_label(label["text"], "营业期限")
        normalized = _normalize_business_term(inline)
        if normalized:
            return normalized

    match = re.search(
        r"营业期限[：:]?(长期|\d{4}年\d{1,2}月\d{1,2}日至(?:长期|\d{4}年\d{1,2}月\d{1,2}日))",
        full,
    )
    if match:
        return match.group(1)
    if "营业期限" in full and "长期" in full:
        return "长期"
    return None


def _extract_business_scope(full: str, items: list[dict]) -> str | None:
    label = _find_label_item(items, "经营范围", column="left")
    if label:
        parts: list[str] = []
        inline = _inline_after_label(label["text"], "经营范围")
        if inline:
            parts.append(inline)
        _, label_top, label_right, label_bottom = _box_edges(label["box"])
        split_x = _column_split_x(items)
        scope_items: list[tuple[float, float, str]] = []
        for item in items:
            if item is label:
                continue
            left, top, right, bottom = _box_edges(item["box"])
            cy = _box_center(item["box"])[1]
            if cy < label_top - 20 or cy > label_bottom + 130:
                continue
            if left >= split_x:
                continue
            if right <= label_right and "经营范围" not in item["text"]:
                continue
            text = item["text"].strip()
            if not text or any(stop in text for stop in ("登记机关", "国家企业信用信息公示系统")):
                continue
            if text in {"法定代表人", "夏燕", "类", "型", "名", "住", "所"}:
                continue
            if re.search(r"^(有限责任|成立日期|营业期限|注册资本)", text):
                continue
            scope_items.append((cy, left, text))
        scope_items.sort(key=lambda x: (x[0], x[1]))
        parts.extend(text for _, _, text in scope_items)
        if parts:
            return _compact("".join(parts))

    match = re.search(
        r"经营范围[：:]?(.+?)(?:登记机关|国家企业信用信息公示系统|$)",
        full,
    )
    if match:
        value = match.group(1).strip()
        if value:
            return value
    return None


def _extract_registered_address(full: str, items: list[dict]) -> str | None:
    for item in items:
        if _box_center(item["box"])[0] < _column_split_x(items):
            continue
        text = item["text"].strip()
        if text.startswith("所") and len(text) > 1:
            return text[1:].strip("：: ")
        inline = _inline_after_label(text, "住所")
        if inline:
            return inline.strip()

    label = _find_label_item(items, ["住所", "住"], column="right")
    if label:
        inline = _inline_after_label(label["text"], ["住所", "住"])
        if inline:
            return inline.strip()
        row_values = _values_right_of_label(items, label)
        if row_values:
            return _compact("".join(row_values))

    match = re.search(
        r"住所[：:]?([\u4e00-\u9fa5\d\-号组弄巷里路街道区市县镇村（）()A-Za-z0-9·#]+?)(?:登记机关|国家企业信用信息公示系统|$)",
        full,
    )
    if match:
        return match.group(1).strip()
    return None


def _extract_registration_authority(full: str, items: list[dict]) -> str | None:
    patterns = [
        r"([\u4e00-\u9fa5]{2,20}市场监督管理局)",
        r"([\u4e00-\u9fa5]{2,20}市场监管局)",
        r"([\u4e00-\u9fa5]{2,20}行政审批局)",
        r"([\u4e00-\u9fa5]{2,20}工商局)",
    ]
    for item in sorted(items, key=lambda x: (_box_center(x["box"])[1], _box_center(x["box"])[0]), reverse=True):
        text = item["text"]
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(1)

    for pattern in patterns:
        match = re.search(pattern, full)
        if match:
            return match.group(1)

    label = _find_label_item(items, "登记机关")
    if label:
        row_values = _values_right_of_label(items, label)
        for value in row_values:
            for pattern in patterns:
                match = re.search(pattern, value)
                if match:
                    return match.group(1)
            cleaned = re.sub(r"^登记机关[：:]?", "", value).strip()
            match = re.match(r"([\u4e00-\u9fa5]{2,30}(?:局|厅|委|处|所)?)", cleaned)
            if match and len(match.group(1)) >= 4:
                return match.group(1)
    return None


def _field_confidences(items: list[dict], fields: dict) -> dict[str, float | None]:
    mapping: dict[str, list[str]] = {
        "company_name": ["名称", "企业名称", "名"],
        "credit_code": ["统一社会信用代码", "社会信用代码"],
        "company_type": ["类型", "公司类型", "企业类型"],
        "legal_representative": ["法定代表人"],
        "registered_capital": ["注册资本"],
        "establishment_date": ["成立日期"],
        "establishment_date_iso": ["成立日期"],
        "business_term": ["营业期限", "长期"],
        "business_scope": ["经营范围"],
        "registered_address": ["住所", "住", "所"],
        "registration_authority": ["登记机关", "市场监督管理局", "市场监管局"],
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
