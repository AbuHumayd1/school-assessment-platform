import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('subjects', '0001_initial')]
    operations = [
        migrations.AddField(model_name='subject', name='owner_scope', field=models.CharField(choices=[('institution', 'Institution'), ('platform', 'Platform')], default='institution', max_length=16)),
        migrations.AddField(model_name='subject', name='platform_code', field=models.CharField(blank=True, editable=False, max_length=64, null=True, unique=True)),
        migrations.AlterField(model_name='subject', name='institution', field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='subjects', to='institutions.institution')),
        migrations.AddConstraint(model_name='subject', constraint=models.CheckConstraint(condition=(models.Q(owner_scope='institution', institution__isnull=False) | models.Q(owner_scope='platform', institution__isnull=True)), name='subject_owner_shape')),
        migrations.AddConstraint(model_name='subject', constraint=models.CheckConstraint(condition=(models.Q(owner_scope='institution', platform_code__isnull=True) | models.Q(owner_scope='platform', platform_code__isnull=False, platform_code=models.F('code'))), name='subject_platform_code_shape')),
    ]
