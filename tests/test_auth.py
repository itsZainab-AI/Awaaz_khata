from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.main import create_app


def register(client: TestClient, phone: str, shop_name: str) -> dict:
    response = client.post(
        "/api/register",
        json={
            "shop_name": shop_name,
            "owner_name": "Owner",
            "phone": phone,
            "pin": "1234",
            "language": "hi-en",
            "upi_id": "",
        },
    )
    if response.status_code != 201:
        raise AssertionError(response.text)
    return response.json()["shop"]


class AuthAndIsolationTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp_dir.name) / "auth.sqlite3"
        self.app = create_app(self.database_path)
        self.client = TestClient(self.app)
        self.client.__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)
        self.addCleanup(self.temp_dir.cleanup)

    def test_private_routes_require_login_and_pin_hash_is_not_exposed(self):
        self.assertEqual(self.client.get("/ledger").status_code, 401)
        self.assertEqual(
            self.client.post(
                "/voice",
                files={"audio": ("voice.wav", b"audio", "audio/wav")},
            ).status_code,
            401,
        )
        shop = register(self.client, "9876543210", "Asha Stores")
        self.assertNotIn("pin", shop)
        cookie = self.client.cookies.get("awaaz_session")
        self.assertTrue(cookie)
        self.assertEqual(self.client.get("/api/me").json()["shop"]["id"], shop["id"])
        with sqlite3.connect(self.database_path) as connection:
            pin_hash = connection.execute(
                "SELECT pin_hash FROM shops WHERE id = ?", (shop["id"],)
            ).fetchone()[0]
        self.assertTrue(pin_hash.startswith("$2"))
        self.assertNotEqual(pin_hash, "1234")

    def test_session_cookie_is_http_only_and_same_site_strict(self):
        response = self.client.post(
            "/api/register",
            json={
                "shop_name": "Asha Stores",
                "owner_name": "Asha",
                "phone": "9876543210",
                "pin": "1234",
            },
        )
        cookie = response.headers["set-cookie"].lower()
        self.assertIn("httponly", cookie)
        self.assertIn("samesite=strict", cookie)

    def test_settings_are_scoped_and_account_deletion_removes_access(self):
        register(self.client, "9876543210", "Asha Stores")
        updated = self.client.patch(
            "/api/settings",
            json={
                "shop_name": "Asha Kirana",
                "language": "mr-IN",
                "upi_id": "asha@upi",
            },
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json()["shop"]["shop_name"], "Asha Kirana")
        self.assertEqual(updated.json()["shop"]["language"], "mr-IN")

        deleted = self.client.delete("/api/account")
        self.assertEqual(deleted.status_code, 204)
        self.assertEqual(self.client.get("/ledger").status_code, 401)

    def test_shops_cannot_read_each_others_customers_or_pending_confirmations(self):
        first_shop = register(self.client, "9876543210", "Asha Stores")
        with patch(
            "backend.main.transcribe",
            return_value="Ramesh ko paanch sau udhaar diya",
        ), patch(
            "backend.main.parse_transactions",
            return_value=[{
                "person": "Ramesh",
                "amount": 500,
                "type": "credit_given",
                "note": "udhaar diya",
            }],
        ), patch("backend.main.speak", return_value=b"speech"):
            staged = self.client.post(
                "/voice",
                files={"audio": ("voice.wav", b"audio", "audio/wav")},
            ).json()
        self.client.post(
            "/confirm",
            json={"confirmation_id": staged["confirmation_id"], "confirmed": True},
        )

        other_client = TestClient(self.app)
        other_client.__enter__()
        self.addCleanup(other_client.__exit__, None, None, None)
        second_shop = register(other_client, "9876543211", "Bharat Stores")

        self.assertNotEqual(first_shop["id"], second_shop["id"])
        self.assertEqual(other_client.get("/ledger").json()["customers"], [])
        self.assertEqual(other_client.get("/customer/Ramesh").status_code, 404)
        self.assertEqual(
            other_client.post(
                "/confirm",
                json={"confirmation_id": staged["confirmation_id"], "confirmed": True},
            ).status_code,
            404,
        )
        with patch(
            "backend.main.transcribe",
            return_value="Ramesh ka kitna baaki hai?",
        ), patch("backend.main.speak", return_value=b"speech"):
            query = other_client.post(
                "/voice",
                files={"audio": ("question.wav", b"audio", "audio/wav")},
            ).json()
        self.assertEqual(query["status"], "query_answer")
        self.assertIn("couldn't find", query["answer"])

    def test_fifth_failed_pin_attempt_locks_login_for_fifteen_minutes(self):
        register(self.client, "9876543210", "Asha Stores")
        login_client = TestClient(self.app)
        login_client.__enter__()
        self.addCleanup(login_client.__exit__, None, None, None)
        for attempt in range(5):
            response = login_client.post(
                "/api/login",
                json={"phone": "9876543210", "pin": "9999"},
            )
            self.assertEqual(response.status_code, 429 if attempt == 4 else 401)

        blocked = login_client.post(
            "/api/login",
            json={"phone": "9876543210", "pin": "1234"},
        )
        self.assertEqual(blocked.status_code, 429)
        self.assertGreater(int(blocked.headers["Retry-After"]), 0)
        self.assertLessEqual(int(blocked.headers["Retry-After"]), 900)

    def test_pin_length_validation_is_enforced(self):
        response = self.client.post(
            "/api/register",
            json={
                "shop_name": "Asha Stores",
                "owner_name": "Asha",
                "phone": "9876543210",
                "pin": "123",
                "language": "hi-en",
            },
        )
        self.assertEqual(response.status_code, 422)

    def test_demo_login_seeds_eight_customers_and_thirty_entries_then_resets(self):
        response = self.client.post("/api/demo-login")
        self.assertEqual(response.status_code, 200)
        ledger = self.client.get("/ledger").json()
        self.assertEqual(len(ledger["customers"]), 8)
        self.assertEqual(ledger["summary"]["transaction_count"], 30)

        with sqlite3.connect(self.database_path) as connection:
            connection.execute(
                "UPDATE transactions SET note = 'changed' WHERE shop_id = "
                "(SELECT id FROM shops WHERE is_demo = 1) LIMIT 1"
            )
            connection.execute(
                "UPDATE shops SET demo_reset_at = 0 WHERE is_demo = 1"
            )
        self.client.post("/api/demo-login")
        self.assertEqual(
            self.client.get("/ledger").json()["summary"]["transaction_count"],
            30,
        )
        with sqlite3.connect(self.database_path) as connection:
            notes = connection.execute(
                "SELECT note FROM transactions WHERE note = 'changed'"
            ).fetchall()
        self.assertEqual(notes, [])


if __name__ == "__main__":
    unittest.main()
