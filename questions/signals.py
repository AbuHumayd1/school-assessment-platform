from django.db import transaction
from django.db.models.signals import post_delete
from django.dispatch import receiver
from .models import QuestionMedia


@receiver(post_delete, sender=QuestionMedia)
def remove_private_file(sender, instance, **kwargs):
    storage, name = instance.file.storage, instance.file.name
    if name:
        def delete_unreferenced_file():
            if not QuestionMedia.objects.filter(file=name).exists():
                storage.delete(name)
        transaction.on_commit(delete_unreferenced_file)
