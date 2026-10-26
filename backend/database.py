from contextlib import closing
import json
from pathlib import Path
import sqlite3


SCHEMA = """
CREATE TABLE IF NOT EXISTS customers (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL COLLATE NOCASE UNIQUE,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL REFERENCES customers(id),
    amount REAL NOT NULL CHECK (amount > 0),
    type TEXT NOT NULL CHECK (type IN ('credit_given', 'payment_received')),
    note TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS pending_confirmations (
    confirmation_id TEXT PRIMARY KEY,
    transcript TEXT NOT NULL,
    transactions_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


def initialize_database(database_path: Path) -> None:
    database_path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(database_path)) as connection:
        connection.executescript(SCHEMA)


def create_customer(database_path: Path, name: str) -> dict:
    with closing(sqlite3.connect(database_path)) as connection, connection:
        connection.execute(
            "INSERT OR IGNORE INTO customers (name) VALUES (?)",
            (name,),
        )
    customer = get_customer(database_path, name)
    if customer is None:
        raise RuntimeError("Could not find or create the customer.")
    return customer


def stage_confirmation(
    database_path: Path,
    confirmation_id: str,
    transcript: str,
    transactions: list[dict],
) -> None:
    with closing(sqlite3.connect(database_path)) as connection, connection:
        connection.execute(
            """
            INSERT INTO pending_confirmations
                (confirmation_id, transcript, transactions_json)
            VALUES (?, ?, ?)
            """,
            (confirmation_id, transcript, json.dumps(transactions)),
        )


def get_ledger(database_path: Path) -> list[dict]:
    with closing(sqlite3.connect(database_path)) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """
            SELECT customers.id, customers.name,
                COALESCE(SUM(
                    CASE transactions.type
                        WHEN 'credit_given' THEN transactions.amount
                        WHEN 'payment_received' THEN -transactions.amount
                    END
                ), 0) AS balance
            FROM customers
            LEFT JOIN transactions ON transactions.customer_id = customers.id
            GROUP BY customers.id, customers.name
            ORDER BY customers.name COLLATE NOCASE
            """
        ).fetchall()
    return [dict(row) for row in rows]


def get_ledger_summary(database_path: Path) -> dict:
    with closing(sqlite3.connect(database_path)) as connection:
        row = connection.execute(
            """
            SELECT
                COALESCE(SUM(CASE WHEN type = 'credit_given' THEN amount ELSE 0 END), 0),
                COALESCE(SUM(CASE WHEN type = 'payment_received' THEN amount ELSE 0 END), 0),
                COUNT(*)
            FROM transactions
            """
        ).fetchone()
    return {
        "credit": row[0],
        "paid": row[1],
        "transaction_count": row[2],
    }


def get_customer(database_path: Path, name: str) -> dict | None:
    with closing(sqlite3.connect(database_path)) as connection:
        connection.row_factory = sqlite3.Row
        customer = connection.execute(
            """
            SELECT id, name,
                COALESCE((
                    SELECT SUM(
                        CASE transactions.type
                            WHEN 'credit_given' THEN transactions.amount
                            WHEN 'payment_received' THEN -transactions.amount
                        END
                    )
                    FROM transactions
                    WHERE transactions.customer_id = customers.id
                ), 0) AS balance
            FROM customers
            WHERE name = ? COLLATE NOCASE
            """,
            (name,),
        ).fetchone()
        if customer is None:
            return None
        transactions = connection.execute(
            """
            SELECT id, amount, type, note, created_at
            FROM transactions
            WHERE customer_id = ?
            ORDER BY id
            """,
            (customer["id"],),
        ).fetchall()
    return {
        **dict(customer),
        "transactions": [dict(row) for row in transactions],
    }


def confirm_transactions(
    database_path: Path,
    confirmation_id: str,
    edited_transactions: list[dict] | None = None,
) -> tuple[str, list[dict]] | None:
    with closing(sqlite3.connect(database_path)) as connection, connection:
        connection.execute("BEGIN IMMEDIATE")
        pending = connection.execute(
            """
            SELECT transcript, transactions_json
            FROM pending_confirmations
            WHERE confirmation_id = ?
            """,
            (confirmation_id,),
        ).fetchone()
        if pending is None:
            return None

        transactions = (
            edited_transactions
            if edited_transactions is not None
            else json.loads(pending[1])
        )
        for transaction in transactions:
            connection.execute(
                "INSERT OR IGNORE INTO customers (name) VALUES (?)",
                (transaction["person"],),
            )
            customer = connection.execute(
                "SELECT id FROM customers WHERE name = ? COLLATE NOCASE",
                (transaction["person"],),
            ).fetchone()
            if customer is None:
                raise RuntimeError("Could not find or create the transaction customer.")
            connection.execute(
                """
                INSERT INTO transactions (customer_id, amount, type, note)
                VALUES (?, ?, ?, ?)
                """,
                (
                    customer[0],
                    transaction["amount"],
                    transaction["type"],
                    transaction["note"],
                ),
            )
        connection.execute(
            "DELETE FROM pending_confirmations WHERE confirmation_id = ?",
            (confirmation_id,),
        )
    return pending[0], transactions


def cancel_confirmation(database_path: Path, confirmation_id: str) -> bool:
    with closing(sqlite3.connect(database_path)) as connection, connection:
        cursor = connection.execute(
            "DELETE FROM pending_confirmations WHERE confirmation_id = ?",
            (confirmation_id,),
        )
    return cursor.rowcount > 0
