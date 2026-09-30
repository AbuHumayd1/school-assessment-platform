from decimal import Decimal

from django.db import migrations, models
import django.core.validators


def copy_phase3_marking_configuration(apps, schema_editor):
    Attempt = apps.get_model("attempts", "Attempt")
    AttemptQuestion = apps.get_model("attempts", "AttemptQuestion")
    AssessmentQuestion = apps.get_model("assessments", "AssessmentQuestion")
    db = schema_editor.connection.alias
    for attempt in Attempt.objects.using(db).select_related("assessment").iterator():
        Attempt.objects.using(db).filter(pk=attempt.pk).update(pass_mark_snapshot=attempt.assessment.pass_mark)
        for row in AttemptQuestion.objects.using(db).filter(attempt_id=attempt.pk).iterator():
            configured = AssessmentQuestion.objects.using(db).filter(assessment_id=attempt.assessment_id, question_id=row.question_id).first()
            if configured:
                marks = configured.marks
            else:
                marks = row.question.marks
            AttemptQuestion.objects.using(db).filter(pk=row.pk).update(marks_available=marks)


class Migration(migrations.Migration):
    dependencies = [("attempts", "0001_initial")]
    operations = [
        migrations.AddField(
            model_name="attempt",
            name="pass_mark_snapshot",
            field=models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=9),
        ),
        migrations.AddField(
            model_name="attemptquestion",
            name="marks_available",
            field=models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=7, validators=[django.core.validators.MinValueValidator(Decimal("0.00"))]),
        ),
        migrations.RunPython(copy_phase3_marking_configuration, migrations.RunPython.noop),
    ]
