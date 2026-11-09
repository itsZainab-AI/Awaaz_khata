import base64
from pathlib import Path
import tempfile
from urllib.parse import parse_qs, urlparse
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
import uharfbuzz

from backend.database import create_customer
from backend.gnani_client import AUTO_LANGUAGE, TranscriptionResult
from backend.languages import LANGUAGES, get_template
from backend.main import _PDF_SCRIPT_FONTS, _pdf_export, _pdf_markup, create_app
from reportlab.pdfbase import pdfmetrics


class LedgerAPITests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp_dir.name) / "test-ledger.sqlite3"
        self.client = TestClient(create_app(self.database_path))
        self.client.__enter__()
        registered = self.client.post(
            "/api/register",
            json={
                "shop_name": "Test Kirana",
                "owner_name": "Test Owner",
                "phone": "9876543210",
                "pin": "1234",
                "language": "hi-en",
                "upi_id": "",
            },
        )
        self.assertEqual(registered.status_code, 201)
        self.shop_id = registered.json()["shop"]["id"]
        self.transcribe = patch(
            "backend.main.transcribe",
            return_value="Ramesh ko paanch sau udhaar diya",
        ).start()
        self.parse = patch(
            "backend.main.parse_transactions",
            return_value=[
                {
                    "person": "Ramesh",
                    "amount": 500,
                    "type": "credit_given",
                    "note": "udhaar diya",
                }
            ],
        ).start()
        self.speak = patch(
            "backend.main.speak",
            return_value=b"spoken audio",
        ).start()
        self.addCleanup(patch.stopall)
        self.addCleanup(self.client.__exit__, None, None, None)
        self.addCleanup(self.temp_dir.cleanup)

    def test_voice_stages_entries_then_confirm_saves_them(self):
        response = self.client.post(
            "/voice",
            files={"audio": ("recording.wav", b"audio bytes", "audio/wav")},
        )

        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertEqual(result["status"], "confirmation_required")
        self.assertEqual(result["entries"][0]["person"], "Ramesh")
        self.assertEqual(base64.b64decode(result["audio_base64"]), b"spoken audio")
        self.assertEqual(
            self.client.get("/ledger").json(),
            {
                "customers": [],
                "summary": {"credit": 0, "paid": 0, "transaction_count": 0},
            },
        )

        confirmed = self.client.post(
            "/confirm",
            json={"confirmation_id": result["confirmation_id"], "confirmed": True},
        )
        self.assertEqual(confirmed.status_code, 200)
        self.assertTrue(confirmed.json()["saved"])
        self.assertEqual(confirmed.json()["status"], "saved")
        self.assertEqual(self.client.get("/ledger").json()["customers"][0]["balance"], 500)

        repeated = self.client.post(
            "/confirm",
            json={"confirmation_id": result["confirmation_id"], "confirmed": True},
        )
        self.assertEqual(repeated.status_code, 404)

    def test_languages_endpoint_returns_registry_languages(self):
        response = self.client.get("/api/languages")

        self.assertEqual(response.status_code, 200)
        languages = response.json()
        self.assertEqual({item["code"] for item in languages}, set(LANGUAGES))
        self.assertTrue(all({"label", "native_label"} <= set(item) for item in languages))
        self.assertTrue(all({"stt_code", "tts_code"} <= set(item) for item in languages))
        for language in languages:
            config = LANGUAGES[language["code"]]
            self.assertEqual(language["stt_code"], config["stt_code"])
            self.assertEqual(language["tts_code"], config["tts_code"])

    def test_voice_uses_registry_stt_code_for_selected_language(self):
        response = self.client.post(
            "/voice",
            files={"audio": ("recording.wav", b"audio bytes", "audio/wav")},
            data={"language": "hi-en", "speech_language": "hi-en"},
        )

        self.assertEqual(response.status_code, 200)
        self.transcribe.assert_called_once_with(b"audio bytes", language_hint="hi-IN")

    def test_marathi_voice_uses_rule_fallback_after_gemini_failure(self):
        from backend.parser import parse_fallback

        self.transcribe.return_value = "रमेशला 500 रुपये उधार दिले."
        with patch(
            "backend.main.parse_transactions",
            side_effect=lambda transcript, **kwargs: parse_fallback(transcript),
        ) as parse:
            response = self.client.post(
                "/voice",
                files={"audio": ("recording.wav", b"audio bytes", "audio/wav")},
                data={"language": "mr-IN", "speech_language": "mr-IN"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "confirmation_required")
        self.assertEqual(response.json()["entries"][0]["person"], "रमेश")
        self.assertEqual(response.json()["entries"][0]["amount"], 500)
        parse.assert_called_once_with(
            "रमेशला 500 रुपये उधार दिले.",
            shop_id=self.shop_id,
            language="mr-IN",
        )

    def test_auto_voice_uses_detected_language_for_speech_and_returns_it(self):
        self.transcribe.return_value = TranscriptionResult(
            "ரமேஷ் கணக்கில் எவ்வளவு பாக்கி இருக்கிறது?",
            "ta-IN",
        )
        with patch(
            "backend.main.parse_query_intent_for_language",
            return_value=None,
        ) as classify_query:
            response = self.client.post(
                "/voice",
                files={"audio": ("recording.wav", b"audio bytes", "audio/wav")},
                data={"language": "auto", "speech_language": "auto"},
            )

        self.assertEqual(response.status_code, 200)
        self.transcribe.assert_called_once_with(
            b"audio bytes",
            language_hint=AUTO_LANGUAGE,
        )
        classify_query.assert_called_once_with(
            "ரமேஷ் கணக்கில் எவ்வளவு பாக்கி இருக்கிறது?",
            "ta-IN",
        )
        self.speak.assert_called_once()
        self.assertEqual(self.speak.call_args.args[1], "ta-IN")
        self.assertEqual(
            response.json()["detected_language"],
            {"code": "ta-IN", "label": "Tamil", "native_label": "தமிழ்"},
        )

    def test_manual_language_remains_tts_override_when_detection_differs(self):
        self.transcribe.return_value = TranscriptionResult(
            "ரமேஷ் கணக்கில் எவ்வளவு பாக்கி இருக்கிறது?",
            "ta-IN",
        )
        with patch("backend.main.parse_query_intent_for_language", return_value=None):
            response = self.client.post(
                "/voice",
                files={"audio": ("recording.wav", b"audio bytes", "audio/wav")},
                data={"language": "hi-IN", "speech_language": "hi-en"},
            )

        self.assertEqual(response.status_code, 200)
        self.speak.assert_called_once()
        self.assertEqual(self.speak.call_args.args[1], "hi-en")
        self.assertEqual(response.json()["detected_language"]["code"], "ta-IN")

    def test_voice_uses_provider_query_classifier_for_non_local_language(self):
        self.transcribe.return_value = "ரமேஷ் கணக்கில் எவ்வளவு பாக்கி இருக்கிறது?"
        with patch(
            "backend.main.parse_query_intent_for_language",
            return_value=None,
        ) as classify_query:
            response = self.client.post(
                "/voice",
                files={"audio": ("recording.wav", b"audio bytes", "audio/wav")},
                data={"language": "ta-IN", "speech_language": "ta-IN"},
            )

        self.assertEqual(response.status_code, 200)
        classify_query.assert_called_once_with(
            "ரமேஷ் கணக்கில் எவ்வளவு பாக்கி இருக்கிறது?",
            "ta-IN",
        )

    def test_voice_suggests_and_confirms_transliterated_customer_match(self):
        create_customer(self.database_path, self.shop_id, "Ramesh")
        self.transcribe.return_value = "ரமேஷ் ஐநூறு ரூபாய் கடனாக கொடுத்தேன்"
        self.parse.return_value = [
            {
                "person": "ரமேஷ்",
                "normalized_person": "Ramesh",
                "amount": 500,
                "type": "credit_given",
                "note": "கடனாக கொடுத்தேன்",
            }
        ]
        with patch("backend.main.parse_query_intent_for_language", return_value=None):
            staged = self.client.post(
                "/voice",
                files={"audio": ("recording.wav", b"audio bytes", "audio/wav")},
                data={"language": "ta-IN", "speech_language": "ta-IN"},
            )

        self.assertEqual(staged.status_code, 200)
        entry = staged.json()["entries"][0]
        self.assertEqual(entry["person"], "Ramesh")
        self.assertEqual(entry["original_person"], "ரமேஷ்")
        self.assertEqual(entry["match_suggestion"], "Ramesh")

        confirmed = self.client.post(
            "/confirm",
            json={
                "confirmation_id": staged.json()["confirmation_id"],
                "confirmed": True,
            },
        )
        self.assertEqual(confirmed.status_code, 200)
        self.assertEqual(len(self.client.get("/ledger").json()["customers"]), 1)
        self.assertEqual(self.client.get("/customer/Ramesh").json()["balance"], 500)

    def test_voice_skips_speech_when_language_has_no_tts(self):
        language = {**LANGUAGES["hi-en"], "tts_available": False}
        with patch.dict(LANGUAGES, {"hi-en": language}):
            response = self.client.post(
                "/voice",
                files={"audio": ("recording.wav", b"audio bytes", "audio/wav")},
                data={"language": "hi-en", "speech_language": "hi-en"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("audio_base64", response.json())
        self.speak.assert_not_called()

    def test_edited_entries_are_saved_instead_of_original_parse(self):
        staged = self.client.post(
            "/voice",
            files={"audio": ("recording.wav", b"audio bytes", "audio/wav")},
        ).json()
        response = self.client.post(
            "/confirm",
            json={
                "confirmation_id": staged["confirmation_id"],
                "confirmed": True,
                "entries": [
                    {
                        "person": "Ramesh",
                        "amount": 450,
                        "type": "credit_given",
                        "note": "corrected amount",
                    }
                ],
            },
        )

        self.assertEqual(response.status_code, 200)
        customer = self.client.get("/customer/Ramesh").json()
        self.assertEqual(customer["balance"], 450)
        self.assertEqual(customer["transactions"][0]["note"], "corrected amount")

    def test_unrecognized_intent_is_spoken_and_not_staged(self):
        from backend.parser import ParserClarification

        self.parse.side_effect = ParserClarification("How much did Ramesh pay?")
        response = self.client.post(
            "/voice",
            files={"audio": ("recording.wav", b"audio bytes", "audio/wav")},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "unrecognized")
        self.assertEqual(
            response.json()["message"],
            get_template("hi-en", "samajh_nahi_aaya"),
        )
        self.speak.assert_called_once_with(
            get_template("hi-en", "samajh_nahi_aaya"),
            "hi-en",
        )
        self.assertEqual(
            self.client.get("/ledger").json()["summary"]["transaction_count"],
            0,
        )

    def test_create_customer_intent_creates_zero_balance_and_speaks(self):
        from backend.parser import parse_fallback

        self.transcribe.return_value = "Ramesh ke naam se khata banao"
        self.parse.side_effect = lambda transcript, **_: parse_fallback(transcript)
        response = self.client.post(
            "/voice",
            files={"audio": ("recording.wav", b"audio bytes", "audio/wav")},
        )

        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertEqual(result["status"], "customer_created")
        self.assertEqual(result["confirmation_text"], "Ramesh ka khata ban gaya")
        self.speak.assert_called_once_with("Ramesh ka khata ban gaya", "hi-en")
        self.assertEqual(self.client.get("/customer/Ramesh").json()["balance"], 0)
        self.assertEqual(self.client.get("/ledger").json()["customers"][0]["balance"], 0)

    def test_voice_example_endpoint_uses_timbre(self):
        response = self.client.get("/voice-example?speech_language=hi-en")

        self.assertEqual(response.status_code, 200)
        self.speak.assert_called_once_with("Ramesh ko 500 udhaar diya", "hi-en")
        self.assertEqual(base64.b64decode(response.json()["audio_base64"]), b"spoken audio")

    def test_empty_transcript_is_reported_and_spoken(self):
        self.transcribe.return_value = ""
        response = self.client.post(
            "/voice",
            files={"audio": ("recording.wav", b"audio bytes", "audio/wav")},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "unrecognized")
        self.speak.assert_called_once_with(
            get_template("hi-en", "samajh_nahi_aaya"),
            "hi-en",
        )
        self.parse.assert_not_called()

    def test_declining_confirmation_does_not_save(self):
        staged = self.client.post(
            "/voice",
            files={"audio": ("recording.wav", b"audio bytes", "audio/wav")},
        ).json()
        response = self.client.post(
            "/confirm",
            json={"confirmation_id": staged["confirmation_id"], "confirmed": False},
        )

        self.assertEqual(response.json()["status"], "cancelled")
        self.assertEqual(
            self.client.get("/ledger").json()["summary"]["transaction_count"],
            0,
        )

    def test_customer_detail_and_reminder_report_balance(self):
        staged = self.client.post(
            "/voice",
            files={"audio": ("recording.wav", b"audio bytes", "audio/wav")},
        ).json()
        self.client.post(
            "/confirm",
            json={"confirmation_id": staged["confirmation_id"], "confirmed": True},
        )

        customer = self.client.get("/customer/ramesh")
        self.client.patch(
            "/api/settings",
            json={"shop_name": "Test Kirana", "language": "hi-en", "upi_id": "test@upi"},
        )
        reminder = self.client.post("/remind/Ramesh")
        self.assertEqual(customer.json()["balance"], 500)
        self.assertEqual(len(customer.json()["transactions"]), 1)
        self.assertEqual(reminder.json()["balance"], 500)
        self.assertIn("500", reminder.json()["reminder_text"])
        self.assertIn("wa.me", reminder.json()["whatsapp_url"])
        self.assertEqual(
            parse_qs(urlparse(reminder.json()["upi_link"]).query)["am"],
            ["500.00"],
        )

    def test_customer_and_full_ledger_export_csv_and_pdf(self):
        staged = self.client.post(
            "/voice",
            files={"audio": ("recording.wav", b"audio bytes", "audio/wav")},
        ).json()
        self.client.post(
            "/confirm",
            json={"confirmation_id": staged["confirmation_id"], "confirmed": True},
        )

        customer_csv = self.client.get("/export/customer/Ramesh?format=csv")
        ledger_csv = self.client.get("/export/ledger?format=csv")
        self.assertEqual(customer_csv.status_code, 200)
        self.assertTrue(customer_csv.content.startswith(b"\xef\xbb\xbf"))
        self.assertIn(b"Ramesh", customer_csv.content)
        self.assertIn(b"Ramesh", ledger_csv.content)

        customer_pdf = self.client.get("/export/customer/Ramesh?format=pdf")
        ledger_pdf = self.client.get("/export/ledger?format=pdf")
        self.assertEqual(customer_pdf.status_code, 200, customer_pdf.text)
        self.assertEqual(ledger_pdf.status_code, 200, ledger_pdf.text)
        self.assertTrue(customer_pdf.content.startswith(b"%PDF"))
        self.assertTrue(ledger_pdf.content.startswith(b"%PDF"))

    def test_pdf_renders_customer_names_in_all_supported_scripts(self):
        names = {
            "devanagari": "रमेश",
            "tamil": "தமிழ்",
            "telugu": "తెలుగు",
            "gujarati": "ગુજરાતી",
            "bengali": "বাংলা",
            "kannada": "ಕನ್ನಡ",
            "malayalam": "മലയാളം",
            "gurmukhi": "ਪੰਜਾਬੀ",
        }
        rows = [
            ["Customer", "Type", "Amount", "Note", "Date"],
            *[
                [name, "credit_given", 500, "Customer ledger entry", "2026-11-09"]
                for name in names.values()
            ],
        ]
        pdf = _pdf_export("Multilingual customer names", rows)

        self.assertTrue(pdf.startswith(b"%PDF"))
        for script, name in names.items():
            with self.subTest(script=script):
                font_name = _PDF_SCRIPT_FONTS[script]
                self.assertIn(f'<font name="{font_name}">'.encode(), _pdf_markup(name).encode())
                font = pdfmetrics.getFont(font_name)
                self.assertTrue(font.shapable)
                buffer = uharfbuzz.Buffer()
                buffer.add_str(name)
                buffer.guess_segment_properties()
                uharfbuzz.shape(font.hbFont(12), buffer)
                self.assertTrue(buffer.glyph_infos)
                self.assertTrue(
                    all(glyph.codepoint != 0 for glyph in buffer.glyph_infos),
                    f"{script} produced a missing-glyph box",
                )

    def test_voice_balance_query_reads_ledger_and_speaks_answer(self):
        staged = self.client.post(
            "/voice",
            files={"audio": ("recording.wav", b"audio bytes", "audio/wav")},
        ).json()
        self.client.post(
            "/confirm",
            json={"confirmation_id": staged["confirmation_id"], "confirmed": True},
        )

        self.transcribe.return_value = "Ramesh ka kitna baaki hai?"
        self.parse.reset_mock()
        response = self.client.post(
            "/voice",
            files={"audio": ("recording.wav", b"question audio", "audio/wav")},
        )
        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertEqual(result["status"], "query_answer")
        self.assertEqual(
            result["answer"],
            get_template("hi-en", "owes_you", name="Ramesh", amount="₹500"),
        )
        self.parse.assert_not_called()
        self.speak.assert_called_with(result["answer"], "hi-en")

    def test_ledger_balance_subtracts_received_payments(self):
        self.parse.return_value = [
            {
                "person": "Ramesh",
                "amount": 500,
                "type": "credit_given",
                "note": "udhaar diya",
            },
            {
                "person": "Ramesh",
                "amount": 200,
                "type": "payment_received",
                "note": "payment received",
            },
        ]
        staged = self.client.post(
            "/voice",
            files={"audio": ("recording.wav", b"audio bytes", "audio/wav")},
        ).json()
        self.client.post(
            "/confirm",
            json={"confirmation_id": staged["confirmation_id"], "confirmed": True},
        )

        ledger = self.client.get("/ledger").json()
        self.assertEqual(ledger["customers"][0]["balance"], 300)
        self.assertEqual(
            ledger["summary"],
            {"credit": 500, "paid": 200, "transaction_count": 2},
        )

    def test_oversized_audio_is_rejected(self):
        from backend.main import MAX_AUDIO_BYTES

        response = self.client.post(
            "/voice",
            files={"audio": ("recording.wav", b"x" * (MAX_AUDIO_BYTES + 1), "audio/wav")},
        )

        self.assertEqual(response.status_code, 413)
        self.transcribe.assert_not_called()

    def test_frontend_is_served_by_fastapi(self):
        page = self.client.get("/")
        dashboard = self.client.get("/dashboard")
        script = self.client.get("/frontend/app.js")
        stylesheet = self.client.get("/frontend/styles.css")
        manifest = self.client.get("/frontend/manifest.webmanifest")
        service_worker = self.client.get("/service-worker.js")
        offline = self.client.get("/offline.html")

        self.assertEqual(page.status_code, 200)
        self.assertIn("Udhaar is easy to give", page.text)
        self.assertIn("Built with Gnani Prisma + Timbre", page.text)
        self.assertEqual(dashboard.status_code, 200)
        self.assertIn('id="splash-screen"', dashboard.text)
        self.assertEqual(dashboard.text.count('class="transcript-panel glass-card"'), 1)
        self.assertIn('class="summary-card glass-card" hidden', dashboard.text)
        self.assertIn('id="summary-stats" hidden', dashboard.text)
        self.assertIn("transliterateDevanagari", script.text)
        self.assertIn("data-play-example", script.text)
        self.assertIn("@media (max-width: 560px)", stylesheet.text)
        self.assertEqual(script.status_code, 200)
        self.assertIn("MediaRecorder", script.text)
        self.assertIn('classList.add("is-dismissed")', script.text)
        self.assertEqual(stylesheet.status_code, 200)
        self.assertIn("Noto Sans Devanagari", stylesheet.text)
        self.assertIn(".splash-screen", stylesheet.text)
        self.assertEqual(manifest.status_code, 200)
        self.assertEqual(service_worker.status_code, 200)
        self.assertEqual(service_worker.headers["Service-Worker-Allowed"], "/")
        self.assertIn("/api/", service_worker.text)
        self.assertIn("You’re offline", offline.text)


if __name__ == "__main__":
    unittest.main()
