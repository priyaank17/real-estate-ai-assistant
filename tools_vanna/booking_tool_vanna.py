"""
Booking Tool - Vanna 2.0 Format

Books property viewings for users.
"""
from vanna.core.tool import Tool, ToolContext, ToolResult
from pydantic import BaseModel, Field
from typing import Type
from agents.models import Project, Lead, Booking
from datetime import datetime


class BookingArgs(BaseModel):
    project_name: str = Field(description="Name of the property project")
    visitor_name: str = Field(description="Name of the visitor")
    visitor_email: str = Field(description="Email of the visitor")
    visit_date: str = Field(description="Preferred visit date (YYYY-MM-DD format)")


class BookingToolVanna(Tool[BookingArgs]):
    """Book a property viewing."""
    
    @property
    def name(self) -> str:
        return "book_viewing"
    
    @property
    def description(self) -> str:
        return "Schedule a property viewing for a potential buyer"
    
    def get_args_schema(self) -> Type[BookingArgs]:
        return BookingArgs
    
    async def execute(self, context: ToolContext, args: BookingArgs) -> ToolResult:
        """Execute booking."""
        try:
            # Find project
            project = Project.objects.filter(name__icontains=args.project_name).first()
            
            if not project:
                return ToolResult(
                    success=False,
                    result_for_llm=f"Project '{args.project_name}' not found."
                )
            
            # Parse date
            try:
                visit_date = datetime.strptime(args.visit_date, "%Y-%m-%d").date()
            except ValueError:
                return ToolResult(
                    success=False,
                    result_for_llm="Invalid date format. Please use YYYY-MM-DD format."
                )
            
            # Get or create lead
            lead, created = Lead.objects.get_or_create(
                email=args.visitor_email,
                defaults={'name': args.visitor_name}
            )
            
            # Create booking
            booking = Booking.objects.create(
                project=project,
                lead=lead,
                visit_date=visit_date,
                status='pending'
            )
            
            result = (
                f"**Viewing Booked Successfully!**\n\n"
                f"- **Property**: {project.name}\n"
                f"- **Visitor**: {args.visitor_name}\n"
                f"- **Date**: {visit_date.strftime('%B %d, %Y')}\n"
                f"- **Confirmation**: #{booking.id}\n\n"
                f"A confirmation email will be sent to {args.visitor_email}"
            )
            
            return ToolResult(success=True, result_for_llm=result)
            
        except Exception as e:
            return ToolResult(
                success=False,
                result_for_llm=f"Error booking viewing: {str(e)}"
            )
