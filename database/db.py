import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path

from services.short_links import (
    create_short_link,
    delete_short_link_by_url,
    init_short_links_schema,
)
from services.xui_client import XUIClient, XUIError


BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "bot.db"
DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"
SHORT_LINK_BASE_URL = "https://golum.shop"
MANUAL_PAYMENT_STATUS_PENDING = "pending_receipt"
MANUAL_PAYMENT_STATUS_RECEIPT_UPLOADED = "receipt_uploaded"
MANUAL_PAYMENT_STATUS_WAITING_ADMIN = "waiting_admin_confirmation"
MANUAL_PAYMENT_STATUS_PROCESSING = "processing"
MANUAL_PAYMENT_STATUS_APPROVED = "approved"
MANUAL_PAYMENT_STATUS_REPLACED = "replaced"
MANUAL_PAYMENT_STATUS_CANCELLED = "cancelled"
VALID_DEVICE_TYPES = {"ios", "android", "windows", "mac"}


@contextmanager
def get_connection():
    conn = sqlite3.connect(DB_PATH, timeout=30, cached_statements=128)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
        conn.execute("PRAGMA busy_timeout = 30000")
        yield conn
        conn.commit()
    finally:
        conn.close()


def _fetchone(query, params=()):
    with get_connection() as conn:
        return conn.execute(query, params).fetchone()


def _fetchall(query, params=()):
    with get_connection() as conn:
        return conn.execute(query, params).fetchall()


def _execute(query, params=()):
    with get_connection() as conn:
        conn.execute(query, params)


def _table_columns(conn, table_name: str) -> set[str]:
    return {
        row["name"]
        for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    }


def _add_column_if_missing(conn, table_name: str, column_name: str, column_definition: str):
    if column_name not in _table_columns(conn, table_name):
        conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_definition}")


def _now():
    return datetime.now()


def _format_datetime(value: datetime) -> str:
    return value.strftime(DATETIME_FORMAT)


def _upsert_user(conn, telegram_id, username, first_name):
    conn.execute(
        """
        INSERT INTO users (telegram_id, username, first_name, used_trial, trial_activated_at)
        VALUES (?, ?, ?, 0, NULL)
        ON CONFLICT(telegram_id) DO UPDATE SET
            username = excluded.username,
            first_name = excluded.first_name
        """,
        (telegram_id, username, first_name),
    )


