"""
Database seeding script - loads data from CSV file.
"""
import os
import sys
import django
import pandas as pd

# Setup Django environment
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
sys.path.insert(0, project_root)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'silver_land.settings')
django.setup()

from agents.models import Project

def seed_from_csv():
    """
    Seed database from CSV file (data/properties.csv).
    Only creates records if database is empty.
    """
    if Project.objects.exists():
        count = Project.objects.count()
        print(f"✓ Database already contains {count} projects. Skipping seed.")
        return
    
    # Load CSV
    csv_path = os.path.join(project_root, 'data', 'properties.csv')
    if not os.path.exists(csv_path):
        print(f"❌ Error: CSV file not found at {csv_path}")
        print("   Make sure data/properties.csv exists.")
        return
    
    print(f"📂 Loading data from {csv_path}...")
    df = pd.read_csv(csv_path)
    
    # Map CSV columns to Django model fields
    column_mapping = {
        'Project name': 'name',
        'No of bedrooms': 'bedrooms',
        'bathrooms': 'bathrooms',
        'unit type': 'property_type',
        'Completion status (off plan/available)': 'completion_status',
        'developer name': 'developer',
        'Price (USD)': 'price',
        'Area (sq mtrs)': 'area',
        'Property type (apartment/villa)': 'property_type',
        'city': 'city',
        'country': 'country',
        'completion_date': 'completion_date',
        'features': 'features',
        'facilities': 'facilities',
        'Project description': 'description'
    }
    
    # Rename columns
    df = df.rename(columns=column_mapping)
    
    # Clean completion_status
    df['completion_status'] = df['completion_status'].apply(
        lambda x: 'available' if isinstance(x, str) and 'available' in x.lower() else 'off_plan'
    )
    
    # Convert property_type to lowercase
    df['property_type'] = df['property_type'].str.lower()
    
    # Create records
    created_count = 0
    error_count = 0
    
    print(f"📝 Creating {len(df)} project records...")
    
    for idx, row in df.iterrows():
        try:
            Project.objects.create(
                name=row.get('name', 'Unknown'),
                bedrooms=row.get('bedrooms', 0) if pd.notna(row.get('bedrooms')) else 0,
                bathrooms=row.get('bathrooms', 0) if pd.notna(row.get('bathrooms')) else 0,
                property_type=row.get('property_type', 'apartment'),
                completion_status=row.get('completion_status', 'available'),
                developer=row.get('developer', '') if pd.notna(row.get('developer')) else '',
                price=row.get('price', 0) if pd.notna(row.get('price')) else 0,
                area=row.get('area', 0) if pd.notna(row.get('area')) else 0,
                city=row.get('city', '') if pd.notna(row.get('city')) else '',
                country=row.get('country', '') if pd.notna(row.get('country')) else '',
                completion_date=row.get('completion_date') if pd.notna(row.get('completion_date')) else None,
                features=str(row.get('features', '[]')),
                facilities=str(row.get('facilities', '[]')),
                description=row.get('description', '') if pd.notna(row.get('description')) else ''
            )
            created_count += 1
            if created_count % 100 == 0:
                print(f"   ✓ Created {created_count} projects...")
        except Exception as e:
            error_count += 1
            if error_count <= 5:  # Only show first 5 errors
                print(f"   ⚠️  Error on row {idx}: {str(e)}")
    
    print(f"\n✅ Database seeding complete!")
    print(f"   - Created: {created_count} projects")
    print(f"   - Errors: {error_count}")

if __name__ == "__main__":
    seed_from_csv()
