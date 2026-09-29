import os
from .base import *

DEBUG = os.getenv("DJANGO_DEBUG", "True").lower() in {"1", "true", "yes"}
ALLOWED_HOSTS = ["localhost", "127.0.0.1"]
