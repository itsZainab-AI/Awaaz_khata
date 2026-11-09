from types import SimpleNamespace
import unittest
from unittest.mock import patch

from backend.languages import LANGUAGES, get_template
from backend.gnani_client import speak


LANGUAGE_CODES = {
    "hi-en",
    "hi-IN",
    "mr-IN",
    "ta-IN",
    "te-IN",
    "gu-IN",
    "bn-IN",
    "kn-IN",
    "ml-IN",
    "pa-IN",
    "en-IN",
}
STT_CODES = {
    "hi-IN",
    "mr-IN",
    "ta-IN",
    "te-IN",
    "gu-IN",
    "bn-IN",
    "kn-IN",
    "ml-IN",
    "pa-IN",
    "en-IN",
}
TTS_CODES = STT_CODES | {"hi-en"}
TEMPLATE_KEYS = {
    "customer_not_found",
    "owes_you",
    "you_owe",
    "settled",
    "today_credit",
    "no_unpaid",
    "unpaid_list",
    "reminder_due",
    "reminder_clear",
    "samajh_nahi_aaya",
}


class LanguageTemplateTests(unittest.TestCase):
    def test_registry_and_provider_codes_are_complete(self):
        self.assertEqual(set(LANGUAGES), LANGUAGE_CODES)
        self.assertEqual(
            {config["stt_code"] for config in LANGUAGES.values()},
            STT_CODES,
        )
        self.assertEqual(
            {config["tts_code"] for config in LANGUAGES.values()},
            TTS_CODES,
        )

    def test_every_language_defines_every_template(self):
        for language, config in LANGUAGES.items():
            with self.subTest(language=language):
                self.assertEqual(set(config["templates"]), TEMPLATE_KEYS)

    def test_templates_accept_the_shared_placeholder_values(self):
        values = {
            "name": "Ramesh",
            "amount": "₹500",
            "days": "30",
            "names": "Ramesh ₹500",
        }
        for language in LANGUAGES:
            for key in TEMPLATE_KEYS:
                with self.subTest(language=language, key=key):
                    self.assertTrue(get_template(language, key, **values))

    def test_missing_language_or_template_uses_hinglish(self):
        expected = LANGUAGES["hi-en"]["templates"]["customer_not_found"].format(
            name="Ramesh"
        )
        self.assertEqual(
            get_template("unsupported", "customer_not_found", name="Ramesh"),
            expected,
        )
        incomplete_language = {**LANGUAGES["hi-IN"], "templates": {}}
        with patch.dict(LANGUAGES, {"hi-IN": incomplete_language}):
            self.assertEqual(
                get_template("hi-IN", "customer_not_found", name="Ramesh"),
                expected,
            )

    def test_timbre_uses_each_language_code_and_voice(self):
        response = SimpleNamespace(
            content=b"audio",
            headers={"Content-Type": "audio/mpeg"},
        )
        with patch("backend.gnani_client._post", return_value=response) as post:
            for code, config in LANGUAGES.items():
                with self.subTest(language=code):
                    speak("Khata update", code)
                    payload = post.call_args.kwargs["json"]
                    self.assertEqual(payload["language"], config["tts_code"])
                    self.assertEqual(payload["voice"], config["tts_voice"])


if __name__ == "__main__":
    unittest.main()
