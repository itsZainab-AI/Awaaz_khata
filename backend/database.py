from contextlib import closing
import json
from datetime import datetime, timedelta
from pathlib import Path
import sqlite3


SCHEMA = """
CREATE TABLE IF NOT EXISTS shops (
    id INTEGER PRIMARY KEY,
    shop_name TEXT NOT NULL,
    owner_name TEXT NOT NULL,
    phone TEXT NOT NULL UNIQUE,
    pin_hash TEXT NOT NULL,
    language TEXT NOT NULL DEFAULT 'hi-en',
    upi_id TEXT NOT NULL DEFAULT '',
    is_demo INTEGER NOT NULL DEFAULT 0,
    demo_reset_at INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS customers (
    id INTEGER PRIMARY KEY,
    shop_id INTEGER NOT NULL REFERENCES shops(id) ON DELETE CASCADE,
    name TEXT NOT NULL COLLATE NOCASE,
    preferred_language TEXT NOT NULL DEFAULT 'hi-en',
    phone TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (shop_id, name),
    UNIQUE (id, shop_id)
);

CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY,
    shop_id INTEGER NOT NULL REFERENCES shops(id) ON DELETE CASCADE,
    customer_id INTEGER NOT NULL,
    amount REAL NOT NULL CHECK (amount > 0),
    type TEXT NOT NULL CHECK (type IN ('credit_given', 'payment_received')),
    note TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (customer_id, shop_id) REFERENCES customers(id, shop_id)
        ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS pending_confirmations (
    confirmation_id TEXT PRIMARY KEY,
    shop_id INTEGER NOT NULL REFERENCES shops(id) ON DELETE CASCADE,
    transcript TEXT NOT NULL,
    transactions_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS login_attempts (
    phone TEXT PRIMARY KEY,
    shop_id INTEGER REFERENCES shops(id) ON DELETE CASCADE,
    failures INTEGER NOT NULL DEFAULT 0,
    locked_until INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS transactions_shop_customer
    ON transactions(shop_id, customer_id);

CREATE UNIQUE INDEX IF NOT EXISTS one_demo_shop
    ON shops(is_demo) WHERE is_demo = 1;
"""


def initialize_database(
    database_path: Path,
    *,
    legacy_phone: str = "",
    legacy_pin_hash: str = "",
) -> None:
    database_path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(database_path)) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        if "customers" in tables:
            columns = {
                row[1] for row in connection.execute("PRAGMA table_info(customers)")
            }
            if "shop_id" not in columns:
                _migrate_single_shop_database(
                    connection,
                    legacy_phone=legacy_phone,
                    legacy_pin_hash=legacy_pin_hash,
                )
                return
        connection.executescript(SCHEMA)


def _migrate_single_shop_database(
    connection: sqlite3.Connection,
    *,
    legacy_phone: str,
    legacy_pin_hash: str,
) -> None:
    connection.execute("PRAGMA foreign_keys = OFF")
    connection.execute("BEGIN IMMEDIATE")
    old_tables = {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )
    }
    for table in ("pending_confirmations", "transactions", "customers"):
        if table in old_tables:
            connection.execute(f"ALTER TABLE {table} RENAME TO _legacy_{table}")
    try:
        for statement in SCHEMA.split(";"):
            if statement.strip():
                connection.execute(statement)
        phone = legacy_phone.strip() or "legacy-unclaimed"
        pin_hash = legacy_pin_hash or "!legacy-data-locked!"
        cursor = connection.execute(
            """
            INSERT INTO shops (shop_name, owner_name, phone, pin_hash)
            VALUES ('Imported legacy khata', 'Previous shop owner', ?, ?)
            """,
            (phone, pin_hash),
        )
        shop_id = int(cursor.lastrowid)
        if "customers" in old_tables:
            connection.execute(
                """
                INSERT INTO customers (id, shop_id, name, created_at)
                SELECT id, ?, name, created_at FROM _legacy_customers
                """,
                (shop_id,),
            )
        if "transactions" in old_tables:
            connection.execute(
                """
                INSERT INTO transactions
                    (id, shop_id, customer_id, amount, type, note, created_at)
                SELECT id, ?, customer_id, amount, type, note, created_at
                FROM _legacy_transactions
                """,
                (shop_id,),
            )
        if "pending_confirmations" in old_tables:
            connection.execute(
                """
                INSERT INTO pending_confirmations
                    (confirmation_id, shop_id, transcript, transactions_json, created_at)
                SELECT confirmation_id, ?, transcript, transactions_json, created_at
                FROM _legacy_pending_confirmations
                """,
                (shop_id,),
            )
        for table in ("pending_confirmations", "transactions", "customers"):
            if table in old_tables:
                connection.execute(f"DROP TABLE _legacy_{table}")
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.execute("PRAGMA foreign_keys = ON")


