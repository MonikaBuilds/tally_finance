import logging
import os
import uuid
from dataclasses import dataclass

from app.security.db import get_connection
from dotenv import load_dotenv

from app.security.passwords import hash_password, verify_password

logger = logging.getLogger(__name__)

load_dotenv()

# Precomputed dummy hash for constant-time comparison when username does not exist.
# Prevents side-channel timing attacks that allow username enumeration.
_DUMMY_PASSWORD_HASH = hash_password("dummy-defense-timing-salt")


@dataclass(frozen=True)
class StoredUser:
    user_id: str
    username: str
    password_hash: str
    is_active: bool


def initialize_user_store() -> None:
    connection = get_connection()
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


def bootstrap_initial_admin() -> str | None:
    """
    Bootstrap an initial administrator account on first boot
    if no users currently exist in the database.

    Reads configuration from environment variables:
    - INITIAL_ADMIN_USERNAME (default: 'admin')
    - INITIAL_ADMIN_PASSWORD (default: 'Admin@2026!')
    - INITIAL_ADMIN_COMPANY (default: 'ABC Pvt Ltd')
    - INITIAL_ADMIN_ORG_ID (default: 'e7747b1f-36c9-4ea1-85d9-965f5c55d679')

    Assigns 'superadmin' and 'admin' roles, and grants all default
    permissions ('financial', 'inventory', 'banking', 'tax').

    Returns the created user_id, or None if users already exist.
    """
    connection = get_connection()
    cursor = connection.cursor()

    try:
        cursor.execute("SELECT COUNT(*) FROM users")
        row = cursor.fetchone()
        user_count = row[0] if row else 0

        if user_count > 0:
            logger.debug(
                "Users already exist in the database (%s users). Skipping initial admin bootstrap.",
                user_count,
            )
            return None

        # Resolve organization_id
        target_org = os.getenv(
            "INITIAL_ADMIN_ORG_ID",
            "e7747b1f-36c9-4ea1-85d9-965f5c55d679",
        ).strip()
        cursor.execute(
            "SELECT organization_id FROM organizations WHERE organization_id = %s LIMIT 1",
            (target_org,),
        )
        org_row = cursor.fetchone()
        if org_row:
            org_id = org_row[0]
        else:
            cursor.execute(
                "SELECT organization_id FROM organizations ORDER BY organization_id LIMIT 1"
            )
            first_org = cursor.fetchone()
            org_id = first_org[0] if first_org else "default"

    finally:
        cursor.close()
        connection.close()

    admin_username = os.getenv("INITIAL_ADMIN_USERNAME", "admin").strip() or "admin"
    admin_password = os.getenv("INITIAL_ADMIN_PASSWORD", "Admin@2026!").strip() or "Admin@2026!"
    admin_company = os.getenv("INITIAL_ADMIN_COMPANY", "ABC Pvt Ltd").strip() or "ABC Pvt Ltd"

    user_id = create_user(
        username=admin_username,
        password=admin_password,
        companies=[admin_company],
        organization_id=org_id,
    )

    # Assign roles and default permissions
    from app.security.permissions import (
        assign_permission_to_user,
        assign_role_to_user,
    )

    assign_role_to_user(user_id, "superadmin")
    assign_role_to_user(user_id, "admin")

    for perm in ("financial", "inventory", "banking", "tax"):
        assign_permission_to_user(user_id, perm)

    logger.info(
        "Successfully bootstrapped initial admin user: %s (id: %s)",
        admin_username,
        user_id,
    )
    return user_id


def create_user(
    *,
    user_id: str | None = None,
    username: str,
    password: str,
    companies: list[str],
    organization_id: str = "default",
) -> str:
    clean_user_id = user_id.strip() if user_id and user_id.strip() else str(uuid.uuid4())
    clean_username = username.strip()
    clean_organization_id = (organization_id or "default").strip() or "default"

    if not clean_username:
        raise ValueError("username is required")
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

    connection = get_connection()
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

    connection = get_connection()
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

    connection = get_connection()
    cursor = connection.cursor()

    try:
        cursor.execute(
            """
            SELECT 1 FROM users WHERE user_id = %s LIMIT 1
            """,
            (clean_user_id,),
        )
        if cursor.fetchone() is None:
            return False

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

        connection.commit()

        if not is_active:
            from app.security.refresh_store import revoke_all_user_sessions
            revoke_all_user_sessions(clean_user_id)

        return True

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

    connection = get_connection()
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

