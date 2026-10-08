import os
import runpy
from unittest.mock import patch

from django.conf import settings
from django.test import SimpleTestCase


class SelfServiceSettingsTests(SimpleTestCase):
    def test_flags_are_safe_by_default_and_require_explicit_truthy_values(self):
        names = ("MADAAR_PUBLIC_REGISTRATION_ENABLED", "MADAAR_PUBLIC_WORKSPACE_CREATION_ENABLED")
        for value, enabled in ((None, False), ("false", False), ("0", False), ("no", False),
                               ("unexpected", False), ("", False), (" TRUE ", True), ("1", True), ("yes", True)):
            with self.subTest(value=value), patch.dict(os.environ), patch("dotenv.load_dotenv"):
                for name in names:
                    if value is None:
                        os.environ.pop(name, None)
                    else:
                        os.environ[name] = value
                values = runpy.run_path(str(settings.BASE_DIR / "config/settings/base.py"))
                for name in names:
                    self.assertIs(values[name], enabled)