def create_shop(
    database_path: Path,
    *,
    shop_name: str,
    owner_name: str,
    phone: str,
    pin_hash: str,
    language: str,
    upi_id: str = "",
) -> int:
    with closing(sqlite3.connect(database_path)) as connection, connection:
        cursor = connection.execute(
            """
            INSERT INTO shops (shop_name, owner_name, phone, pin_hash, language, upi_id)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (shop_name, owner_name, phone, pin_hash, language, upi_id),
        )
        return int(cursor.lastrowid)


def get_shop_by_phone(database_path: Path, phone: str) -> dict | None:
    with closing(sqlite3.connect(database_path)) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            """
            SELECT id, shop_name, owner_name, phone, pin_hash, language, upi_id
            FROM shops WHERE phone = ?
            """,
            (phone,),
        ).fetchone()
    return dict(row) if row else None


def ensure_demo_shop(database_path: Path, pin_hash: str) -> int:
    now = int(datetime.now().timestamp())
    with closing(sqlite3.connect(database_path)) as connection, connection:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("BEGIN IMMEDIATE")
        shop = connection.execute(
            "SELECT id, demo_reset_at FROM shops WHERE is_demo = 1"
        ).fetchone()
        if shop is None:
            cursor = connection.execute(
                """
                INSERT INTO shops
                    (shop_name, owner_name, phone, pin_hash, language, is_demo)
                VALUES ('Demo Kirana', 'Demo Shopkeeper', '0000000000', ?, 'hi-en', 1)
                """,
                (pin_hash,),
            )
            shop_id = int(cursor.lastrowid)
            reset_at = 0
        else:
            shop_id, reset_at = int(shop[0]), int(shop[1])

        if reset_at and now - reset_at < 24 * 60 * 60:
            return shop_id

        connection.execute("DELETE FROM customers WHERE shop_id = ?", (shop_id,))
        connection.execute(
            "DELETE FROM pending_confirmations WHERE shop_id = ?", (shop_id,)
        )
        customers = (
            ("Ramesh", "hi-en", "9876500001"),
            ("Sita", "hi-IN", "9876500002"),
            ("Amit", "hi-en", "9876500003"),
            ("Meena", "mr-IN", "9876500004"),
            ("Kaka", "mr-IN", "9876500005"),
            ("Farah", "hi-en", "9876500006"),
            ("Rohit", "hi-en", "9876500007"),
            ("Geeta", "hi-IN", "9876500008"),
        )
        customer_ids: dict[str, int] = {}
        for name, language, phone in customers:
            cursor = connection.execute(
                """
                INSERT INTO customers (shop_id, name, preferred_language, phone)
                VALUES (?, ?, ?, ?)
                """,
                (shop_id, name, language, phone),
            )
            customer_ids[name] = int(cursor.lastrowid)

        entries = (
            ("Ramesh", 500, "credit_given", "chai-patti aur biscuit udhaar", 2),
            ("Sita", 300, "credit_given", "doodh aur dahi", 1),
            ("Amit", 1200, "credit_given", "mahine ka ration", 42),
            ("Meena", 800, "credit_given", "kirana samaan", 36),
            ("Kaka", 450, "credit_given", "tel aur cheeni", 3),
            ("Farah", 700, "credit_given", "daal chawal udhaar", 31),
            ("Rohit", 900, "credit_given", "ghar ka samaan", 5),
            ("Geeta", 650, "credit_given", "sabzi aur masale", 4),
            ("Ramesh", 200, "payment_received", "thoda paisa mila", 1),
            ("Sita", 100, "payment_received", "UPI se jama", 0),
            ("Amit", 200, "payment_received", "purana baki chukaya", 55),
            ("Meena", 200, "payment_received", "pichla udhaar parat", 60),
            ("Kaka", 150, "payment_received", "cash jama kiya", 1),
            ("Farah", 200, "payment_received", "thoda payment mila", 44),
            ("Rohit", 300, "payment_received", "kal ke paise mile", 2),
            ("Geeta", 250, "payment_received", "udhaar ka kuch hissa", 2),
            ("Ramesh", 350, "credit_given", "sabun aur biscuit", 6),
            ("Sita", 250, "credit_given", "atta aur chawal", 7),
            ("Amit", 600, "credit_given", "tel ka dabba aur cheeni", 49),
            ("Meena", 400, "credit_given", "aaj ka kirana", 43),
            ("Kaka", 250, "credit_given", "chai aur nashta samaan", 9),
            ("Farah", 500, "credit_given", "bachchon ka snacks", 40),
            ("Rohit", 400, "credit_given", "udhaar mein samaan", 12),
            ("Geeta", 300, "credit_given", "doodh aur masale", 10),
            ("Ramesh", 150, "payment_received", "cash diya", 0),
            ("Sita", 200, "payment_received", "baki mein jama", 2),
            ("Amit", 100, "payment_received", "thoda paisa wapas", 48),
            ("Meena", 100, "payment_received", "paise parat kele", 42),
            ("Kaka", 100, "payment_received", "UPI payment mila", 3),
            ("Rohit", 150, "payment_received", "jama kiye", 1),
        )
        for name, amount, kind, note, days_ago in entries:
            created_at = (datetime.now() - timedelta(days=days_ago)).strftime(
                "%Y-%m-%d %H:%M:%S"
            )
            connection.execute(
                """
                INSERT INTO transactions
                    (shop_id, customer_id, amount, type, note, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (shop_id, customer_ids[name], amount, kind, note, created_at),
            )
        connection.execute(
            "UPDATE shops SET demo_reset_at = ? WHERE id = ?",
            (now, shop_id),
        )
    return shop_id


def get_shop(database_path: Path, shop_id: int) -> dict | None:
    with closing(sqlite3.connect(database_path)) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            """
            SELECT id, shop_name, owner_name, phone, language, upi_id, is_demo
            FROM shops WHERE id = ?
            """,
            (shop_id,),
        ).fetchone()
    return dict(row) if row else None


