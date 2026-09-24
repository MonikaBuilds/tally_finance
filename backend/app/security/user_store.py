import os
import uuid
from dataclasses import dataclass

import mysql.connector
from dotenv import load_dotenv

from app.security.passwords import hash_password, verify_password


load_dotenv()


@dataclass(frozen=True)
class StoredUser:
    user_id: str
    username: str
    password_hash: str
    is_active: bool


def _connect():
    return mysql.connector.connect(
        host=os.getenv("DB_HOST"),
        port=int(os.getenv("DB_PORT", "3306")),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        database=os.getenv("DB_NAME"),
    )


def initialize_user_store() -> None:
    connection = _connect()
    cursor = connection.cursor()

    try:
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id VARCHAR(100) PRIMARY KEY,
                username VARCHAR(255) NOT NULL UNIQUE,
                password_hash VARCHAR(255) NOT NULL,
                is_active BOOLEAN NOT NULL DEFAULT TRUE,
                organization_id VARCHAR(100) NOT NULL,

                CONSTRAINT fk_users_organization
                    FOREIGN KEY (organization_id)
                    REFERENCES organizations(organization_id)
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS user_companies (
                user_id VARCHAR(100) NOT NULL,
                company_name VARCHAR(255) NOT NULL,

                PRIMARY KEY (
                    user_id,
                    company_name
                ),

                CONSTRAINT fk_user_companies_user
                    FOREIGN KEY (user_id)
                    REFERENCES users(user_id)
                    ON DELETE CASCADE
            )
            """
        )

        connection.commit()

    finally:
        cursor.close()
        connection.close()


def create_user(
    *,
    username: str,
    password: str,
    companies: list[str],
    organization_id: str,
) -> str:
    clean_user_id = str(uuid.uuid4())
    clean_username = username.strip()
    clean_organization_id = organization_id.strip()

    if not clean_username:
        raise ValueError("username is required")

    if not clean_organization_id:
        raise ValueError(
            "organization_id is required"
        )
    if len(password) < 8:
        raise ValueError(
            "password must be at least 8 characters"
        )

    clean_companies = sorted(
        {
            company.strip()
            for company in companies
            if company.strip()
        }
    )

    if not clean_companies:
        raise ValueError(
            "at least one company is required"
        )

    password_hash = hash_password(password)

    connection = _connect()
    cursor = connection.cursor()

    try:
        cursor.execute(
            """
            INSERT INTO users (
                user_id,
                username,
                password_hash,
                is_active,
                organization_id
            )
            VALUES (%s, %s, %s, 1, %s)
            """,
            (
                clean_user_id,
                clean_username,
                password_hash,
                clean_organization_id,
            ),
        )

        cursor.executemany(
            """
            INSERT INTO user_companies (
                user_id,
                company_name
            )
            VALUES (%s, %s)
            """,
            [
                (
                    clean_user_id,
                    company_name,
                )
                for company_name in clean_companies
            ],
        )

        connection.commit()

        return clean_user_id

    except Exception:
        connection.rollback()
        raise

    finally:
        cursor.close()
        connection.close()

def delete_user(
    user_id: str,
) -> bool:
    """
    Delete a user from MySQL.

    Related company, role, and permission assignments
    are removed through foreign-key cascade rules.

    Returns True when a user was deleted.
    Returns False when the user does not exist.
    """
    clean_user_id = user_id.strip()

    if not clean_user_id:
        return False

    connection = _connect()
    cursor = connection.cursor()

    try:
        cursor.execute(
            """
            DELETE FROM users
            WHERE user_id = %s
            """,
            (clean_user_id,),
        )

        deleted = cursor.rowcount > 0

        connection.commit()

        return deleted

    except Exception:
        connection.rollback()
        raise

    finally:
        cursor.close()
        connection.close()

def set_user_active_status(
    user_id: str,
    is_active: bool,
) -> bool:
    """
    Activate or deactivate a user without deleting the account.

    Returns True when the user exists and was updated.
    Returns False when the user does not exist.
    """
    clean_user_id = user_id.strip()

    if not clean_user_id:
        return False

    connection = _connect()
    cursor = connection.cursor()

    try:
        cursor.execute(
            """
            UPDATE users
            SET is_active = %s
            WHERE user_id = %s
            """,
            (
                is_active,
                clean_user_id,
            ),
        )

        updated = cursor.rowcount > 0

        connection.commit()

        return updated

    except Exception:
        connection.rollback()
        raise

    finally:
        cursor.close()
        connection.close()

def get_user_by_username(
    username: str,
) -> StoredUser | None:
    clean_username = username.strip()

    if not clean_username:
        return None

    connection = _connect()
    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute(
            """
            SELECT
                user_id,
                username,
                password_hash,
                is_active
            FROM users
            WHERE username = %s
            """,
            (clean_username,),
        )

        row = cursor.fetchone()

    finally:
        cursor.close()
        connection.close()

    if row is None:
        return None

    return StoredUser(
        user_id=row["user_id"],
        username=row["username"],
        password_hash=row["password_hash"],
        is_active=bool(row["is_active"]),
    )


def get_user_organization_id(
    user_id: str,
) -> str | None:
    """
    Return the organization ID assigned to a user.
    """
    clean_user_id = user_id.strip()

    if not clean_user_id:
        return None

    connection = _connect()
    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute(
            """
            SELECT organization_id
            FROM users
            WHERE user_id = %s
            """,
            (clean_user_id,),
        )

        row = cursor.fetchone()

    finally:
        cursor.close()
        connection.close()

    if row is None:
        return None

    return row["organization_id"]

def get_all_users(
    organization_id: str,
) -> list[dict]:
    """
    Return users belonging to one organization.

    Password hashes are intentionally not returned.
    """
    clean_organization_id = organization_id.strip()

    if not clean_organization_id:
        return []

    connection = _connect()
    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute(
            """
            SELECT
                user_id,
                username,
                is_active
            FROM users
            WHERE organization_id = %s
            ORDER BY username
            """,
            (clean_organization_id,),
        )

        rows = cursor.fetchall()

    finally:
        cursor.close()
        connection.close()

    return [
        {
            "user_id": row["user_id"],
            "username": row["username"],
            "is_active": bool(row["is_active"]),
        }
        for row in rows
    ]

def user_belongs_to_organization(
    user_id: str,
    organization_id: str,
) -> bool:
    """
    Return True only when the user belongs to
    the specified organization.
    """
    clean_user_id = user_id.strip()
    clean_organization_id = organization_id.strip()

    if not clean_user_id or not clean_organization_id:
        return False

    connection = _connect()
    cursor = connection.cursor()

    try:
        cursor.execute(
            """
            SELECT 1
            FROM users
            WHERE user_id = %s
              AND organization_id = %s
            LIMIT 1
            """,
            (
                clean_user_id,
                clean_organization_id,
            ),
        )

        return cursor.fetchone() is not None

    finally:
        cursor.close()
        connection.close()

def get_user_companies(
    user_id: str,
) -> tuple[str, ...]:
    connection = _connect()
    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute(
            """
            SELECT company_name
            FROM user_companies
            WHERE user_id = %s
            ORDER BY company_name
            """,
            (user_id,),
        )

        rows = cursor.fetchall()

    finally:
        cursor.close()
        connection.close()

    return tuple(
        row["company_name"]
        for row in rows
    )


def authenticate_user(
    username: str,
    password: str,
) -> tuple[StoredUser, tuple[str, ...]] | None:
    user = get_user_by_username(username)

    if user is None:
        return None

    if not user.is_active:
        return None

    if not verify_password(
        password,
        user.password_hash,
    ):
        return None

    companies = get_user_companies(
        user.user_id
    )

    return user, companies


def update_user_password(
    username: str,
    new_password: str,
) -> None:
    clean_username = username.strip()

    if not clean_username:
        raise ValueError("username is required")

    if len(new_password) < 8:
        raise ValueError(
            "password must be at least 8 characters"
        )

    password_hash = hash_password(new_password)

    connection = _connect()
    cursor = connection.cursor()

    try:
        cursor.execute(
            """
            UPDATE users
            SET password_hash = %s
            WHERE username = %s
            """,
            (
                password_hash,
                clean_username,
            ),
        )

        if cursor.rowcount == 0:
            raise ValueError(
                "user does not exist"
            )

        connection.commit()

    except Exception:
        connection.rollback()
        raise

    finally:
        cursor.close()
        connection.close()
