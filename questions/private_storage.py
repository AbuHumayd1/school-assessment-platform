from pathlib import Path
from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.utils.deconstruct import deconstructible


@deconstructible
class QuestionPrivateStorage(FileSystemStorage):
    """No public URL. Production can replace this backend with private object storage."""
    def __init__(self):
        super().__init__(location=getattr(settings, 'QUESTION_PRIVATE_ROOT', Path(settings.BASE_DIR) / 'private-question-media'))

    def url(self, name):
        raise ValueError('Question media requires an authorized API request.')


private_storage = QuestionPrivateStorage()
