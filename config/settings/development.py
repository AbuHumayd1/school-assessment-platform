import os
from .base import *
from .origins import environment_origins

DEBUG = os.getenv("DJANGO_DEBUG", "True").lower() in {"1", "true", "yes"}
ALLOWED_HOSTS = ["localhost", "127.0.0.1"]
# Vite proxy remains supported; explicit origins also permit direct local API use.
CORS_ALLOWED_ORIGINS = environment_origins("DJANGO_CORS_ALLOWED_ORIGINS") or ["http://localhost:5173", "http://127.0.0.1:5173"]
CSRF_TRUSTED_ORIGINS = environment_origins("DJANGO_CSRF_TRUSTED_ORIGINS") or CORS_ALLOWED_ORIGINS
CORS_ALLOW_CREDENTIALS = True
