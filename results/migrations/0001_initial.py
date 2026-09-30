import django.core.validators
import django.db.models.deletion
from decimal import Decimal
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = [
        ("attempts", "0002_attempt_passmark_snapshot_attemptquestion_marks_available"),
        ("assessments", "0002_assessment_resume_allowed"),
        ("candidates", "0001_initial"),
        ("institutions", "0001_initial"),
    ]
    operations = [
        migrations.CreateModel(
            name="Result",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("total_marks", models.DecimalField(decimal_places=2, max_digits=9, validators=[django.core.validators.MinValueValidator(Decimal("0.00"))])),
                ("marks_obtained", models.DecimalField(decimal_places=2, max_digits=9, validators=[django.core.validators.MinValueValidator(Decimal("0.00"))])),
                ("pass_mark", models.DecimalField(decimal_places=2, max_digits=9, validators=[django.core.validators.MinValueValidator(Decimal("0.00"))])),
                ("percentage", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=6)),
                ("grade", models.CharField(default="F", max_length=2)),
                ("passed", models.BooleanField(default=False)),
                ("status", models.CharField(choices=[("provisional", "Provisional"), ("published", "Published"), ("withheld", "Withheld")], db_index=True, default="provisional", max_length=16)),
                ("marked_at", models.DateTimeField()),
                ("published_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("assessment", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="results", to="assessments.assessment")),
                ("attempt", models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name="result", to="attempts.attempt")),
                ("candidate", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="results", to="candidates.candidate")),
                ("institution", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="results", to="institutions.institution")),
            ],
            options={"ordering": ("-marked_at", "-id")},
        ),
        migrations.CreateModel(
            name="ResultQuestion",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("marks_available", models.DecimalField(decimal_places=2, max_digits=7, validators=[django.core.validators.MinValueValidator(Decimal("0.00"))])),
                ("marks_obtained", models.DecimalField(decimal_places=2, max_digits=7, validators=[django.core.validators.MinValueValidator(Decimal("0.00"))])),
                ("status", models.CharField(choices=[("correct", "Correct"), ("incorrect", "Incorrect"), ("unanswered", "Unanswered"), ("invalid", "Invalid stored answer")], max_length=16)),
                ("validation_note", models.CharField(blank=True, max_length=200)),
                ("attempt_question", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="result_rows", to="attempts.attemptquestion")),
                ("result", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="questions", to="results.result")),
            ],
            options={"ordering": ("attempt_question__order", "id")},
        ),
        migrations.AddConstraint(model_name="result", constraint=models.CheckConstraint(condition=models.Q(("total_marks__gte", 0)), name="result_total_nonnegative")),
        migrations.AddConstraint(model_name="result", constraint=models.CheckConstraint(condition=models.Q(("marks_obtained__gte", 0)), name="result_obtained_nonnegative")),
        migrations.AddConstraint(model_name="result", constraint=models.CheckConstraint(condition=models.Q(("marks_obtained__lte", models.F("total_marks"))), name="result_obtained_lte_total")),
        migrations.AddConstraint(model_name="result", constraint=models.CheckConstraint(condition=models.Q(("pass_mark__gte", 0)), name="result_passmark_nonnegative")),
        migrations.AddConstraint(model_name="resultquestion", constraint=models.UniqueConstraint(fields=("result", "attempt_question"), name="unique_result_attempt_question")),
        migrations.AddConstraint(model_name="resultquestion", constraint=models.CheckConstraint(condition=models.Q(("marks_available__gte", 0)), name="result_q_available_nonnegative")),
        migrations.AddConstraint(model_name="resultquestion", constraint=models.CheckConstraint(condition=models.Q(("marks_obtained__gte", 0)), name="result_q_obtained_nonnegative")),
        migrations.AddConstraint(model_name="resultquestion", constraint=models.CheckConstraint(condition=models.Q(("marks_obtained__lte", models.F("marks_available"))), name="result_q_obtained_lte_available")),
        migrations.AddIndex(model_name="result", index=models.Index(fields=["institution", "status"], name="result_tenant_status_idx")),
        migrations.AddIndex(model_name="result", index=models.Index(fields=["candidate", "assessment"], name="result_candidate_assess_idx")),
        migrations.AddIndex(model_name="result", index=models.Index(fields=["published_at"], name="result_published_idx")),
    ]
