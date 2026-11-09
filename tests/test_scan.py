from io import BytesIO
from pathlib import Path
import sqlite3
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch
import os

from fastapi.testclient import TestClient
from PIL import Image

from backend.database import create_customer
from backend.main import create_app
from backend.parser import GeminiProvider, ScanResult, ScanRow


def make_test_image(width: int = 100, height: int = 100, fmt: str = "PNG") -> bytes:
    image = Image.new("RGB", (width, height), color=(240, 240, 240))
    buffer = BytesIO()
    image.save(buffer, format=fmt)
    return buffer.getvalue()


class ScanNotebookTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.database_path = Path(self.temp_dir.name) / "scan-test.sqlite3"
        self.client = TestClient(create_app(self.database_path))
        self.client.__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)
        self.addCleanup(self.temp_dir.cleanup)

        # Register shop
        registered = self.client.post(
            "/api/register",
            json={
                "shop_name": "Sharma Kirana",
                "owner_name": "Sharma Ji",
                "phone": "9876543210",
                "pin": "1234",
                "language": "hi-en",
                "upi_id": "",
            },
        )
        self.assertEqual(registered.status_code, 201)
        self.shop_id = registered.json()["shop"]["id"]

        # Add one existing customer
        self.existing_customer = create_customer(
            self.database_path,
            self.shop_id,
            "Ramesh Sharma",
            preferred_language="hi-en",
        )

    def test_scan_notebook_requires_login(self):
        unauth_client = TestClient(create_app(self.database_path))
        with unauth_client:
            image_bytes = make_test_image()
            response = unauth_client.post(
                "/scan-notebook",
                files={"image": ("notebook.png", image_bytes, "image/png")},
            )
            self.assertEqual(response.status_code, 401)

    @patch("backend.main.scan_notebook_image")
    def test_valid_rows_become_drafts_with_customer_matching(self, mock_scan):
        mock_scan.return_value = ScanResult(
            rows=[
                ScanRow(
                    person="Ramesh Sharma",
                    amount=500.0,
                    type="credit_given",
                    note="Udhaar ration",
                    date="2026-11-01",
                    confidence="high",
                ),
                ScanRow(
                    person="Suresh Verma",
                    amount=250.0,
                    type="payment_received",
                    note="Jama cash",
                    date="2026-11-02",
                    confidence="low",
                ),
            ]
        )

        image_bytes = make_test_image()
        response = self.client.post(
            "/scan-notebook",
            files={"image": ("khata.png", image_bytes, "image/png")},
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "success")
        drafts = data["drafts"]
        self.assertEqual(len(drafts), 2)

        # First row matched existing customer Ramesh Sharma
        self.assertEqual(drafts[0]["person"], "Ramesh Sharma")
        self.assertEqual(drafts[0]["amount"], 500.0)
        self.assertEqual(drafts[0]["type"], "credit_given")
        self.assertEqual(drafts[0]["matched_customer_id"], self.existing_customer["id"])
        self.assertFalse(drafts[0]["is_new_customer"])
        self.assertEqual(drafts[0]["confidence"], "high")

        # Second row is a new customer
        self.assertEqual(drafts[1]["person"], "Suresh Verma")
        self.assertEqual(drafts[1]["amount"], 250.0)
        self.assertEqual(drafts[1]["type"], "payment_received")
        self.assertIsNone(drafts[1]["matched_customer_id"])
        self.assertTrue(drafts[1]["is_new_customer"])
        self.assertEqual(drafts[1]["confidence"], "low")

    @patch("backend.main.scan_notebook_image")
    def test_zero_or_negative_amount_is_rejected(self, mock_scan):
        # ScanRow model_validator rejects amounts that are not positive.
        with self.assertRaises(ValueError):
            ScanRow(
                person="Mohan",
                amount=0.0,
                type="credit_given",
                note="bad amount",
            )

        with self.assertRaises(ValueError):
            ScanRow(
                person="Mohan",
                amount=-100.0,
                type="credit_given",
                note="bad amount",
            )

        # Parser errors are returned to the frontend instead of looking like no rows.
        from backend.parser import ParserError
        mock_scan.side_effect = ParserError("Gemini returned invalid scan JSON: amount must be greater than zero")

        image_bytes = make_test_image()
        response = self.client.post(
            "/scan-notebook",
            files={"image": ("khata.png", image_bytes, "image/png")},
        )
        self.assertEqual(response.status_code, 502)
        self.assertIn("amount must be greater than zero", response.json()["detail"])

    @patch("backend.main.scan_notebook_image")
    def test_unmatched_rows_are_kept_even_with_low_confidence_or_missing_name(self, mock_scan):
        mock_scan.return_value = ScanResult(
            rows=[
                ScanRow(person="", amount=75.0, confidence="low"),
                ScanRow(person="No amount", amount=10.0),
            ]
        )

        response = self.client.post(
            "/scan-notebook",
            files={"image": ("khata.png", make_test_image(), "image/png")},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()["drafts"]), 2)
        self.assertEqual(response.json()["drafts"][0]["person"], "")
        self.assertIsNone(response.json()["drafts"][0]["matched_customer_id"])

    def test_gemini_scan_sends_nonempty_image_and_drops_only_missing_amounts(self):
        request = {}

        class FakePart:
            @staticmethod
            def from_bytes(*, data, mime_type):
                return {"data": data, "mime_type": mime_type}

        def generate_content(**kwargs):
            request.update(kwargs)
            return SimpleNamespace(
                text=(
                    '{"rows":[{"person":"A","amount":25,"type":"credit_given",'
                    '"confidence":"low"},{"person":"B","type":"payment_received"}]}'
                )
            )

        provider = GeminiProvider.__new__(GeminiProvider)
        provider._client = SimpleNamespace(
            models=SimpleNamespace(generate_content=generate_content)
        )
        provider._types = SimpleNamespace(
            Part=FakePart,
            GenerateContentConfig=lambda **kwargs: kwargs,
        )
        provider._model = "gemini-3-flash-preview"

        result = provider.scan_notebook(b"image bytes", mime_type="image/png")

        self.assertEqual(len(result.rows), 1)
        self.assertEqual(result.rows[0].confidence, "low")
        image_part = request["contents"][1]
        self.assertEqual(image_part, {"data": b"image bytes", "mime_type": "image/png"})

        def schema_keys(value):
            if isinstance(value, dict):
                return set(value).union(*(schema_keys(item) for item in value.values()))
            if isinstance(value, list):
                return set().union(*(schema_keys(item) for item in value))
            return set()

        self.assertFalse(
            schema_keys(request["config"]["response_schema"])
            & {"gt", "ge", "lt", "le", "exclusiveMinimum"}
        )

    @patch.dict(os.environ, {"GEMINI_API_KEY": "test-key", "SCAN_MODEL": "gemini-3-flash-preview"})
    @patch("backend.parser.GeminiProvider")
    def test_scan_uses_scan_model_with_60_second_timeout(self, mock_provider):
        mock_provider.return_value.scan_notebook.return_value = ScanResult(rows=[])

        from backend.parser import scan_notebook_image
        scan_notebook_image(b"image bytes")

        mock_provider.assert_called_once_with(
            "test-key",
            "gemini-3-flash-preview",
            60,
        )

    def test_oversized_upload_returns_error(self):
        # 8 MB + 1 byte
        oversized_data = b"x" * (8 * 1024 * 1024 + 1)
        response = self.client.post(
            "/scan-notebook",
            files={"image": ("large.png", oversized_data, "image/png")},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("exceeds 8 MB", response.json()["detail"])

    def test_non_image_upload_returns_error(self):
        fake_data = b"This is not a real image file."
        response = self.client.post(
            "/scan-notebook",
            files={"image": ("not_an_image.txt", fake_data, "text/plain")},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("not a valid image", response.json()["detail"])

    @patch("backend.main.scan_notebook_image")
    def test_nothing_is_written_to_database_by_scan_notebook(self, mock_scan):
        mock_scan.return_value = ScanResult(
            rows=[
                ScanRow(
                    person="New Customer",
                    amount=1200.0,
                    type="credit_given",
                    note="Ghee and oil",
                    date="2026-11-03",
                    confidence="high",
                )
            ]
        )

        with sqlite3.connect(self.database_path) as conn:
            customers_before = conn.execute("SELECT count(*) FROM customers").fetchone()[0]
            tx_before = conn.execute("SELECT count(*) FROM transactions").fetchone()[0]
            pending_before = conn.execute("SELECT count(*) FROM pending_confirmations").fetchone()[0]

        image_bytes = make_test_image()
        response = self.client.post(
            "/scan-notebook",
            files={"image": ("khata.png", image_bytes, "image/png")},
        )
        self.assertEqual(response.status_code, 200)

        with sqlite3.connect(self.database_path) as conn:
            customers_after = conn.execute("SELECT count(*) FROM customers").fetchone()[0]
            tx_after = conn.execute("SELECT count(*) FROM transactions").fetchone()[0]
            pending_after = conn.execute("SELECT count(*) FROM pending_confirmations").fetchone()[0]

        self.assertEqual(customers_before, customers_after)
        self.assertEqual(tx_before, tx_after)
        self.assertEqual(pending_before, pending_after)

    @patch("backend.main.scan_notebook_image")
    def test_large_image_is_resized_and_converted_to_jpeg_before_gemini_call(self, mock_scan):
        mock_scan.return_value = ScanResult(
            rows=[
                ScanRow(
                    person="Ramesh Sharma",
                    amount=300.0,
                    type="credit_given",
                    note="Biscuits",
                    date=None,
                    confidence="high",
                )
            ]
        )

        # 2400 x 1800 image
        large_image = make_test_image(width=2400, height=1800, fmt="JPEG")
        response = self.client.post(
            "/scan-notebook",
            files={"image": ("large_khata.jpg", large_image, "image/jpeg")},
        )
        self.assertEqual(response.status_code, 200)

        # Inspect bytes sent to scan_notebook_image
        self.assertTrue(mock_scan.called)
        sent_bytes, _ = mock_scan.call_args[0] if len(mock_scan.call_args[0]) >= 2 else (mock_scan.call_args[0][0], None)
        opened = Image.open(BytesIO(sent_bytes))
        self.assertEqual(opened.format, "JPEG")
        self.assertLessEqual(max(opened.width, opened.height), 1280)
        self.assertEqual(mock_scan.call_args.kwargs["mime_type"], "image/jpeg")

    @patch("backend.main.scan_notebook_image")
    def test_confirm_flow_saves_scanned_entries_to_ledger(self, mock_scan):
        mock_scan.return_value = ScanResult(
            rows=[
                ScanRow(
                    person="Brand New Person",
                    amount=850.0,
                    type="credit_given",
                    note="Scan entry note",
                    date=None,
                    confidence="high",
                )
            ]
        )

        image_bytes = make_test_image()
        scan_response = self.client.post(
            "/scan-notebook",
            files={"image": ("khata.png", image_bytes, "image/png")},
        )
        drafts = scan_response.json()["drafts"]

        # Confirm using confirm flow
        confirm_response = self.client.post(
            "/confirm",
            json={
                "confirmation_id": "scan-abc-123",
                "confirmed": True,
                "entries": [
                    {
                        "person": drafts[0]["person"],
                        "amount": drafts[0]["amount"],
                        "type": drafts[0]["type"],
                        "note": drafts[0]["note"],
                    }
                ],
            },
        )
        self.assertEqual(confirm_response.status_code, 200)
        self.assertTrue(confirm_response.json()["saved"])

        # Check that the new customer was created and the transaction saved
        with sqlite3.connect(self.database_path) as conn:
            conn.row_factory = sqlite3.Row
            customer = conn.execute(
                "SELECT * FROM customers WHERE name = 'Brand New Person'"
            ).fetchone()
            self.assertIsNotNone(customer)
            tx = conn.execute(
                "SELECT * FROM transactions WHERE customer_id = ?",
                (customer["id"],),
            ).fetchone()
            self.assertIsNotNone(tx)
            self.assertEqual(tx["amount"], 850.0)
            self.assertEqual(tx["type"], "credit_given")


if __name__ == "__main__":
    unittest.main()