def _insert_vpn_key(
    conn,
    telegram_id,
    key_name,
    key_value,
    is_trial,
    server_id,
    inbound_id,
    email,
    client_uuid,
    duration_days,
    traffic_limit_gb,
):
    now = _now()
    expires = now + timedelta(days=duration_days)
    traffic_limit_bytes = traffic_limit_gb * 1024 * 1024 * 1024 if traffic_limit_gb > 0 else 0

    conn.execute(
        """
        INSERT INTO vpn_keys (
            telegram_id,
            key_name,
            key_value,
            is_trial,
            is_active,
            created_at,
            expires_at,
            server_id,
            panel_inbound_id,
            panel_email,
            client_uuid,
            traffic_limit,
            traffic_used
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            telegram_id,
            key_name,
            key_value,
            is_trial,
            1,
            _format_datetime(now),
            _format_datetime(expires),
            server_id,
            inbound_id,
            email,
            client_uuid,
            traffic_limit_bytes,
            0,
        ),
    )

    return expires


async def _issue_key(
    telegram_id,
    key_name,
    duration_days,
    username=None,
    first_name=None,
    traffic_limit_gb=0,
    is_trial=False,
):
    add_or_update_user(telegram_id, username, first_name)

    server = get_active_server()
    if not server:
        raise XUIError("Нет активного VPN-сервера")

    client = XUIClient(dict(server))

    try:
        inbounds = await client.get_inbounds()
        if not inbounds:
            raise XUIError("На сервере не найдено ни одного inbound")

        inbound = inbounds[0]
        inbound_id = inbound["id"]
        flow = client._resolve_inbound_flow(inbound)
        email = generate_panel_email(telegram_id, username)

        result = await client.add_client(
            inbound_id=inbound_id,
            email=email,
            expire_days=duration_days,
            total_gb=traffic_limit_gb,
            flow=flow,
        )

        uri = await client.build_connection_uri(
            inbound_id=inbound_id,
            email=email,
            client_uuid=result["uuid"],
            flow=flow,
        )
        short_uri = create_short_link(uri, base_url=SHORT_LINK_BASE_URL)

        with get_connection() as conn:
            _insert_vpn_key(
                conn=conn,
                telegram_id=telegram_id,
                key_name=key_name,
                key_value=short_uri,
                is_trial=int(is_trial),
                server_id=server["id"],
                inbound_id=inbound_id,
                email=email,
                client_uuid=result["uuid"],
                duration_days=duration_days,
                traffic_limit_gb=traffic_limit_gb,
            )

            if is_trial:
                conn.execute(
                    """
                    UPDATE users
                    SET used_trial = 1,
                        trial_activated_at = ?
                    WHERE telegram_id = ?
                    """,
                    (_format_datetime(_now()), telegram_id),
                )

        return short_uri
    finally:
        await client.close()


def add_or_update_user(telegram_id, username, first_name):
    with get_connection() as conn:
        _upsert_user(conn, telegram_id, username, first_name)


def create_manual_payment(telegram_id, tariff_code):
    now = _format_datetime(_now())

    for _ in range(5):
        order_id = uuid.uuid4().hex[:8].upper()
        try:
            with get_connection() as conn:
                conn.execute(
                    """
                    UPDATE manual_payments
                    SET status = ?,
                        updated_at = ?
                    WHERE telegram_id = ?
                      AND status IN (?, ?, ?)
                    """,
                    (
                        MANUAL_PAYMENT_STATUS_REPLACED,
                        now,
                        telegram_id,
                        MANUAL_PAYMENT_STATUS_PENDING,
                        MANUAL_PAYMENT_STATUS_RECEIPT_UPLOADED,
                        MANUAL_PAYMENT_STATUS_WAITING_ADMIN,
                    ),
                )
                conn.execute(
                    """
                    INSERT INTO manual_payments (
                        order_id,
                        telegram_id,
                        tariff_code,
                        status,
                        created_at,
                        updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        order_id,
                        telegram_id,
                        tariff_code,
                        MANUAL_PAYMENT_STATUS_PENDING,
                        now,
                        now,
                    ),
                )
            return get_manual_payment_by_order_id(order_id)
        except sqlite3.IntegrityError:
            continue

    raise ValueError("Не удалось создать ID оплаты")


def get_manual_payment_by_order_id(order_id):
    return _fetchone(
        """
        SELECT *
        FROM manual_payments
        WHERE order_id = ?
        """,
        (order_id,),
    )


def get_pending_manual_payments(limit=10):
    return _fetchall(
        """
        SELECT *
        FROM manual_payments
        WHERE status IN (?, ?, ?, ?)
        ORDER BY id DESC
        LIMIT ?
        """,
        (
            MANUAL_PAYMENT_STATUS_PENDING,
            MANUAL_PAYMENT_STATUS_RECEIPT_UPLOADED,
            MANUAL_PAYMENT_STATUS_WAITING_ADMIN,
            MANUAL_PAYMENT_STATUS_PROCESSING,
            limit,
        ),
    )


def count_pending_manual_payments():
    row = _fetchone(
        """
        SELECT COUNT(*)
        FROM manual_payments
        WHERE status IN (?, ?, ?, ?)
        """,
        (
            MANUAL_PAYMENT_STATUS_PENDING,
            MANUAL_PAYMENT_STATUS_RECEIPT_UPLOADED,
            MANUAL_PAYMENT_STATUS_WAITING_ADMIN,
            MANUAL_PAYMENT_STATUS_PROCESSING,
        ),
    )
    return row[0]


def get_latest_open_manual_payment(telegram_id):
    return _fetchone(
        """
        SELECT *
        FROM manual_payments
        WHERE telegram_id = ?
          AND status IN (?, ?)
        ORDER BY id DESC
        LIMIT 1
        """,
        (
            telegram_id,
            MANUAL_PAYMENT_STATUS_PENDING,
            MANUAL_PAYMENT_STATUS_RECEIPT_UPLOADED,
        ),
    )


def mark_manual_payment_waiting_admin(order_id, user_message_id=None):
    now = _format_datetime(_now())
    with get_connection() as conn:
        cursor = conn.execute(
            """
            UPDATE manual_payments
            SET status = ?,
                user_message_id = COALESCE(?, user_message_id),
                updated_at = ?
            WHERE order_id = ?
              AND status = ?
            """,
            (
                MANUAL_PAYMENT_STATUS_WAITING_ADMIN,
                user_message_id,
                now,
                order_id,
                MANUAL_PAYMENT_STATUS_RECEIPT_UPLOADED,
            ),
        )
        return cursor.rowcount > 0


