from typing import Dict, Any, List
from langchain_core.tools import tool
from django.conf import settings
from agents.models import Project
import pandas as pd


@tool
def compare_properties(project_ids: List[str]) -> Dict[str, Any]:
    """
    Compare multiple properties by key metrics.
    """
    try:
        if not project_ids:
            return {"error": "No project_ids provided for comparison.", "source_tool": "compare_properties"}
        qs = Project.objects.filter(id__in=project_ids)
        rows = []
        for p in qs:
            rows.append({
                "id": str(p.id),
                "name": p.name,
                "city": p.city,
                "property_type": p.property_type,
                "bedrooms": p.bedrooms,
                "bathrooms": p.bathrooms,
                "price": float(p.price) if p.price is not None else None,
                "area": p.area,
                "price_per_sqm": float(p.price) / p.area if p.price and p.area else None,
                "status": p.status,
                "developer": p.developer,
                "completion_date": p.completion_date,
            })
        if not rows:
            return {"error": "No matching projects found for comparison.", "source_tool": "compare_properties"}
        df = pd.DataFrame(rows)
        preview_cols = [c for c in ["id", "name", "city", "property_type", "bedrooms", "price", "area", "price_per_sqm", "status"] if c in df.columns]
        preview_md = ""
        if preview_cols:
            preview_md = df.head(5)[preview_cols].to_markdown(index=False)
        return {
            "rows": rows,
            "row_count": len(rows),
            "preview_markdown": preview_md,
            "project_ids": [r["id"] for r in rows],
            "source_tool": "compare_properties",
        }
    except Exception as e:
        return {"error": f"Comparison failed: {e}", "source_tool": "compare_properties"}
