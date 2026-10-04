from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from questions.models import DocxImportSession


class Command(BaseCommand):
    help = 'Remove expired DOCX preview state and unpromoted private files. Schedule hourly.'

    def handle(self, **options):
        count = 0
        for pk in DocxImportSession.objects.filter(expires_at__lte=timezone.now()).values_list('pk', flat=True).iterator():
            with transaction.atomic():
                session = DocxImportSession.objects.select_for_update().filter(pk=pk, expires_at__lte=timezone.now()).first()
                if not session: continue
                session.delete()
                count += 1
        self.stdout.write(f'Removed {count} expired import sessions.')