def reset_manual_payment_waiting_admin(order_id):
    now = _format_datetime(_now())
    _execute(
        """
        UPDATE manual_payments
        SET status = ?,
            updated_at = ?
        WHERE order_id = ?
          AND status = ?
        """,
        (
            MANUAL_PAYMENT_STATUS_RECEIPT_UPLOADED,
            now,
            order_id,
            MANUAL_PAYMENT_STATUS_WAITING_ADMIN,
        ),
    )


def cancel_pending_manual_payment(order_id):
    now = _format_datetime(_now())
    with get_connection() as conn:
        cursor = conn.execute(
            """
            UPDATE manual_payments
            SET status = ?,
                cancelled_at = ?,
                updated_at = ?
            WHERE order_id = ?
              AND status = ?
            """,
            (
                MANUAL_PAYMENT_STATUS_CANCELLED,
                now,
                now,
                order_id,
                MANUAL_PAYMENT_STATUS_PENDING,
            ),
        )
        return cursor.rowcount > 0


def mark_manual_payment_reminded(order_id):
    now = _format_datetime(_now())
    with get_connection() as conn:
        cursor = conn.execute(
            """
            UPDATE manual_payments
            SET manual_reminded_at = ?,
                updated_at = ?
            WHERE order_id = ?
              AND status = ?
              AND manual_reminded_at IS NULL
            """,
            (
                now,
                now,
                order_id,
                MANUAL_PAYMENT_STATUS_PENDING,
            ),
        )
        return cursor.rowcount > 0


def attach_manual_payment_receipt(order_id, receipt_file_id, receipt_unique_id=None, user_message_id=None):
    now = _format_datetime(_now())
    _execute(
        """
        UPDATE manual_payments
        SET status = ?,
            receipt_file_id = ?,
            receipt_unique_id = ?,
            user_message_id = ?,
            updated_at = ?
        WHERE order_id = ?
          AND status IN (?, ?)
        """,
        (
            MANUAL_PAYMENT_STATUS_RECEIPT_UPLOADED,
            receipt_file_id,
            receipt_unique_id,
            user_message_id,
            now,
            order_id,
            MANUAL_PAYMENT_STATUS_PENDING,
            MANUAL_PAYMENT_STATUS_RECEIPT_UPLOADED,
        ),
    )


def start_manual_payment_processing(order_id, admin_id):
    now = _format_datetime(_now())
    with get_connection() as conn:
        cursor = conn.execute(
            """
            UPDATE manual_payments
            SET status = ?,
                approved_by = ?,
                updated_at = ?
            WHERE order_id = ?
              AND status IN (?, ?)
            """,
            (
                MANUAL_PAYMENT_STATUS_PROCESSING,
                admin_id,
                now,
                order_id,
                MANUAL_PAYMENT_STATUS_WAITING_ADMIN,
                MANUAL_PAYMENT_STATUS_RECEIPT_UPLOADED,
            ),
        )
        return cursor.rowcount > 0


def reopen_manual_payment(order_id):
    now = _format_datetime(_now())
    _execute(
        """
        UPDATE manual_payments
        SET status = ?,
            approved_by = NULL,
            updated_at = ?
        WHERE order_id = ?
          AND status = ?
        """,
        (
            MANUAL_PAYMENT_STATUS_WAITING_ADMIN,
            now,
            order_id,
            MANUAL_PAYMENT_STATUS_PROCESSING,
        ),
    )


def mark_manual_payment_approved(order_id, admin_id):
    now = _format_datetime(_now())
    _execute(
        """
        UPDATE manual_payments
        SET status = ?,
            approved_by = ?,
            approved_at = ?,
            updated_at = ?
        WHERE order_id = ?
        """,
        (
            MANUAL_PAYMENT_STATUS_APPROVED,
            admin_id,
            now,
            now,
            order_id,
        ),
    )


def has_used_trial(telegram_id):
    row = _fetchone(
        "SELECT used_trial FROM users WHERE telegram_id = ?",
        (telegram_id,),
    )
    return bool(row["used_trial"]) if row else False


def mark_trial_as_used(telegram_id):
    _execute(
        """
        UPDATE users
        SET used_trial = 1,
            trial_activated_at = ?
        WHERE telegram_id = ?
        """,
        (_format_datetime(_now()), telegram_id),
    )


def get_user(telegram_id):
    return _fetchone(
        "SELECT * FROM users WHERE telegram_id = ?",
        (telegram_id,),
    )


