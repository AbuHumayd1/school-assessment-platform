from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("audit", "0002_phase6_institution_membership_events")]

    operations = [
        migrations.AlterField(
            model_name="auditevent",
            name="event_type",
            field=models.CharField(
                choices=[
                    ("assessment_approved", "Assessment approved"),
                    ("assessment_scheduled", "Assessment scheduled"),
                    ("attempt_started", "Attempt started"),
                    ("attempt_submitted", "Attempt submitted"),
                    ("attempt_expired", "Attempt expired"),
                    ("result_marked", "Result marked"),
                    ("result_published", "Result published"),
                    ("result_withheld", "Result withheld"),
                    ("institution_profile_updated", "Institution profile updated"),
                    ("membership_changed", "Institution membership changed"),
                    ("question_import", "Question bank CSV import"),
                ],
                max_length=32,
            ),
        ),
    ]
