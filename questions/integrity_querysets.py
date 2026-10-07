"""Keep bulk ORM writes on the same validation boundary as individual writes."""
from django.core.exceptions import ValidationError
from django.db import models, transaction


class IntegrityQuerySet(models.QuerySet):
    def _rows(self):
        return self.model.objects.using(self.db).filter(pk__in=self.values('pk')).select_for_update().order_by('pk')

    def update(self, **kwargs):
        if any(hasattr(value, 'resolve_expression') for value in kwargs.values()):
            raise ValidationError('Expression updates are not supported for integrity-protected records.')
        with transaction.atomic(using=self.db):
            rows = list(self._rows())
            for row in rows:
                for name, value in kwargs.items():
                    field = self.model._meta.get_field(name)
                    setattr(row, field.attname, getattr(value, 'pk', value))
                row.save(using=self.db, update_fields=list(kwargs))
            return len(rows)

    def bulk_update(self, objs, fields, batch_size=None):
        objs = list(objs)
        with transaction.atomic(using=self.db):
            for obj in objs:
                obj.save(using=self.db, update_fields=fields)
            return len(objs)

    def bulk_create(self, objs, batch_size=None, **kwargs):
        if kwargs.get('ignore_conflicts') or kwargs.get('update_conflicts'):
            raise ValidationError('Conflict-skipping/upsert writes are not supported for integrity-protected records.')
        objs = list(objs)
        with transaction.atomic(using=self.db):
            for obj in objs:
                # Save also serializes revision families and applies lifecycle rules.
                obj.save(using=self.db, force_insert=True)
            return objs

    def delete(self):
        with transaction.atomic(using=self.db):
            for obj in self._rows():
                obj.validate_integrity_delete()
            return super().delete()
