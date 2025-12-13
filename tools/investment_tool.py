from typing import Dict, Any, List, Optional
from decimal import Decimal
from langchain_core.tools import tool
from django.conf import settings
from agents.models import Project


def _to_float(val: Optional[Decimal]) -> Optional[float]:
    try:
        return float(val) if val is not None else None
    except Exception:
        return None


def _price_per_sqm(price: Optional[Decimal], area: Optional[float]) -> Optional[float]:
    if price is None or not area or area <= 0:
        return None
    try:
        return float(price) / float(area)
    except Exception:
        return None


def _city_yield(city: Optional[str]) -> float:
    if not city:
        return 0.045
    c = city.lower()
    if "dubai" in c:
        return 0.06
    if "miami" in c or "florida" in c:
        return 0.05
    if "london" in c:
        return 0.035
    return 0.045


def _score(price: Optional[float], price_per_sqm: Optional[float], rental_yield: float) -> float:
    base = 7.0
    if price and price > 2_000_000:
        base -= 0.5
    if price_per_sqm and price_per_sqm < 8000:
        base += 0.5
    if rental_yield > 0.05:
        base += 0.5
    return max(1.0, min(10.0, round(base, 1)))


def _summarize(project: Project) -> Dict[str, Any]:
    price = _to_float(project.price)
    ppsqm = _price_per_sqm(project.price, project.area)
    ry = _city_yield(project.city)
    score = _score(price, ppsqm, ry)
    return {
        "project_id": str(project.id),
        "project_name": project.name,
        "city": project.city,
        "country": project.country,
        "property_type": project.property_type,
        "bedrooms": project.bedrooms,
        "price": price,
        "area": project.area,
        "price_per_sqm": ppsqm,
        "estimated_rental_yield": round(ry * 100, 2),
        "estimated_appreciation": 6.0,  # simple placeholder %
        "investment_score": score,
        "status": project.status,
        "developer": project.developer,
    }


@tool
def analyze_investment(project_id: str = "", city: str = "", budget: float = None) -> Dict[str, Any]:
    """
    Basic investment analysis:
    - If project_id provided, analyze that project.
    - Else, pick up to 3 projects by city (and optional budget) ordered by price.
    Returns metrics per project.
    """
    try:
        projects: List[Project] = []
        if project_id:
            p = Project.objects.filter(id__icontains=project_id).first()
            if p:
                projects = [p]
        if not projects:
            qs = Project.objects.all()
            if city:
                qs = qs.filter(city__icontains=city)
            if budget is not None:
                qs = qs.filter(price__lte=budget)
            projects = list(qs.order_by("price")[:3])

        if not projects:
            return {"error": "No projects found for investment analysis.", "source_tool": "analyze_investment"}

        analyses = [_summarize(p) for p in projects]
        return {
            "projects": analyses,
            "project_ids": [a["project_id"] for a in analyses],
            "source_tool": "analyze_investment",
        }
    except Exception as e:
        return {"error": f"Investment analysis failed: {e}", "source_tool": "analyze_investment"}
