import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('questions', '0004_question_revision_identity'), ('subjects', '0002_content_ownership')]
    operations = [
        migrations.AddField(model_name='topic', name='owner_scope', field=models.CharField(choices=[('institution', 'Institution'), ('platform', 'Platform')], default='institution', max_length=16)),
        migrations.AddField(model_name='question', name='owner_scope', field=models.CharField(choices=[('institution', 'Institution'), ('platform', 'Platform')], default='institution', max_length=16)),
        migrations.AlterField(model_name='topic', name='institution', field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='topics', to='institutions.institution')),
        migrations.AlterField(model_name='question', name='institution', field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='questions', to='institutions.institution')),
        migrations.AddConstraint(model_name='topic', constraint=models.CheckConstraint(condition=(models.Q(owner_scope='institution', institution__isnull=False) | models.Q(owner_scope='platform', institution__isnull=True)), name='topic_owner_shape')),
        migrations.AddConstraint(model_name='question', constraint=models.CheckConstraint(condition=(models.Q(owner_scope='institution', institution__isnull=False) | models.Q(owner_scope='platform', institution__isnull=True)), name='question_owner_shape')),
        migrations.AddConstraint(model_name='topic', constraint=models.UniqueConstraint(fields=('subject', 'name'), name='unique_topic_name_per_owner_subject')),
    ]