def get_user_by_id(
    user_id: str,
) -> StoredUser | None:
    """
    Return a user by user ID.
    """

    clean_user_id = user_id.strip()

    if not clean_user_id:
        return None

    connection = get_connection()
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

    if clean_user_id == "development-user":
        return "default"

    connection = get_connection()
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
        return "default"

    return row["organization_id"] or "default"

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

    connection = get_connection()
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

    connection = get_connection()
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
    connection = get_connection()
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


def set_user_companies(
    user_id: str,
    companies: list[str],
) -> tuple[str, ...]:
    """
    Replace the company assignments for an existing user.

    Validates that:
    - user_id is provided and user exists.
    - At least one valid company name is provided.

    Atomically deletes old assignments in user_companies and inserts new ones.
    Revokes any active refresh sessions for the user so subsequent requests
    must refresh/re-authenticate with the updated company scope.

    Returns the updated tuple of company names.
    """
    clean_user_id = user_id.strip() if user_id else ""
    if not clean_user_id:
        raise ValueError("user_id is required")

    clean_companies = sorted(
        {
            company.strip()
            for company in companies
            if company.strip()
        }
    )
    if not clean_companies:
        raise ValueError("at least one company is required")

    connection = get_connection()
    cursor = connection.cursor()

    try:
        cursor.execute(
            "SELECT 1 FROM users WHERE user_id = %s LIMIT 1",
            (clean_user_id,),
        )
        if cursor.fetchone() is None:
            raise ValueError("user does not exist")

        cursor.execute(
            "DELETE FROM user_companies WHERE user_id = %s",
            (clean_user_id,),
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
                (clean_user_id, comp)
                for comp in clean_companies
            ],
        )

        connection.commit()

        # Invalidate active refresh sessions so client tokens are synchronized
        from app.security.refresh_store import revoke_all_user_sessions
        revoke_all_user_sessions(clean_user_id)

        return tuple(clean_companies)

    except Exception:
        connection.rollback()
        raise

    finally:
        cursor.close()
        connection.close()


def authenticate_user(
    username: str,
    password: str,
) -> tuple[StoredUser, tuple[str, ...]] | None:
    user = get_user_by_username(username)

    if user is None:
        # Constant-time mitigation: calculate dummy PBKDF2 hash
        # so response time does not reveal whether username exists.
        verify_password(password, _DUMMY_PASSWORD_HASH)
        return None

    if not user.is_active:
        verify_password(password, user.password_hash)
        logger.warning("Authentication failed: User '%s' is inactive.", username)
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
    username: str | None = None,
    new_password: str = "",
    *,
    user_id: str | None = None,
) -> str:
    """
    Update a user's password in MySQL and immediately invalidate
    all active refresh sessions for the account.

    Can be called with either `username` or `user_id`.
    Returns the resolved `user_id`.
    """
    if len(new_password) < 8:
        raise ValueError(
            "password must be at least 8 characters"
        )

    clean_username = username.strip() if username else None
    clean_user_id = user_id.strip() if user_id else None

    if not clean_username and not clean_user_id:
        raise ValueError("username or user_id is required")

    password_hash = hash_password(new_password)

    connection = get_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        if clean_user_id:
            cursor.execute(
                "SELECT user_id, username FROM users WHERE user_id = %s LIMIT 1",
                (clean_user_id,),
            )
        else:
            cursor.execute(
                "SELECT user_id, username FROM users WHERE username = %s LIMIT 1",
                (clean_username,),
            )

        row = cursor.fetchone()
        if row is None:
            raise ValueError("user does not exist")

        resolved_user_id = row["user_id"]

        cursor.execute(
            """
            UPDATE users
            SET password_hash = %s
            WHERE user_id = %s
            """,
            (
                password_hash,
                resolved_user_id,
            ),
        )

        connection.commit()

        # Invalidate all active refresh sessions for the user
        from app.security.refresh_store import revoke_all_user_sessions
        revoke_all_user_sessions(resolved_user_id)

        return resolved_user_id

    except Exception:
        connection.rollback()
        raise

    finally:
        cursor.close()
        connection.close()
