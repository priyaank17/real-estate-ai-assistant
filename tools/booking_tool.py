from typing import Any, Dict, Optional
from datetime import datetime

from langchain_core.tools import tool
from django.db import transaction

from agents.models import Lead, Project, VisitBooking


@tool
def book_viewing(
    project_id: str,
    customer_name: str,
    customer_email: str,
    city: str = "",
    preferred_date: str = "",
    preferences: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Store a confirmed property visit booking (visit_bookings table) and upsert lead details.
    
    Args:
        project_id: UUID of the selected project
        customer_name: Buyer's full name
        customer_email: Buyer's email
        city: City of interest (optional, for lead enrichment)
        preferred_date: Optional preferred visit date (YYYY-MM-DD)
        preferences: Optional free-text preferences (beds, budget, type)
    
    Returns:
        Dict with booking details or error message
    """
    try:
        project = Project.objects.get(id=project_id)
    except Project.DoesNotExist:
        return {"error": f"Project with ID {project_id} not found."}

    first_name = customer_name.strip().split(" ")[0] if customer_name else ""
    last_name = " ".join(customer_name.strip().split(" ")[1:]) if customer_name and len(customer_name.split(" ")) > 1 else ""

    parsed_date = None
    if preferred_date:
        try:
            parsed_date = datetime.strptime(preferred_date, "%Y-%m-%d").date()
        except ValueError:
            return {"error": "Invalid date format. Use YYYY-MM-DD (e.g., 2024-12-20)."}

    try:
        with transaction.atomic():
            lead, created = Lead.objects.get_or_create(
                email=customer_email,
                defaults={
                    "first_name": first_name or "Guest",
                    "last_name": last_name or "",
                    "preferences": preferences or city or project.city or "",
                },
            )

            # Update lead info if we learn more later
            updated = False
            if not created:
                if first_name and not lead.first_name:
                    lead.first_name = first_name
                    updated = True
                if last_name and not lead.last_name:
                    lead.last_name = last_name
                    updated = True
                if preferences:
                    lead.preferences = preferences
                    updated = True
                elif city and not lead.preferences:
                    lead.preferences = city
                    updated = True
                if updated:
                    lead.save()

            booking = VisitBooking.objects.create(
                lead=lead,
                project=project,
                city=city or project.city,
                preferred_date=parsed_date,
            )

        return {
            "message": "Viewing booked successfully.",
            "booking_id": str(booking.id),
            "project_name": project.name,
            "customer_name": customer_name,
            "customer_email": customer_email,
            "city": city or project.city,
            "preferred_date": str(parsed_date) if parsed_date else None,
            "lead_id": str(lead.id),
        }
    except Exception as e:
        return {"error": f"Error booking viewing: {str(e)}"}