def update_shop_settings(
    database_path: Path,
    shop_id: int,
    *,
    shop_name: str,
    language: str,
    upi_id: str,
) -> None:
    with closing(sqlite3.connect(database_path)) as connection, connection:
        connection.execute(
            "UPDATE shops SET shop_name = ?, language = ?, upi_id = ? WHERE id = ?",
            (shop_name, language, upi_id, shop_id),
        )


def delete_shop(database_path: Path, shop_id: int) -> None:
    with closing(sqlite3.connect(database_path)) as connection, connection:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("DELETE FROM shops WHERE id = ?", (shop_id,))


def record_login_failure(database_path: Path, phone: str, shop_id: int | None) -> int:
    with closing(sqlite3.connect(database_path)) as connection, connection:
        connection.execute(
            """
            INSERT INTO login_attempts (phone, shop_id, failures, locked_until)
            VALUES (?, ?, 1, 0)
            ON CONFLICT(phone) DO UPDATE SET failures = failures + 1, shop_id = excluded.shop_id
            """,
            (phone, shop_id),
        )
        return int(connection.execute(
            "SELECT failures FROM login_attempts WHERE phone = ?", (phone,)
        ).fetchone()[0])


def get_login_lock(database_path: Path, phone: str) -> tuple[int, int]:
    with closing(sqlite3.connect(database_path)) as connection:
        row = connection.execute(
            "SELECT failures, locked_until FROM login_attempts WHERE phone = ?",
            (phone,),
        ).fetchone()
    return (int(row[0]), int(row[1])) if row else (0, 0)


