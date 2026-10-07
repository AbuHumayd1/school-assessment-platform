import uuid

import django.db.models.deletion
from django.db import migrations, models


def initialize_revisions(apps, schema_editor):
    Question = apps.get_model('questions', 'Question')
    AttemptQuestion = apps.get_model('attempts', 'AttemptQuestion')
    using = schema_editor.connection.alias
    used = set(AttemptQuestion.objects.using(using).values_list('question_id', flat=True))
    for row in Question.objects.using(using).only('pk', 'status').iterator(chunk_size=500):
        Question.objects.using(using).filter(pk=row.pk).update(
            revision_family=uuid.uuid4(), revision_number=1,
            content_locked=row.status in {'approved', 'archived'} or row.pk in used,
            available_for_new_assessments=row.status != 'archived')


class Migration(migrations.Migration):
    dependencies = [
        ('questions', '0003_alter_questionmedia_import_session_and_more'),
        ('attempts', '0002_attempt_passmark_snapshot_attemptquestion_marks_available'),
    ]
    operations = [
        migrations.AddField(model_name='question', name='revision_family', field=models.UUIDField(null=True, editable=False)),
        migrations.AddField(model_name='question', name='revision_number', field=models.PositiveIntegerField(default=1, editable=False)),
        migrations.AddField(model_name='question', name='content_locked', field=models.BooleanField(default=False, editable=False)),
        migrations.AddField(model_name='question', name='available_for_new_assessments', field=models.BooleanField(default=True, editable=False)),
        migrations.RunPython(initialize_revisions, migrations.RunPython.noop),
        migrations.AlterField(model_name='question', name='revision_family', field=models.UUIDField(default=uuid.uuid4, editable=False)),
        migrations.AddConstraint(model_name='question', constraint=models.UniqueConstraint(fields=('revision_family', 'revision_number'), name='unique_question_family_revision')),
        migrations.AddConstraint(model_name='question', constraint=models.CheckConstraint(condition=models.Q(revision_number__gte=1), name='question_revision_positive')),
        migrations.AddConstraint(model_name='question', constraint=models.CheckConstraint(condition=models.Q(content_locked=True) | ~models.Q(status__in=['approved', 'archived']), name='question_approved_content_locked')),
        migrations.AlterField(model_name='question', name='institution', field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='questions', to='institutions.institution')),
        migrations.AlterField(model_name='question', name='subject', field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='questions', to='subjects.subject')),
        migrations.AlterField(model_name='question', name='topic', field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='questions', to='questions.topic')),
    ]