def get_user_by_username(username):
    return _fetchone(
        """
        SELECT *
        FROM users
        WHERE lower(username) = lower(?)
        """,
        (username.removeprefix("@").strip(),),
    )


def get_active_server():
    return _fetchone("SELECT * FROM servers WHERE is_active = 1 LIMIT 1")


def generate_panel_email(telegram_id, username):
    suffix = uuid.uuid4().hex[:5]
    base = f"user_{username}" if username else f"user_{telegram_id}"
    return f"{base}_{suffix}"


async def create_paid_key(
    telegram_id,
    tariff_name,
    duration_days,
    username=None,
    first_name=None,
    traffic_limit_gb=0,
):
    return await _issue_key(
        telegram_id=telegram_id,
        key_name=tariff_name,
        duration_days=duration_days,
        username=username,
        first_name=first_name,
        traffic_limit_gb=traffic_limit_gb,
        is_trial=False,
    )


async def create_trial_key(telegram_id, username=None, first_name=None):
    return await _issue_key(
        telegram_id=telegram_id,
        key_name="trial",
        duration_days=7,
        username=username,
        first_name=first_name,
        traffic_limit_gb=0,
        is_trial=True,
    )


def get_latest_paid_key_by_tariff(telegram_id, tariff_name):
    return _fetchone(
        """
        SELECT *
        FROM vpn_keys
        WHERE telegram_id = ?
          AND key_name = ?
          AND is_trial = 0
        ORDER BY id DESC
        LIMIT 1
        """,
        (telegram_id, tariff_name),
    )


def extend_key(key_id, duration_days):
    key = get_key_by_id(key_id)
    if not key:
        return None

    now = _now()
    current_expires = parse_datetime(key["expires_at"])
    base_date = current_expires if current_expires and current_expires > now else now
    new_expires = base_date + timedelta(days=duration_days)
    new_expires_str = _format_datetime(new_expires)

    _execute(
        """
        UPDATE vpn_keys
        SET expires_at = ?,
            is_active = 1
        WHERE id = ?
        """,
        (new_expires_str, key_id),
    )

    return new_expires_str


def update_key_device_type(key_id, device_type):
    if device_type not in VALID_DEVICE_TYPES:
        return False

    with get_connection() as conn:
        cursor = conn.execute(
            """
            UPDATE vpn_keys
            SET device_type = ?
            WHERE id = ?
            """,
            (device_type, key_id),
        )
        return cursor.rowcount > 0


def init_db():
    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                telegram_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                used_trial INTEGER DEFAULT 0,
                trial_activated_at TEXT
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS servers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                host TEXT,
                port INTEGER,
                protocol TEXT,
                web_base_path TEXT,
                login TEXT,
                password TEXT,
                is_active INTEGER DEFAULT 1
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS vpn_keys (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER,
                key_name TEXT,
                key_value TEXT,
                device_type TEXT,
                is_trial INTEGER DEFAULT 0,
                is_active INTEGER DEFAULT 1,
                created_at TEXT,
                expires_at TEXT,
                server_id INTEGER,
                panel_inbound_id INTEGER,
                panel_email TEXT,
                client_uuid TEXT,
                traffic_limit INTEGER DEFAULT 0,
                traffic_used INTEGER DEFAULT 0
            )
            """
        )
        _add_column_if_missing(conn, "vpn_keys", "device_type", "TEXT")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS manual_payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id TEXT NOT NULL UNIQUE,
                telegram_id INTEGER NOT NULL,
                tariff_code TEXT NOT NULL,
                status TEXT NOT NULL,
                receipt_file_id TEXT,
                receipt_unique_id TEXT,
                user_message_id INTEGER,
                approved_by INTEGER,
                approved_at TEXT,
                manual_reminded_at TEXT,
                cancelled_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        init_short_links_schema(conn)
        _add_column_if_missing(conn, "manual_payments", "manual_reminded_at", "TEXT")
        _add_column_if_missing(conn, "manual_payments", "cancelled_at", "TEXT")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS link_clicks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT NOT NULL,
                ip TEXT,
                user_agent TEXT,
                clicked_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_vpn_keys_telegram_id
            ON vpn_keys (telegram_id)
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_vpn_keys_telegram_active_expires
            ON vpn_keys (telegram_id, is_active, expires_at)
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_vpn_keys_tariff_lookup
            ON vpn_keys (telegram_id, key_name, is_trial, id DESC)
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_servers_active
            ON servers (is_active)
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_manual_payments_user_status
            ON manual_payments (telegram_id, status, id DESC)
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_manual_payments_order_id
            ON manual_payments (order_id)
            """
        )


