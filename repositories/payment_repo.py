from database.connection import get_connection


def _placeholders(values) -> str:
    return ", ".join("?" for _ in values)


def get_by_idempotency_key_conn(conn, idempotency_key):
    return conn.execute(
        """
        SELECT *
        FROM manual_payments
        WHERE idempotency_key = ?
        """,
        (idempotency_key,),
    ).fetchone()


def replace_open_payments_conn(conn, telegram_id, status, updated_at, open_statuses):
    status_placeholders = _placeholders(open_statuses)
    conn.execute(
        f"""
        UPDATE manual_payments
        SET status = ?,
            updated_at = ?
        WHERE telegram_id = ?
          AND status IN ({status_placeholders})
        """,
        (status, updated_at, telegram_id, *open_statuses),
    )


def insert_manual_payment_conn(
    conn,
    order_id,
    telegram_id,
    tariff_code,
    idempotency_key,
    status,
    created_at,
    updated_at,
):
    conn.execute(
        """
        INSERT INTO manual_payments (
            order_id,
            telegram_id,
            tariff_code,
            idempotency_key,
            status,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            order_id,
            telegram_id,
            tariff_code,
            idempotency_key,
            status,
            created_at,
            updated_at,
        ),
    )


def get_by_order_id(order_id):
    with get_connection() as conn:
        return conn.execute(
            """
            SELECT *
            FROM manual_payments
            WHERE order_id = ?
            """,
            (order_id,),
        ).fetchone()


def get_pending_by_statuses(statuses, limit):
    status_placeholders = _placeholders(statuses)
    with get_connection() as conn:
        return conn.execute(
            f"""
            SELECT *
            FROM manual_payments
            WHERE status IN ({status_placeholders})
            ORDER BY id DESC
            LIMIT ?
            """,
            (*statuses, limit),
        ).fetchall()


def count_by_statuses(statuses):
    status_placeholders = _placeholders(statuses)
    with get_connection() as conn:
        return conn.execute(
            f"""
            SELECT COUNT(*)
            FROM manual_payments
            WHERE status IN ({status_placeholders})
            """,
            tuple(statuses),
        ).fetchone()


def get_latest_for_user_by_statuses(telegram_id, statuses):
    status_placeholders = _placeholders(statuses)
    with get_connection() as conn:
        return conn.execute(
            f"""
            SELECT *
            FROM manual_payments
            WHERE telegram_id = ?
              AND status IN ({status_placeholders})
            ORDER BY id DESC
            LIMIT 1
            """,
            (telegram_id, *statuses),
        ).fetchone()


def mark_waiting_admin(order_id, status, user_message_id, updated_at, expected_status):
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
            (status, user_message_id, updated_at, order_id, expected_status),
        )
        return cursor.rowcount > 0


def reset_waiting_admin(order_id, status, updated_at, expected_status):
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE manual_payments
            SET status = ?,
                updated_at = ?
            WHERE order_id = ?
              AND status = ?
            """,
            (status, updated_at, order_id, expected_status),
        )


def cancel_pending(order_id, status, cancelled_at, updated_at, expected_status):
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
            (status, cancelled_at, updated_at, order_id, expected_status),
        )
        return cursor.rowcount > 0


def mark_reminded(order_id, reminded_at, updated_at, expected_status):
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
            (reminded_at, updated_at, order_id, expected_status),
        )
        return cursor.rowcount > 0


def attach_receipt(
    order_id,
    status,
    receipt_file_id,
    receipt_unique_id,
    user_message_id,
    updated_at,
    allowed_statuses,
):
    status_placeholders = _placeholders(allowed_statuses)
    with get_connection() as conn:
        conn.execute(
            f"""
            UPDATE manual_payments
            SET status = ?,
                receipt_file_id = ?,
                receipt_unique_id = ?,
                user_message_id = ?,
                updated_at = ?
            WHERE order_id = ?
              AND status IN ({status_placeholders})
            """,
            (
                status,
                receipt_file_id,
                receipt_unique_id,
                user_message_id,
                updated_at,
                order_id,
                *allowed_statuses,
            ),
        )


def start_processing(order_id, status, admin_id, updated_at, allowed_statuses):
    status_placeholders = _placeholders(allowed_statuses)
    with get_connection() as conn:
        cursor = conn.execute(
            f"""
            UPDATE manual_payments
            SET status = ?,
                approved_by = ?,
                updated_at = ?
            WHERE order_id = ?
              AND status IN ({status_placeholders})
            """,
            (status, admin_id, updated_at, order_id, *allowed_statuses),
        )
        return cursor.rowcount > 0


def reopen_processing(order_id, status, updated_at, expected_status):
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE manual_payments
            SET status = ?,
                approved_by = NULL,
                updated_at = ?
            WHERE order_id = ?
              AND status = ?
            """,
            (status, updated_at, order_id, expected_status),
        )


def mark_approved(order_id, status, admin_id, approved_at, updated_at, expected_status):
    with get_connection() as conn:
        cursor = conn.execute(
            """
            UPDATE manual_payments
            SET status = ?,
                approved_by = ?,
                approved_at = ?,
                updated_at = ?
            WHERE order_id = ?
              AND status = ?
            """,
            (status, admin_id, approved_at, updated_at, order_id, expected_status),
        )
        return cursor.rowcount > 0
