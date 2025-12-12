from langchain_core.tools import tool
from typing import List, Optional, Dict

@tool
def update_ui_context(shortlisted_project_ids: Optional[List[int]] = None, booking_status: Optional[str] = None):
    """
    Update the user interface with structured data.
    Call this tool when you have found specific projects to show to the user, 
    or when a booking status changes.
    
    Args:
        shortlisted_project_ids: List of Project IDs to highlight or show in a list/map.
        booking_status: Status of a booking (e.g., "confirmed", "pending").
    """
    # This tool doesn't "do" anything in the backend, it just returns the data 
    # so it gets recorded in the message history. 
    # The API will extract this tool call's arguments to send to the frontend.
    return "UI Context Updated."