def get_user_keys(telegram_id):
    return _fetchall(
        """
        SELECT *
        FROM vpn_keys
        WHERE telegram_id = ?
        ORDER BY id DESC
        """,
        (telegram_id,),
    )


def get_key_by_id(key_id):
    return _fetchone(
        """
        SELECT *
        FROM vpn_keys
        WHERE id = ?
        """,
        (key_id,),
    )


def parse_datetime(value):
    if not value:
        return None

    try:
        return datetime.strptime(value, DATETIME_FORMAT)
    except ValueError:
        return None


def is_key_active(key):
    if not key:
        return False

    expires_at = parse_datetime(key["expires_at"])
    if expires_at and expires_at <= _now():
        return False

    return bool(key["is_active"])


def count_user_keys(telegram_id):
    row = _fetchone(
        """
        SELECT COUNT(*)
        FROM vpn_keys
        WHERE telegram_id = ?
        """,
        (telegram_id,),
    )
    return row[0]


def count_active_user_keys(telegram_id):
    row = _fetchone(
        """
        SELECT COUNT(*)
        FROM vpn_keys
        WHERE telegram_id = ?
          AND is_active = 1
          AND (
              expires_at IS NULL
              OR expires_at = ''
              OR expires_at > ?
          )
        """,
        (telegram_id, _format_datetime(_now())),
    )
    return row[0]


def get_user_key_stats(telegram_id):
    row = _fetchone(
        """
        SELECT
            COUNT(*) AS total_keys,
            SUM(
                CASE
                    WHEN is_active = 1
                     AND (
                         expires_at IS NULL
                         OR expires_at = ''
                         OR expires_at > ?
                     )
                    THEN 1
                    ELSE 0
                END
            ) AS active_keys
        FROM vpn_keys
        WHERE telegram_id = ?
        """,
        (_format_datetime(_now()), telegram_id),
    )
    return {
        "total_keys": row["total_keys"] or 0,
        "active_keys": row["active_keys"] or 0,
    }


def get_admin_dashboard_stats():
    now = _format_datetime(_now())
    users = _fetchone("SELECT COUNT(*) FROM users")[0]
    keys = _fetchone(
        """
        SELECT
            COUNT(*) AS total_keys,
            SUM(
                CASE
                    WHEN is_active = 1
                     AND (
                         expires_at IS NULL
                         OR expires_at = ''
                         OR expires_at > ?
                     )
                    THEN 1
                    ELSE 0
                END
            ) AS active_keys,
            SUM(
                CASE
                    WHEN expires_at IS NOT NULL
                     AND expires_at != ''
                     AND expires_at <= ?
                    THEN 1
                    ELSE 0
                END
            ) AS expired_keys
        FROM vpn_keys
        """,
        (now, now),
    )

    return {
        "users": users or 0,
        "total_keys": keys["total_keys"] or 0,
        "active_keys": keys["active_keys"] or 0,
        "expired_keys": keys["expired_keys"] or 0,
        "pending_payments": count_pending_manual_payments(),
    }


def get_server_by_id(server_id):
    return _fetchone(
        "SELECT * FROM servers WHERE id = ?",
        (server_id,),
    )


def delete_key_from_db(key_id):
    key = get_key_by_id(key_id)
    if key:
        delete_short_link_by_url(key["key_value"])
    _execute("DELETE FROM vpn_keys WHERE id = ?", (key_id,))


async def delete_key_completely(key_id):
    key = get_key_by_id(key_id)
    if not key:
        return False, "Ключ не найден"

    server_id = key["server_id"]
    inbound_id = key["panel_inbound_id"]
    client_uuid = key["client_uuid"]

    if not server_id or not inbound_id or not client_uuid:
        delete_key_from_db(key_id)
        return True, "Ключ удалён только из базы"

    server = get_server_by_id(server_id)
    if not server:
        return False, "Сервер не найден"

    client = XUIClient(dict(server))

    try:
        await client.delete_client(
            inbound_id=inbound_id,
            client_uuid=client_uuid,
        )
        delete_key_from_db(key_id)
        return True, "Ключ удалён с сервера и из базы"
    except Exception as error:
        return False, f"Ошибка удаления: {error}"
    finally:
        await client.close()
