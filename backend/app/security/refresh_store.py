import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from app.security.db import get_connection


@dataclass(frozen=True)
class RefreshSession:
    session_id: str
    user_id: str
    expires_at: datetime
    revoked_at: datetime | None


def hash_refresh_token(token: str) -> str:
    """
    Create a one-way SHA-256 hash of a refresh token.

    The raw refresh token must never be stored in MySQL.
    """
    return hashlib.sha256(
        token.encode("utf-8")
    ).hexdigest()


def generate_refresh_token() -> str:
    """
    Generate a cryptographically secure refresh token.
    """
    return secrets.token_urlsafe(64)


def initialize_refresh_store() -> None:
    """
    Create the refresh_sessions table when it does not exist.
    """

    connection = get_connection()
    cursor = connection.cursor()

    try:
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS refresh_sessions (
                session_id VARCHAR(100) PRIMARY KEY,
                user_id VARCHAR(100) NOT NULL,
                token_hash CHAR(64) NOT NULL UNIQUE,
                expires_at DATETIME NOT NULL,
                revoked_at DATETIME NULL,
                created_at DATETIME NOT NULL
                    DEFAULT CURRENT_TIMESTAMP,

                CONSTRAINT fk_refresh_sessions_user
                    FOREIGN KEY (user_id)
                    REFERENCES users(user_id)
                    ON DELETE CASCADE
            )
            """
        )

        connection.commit()

    except Exception:
        connection.rollback()
        raise

    finally:
        cursor.close()
        connection.close()


def create_refresh_session(
    *,
    user_id: str,
    token: str,
    expires_at: datetime,
) -> str:
    """
    Store a new refresh session.

    Only the token hash is stored.
    """

    session_id = str(uuid.uuid4())
    token_hash = hash_refresh_token(token)

    connection = get_connection()
    cursor = connection.cursor()

    try:
        cursor.execute(
            """
            INSERT INTO refresh_sessions (
                session_id,
                user_id,
                token_hash,
                expires_at,
                revoked_at
            )
            VALUES (%s, %s, %s, %s, NULL)
            """,
            (
                session_id,
                user_id,
                token_hash,
                expires_at,
            ),
        )

        connection.commit()

        return session_id

    except Exception:
        connection.rollback()
        raise

    finally:
        cursor.close()
        connection.close()


def get_refresh_session(
    token: str,
) -> RefreshSession | None:
    """
    Return an active refresh session matching
    the supplied token.

    Expired or revoked sessions are rejected.
    """

    token_hash = hash_refresh_token(token)

    connection = get_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute(
            """
            SELECT
                session_id,
                user_id,
                expires_at,
                revoked_at
            FROM refresh_sessions
            WHERE token_hash = %s
            LIMIT 1
            """,
            (token_hash,),
        )

        row = cursor.fetchone()

    finally:
        cursor.close()
        connection.close()

    if row is None:
        return None

    if row["revoked_at"] is not None:
        return None

    expires_at = row["expires_at"]

    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(
            tzinfo=timezone.utc
        )

    if expires_at <= datetime.now(timezone.utc):
        return None

    return RefreshSession(
        session_id=row["session_id"],
        user_id=row["user_id"],
        expires_at=expires_at,
        revoked_at=row["revoked_at"],
    )


def revoke_refresh_session(
    token: str,
) -> bool:
    """
    Revoke the refresh session matching the supplied token.
    """

    token_hash = hash_refresh_token(token)

    connection = get_connection()
    cursor = connection.cursor()

    try:
        cursor.execute(
            """
            UPDATE refresh_sessions
            SET revoked_at = UTC_TIMESTAMP()
            WHERE token_hash = %s
              AND revoked_at IS NULL
            """,
            (token_hash,),
        )

        revoked = cursor.rowcount > 0

        connection.commit()

        return revoked

    except Exception:
        connection.rollback()
        raise

    finally:
        cursor.close()
        connection.close()


def rotate_refresh_session(
    *,
    old_token: str,
    new_token: str,
    expires_at: datetime,
) -> RefreshSession | None:
    """
    Atomically rotate an active refresh session.

    The old session is locked and validated, then revoked.
    A replacement session is created in the same transaction.

    If any operation fails, the complete transaction
    is rolled back.
    """

    old_token_hash = hash_refresh_token(
        old_token
    )

    new_token_hash = hash_refresh_token(
        new_token
    )

    new_session_id = str(uuid.uuid4())

    connection = get_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        connection.start_transaction()

        cursor.execute(
            """
            SELECT
                session_id,
                user_id,
                expires_at,
                revoked_at
            FROM refresh_sessions
            WHERE token_hash = %s
            LIMIT 1
            FOR UPDATE
            """,
            (old_token_hash,),
        )

        row = cursor.fetchone()

        if row is None:
            connection.rollback()
            return None

        if row["revoked_at"] is not None:
            connection.rollback()
            return None

        old_expires_at = row["expires_at"]

        if old_expires_at.tzinfo is None:
            old_expires_at = old_expires_at.replace(
                tzinfo=timezone.utc
            )

        if old_expires_at <= datetime.now(timezone.utc):
            connection.rollback()
            return None

        cursor.execute(
            """
            UPDATE refresh_sessions
            SET revoked_at = UTC_TIMESTAMP()
            WHERE session_id = %s
              AND revoked_at IS NULL
            """,
            (row["session_id"],),
        )

        if cursor.rowcount != 1:
            connection.rollback()
            return None

        cursor.execute(
            """
            INSERT INTO refresh_sessions (
                session_id,
                user_id,
                token_hash,
                expires_at,
                revoked_at
            )
            VALUES (%s, %s, %s, %s, NULL)
            """,
            (
                new_session_id,
                row["user_id"],
                new_token_hash,
                expires_at,
            ),
        )

        connection.commit()

        return RefreshSession(
            session_id=new_session_id,
            user_id=row["user_id"],
            expires_at=expires_at,
            revoked_at=None,
        )

    except Exception:
        connection.rollback()
        raise

    finally:
        cursor.close()
        connection.close()