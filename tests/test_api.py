import base64
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.main import create_app


class LedgerAPITests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        database_path = Path(self.temp_dir.name) / "test-ledger.sqlite3"
        self.client = TestClient(create_app(database_path))
        self.client.__enter__()
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
        self.assertEqual(self.client.get("/ledger").json(), {"customers": []})

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

    def test_clarification_is_spoken_and_not_staged(self):
        from backend.parser import ParserClarification

        self.parse.side_effect = ParserClarification("How much did Ramesh pay?")
        response = self.client.post(
            "/voice",
            files={"audio": ("recording.wav", b"audio bytes", "audio/wav")},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "clarification_required")
        self.assertEqual(
            response.json()["clarification_question"],
            "How much did Ramesh pay?",
        )
        self.speak.assert_called_once_with("How much did Ramesh pay?", "hi-en")
        self.assertEqual(self.client.get("/ledger").json(), {"customers": []})

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
        self.assertEqual(self.client.get("/ledger").json(), {"customers": []})

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
        reminder = self.client.post("/remind/Ramesh")
        self.assertEqual(customer.json()["balance"], 500)
        self.assertEqual(len(customer.json()["transactions"]), 1)
        self.assertEqual(reminder.json()["balance"], 500)
        self.assertIn("500 rupees", reminder.json()["reminder_text"])

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
        script = self.client.get("/frontend/app.js")
        stylesheet = self.client.get("/frontend/styles.css")

        self.assertEqual(page.status_code, 200)
        self.assertIn("Awaaz Khata", page.text)
        self.assertIn('id="splash-screen"', page.text)
        self.assertEqual(script.status_code, 200)
        self.assertIn("MediaRecorder", script.text)
        self.assertIn('classList.add("is-dismissed")', script.text)
        self.assertEqual(stylesheet.status_code, 200)
        self.assertIn("Noto Sans Devanagari", stylesheet.text)
        self.assertIn(".splash-screen", stylesheet.text)


if __name__ == "__main__":
    unittest.main()
