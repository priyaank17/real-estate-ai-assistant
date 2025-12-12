from agents.models import Project
from django.db.models import Q
from langchain_core.tools import tool

@tool
def compare_projects(project_names: list):
    """
    Compares multiple projects side-by-side.
    Returns a Markdown table.
    """
    if not project_names:
        return "Please provide project names to compare."
    
    # Build query to find projects matching names
    query = Q()
    for name in project_names:
        query |= Q(name__icontains=name.strip())
    
    projects = Project.objects.filter(query)
    
    if not projects:
        return "I couldn't find any of the specified projects."
    
    # Build Markdown Table
    headers = ["Feature"] + [p.name for p in projects]
    rows = [
        ["City"] + [p.city for p in projects],
        ["Price"] + [f"${p.price:,.0f}" if p.price else "N/A" for p in projects],
        ["Bedrooms"] + [str(p.bedrooms) if p.bedrooms else "N/A" for p in projects],
        ["Type"] + [p.property_type for p in projects],
        ["Area (sq m)"] + [str(p.area) for p in projects],
        ["Status"] + [p.status for p in projects],
    ]
    
    # Format table
    table = "| " + " | ".join(headers) + " |\n"
    table += "| " + " | ".join(["---"] * len(headers)) + " |\n"
    
    for row in rows:
        table += "| " + " | ".join([str(c) for c in row]) + " |\n"
        
    return table
