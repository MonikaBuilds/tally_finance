import uuid
from dataclasses import dataclass

from app.security.user_store import _connect


@dataclass(frozen=True)
class StoredOrganization:
    organization_id: str
    organization_name: str
    is_active: bool

def initialize_organization_store() -> None:
    """
    Create the organizations table if it does not exist.
    """
    connection = _connect()
    cursor = connection.cursor()

    try:
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS organizations (
                organization_id VARCHAR(100) PRIMARY KEY,
                organization_name VARCHAR(255) NOT NULL UNIQUE,
                is_active BOOLEAN NOT NULL DEFAULT TRUE
            )
            """
        )

        connection.commit()

    finally:
        cursor.close()
        connection.close()
        
def create_organization(
    organization_name: str,
) -> str:
    """
    Create a new organization.

    The organization ID is generated automatically
    using Python's UUID implementation.
    """
    clean_name = organization_name.strip()

    if not clean_name:
        raise ValueError(
            "organization name is required"
        )

    organization_id = str(uuid.uuid4())

    connection = _connect()
    cursor = connection.cursor()

    try:
        cursor.execute(
            """
            INSERT INTO organizations (
                organization_id,
                organization_name,
                is_active
            )
            VALUES (%s, %s, 1)
            """,
            (
                organization_id,
                clean_name,
            ),
        )

        connection.commit()

        return organization_id

    except Exception:
        connection.rollback()
        raise

    finally:
        cursor.close()
        connection.close()


def get_organization(
    organization_id: str,
) -> StoredOrganization | None:
    """
    Return an organization by its ID.
    """
    clean_id = organization_id.strip()

    if not clean_id:
        return None

    connection = _connect()
    cursor = connection.cursor(
        dictionary=True
    )

    try:
        cursor.execute(
            """
            SELECT
                organization_id,
                organization_name,
                is_active
            FROM organizations
            WHERE organization_id = %s
            """,
            (clean_id,),
        )

        row = cursor.fetchone()

    finally:
        cursor.close()
        connection.close()

    if row is None:
        return None

    return StoredOrganization(
        organization_id=row["organization_id"],
        organization_name=row["organization_name"],
        is_active=bool(row["is_active"]),
    )