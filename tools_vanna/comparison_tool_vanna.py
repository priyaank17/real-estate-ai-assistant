"""
Comparison Tool - Vanna 2.0 Format

Compares multiple property projects side-by-side.
"""
from vanna.core.tool import Tool, ToolContext, ToolResult
from pydantic import BaseModel, Field
from typing import Type, List
from agents.models import Project
from django.db.models import Q


class ComparisonArgs(BaseModel):
    project_names: List[str] = Field(description="List of project names to compare (2-5 projects)")


class ComparisonToolVanna(Tool[ComparisonArgs]):
    """Compare multiple projects side-by-side."""
    
    @property
    def name(self) -> str:
        return "compare_projects"
    
    @property
    def description(self) -> str:
        return "Compare multiple property projects side-by-side (price, features, location, etc.)"
    
    def get_args_schema(self) -> Type[ComparisonArgs]:
        return ComparisonArgs
    
    async def execute(self, context: ToolContext, args: ComparisonArgs) -> ToolResult:
        """Execute comparison."""
        try:
            if len(args.project_names) < 2:
                return ToolResult(
                    success=False,
                    result_for_llm="Please provide at least 2 projects to compare."
                )
            
            # Build query
            query = Q()
            for name in args.project_names:
                query |= Q(name__icontains=name.strip())
            
            projects = Project.objects.filter(query)[:5]  # Limit to 5
            
            if not projects:
                return ToolResult(
                    success=False,
                    result_for_llm="Could not find any of the specified projects."
                )
            
            # Build comparison table
            result = "**Property Comparison**\n\n"
            result += "| Feature | " + " | ".join([p.name[:30] for p in projects]) + " |\n"
            result += "|" + "----|" * (len(projects) + 1) + "\n"
            
            # Add rows
            rows = [
                ("City", [p.city for p in projects]),
                ("Price", [f"${p.price:,.0f}" if p.price else "N/A" for p in projects]),
                ("Bedrooms", [str(p.bedrooms) if p.bedrooms else "N/A" for p in projects]),
                ("Type", [p.property_type for p in projects]),
                ("Area (sqm)", [str(p.area) if p.area else "N/A" for p in projects]),
                ("Status", [p.completion_status for p in projects]),
            ]
            
            for label, values in rows:
                result += f"| {label} | " + " | ".join([str(v) for v in values]) + " |\n"
            
            return ToolResult(success=True, result_for_llm=result)
            
        except Exception as e:
            return ToolResult(
                success=False,
                result_for_llm=f"Error comparing projects: {str(e)}"
            )
