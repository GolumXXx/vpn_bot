from database.connection import get_connection


def init_schema_conn(conn):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS platega_payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            payment_id TEXT NOT NULL UNIQUE,
            telegram_id INTEGER NOT NULL,
            tariff_code TEXT NOT NULL,
            amount INTEGER NOT NULL,
            currency TEXT NOT NULL,
            status TEXT NOT NULL,
            payment_url TEXT,
            request_payload TEXT,
            webhook_payload TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            processed_at TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_platega_payments_payment_id
        ON platega_payments (payment_id)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_platega_payments_user_status
        ON platega_payments (telegram_id, status, id DESC)
        """
    )


def insert_payment(
    *,
    payment_id,
    telegram_id,
    tariff_code,
    amount,
    currency,
    status,
    payment_url,
    request_payload,
    created_at,
    updated_at,
):
    with get_connection() as conn:
        init_schema_conn(conn)
        conn.execute(
            """
            INSERT INTO platega_payments (
                payment_id,
                telegram_id,
                tariff_code,
                amount,
                currency,
                status,
                payment_url,
                request_payload,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payment_id,
                telegram_id,
                tariff_code,
                amount,
                currency,
                status,
                payment_url,
                request_payload,
                created_at,
                updated_at,
            ),
        )


def get_by_payment_id(payment_id):
    with get_connection() as conn:
        init_schema_conn(conn)
        return conn.execute(
            """
            SELECT *
            FROM platega_payments
            WHERE payment_id = ?
            """,
            (payment_id,),
        ).fetchone()


def get_recent_by_status(status, since_created_at, limit=100):
    with get_connection() as conn:
        init_schema_conn(conn)
        return conn.execute(
            """
            SELECT *
            FROM platega_payments
            WHERE status = ?
              AND created_at > ?
            ORDER BY id ASC
            LIMIT ?
            """,
            (status, since_created_at, limit),
        ).fetchall()


def update_status(payment_id, *, status, updated_at, webhook_payload=None):
    with get_connection() as conn:
        init_schema_conn(conn)
        conn.execute(
            """
            UPDATE platega_payments
            SET status = ?,
                webhook_payload = COALESCE(?, webhook_payload),
                updated_at = ?
            WHERE payment_id = ?
            """,
            (status, webhook_payload, updated_at, payment_id),
        )


def start_processing(payment_id, *, status, updated_at, webhook_payload, allowed_statuses):
    placeholders = ", ".join("?" for _ in allowed_statuses)
    with get_connection() as conn:
        init_schema_conn(conn)
        cursor = conn.execute(
            f"""
            UPDATE platega_payments
            SET status = ?,
                webhook_payload = ?,
                updated_at = ?
            WHERE payment_id = ?
              AND status IN ({placeholders})
            """,
            (status, webhook_payload, updated_at, payment_id, *allowed_statuses),
        )
        return cursor.rowcount > 0


def mark_processed(payment_id, *, status, processed_at, updated_at, expected_status):
    with get_connection() as conn:
        init_schema_conn(conn)
        cursor = conn.execute(
            """
            UPDATE platega_payments
            SET status = ?,
                processed_at = ?,
                updated_at = ?
            WHERE payment_id = ?
              AND status = ?
            """,
            (status, processed_at, updated_at, payment_id, expected_status),
        )
        return cursor.rowcount > 0
