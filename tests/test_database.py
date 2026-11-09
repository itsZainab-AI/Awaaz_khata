from pathlib import Path
import sqlite3
import tempfile
import unittest

from backend.database import (
    get_customer,
    get_ledger,
    get_ledger_summary,
    initialize_database,
)


class DatabaseMigrationTests(unittest.TestCase):
    def test_legacy_single_shop_data_is_migrated_into_locked_shop_scope(self):
        with tempfile.TemporaryDirectory() as temporary:
            database_path = Path(temporary) / "legacy.sqlite3"
            with sqlite3.connect(database_path) as connection:
                connection.executescript(
                    """
                    CREATE TABLE customers (
                        id INTEGER PRIMARY KEY,
                        name TEXT NOT NULL COLLATE NOCASE UNIQUE,
                        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                    );
                    CREATE TABLE transactions (
                        id INTEGER PRIMARY KEY,
                        customer_id INTEGER NOT NULL REFERENCES customers(id),
                        amount REAL NOT NULL,
                        type TEXT NOT NULL,
                        note TEXT NOT NULL,
                        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                    );
                    CREATE TABLE pending_confirmations (
                        confirmation_id TEXT PRIMARY KEY,
                        transcript TEXT NOT NULL,
                        transactions_json TEXT NOT NULL,
                        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                    );
                    INSERT INTO customers (id, name) VALUES (1, 'Ramesh');
                    INSERT INTO transactions
                        (id, customer_id, amount, type, note)
                        VALUES (1, 1, 250, 'credit_given', 'purana udhaar');
                    """
                )

            initialize_database(database_path)
            with sqlite3.connect(database_path) as connection:
                shop_id, phone, pin_hash = connection.execute(
                    "SELECT id, phone, pin_hash FROM shops"
                ).fetchone()
                customer_columns = {
                    row[1] for row in connection.execute("PRAGMA table_info(customers)")
                }
            self.assertEqual(phone, "legacy-unclaimed")
            self.assertEqual(pin_hash, "!legacy-data-locked!")
            self.assertIn("shop_id", customer_columns)
            self.assertEqual(get_ledger(database_path, shop_id)[0]["balance"], 250)
            self.assertEqual(
                get_ledger_summary(database_path, shop_id)["transaction_count"],
                1,
            )
            self.assertEqual(
                get_customer(database_path, shop_id, "Ramesh")["transactions"][0]["note"],
                "purana udhaar",
            )

    def test_existing_legacy_database_can_be_claimed_with_explicit_hashed_credentials(self):
        with tempfile.TemporaryDirectory() as temporary:
            database_path = Path(temporary) / "claim.sqlite3"
            with sqlite3.connect(database_path) as connection:
                connection.execute(
                    "CREATE TABLE customers (id INTEGER PRIMARY KEY, name TEXT, "
                    "created_at TEXT DEFAULT CURRENT_TIMESTAMP)"
                )
            initialize_database(
                database_path,
                legacy_phone="9876543210",
                legacy_pin_hash="$2b$12$test",
            )
            with sqlite3.connect(database_path) as connection:
                row = connection.execute(
                    "SELECT phone, pin_hash FROM shops"
                ).fetchone()
            self.assertEqual(row, ("9876543210", "$2b$12$test"))


if __name__ == "__main__":
    unittest.main()
