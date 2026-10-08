import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('audit', '0003_phase7a_question_import_event')]
    operations = [
        migrations.AlterField(model_name='auditevent', name='institution', field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='audit_events', to='institutions.institution')),
        migrations.AlterField(model_name='auditevent', name='event_type', field=models.CharField(max_length=32, choices=[
            ('assessment_approved', 'Assessment approved'), ('assessment_scheduled', 'Assessment scheduled'),
            ('attempt_started', 'Attempt started'), ('attempt_submitted', 'Attempt submitted'), ('attempt_expired', 'Attempt expired'),
            ('result_marked', 'Result marked'), ('result_published', 'Result published'), ('result_withheld', 'Result withheld'),
            ('institution_profile_updated', 'Institution profile updated'), ('membership_changed', 'Institution membership changed'),
            ('question_import', 'Question bank CSV import'), ('platform_content_changed', 'Platform Library content changed'),
        ])),
    ]
