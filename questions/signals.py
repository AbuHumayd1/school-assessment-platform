from django.db import transaction
from django.db.models.signals import post_delete, pre_delete
from django.dispatch import receiver
from .models import Question, QuestionMedia, QuestionOption


@receiver(pre_delete, sender=Question)
@receiver(pre_delete, sender=QuestionOption)
@receiver(pre_delete, sender=QuestionMedia)
@receiver(pre_delete, sender='assessments.Assessment')
@receiver(pre_delete, sender='assessments.AssessmentQuestion')
def guard_integrity_cascade(sender, instance, **kwargs):
    # Django's deletion collector bypasses model/QuerySet delete on cascades.
    instance.validate_integrity_delete()


@receiver(pre_delete, sender='accounts.User')
def guard_reviewer_removal(sender, instance, **kwargs):
    from django.core.exceptions import ValidationError
    for question in Question.objects.select_for_update().filter(reviewed_by=instance).order_by('pk'):
        if question.is_content_immutable:
            raise ValidationError('The reviewer of an approved or participated revision cannot be removed.')


@receiver(pre_delete, sender='groups.Group')
def guard_assessment_group_removal(sender, instance, **kwargs):
    from assessments.models import Assessment
    for assessment in Assessment.objects.select_for_update().filter(group=instance).order_by('pk'):
        assessment.group = None
        assessment.validate_integrity()


@receiver(post_delete, sender=QuestionMedia)
def remove_private_file(sender, instance, **kwargs):
    storage, name = instance.file.storage, instance.file.name
    if name:
        def delete_unreferenced_file():
            if not QuestionMedia.objects.filter(file=name).exists():
                storage.delete(name)
        transaction.on_commit(delete_unreferenced_file)
