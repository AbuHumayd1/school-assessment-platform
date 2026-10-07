from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("assessments", "0004_assessment_candidate")]

    operations = [
        migrations.AddField(
            model_name="assessment",
            name="show_score_immediately",
            field=models.BooleanField(default=False),
        ),
    ]
