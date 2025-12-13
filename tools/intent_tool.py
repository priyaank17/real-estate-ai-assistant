import json
import os
import re
from typing import Any, Dict, List, Optional

import logging

from langchain_core.tools import tool
from langchain_openai import AzureChatOpenAI, ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

try:
    from langchain_community.chat_models import ChatOllama  # type: ignore
except ImportError:
    ChatOllama = None

logger = logging.getLogger(__name__)

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
_CITY_NORMALIZE = {
    "dubai": "dubai",
    "dubai marina": "dubai marina",
    "downtown dubai": "dubai",
    "abu dhabi": "abu dhabi",
    "london": "london",
    "miami": "miami",
    "chicago": "chicago",
    "new york": "new york",
    "nyc": "new york",
    "toronto": "toronto",
    "paris": "paris",
    "sydney": "sydney",
    "mumbai": "mumbai",
    "bangalore": "bangalore",
    "delhi": "delhi",
}


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


def _normalize_city(candidate: Optional[str]) -> Optional[str]:
    if not candidate:
        return None
    c = candidate.strip().lower()
    return _CITY_NORMALIZE.get(c)


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


_PROJECT_KEYWORDS = {
    "residence",
    "residences",
    "residency",
    "tower",
    "towers",
    "villa",
    "villas",
    "heights",
    "collection",
    "apartments",
    "resort",
    "bay",
    "marina",
    "harbour",
    "harbor",
    "plaza",
    "residential",
    "signature",
    "downtown",
    "midtown",
    "edgewater",
    "palm",
    "crescent",
}


def _extract_project_keyword_span(text: str, existing_city: Optional[str]) -> Optional[str]:
    """
    Fallback: grab a project-like phrase if the main extractor missed it.
    Looks for 2-7 word spans containing common real-estate keywords.
    """
    candidates = []
    for m in re.finditer(r"([A-Za-z0-9&.'-]+(?:\\s+[A-Za-z0-9&.'-]+){1,6})", text):
        span = m.group(1).strip()
        low = span.lower()
        if any(k in low for k in _PROJECT_KEYWORDS):
            if existing_city and existing_city in low and len(low.split()) <= 2:
                continue
            candidates.append(span)
    if not candidates:
        return None
    return sorted(candidates, key=lambda s: len(s), reverse=True)[0]


def _get_llm():
    # Prefer Ollama if configured
    ollama_model = os.getenv("OLLAMA_MODEL") or os.getenv("INTENT_OLLAMA_MODEL") or "llama3.1"
    if os.getenv("USE_OLLAMA_FOR_INTENT", "").lower() in {"1", "true", "yes"} and ChatOllama:
        try:
            return ChatOllama(model=ollama_model, temperature=0)
        except Exception as e:
            logger.info(f"[intent_llm_extract] Ollama init failed: {e}")

    azure_key = os.getenv("AZURE_OPENAI_API_KEY")
    azure_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
    azure_deployment = os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT", "gpt-4o-mini")
    model_name = os.getenv("OPENAI_LLM_MODEL", "gpt-4o-mini")
    temp = 0
    if (azure_deployment and "nano" in azure_deployment.lower()) or (model_name and "nano" in model_name.lower()):
        temp = 1  # some nano deployments only accept default temperature
    if azure_key and azure_endpoint:
        return AzureChatOpenAI(
            azure_endpoint=azure_endpoint,
            api_key=azure_key,
            api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-05-01-preview"),
            azure_deployment=azure_deployment,
            temperature=temp,
        )
    api_key = os.getenv("OPENAI_API_KEY")
    if api_key:
        return ChatOpenAI(model=model_name, temperature=temp)
    return None


def _safe_float(val: Any) -> Optional[float]:
    try:
        return float(val)
    except Exception:
        return None


