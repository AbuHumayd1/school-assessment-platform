import os
from pathlib import Path
import runpy
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from .private_storage import QuestionPrivateStorage


class QuestionPrivateStorageTests(SimpleTestCase):
    def base_settings(self, value=None):
        with patch.dict(os.environ):
            if value is None:
                os.environ.pop("QUESTION_PRIVATE_ROOT", None)
            else:
                os.environ["QUESTION_PRIVATE_ROOT"] = value
            # Test the environment directly, independently of the local .env.
            with patch("dotenv.load_dotenv"):
                return runpy.run_module("config.settings.base")

    def test_absent_environment_uses_local_default(self):
        values = self.base_settings()
        self.assertEqual(values["QUESTION_PRIVATE_ROOT"], values["BASE_DIR"] / "private-question-media")

    def test_configured_environment_is_used_by_filesystem_storage(self):
        root = Path(__file__).resolve().parent / "configured-private-media"
        values = self.base_settings(str(root))
        self.assertEqual(values["QUESTION_PRIVATE_ROOT"], root)
        with override_settings(QUESTION_PRIVATE_ROOT=values["QUESTION_PRIVATE_ROOT"]):
            self.assertEqual(Path(QuestionPrivateStorage().location), root)

    def test_blank_environment_uses_local_default(self):
        for value in ("", "   "):
            with self.subTest(value=value):
                values = self.base_settings(value)
                self.assertEqual(values["QUESTION_PRIVATE_ROOT"], values["BASE_DIR"] / "private-question-media")

    def test_public_url_generation_is_refused(self):
        with self.assertRaisesMessage(ValueError, "Question media requires an authorized API request."):
            QuestionPrivateStorage().url("question/example.png")