def lock_login(database_path: Path, phone: str, locked_until: int) -> None:
    with closing(sqlite3.connect(database_path)) as connection, connection:
        connection.execute(
            "UPDATE login_attempts SET locked_until = ? WHERE phone = ?",
            (locked_until, phone),
        )


def clear_login_failures(database_path: Path, phone: str) -> None:
    with closing(sqlite3.connect(database_path)) as connection, connection:
        connection.execute("DELETE FROM login_attempts WHERE phone = ?", (phone,))


def create_customer(
    database_path: Path,
    shop_id: int,
    name: str,
    preferred_language: str = "hi-en",
) -> dict:
    with closing(sqlite3.connect(database_path)) as connection, connection:
        connection.execute(
            """
            INSERT OR IGNORE INTO customers (shop_id, name, preferred_language)
            VALUES (?, ?, ?)
            """,
            (shop_id, name, preferred_language),
        )
    customer = get_customer(database_path, shop_id, name)
    if customer is None:
        raise RuntimeError("Could not find or create the customer.")
    return customer


def stage_confirmation(
    database_path: Path,
    shop_id: int,
    confirmation_id: str,
    transcript: str,
    transactions: list[dict],
) -> None:
    with closing(sqlite3.connect(database_path)) as connection, connection:
        connection.execute(
            """
            INSERT INTO pending_confirmations
                (confirmation_id, shop_id, transcript, transactions_json)
            VALUES (?, ?, ?, ?)
            """,
            (confirmation_id, shop_id, transcript, json.dumps(transactions)),
        )