def _llm_extract_entities(text: str) -> Dict[str, Any]:
    """
    LLM-based structured extractor to catch project/developer/city when heuristics miss.
    """
    llm = _get_llm()
    if not llm:
        return {}
    sys = (
        "Extract structured filters from the user message. "
        "Return strict JSON with keys: project_name, developer, city, price_min, price_max, "
        "currency (string like usd/aed/eur), bedrooms (int), property_type, must_have_features (list), "
        "question_type (detail|listing|other), is_detail (bool), lead_name, lead_email. "
        "Use null when absent. Do not invent fields not implied by the text."
    )
    prompt = [
        SystemMessage(content=sys),
        HumanMessage(content=text),
    ]
    try:
        resp = llm.invoke(prompt)
        raw = resp.content if hasattr(resp, "content") else ""
        if isinstance(raw, dict):
            return raw
        data = json.loads(raw)
        if isinstance(data, dict):
            return data
    except Exception as e:
        logger.info(f"[intent_llm_extract] fallback LLM extract failed: {e}")
        return {}
    return {}


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
    llm_data = _llm_extract_entities(query)

    # Fallback: heuristic project phrase if missing
    if not proj_dev["project_name"]:
        proj_dev["project_name"] = _extract_project_keyword_span(query, city)

    def pick(primary, fallback):
        return primary if primary not in (None, "") else fallback

    project_name = pick(proj_dev["project_name"], llm_data.get("project_name"))
    developer = pick(proj_dev["developer"], llm_data.get("developer"))
    city = pick(city, _normalize_city(llm_data.get("city")))
    city = _normalize_city(city)
    bedrooms = pick(bedrooms, llm_data.get("bedrooms"))
    property_type = pick(property_type, llm_data.get("property_type"))

    price_min = price_info["price_min"]
    price_max = price_info["price_max"]
    currency = price_info["currency"]
    if price_min is None:
        price_min = _safe_float(llm_data.get("price_min"))
    if price_max is None:
        price_max = _safe_float(llm_data.get("price_max"))
    if currency == "usd" and llm_data.get("currency"):
        currency = llm_data.get("currency")

    llm_feats = llm_data.get("must_have_features") or []
    if isinstance(llm_feats, str):
        llm_feats = [llm_feats]
    merged_feats = list(dict.fromkeys(features + [f for f in llm_feats if f]))

    lower = query.lower()
    greet_terms = ["hello", "hi", "hey", "good morning", "good evening"]
    off_topic_terms = ["joke", "weather", "movie", "song", "news", "sports"]
    invest_terms = ["investment", "roi", "yield", "cap rate", "appreciation", "irr"]
    compare_terms = ["compare", "vs", "versus", "difference", "better"]
    detail_terms = [
        "amenity",
        "amenities",
        "amenties",
        "facility",
        "facilities",
        "facilty",
        "feature",
        "features",
        "description",
        "what is there",
        "what does it have",
        "cinema",
        "theatre",
        "theater",
        "pool",
        "gym",
        "spa",
    ]

    is_greeting = any(t in lower for t in greet_terms) and not any(term in lower for term in ["apartment", "property", "villa", "house", "project"])
    is_off_topic = not any(k in lower for k in ["property", "project", "apartment", "villa", "bedroom", "budget", "city", "price"]) and any(t in lower for t in off_topic_terms)
    is_investment = any(t in lower for t in invest_terms)
    is_comparison = any(t in lower for t in compare_terms)
    is_detail_question = any(t in lower for t in detail_terms)

    # Regex extraction for lead info
    import re
    lead_email = None
    m = re.search(r"([\\w.+-]+@[\\w-]+\\.[\\w.-]+)", query)
    if m:
        lead_email = m.group(1)
    lead_name = None
    mname = re.search(r"(?:name\\s*[:=]\\s*|i am\\s+|i'm\\s+|my name is\\s+)([A-Za-z][A-Za-z\\s]{1,60})", query, re.IGNORECASE)
    if mname:
        lead_name = mname.group(1).strip().strip(",.")

    return {
        "rewritten_query": query.strip(),
        "project_name": project_name,
        "developer": developer,
        "city": city,
        "price_min": price_min,
        "price_max": price_max,
        "currency": currency,
        "bedrooms": bedrooms,
        "property_type": property_type,
        "must_have_features": merged_feats,
        "note": "Prices assumed USD; currency token captured if provided.",
        "source_tool": "extract_intent_filters",
        "is_greeting": is_greeting or bool(llm_data.get("is_greeting")),
        "is_off_topic": is_off_topic or bool(llm_data.get("is_off_topic")),
        "is_investment": is_investment or bool(llm_data.get("is_investment")),
        "is_comparison": is_comparison or bool(llm_data.get("is_comparison")),
        "is_detail_question": is_detail_question or (llm_data.get("question_type") == "detail") or bool(llm_data.get("is_detail")),
        "lead_name": lead_name or llm_data.get("lead_name"),
        "lead_email": lead_email or llm_data.get("lead_email"),
    }
