from django.db import migrations, models
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ("agents", "0002_remove_project_project_type_project_area_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="VisitBooking",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("city", models.CharField(blank=True, max_length=100, null=True)),
                ("preferred_date", models.DateField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("lead", models.ForeignKey(on_delete=models.deletion.CASCADE, related_name="visit_bookings", to="agents.lead")),
                ("project", models.ForeignKey(on_delete=models.deletion.CASCADE, related_name="visit_bookings", to="agents.project")),
            ],
            options={
                "db_table": "visit_bookings",
            },
        ),
    ]
