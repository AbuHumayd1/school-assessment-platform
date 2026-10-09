import os
from urllib.parse import urlsplit
from django.core.exceptions import ImproperlyConfigured


def environment_origins(name):
    origins = []
    for value in os.getenv(name, "").split(","):
        origin = value.strip()
        if not origin:
            continue
        try:
            parts = urlsplit(origin)
            valid = (parts.scheme in {"http", "https"} and parts.hostname and
                     not parts.username and not parts.password and not parts.path and
                     not parts.query and not parts.fragment and "*" not in origin)
            parts.port
        except ValueError:
            valid = False
        if not valid:
            raise ImproperlyConfigured(f"{name} must contain explicit http(s) origins without paths or wildcards.")
        if origin not in origins:
            origins.append(origin)
    return origins
