import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("institutions", "0001_initial"),
    ]
    operations = [
        migrations.CreateModel(
            name="AuditEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("event_type", models.CharField(choices=[("assessment_approved", "Assessment approved"), ("assessment_scheduled", "Assessment scheduled"), ("attempt_started", "Attempt started"), ("attempt_submitted", "Attempt submitted"), ("attempt_expired", "Attempt expired"), ("result_marked", "Result marked"), ("result_published", "Result published"), ("result_withheld", "Result withheld")], max_length=32)),
                ("resource_type", models.CharField(max_length=100)),
                ("resource_id", models.CharField(max_length=100)),
                ("occurred_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("actor", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="audit_events", to=settings.AUTH_USER_MODEL)),
                ("institution", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="audit_events", to="institutions.institution")),
            ],
            options={"ordering": ("-occurred_at", "-id")},
        ),
        migrations.AddIndex(model_name="auditevent", index=models.Index(fields=["institution", "occurred_at"], name="audit_tenant_time_idx")),
    ]
