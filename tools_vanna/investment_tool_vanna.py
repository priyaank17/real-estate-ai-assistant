"""
Investment Analysis Tool - Vanna 2.0 Format

Analyzes investment potential of a property project.
"""
from vanna.core.tool import Tool, ToolContext, ToolResult
from pydantic import BaseModel, Field
from typing import Type
from agents.models import Project


class InvestmentArgs(BaseModel):
    project_name: str = Field(description="Name of the property project to analyze")


class InvestmentToolVanna(Tool[InvestmentArgs]):
    """Analyze investment potential of a property."""
    
    @property
    def name(self) -> str:
        return "analyze_investment"
    
    @ property
    def description(self) -> str:
        return "Analyze investment potential, ROI, and rental yield of a property project"
    
    def get_args_schema(self) -> Type[InvestmentArgs]:
        return InvestmentArgs
    
    async def execute(self, context: ToolContext, args: InvestmentArgs) -> ToolResult:
        """Execute investment analysis."""
        try:
            # Find project
            project = Project.objects.filter(name__icontains=args.project_name).first()
            
            if not project:
                return ToolResult(
                    success=False,
                    result_for_llm=f"Project '{args.project_name}' not found in database."
                )
            
            # Calculate metrics
            price = project.price or 0
            area = project.area or 1
            price_per_sqm = price / area
            
            # Estimate rental yield (simplified)
            monthly_rent = price * 0.004  # 0.4% of price
            annual_rent = monthly_rent * 12
            rental_yield = (annual_rent / price * 100) if price > 0 else 0
            
            # Estimate appreciation (simplified based on location)
            appreciation_rate = 5.0  # Default 5%
            if project.country == "AE":  # UAE
                appreciation_rate = 6.5
            elif project.country == "US":
                appreciation_rate = 4.5
            
            # Investment score (1-10)
            score = min(10, (rental_yield + appreciation_rate) / 1.5)
            
            # Format response
            result = (
                f"**Investment Analysis for {project.name}**\n\n"
                f"- **Price**: ${price:,.0f}\n"
                f"- **Rental Yield**: {rental_yield:.2f}%\n"
                f"- **Appreciation**: {appreciation_rate:.2f}%\n"
                f"- **Investment Score**: {score:.1f}/10\n"
                f"- **Recommendation**: {'Excellent' if score >= 8 else 'Good' if score >= 6 else 'Fair'} investment\n"
            )
            
            return ToolResult(success=True, result_for_llm=result)
            
        except Exception as e:
            return ToolResult(
                success=False,
                result_for_llm=f"Error analyzing investment: {str(e)}"
            )
