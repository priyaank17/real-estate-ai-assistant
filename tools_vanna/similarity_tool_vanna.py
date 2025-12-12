"""
Similarity/Cross-Selling Tool - Vanna 2.0 Format

When exact matches aren't found, suggest similar properties by relaxing criteria.
"""
from vanna.core.tool import Tool, ToolContext, ToolResult
from pydantic import BaseModel, Field
from typing import Type, Optional
from agents.models import Project


class SimilarityArgs(BaseModel):
    bedrooms: Optional[int] = Field(None, description="Target number of bedrooms")
    city: Optional[str] = Field(None, description="Target city")
    max_price: Optional[float] = Field(None, description="Maximum price")
    property_type: Optional[str] = Field(None, description="Property type (apartment/villa/townhouse)")


class FindSimilarPropertiesTool(Tool[SimilarityArgs]):
    """Find similar properties when exact match returns no results."""
    
    @property
    def name(self) -> str:
        return "find_similar_properties"
    
    @property
    def description(self) -> str:
        return ("When exact search returns 0 results, use this to find similar alternatives "
                "by relaxing search criteria (±1 bedroom, higher budget, nearby cities, etc.)")
    
    def get_args_schema(self) -> Type[SimilarityArgs]:
        return SimilarityArgs
    
    async def execute(self, context: ToolContext, args: SimilarityArgs) -> ToolResult:
        """Execute similarity search with relaxed criteria."""
        try:
            alternatives = []
            
            # Strategy 1: ±1 bedroom in same city (if criteria specified)
            if args.bedrooms and args.city:
                nearby_bedrooms = Project.objects.filter(
                    city__iexact=args.city,
                    bedrooms__in=[args.bedrooms - 1, args.bedrooms, args.bedrooms + 1]
                )
                
                if args.max_price:
                    nearby_bedrooms = nearby_bedrooms.filter(price__lte=args.max_price * 1.2)
                
                nearby_bedrooms = nearby_bedrooms[:3]
                
                if nearby_bedrooms.exists():
                    alternatives.append(("Similar bedroom count", list(nearby_bedrooms)))
            
            # Strategy 2: Same criteria but higher budget
            if args.bedrooms and args.city and args.max_price:
                higher_budget = Project.objects.filter(
                    city__iexact=args.city,
                    bedrooms=args.bedrooms,
                    price__lte=args.max_price * 1.5,
                    price__gt=args.max_price
                )[:3]
                
                if higher_budget.exists():
                    alternatives.append(("Slightly higher budget", list(higher_budget)))
            
            # Strategy 3: Same type but different city
            if args.property_type and args.bedrooms:
                other_cities = Project.objects.filter(
                    property_type=args.property_type,
                    bedrooms=args.bedrooms
                ).exclude(city__iexact=args.city if args.city else "")[:5]
                
                if other_cities.exists():
                    alternatives.append(("Other cities", list(other_cities)))
            
            # Strategy 4: Just show some popular options if nothing else
            if not alternatives:
                popular = Project.objects.all().order_by('-price')[:5]
                alternatives.append(("Popular properties", list(popular)))
            
            # Format response
            result = "**No exact matches, but here are similar alternatives:**\n\n"
            
            for category, props in alternatives:
                result += f"### {category.title()}\n"
                for i, p in enumerate(props, 1):
                    result += (f"{i}. **{p.name}**\n"
                             f"   - {p.bedrooms} bedrooms, {p.city}\n"
                             f"   - ${p.price:,.0f}\n")
                result += "\n"
            
            result += "Would any of these work? Or should I adjust the search criteria?"
            
            return ToolResult(success=True, result_for_llm=result)
            
        except Exception as e:
            return ToolResult(
                success=False,
                result_for_llm=f"Error finding similar properties: {str(e)}"
            )
