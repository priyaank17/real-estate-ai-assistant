from langchain_core.tools import tool
from agents.models import Booking, Project, Lead
from datetime import datetime

@tool
def book_viewing(project_id: int, customer_name: str, customer_email: str, preferred_date: str) -> str:
    """
    Book a property viewing for a customer.
    
    Args:
        project_id: The ID of the project to view
        customer_name: Customer's full name
        customer_email: Customer's email address
        preferred_date: Preferred viewing date in YYYY-MM-DD format
    
    Returns:
        Confirmation message with booking details
    """
    try:
        # Get the project
        project = Project.objects.get(id=project_id)
        
        # Create or get lead
        lead, created = Lead.objects.get_or_create(
            email=customer_email,
            defaults={
                'name': customer_name,
                'phone': '',  # Can be collected later
                'source': 'AI Assistant'
            }
        )
        
        # Create booking
        booking = Booking.objects.create(
            project=project,
            lead=lead,
            viewing_date=datetime.strptime(preferred_date, "%Y-%m-%d").date(),
            status='pending'
        )
        
        return f"✅ Viewing booked successfully!\n\nDetails:\n- Property: {project.name}\n- Customer: {customer_name}\n- Email: {customer_email}\n- Date: {preferred_date}\n- Booking ID: {booking.id}\n\nYou will receive a confirmation email shortly."
        
    except Project.DoesNotExist:
        return f"❌ Error: Project with ID {project_id} not found."
    except ValueError:
        return f"❌ Error: Invalid date format. Please use YYYY-MM-DD (e.g., 2024-03-15)"
    except Exception as e:
        return f"❌ Error booking viewing: {str(e)}"