def get_ledger(database_path: Path, shop_id: int) -> list[dict]:
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
            LEFT JOIN transactions
                ON transactions.customer_id = customers.id
                AND transactions.shop_id = customers.shop_id
            WHERE customers.shop_id = ?
            GROUP BY customers.id, customers.name
            ORDER BY customers.name COLLATE NOCASE
            """,
            (shop_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def get_ledger_summary(database_path: Path, shop_id: int) -> dict:
    with closing(sqlite3.connect(database_path)) as connection:
        row = connection.execute(
            """
            SELECT
                COALESCE(SUM(CASE WHEN type = 'credit_given' THEN amount ELSE 0 END), 0),
                COALESCE(SUM(CASE WHEN type = 'payment_received' THEN amount ELSE 0 END), 0),
                COUNT(*)
            FROM transactions WHERE shop_id = ?
            """,
            (shop_id,),
        ).fetchone()
    return {"credit": row[0], "paid": row[1], "transaction_count": row[2]}


def get_all_transactions(database_path: Path, shop_id: int) -> list[dict]:
    with closing(sqlite3.connect(database_path)) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """
            SELECT customers.name AS customer, transactions.amount, transactions.type,
                transactions.note, transactions.created_at
            FROM transactions
            JOIN customers
                ON customers.id = transactions.customer_id
                AND customers.shop_id = transactions.shop_id
            WHERE transactions.shop_id = ?
            ORDER BY transactions.created_at, transactions.id
            """,
            (shop_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def get_customer_balance(database_path: Path, shop_id: int, name: str) -> dict | None:
    with closing(sqlite3.connect(database_path)) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            """
            SELECT customers.name,
                COALESCE(SUM(
                    CASE transactions.type
                        WHEN 'credit_given' THEN transactions.amount
                        WHEN 'payment_received' THEN -transactions.amount
                    END
                ), 0) AS balance
            FROM customers
            LEFT JOIN transactions
                ON transactions.customer_id = customers.id
                AND transactions.shop_id = customers.shop_id
            WHERE customers.shop_id = ? AND customers.name = ? COLLATE NOCASE
            GROUP BY customers.id, customers.name
            """,
            (shop_id, name),
        ).fetchone()
    return dict(row) if row else None


def get_today_credit(database_path: Path, shop_id: int) -> float:
    with closing(sqlite3.connect(database_path)) as connection:
        row = connection.execute(
            """
            SELECT COALESCE(SUM(amount), 0)
            FROM transactions
            WHERE shop_id = ? AND type = 'credit_given'
                AND date(created_at) = date('now')
            """,
            (shop_id,),
        ).fetchone()
    return float(row[0])


def get_unpaid_customers(
    database_path: Path,
    shop_id: int,
    days: int,
) -> list[dict]:
    with closing(sqlite3.connect(database_path)) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """
            SELECT customers.name,
                COALESCE(SUM(
                    CASE transactions.type
                        WHEN 'credit_given' THEN transactions.amount
                        WHEN 'payment_received' THEN -transactions.amount
                    END
                ), 0) AS balance,
                MAX(CASE WHEN transactions.type = 'payment_received'
                    THEN transactions.created_at END) AS last_payment
            FROM customers
            LEFT JOIN transactions
                ON transactions.customer_id = customers.id
                AND transactions.shop_id = customers.shop_id
            WHERE customers.shop_id = ?
            GROUP BY customers.id, customers.name
            HAVING balance > 0 AND (
                last_payment IS NULL
                OR datetime(last_payment) <= datetime('now', ?)
            )
            ORDER BY customers.name COLLATE NOCASE
            """,
            (shop_id, f"-{days} days"),
        ).fetchall()
    return [dict(row) for row in rows]


def get_customer(database_path: Path, shop_id: int, name: str) -> dict | None:
    with closing(sqlite3.connect(database_path)) as connection:
        connection.row_factory = sqlite3.Row
        customer = connection.execute(
            """
            SELECT id, name, preferred_language, phone,
                COALESCE((
                    SELECT SUM(
                        CASE transactions.type
                            WHEN 'credit_given' THEN transactions.amount
                            WHEN 'payment_received' THEN -transactions.amount
                        END
                    )
                    FROM transactions
                    WHERE transactions.customer_id = customers.id
                        AND transactions.shop_id = customers.shop_id
                ), 0) AS balance
            FROM customers
            WHERE name = ? COLLATE NOCASE AND shop_id = ?
            """,
            (name, shop_id),
        ).fetchone()
        if customer is None:
            return None
        transactions = connection.execute(
            """
            SELECT id, amount, type, note, created_at
            FROM transactions
            WHERE customer_id = ? AND shop_id = ?
            ORDER BY id
            """,
            (customer["id"], shop_id),
        ).fetchall()
    return {**dict(customer), "transactions": [dict(row) for row in transactions]}


def confirm_transactions(
    database_path: Path,
    shop_id: int,
    confirmation_id: str,
    edited_transactions: list[dict] | None = None,
) -> tuple[str, list[dict]] | None:
    with closing(sqlite3.connect(database_path)) as connection, connection:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("BEGIN IMMEDIATE")
        pending = connection.execute(
            """
            SELECT transcript, transactions_json
            FROM pending_confirmations
            WHERE confirmation_id = ? AND shop_id = ?
            """,
            (confirmation_id, shop_id),
        ).fetchone()
        if pending is None:
            return None

        transactions = (
            edited_transactions if edited_transactions is not None else json.loads(pending[1])
        )
        for transaction in transactions:
            connection.execute(
                """
                INSERT OR IGNORE INTO customers (shop_id, name, preferred_language)
                VALUES (?, ?, (SELECT language FROM shops WHERE id = ?))
                """,
                (shop_id, transaction["person"], shop_id),
            )
            customer = connection.execute(
                "SELECT id FROM customers WHERE shop_id = ? AND name = ? COLLATE NOCASE",
                (shop_id, transaction["person"]),
            ).fetchone()
            if customer is None:
                raise RuntimeError("Could not find or create the transaction customer.")
            connection.execute(
                """
                INSERT INTO transactions (shop_id, customer_id, amount, type, note)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    shop_id,
                    customer[0],
                    transaction["amount"],
                    transaction["type"],
                    transaction["note"],
                ),
            )
        connection.execute(
            "DELETE FROM pending_confirmations WHERE confirmation_id = ? AND shop_id = ?",
            (confirmation_id, shop_id),
        )
    return pending[0], transactions


def cancel_confirmation(database_path: Path, shop_id: int, confirmation_id: str) -> bool:
    with closing(sqlite3.connect(database_path)) as connection, connection:
        cursor = connection.execute(
            "DELETE FROM pending_confirmations WHERE confirmation_id = ? AND shop_id = ?",
            (confirmation_id, shop_id),
        )
    return cursor.rowcount > 0
