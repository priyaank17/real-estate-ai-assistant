import re
from typing import Any, Dict, List, Optional

from langchain_core.tools import tool

# Simple heuristics to pull structured filters from a fuzzy user message.
_CITY_CANDIDATES = {
    "dubai",
    "london",
    "miami",
    "chicago",
    "new york",
    "nyc",
    "toronto",
    "paris",
    "sydney",
    "mumbai",
    "bangalore",
    "delhi",
    "abu dhabi",
    "dubai marina",
    "downtown dubai",
}

_PROPERTY_TYPES = {"apartment", "villa", "townhouse", "condo", "flat", "studio"}
_FEATURE_KEYWORDS = {
    "sea view": ["sea view", "ocean view", "waterfront"],
    "pool": ["pool", "swimming"],
    "gym": ["gym", "fitness"],
    "balcony": ["balcony", "terrace"],
    "parking": ["parking"],
    "metro": ["metro", "subway", "train", "station"],
    "ready": ["ready to move", "ready-to-move", "ready"],
}

_CURRENCY_TOKENS = {"aed", "usd", "eur", "gbp", "inr", "cad", "aud", "sgd"}


def _parse_number(value: str, suffix: Optional[str]) -> Optional[float]:
    try:
        num = float(value.replace(",", ""))
    except Exception:
        return None
    if not suffix:
        return num
    suf = suffix.lower()
    if suf in {"k"}:
        return num * 1_000
    if suf in {"m", "mn", "mil", "million"}:
        return num * 1_000_000
    if suf in {"b", "bn", "billion"}:
        return num * 1_000_000_000
    return num


def _extract_price(text: str) -> Dict[str, Any]:
    lower = text.lower()
    currency = None
    for token in _CURRENCY_TOKENS:
        if token in lower:
            currency = token
            break

    price_min = None
    price_max = None

    range_pat = re.search(
        r"(?:between|from)\s+([\d,.]+)\s*(k|m|b|mn|bn|mil|million|billion)?\s*(?:aed|usd|eur|gbp|inr|cad|aud|sgd)?\s*(?:and|to)\s+([\d,.]+)\s*(k|m|b|mn|bn|mil|million|billion)?",
        lower,
    )
    if range_pat:
        price_min = _parse_number(range_pat.group(1), range_pat.group(2))
        price_max = _parse_number(range_pat.group(3), range_pat.group(4))
        return {"price_min": price_min, "price_max": price_max, "currency": currency or "usd"}

    under_pat = re.search(
        r"(?:under|below|less than|up to|max|within)\s+([\d,.]+)\s*(k|m|b|mn|bn|mil|million|billion)?",
        lower,
    )
    if under_pat:
        price_max = _parse_number(under_pat.group(1), under_pat.group(2))
        return {"price_min": None, "price_max": price_max, "currency": currency or "usd"}

    over_pat = re.search(
        r"(?:over|above|at least|min|greater than|more than)\s+([\d,.]+)\s*(k|m|b|mn|bn|mil|million|billion)?",
        lower,
    )
    if over_pat:
        price_min = _parse_number(over_pat.group(1), over_pat.group(2))
        return {"price_min": price_min, "price_max": None, "currency": currency or "usd"}

    return {"price_min": None, "price_max": None, "currency": currency or "usd"}


def _extract_bedrooms(text: str) -> Optional[int]:
    slash = re.search(r"(\d+)\s*/\s*(\d+)", text.lower())
    if slash:
        try:
            return int(slash.group(1))
        except Exception:
            pass
    m = re.search(r"(\d+)\s*(bedroom|bed|br|bhk)", text.lower())
    if not m:
        return None
    try:
        return int(m.group(1))
    except Exception:
        return None


def _extract_property_type(text: str) -> Optional[str]:
    lower = text.lower()
    for pt in _PROPERTY_TYPES:
        if pt in lower:
            # normalize flat/condo/studio to apartment for SQL
            if pt in {"flat", "condo", "studio"}:
                return "apartment"
            return pt
    return None


def _extract_city(text: str) -> Optional[str]:
    lower = text.lower()
    for city in _CITY_CANDIDATES:
        if city in lower:
            return city
    return None


def _extract_project_or_dev(text: str) -> Dict[str, Optional[str]]:
    project = None
    developer = None
    quote = re.search(r"['\"]([^'\"]{3,80})['\"]", text)
    if quote:
        project = quote.group(1).strip()

    if not project:
        m = re.search(r"(?:called|named|project)\s+([A-Za-z][\w\s'-]{3,80})", text, re.IGNORECASE)
        if m:
            project = m.group(1).strip()

    if not developer:
        m = re.search(r"(?:by|developer)\s+([A-Za-z][\w\s'-]{3,80})", text, re.IGNORECASE)
        if m:
            developer = m.group(1).strip()

    return {"project_name": project, "developer": developer}


def _extract_features(text: str) -> List[str]:
    lower = text.lower()
    feats: List[str] = []
    for key, patterns in _FEATURE_KEYWORDS.items():
        if any(p in lower for p in patterns):
            feats.append(key)
    return feats


@tool
def extract_intent_filters(query: str) -> Dict[str, Any]:
    """
    Extract structured filters from a fuzzy user request.
    Returns: project_name, developer, city, price_min, price_max, currency, bedrooms, property_type, must_have_features, rewritten_query.
    """
    price_info = _extract_price(query)
    bedrooms = _extract_bedrooms(query)
    property_type = _extract_property_type(query)
    city = _extract_city(query)
    proj_dev = _extract_project_or_dev(query)
    features = _extract_features(query)

    return {
        "rewritten_query": query.strip(),
        "project_name": proj_dev["project_name"],
        "developer": proj_dev["developer"],
        "city": city,
        "price_min": price_info["price_min"],
        "price_max": price_info["price_max"],
        "currency": price_info["currency"],
        "bedrooms": bedrooms,
        "property_type": property_type,
        "must_have_features": features,
        "note": "Prices assumed USD; currency token captured if provided.",
        "source_tool": "extract_intent_filters",
    }
