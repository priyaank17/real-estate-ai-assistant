from agents.models import Project
import random
from langchain_core.tools import tool

@tool
def analyze_investment(project_name: str):
    """
    Analyzes the investment potential of a project.
    Returns ROI, Rental Yield, and an Investment Score.
    """
    try:
        # Flexible matching
        project = Project.objects.filter(name__icontains=project_name).first()
        if not project:
            return f"I couldn't find a project named '{project_name}' to analyze."
        
        # Mock Investment Logic based on City and Price
        # In a real app, this would use historical data APIs
        
        city_yields = {
            "Dubai": 0.06, # 6%
            "Mumbai": 0.03,
            "London": 0.04,
            "New York": 0.045,
            "Bangalore": 0.05
        }
        
        base_yield = city_yields.get(project.city, 0.04)
        
        # Adjust based on price (lower price often higher yield in some models, or luxury has lower yield)
        # Random variation for demo
        rental_yield = base_yield * random.uniform(0.9, 1.1)
        
        # Appreciation prediction
        appreciation = random.uniform(0.02, 0.08) # 2-8%
        
        # Score (0-10)
        score = (rental_yield * 100) + (appreciation * 50)
        score = min(10, max(1, score))
        
        return {
            "project": project.name,
            "price": float(project.price) if project.price else 0,
            "rental_yield": f"{rental_yield:.2%}",
            "estimated_appreciation": f"{appreciation:.2%}",
            "investment_score": f"{score:.1f}/10",
            "verdict": "Excellent Investment" if score > 7 else "Good Investment" if score > 5 else "Average Investment"
        }
        
    except Exception as e:
        return f"Error analyzing investment: {str(e)}"
