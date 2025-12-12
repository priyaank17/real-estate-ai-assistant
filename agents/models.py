from django.db import models
import uuid

class Project(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    bedrooms = models.IntegerField(null=True, blank=True)
    bathrooms = models.FloatField(null=True, blank=True)
    status = models.CharField(max_length=100, null=True, blank=True)
    unit_type = models.CharField(max_length=100, null=True, blank=True)
    developer = models.CharField(max_length=255, null=True, blank=True)
    price = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    area = models.FloatField(null=True, blank=True)
    property_type = models.CharField(max_length=100, null=True, blank=True)
    city = models.CharField(max_length=100, null=True, blank=True)
    country = models.CharField(max_length=100, null=True, blank=True)
    completion_date = models.CharField(max_length=100, null=True, blank=True)
    features = models.TextField(null=True, blank=True) # Storing as text/JSON
    facilities = models.TextField(null=True, blank=True) # Storing as text/JSON
    description = models.TextField(null=True, blank=True)
    
    def __str__(self):
        return self.name

class Lead(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100, blank=True, null=True)
    email = models.EmailField(unique=True)
    preferences = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.email})"

class Booking(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name='bookings')
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='bookings')
    booking_date = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"Booking for {self.lead} at {self.project}"
