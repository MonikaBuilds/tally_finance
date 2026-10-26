from fastapi import Depends, HTTPException, status

from app.security.auth import (
    UserContext,
    get_current_user,
)
from app.security.db import get_connection


def has_role(
    user_id: str,
    role_name: str,
) -> bool:
    """
    Return True when the user has the requested role.
    """
    clean_user_id = user_id.strip()
    clean_role_name = role_name.strip()

    if not clean_user_id or not clean_role_name:
        return False

    connection = get_connection()
    cursor = connection.cursor()

    try:
        cursor.execute(
            """
            SELECT 1
            FROM user_roles ur
            INNER JOIN roles r
                ON r.role_id = ur.role_id
            WHERE ur.user_id = %s
              AND r.role_name = %s
            LIMIT 1
            """,
            (
                clean_user_id,
                clean_role_name,
            ),
        )

        return cursor.fetchone() is not None

    finally:
        cursor.close()
        connection.close()


def is_superadmin(
    user_id: str,
) -> bool:
    """
    Return True when the user has the superadmin role.
    """
    return has_role(
        user_id,
        "superadmin",
    )


def is_admin(
    user_id: str,
) -> bool:
    """
    Return True when the user has the admin role.
    """
    return has_role(
        user_id,
        "admin",
    )

def can_manage_role(
    manager_user_id: str,
    target_role_name: str,
) -> bool:
    """
    Return True when the manager is allowed
    to create a user with the requested role.

    Superadmin may create admin or user.
    Admin may create user only.
    """
    clean_role_name = target_role_name.strip()

    if not clean_role_name:
        return False

    if is_superadmin(manager_user_id):
        return clean_role_name in {
            "admin",
            "user",
        }

    if is_admin(manager_user_id):
        return clean_role_name == "user"

    return False

async def require_admin(
    current_user: UserContext = Depends(get_current_user),
) -> UserContext:
    """
    Require the authenticated user to have the admin role.

    Authentication is handled by get_current_user().
    Admin authorization is resolved dynamically from MySQL.
    """
    if not (
        is_superadmin(current_user.user_id)
        or is_admin(current_user.user_id)
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator access required.",
        )

    return current_user

def get_all_permissions() -> list[dict]:
    """
    Return all available permissions from MySQL.
    """
    connection = get_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute(
            """
            SELECT
                permission_id,
                permission_code,
                permission_name,
                category,
                subcategory,
                description
            FROM permissions
            ORDER BY category, permission_name
            """
        )

        return cursor.fetchall()

    finally:
        cursor.close()
        connection.close()

def get_user_access(user_id: str) -> dict:
    """
    Return a user's assigned roles and direct permissions.
    """
    if not user_id:
        return {
            "roles": [],
            "permissions": [],
        }

    connection = get_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute(
            """
            SELECT r.role_name
            FROM user_roles ur
            INNER JOIN roles r
                ON r.role_id = ur.role_id
            WHERE ur.user_id = %s
            ORDER BY r.role_name
            """,
            (user_id,),
        )

        role_rows = cursor.fetchall()

        cursor.execute(
            """
            SELECT p.permission_code
            FROM user_permissions up
            INNER JOIN permissions p
                ON p.permission_id = up.permission_id
            WHERE up.user_id = %s
            ORDER BY p.permission_code
            """,
            (user_id,),
        )

        permission_rows = cursor.fetchall()

    finally:
        cursor.close()
        connection.close()

    return {
        "roles": [
            row["role_name"]
            for row in role_rows
        ],
        "permissions": [
            row["permission_code"]
            for row in permission_rows
        ],
    }

def get_all_roles() -> list[dict]:
    """
    Return all roles stored in MySQL.
    """
    connection = get_connection()
    cursor = connection.cursor(
        dictionary=True
    )

    try:
        cursor.execute(
            """
            SELECT
                role_id,
                role_name
            FROM roles
            ORDER BY role_name
            """
        )

        return cursor.fetchall()

    finally:
        cursor.close()
        connection.close()
        
def role_exists(role_name: str) -> bool:
    """
    Return True when the role exists in MySQL.
    """
    if not role_name:
        return False

    connection = get_connection()
    cursor = connection.cursor()

    try:
        cursor.execute(
            """
            SELECT 1
            FROM roles
            WHERE role_name = %s
            LIMIT 1
            """,
            (role_name,),
        )

        return cursor.fetchone() is not None

    finally:
        cursor.close()
        connection.close()
        
def assign_role_to_user(
    user_id: str,
    role_name: str,
) -> bool:
    """
    Assign an existing role to an existing user.

    Returns True when the role is assigned.
    Returns False when the user or role does not exist.
    """
    if not user_id or not role_name:
        return False

    connection = get_connection()
    cursor = connection.cursor()

    try:
        cursor.execute(
            """
            SELECT 1
            FROM users
            WHERE user_id = %s
            LIMIT 1
            """,
            (user_id,),
        )

        if cursor.fetchone() is None:
            return False

        cursor.execute(
            """
            SELECT role_id
            FROM roles
            WHERE role_name = %s
            LIMIT 1
            """,
            (role_name,),
        )

        row = cursor.fetchone()

        if row is None:
            return False

        role_id = row[0]

        cursor.execute(
            """
            INSERT IGNORE INTO user_roles (
                user_id,
                role_id
            )
            VALUES (%s, %s)
            """,
            (
                user_id,
                role_id,
            ),
        )

        connection.commit()
        return True

    except Exception:
        connection.rollback()
        raise

    finally:
        cursor.close()
        connection.close()


def remove_role_from_user(
    user_id: str,
    role_name: str,
) -> bool:
    """
    Remove an assigned role from an existing user.

    Returns True when the role assignment was removed.
    Returns False when the user or role does not exist or was not assigned.
    """
    if not user_id or not role_name:
        return False

    connection = get_connection()
    cursor = connection.cursor()

    try:
        cursor.execute(
            """
            DELETE ur FROM user_roles ur
            JOIN roles r ON ur.role_id = r.role_id
            WHERE ur.user_id = %s
              AND r.role_name = %s
            """,
            (
                user_id,
                role_name,
            ),
        )

        removed = cursor.rowcount > 0
        connection.commit()
        return removed

    except Exception:
        connection.rollback()
        raise

    finally:
        cursor.close()
        connection.close()

  
      
def assign_permission_to_user(
    user_id: str,
    permission_code: str,
) -> bool:
    """
    Assign a permission to a user.

    Returns True when the permission is assigned.
    Returns False when the user or permission does not exist.
    """
    if not user_id or not permission_code:
        return False

    connection = get_connection()
    cursor = connection.cursor()

    try:
        # Verify that the user exists.
        cursor.execute(
            """
            SELECT 1
            FROM users
            WHERE user_id = %s
            LIMIT 1
            """,
            (user_id,),
        )

        if cursor.fetchone() is None:
            return False

        # Find the requested permission.
        cursor.execute(
            """
            SELECT permission_id
            FROM permissions
            WHERE permission_code = %s
            LIMIT 1
            """,
            (permission_code,),
        )

        row = cursor.fetchone()

        if row is None:
            return False

        permission_id = row[0]

        # Assign the permission.
        # Duplicate assignments are safely ignored.
        cursor.execute(
            """
            INSERT IGNORE INTO user_permissions (
                user_id,
                permission_id
            )
            VALUES (%s, %s)
            """,
            (
                user_id,
                permission_id,
            ),
        )

        connection.commit()

        return True

    except Exception:
        connection.rollback()
        raise

    finally:
        cursor.close()
        connection.close()
    
def remove_permission_from_user(
    user_id: str,
    permission_code: str,
) -> bool:
    """
    Remove a directly assigned permission from a user.

    Returns True when a permission assignment was removed.
    Returns False when no matching assignment exists.
    """
    if not user_id or not permission_code:
        return False

    connection = get_connection()
    cursor = connection.cursor()

    try:
        cursor.execute(
            """
            DELETE up
            FROM user_permissions up
            INNER JOIN permissions p
                ON p.permission_id = up.permission_id
            WHERE up.user_id = %s
              AND p.permission_code = %s
            """,
            (
                user_id,
                permission_code,
            ),
        )

        removed = cursor.rowcount > 0

        connection.commit()

        return removed

    except Exception:
        connection.rollback()
        raise

    finally:
        cursor.close()
        connection.close()
        
def get_required_permission(
    tool_name: str,
) -> str | None:
    """
    Return the permission code required by a tool.

    Example:
        get_profit_loss -> financial
        get_stock_summary -> inventory
    """
    if not tool_name:
        return None

    connection = get_connection()
    cursor = connection.cursor()

    try:
        cursor.execute(
            """
            SELECT p.permission_code
            FROM tool_permissions tp
            INNER JOIN permissions p
                ON p.permission_id = tp.permission_id
            WHERE tp.tool_name = %s
            LIMIT 1
            """,
            (tool_name,),
        )

        row = cursor.fetchone()

    finally:
        cursor.close()
        connection.close()

    if row is None:
        return None

    return row[0]


def user_has_permission(
    user_id: str,
    permission_code: str,
) -> bool:
    """
    Return True when the user has the requested
    permission assigned in MySQL.
    """
    if not user_id or not permission_code:
        return False

    if is_superadmin(user_id):
        return True

    connection = get_connection()
    cursor = connection.cursor()

    try:
        cursor.execute(
            """
            SELECT 1
            FROM user_permissions up
            INNER JOIN permissions p
                ON p.permission_id = up.permission_id
            WHERE up.user_id = %s
              AND p.permission_code = %s
            LIMIT 1
            """,
            (
                user_id,
                permission_code,
            ),
        )

        return cursor.fetchone() is not None

    finally:
        cursor.close()
        connection.close()


def can_execute_tool(
    user_id: str,
    tool_name: str,
) -> bool:
    """
    Decide whether a user may execute a chatbot tool.

    Superadmin may execute every mapped tool.

    Admin and normal users require the permission
    assigned to the requested tool.

    Unknown or unmapped tools are denied.
    """
    if not user_id or not tool_name:
        return False

    # Fail closed: every executable tool must have
    # an explicit permission mapping.
    required_permission = get_required_permission(
        tool_name
    )

    if required_permission is None:
        return False

    # Superadmin has full access to mapped tools.
    if is_superadmin(user_id):
        return True

    # Admin and User must have the permission
    # required by this tool.
    return user_has_permission(
        user_id,
        required_permission,
    )


DEFAULT_ROLES: tuple[str, ...] = ("admin", "user", "superadmin")

DEFAULT_PERMISSIONS: tuple[tuple[str, str, str, str, str], ...] = (
    ("financial", "Financial", "Accounting", "Financial Reports", "Access financial reports, profitability, expenses, trends, receivables and payables."),
    ("inventory", "Inventory / Stock", "Inventory", "Stock Management", "Access stock summaries, stock items, stock details, stock movement and inventory analysis."),
    ("banking", "Banking", "Banking", "Bank and Cash", "Access bank accounts, cash and bank transactions, balances and related banking information."),
    ("tax", "Tax / TDS", "Taxation", "TDS and GST", "Access TDS, GST and other supported tax-related information."),
)

DEFAULT_TOOL_PERMISSIONS: dict[str, str] = {
    # financial
    "get_aged_payables": "financial",
    "get_aged_receivables": "financial",
    "get_balance_sheet": "financial",
    "get_company_comparison": "financial",
    "get_cost_centre_analysis": "financial",
    "get_credit_note_transactions": "financial",
    "get_customer_profitability": "financial",
    "get_customer_statement": "financial",
    "get_debit_note_transactions": "financial",
    "get_expenses": "financial",
    "get_financial_summary": "financial",
    "get_financial_trends": "financial",
    "get_highest_payable": "financial",
    "get_highest_receivable": "financial",
    "get_invoice_details": "financial",
    "get_invoice_status": "financial",
    "get_ledger_balance": "financial",
    "get_ledger_report": "financial",
    "get_ledger_transactions": "financial",
    "get_net_profit": "financial",
    "get_outstanding_summary": "financial",
    "get_overdue_invoices": "financial",
    "get_overdue_payables": "financial",
    "get_overdue_receivables": "financial",
    "get_party_outstanding_summary": "financial",
    "get_party_statement": "financial",
    "get_payables": "financial",
    "get_payment_transactions": "financial",
    "get_pending_invoices": "financial",
    "get_period_comparison": "financial",
    "get_period_trend": "financial",
    "get_profit_loss": "financial",
    "get_profitability_summary": "financial",
    "get_purchase_transactions": "financial",
    "get_purchases_by_supplier": "financial",
    "get_receipt_transactions": "financial",
    "get_receivables": "financial",
    "get_revenue": "financial",
    "get_sales_by_customer": "financial",
    "get_sales_transactions": "financial",
    "get_supplier_statement": "financial",
    "get_top_customers": "financial",
    "get_top_expenses": "financial",
    "get_top_payables": "financial",
    "get_top_receivables": "financial",
    "get_top_suppliers": "financial",
    "get_trial_balance": "financial",

    # inventory
    "get_low_selling_items": "inventory",
    "get_negative_stock_items": "inventory",
    "get_product_profitability": "inventory",
    "get_purchases_by_item": "inventory",
    "get_sales_by_item": "inventory",
    "get_stock_item_details": "inventory",
    "get_stock_items": "inventory",
    "get_stock_movement": "inventory",
    "get_stock_summary": "inventory",
    "get_top_selling_items": "inventory",
    "get_top_stock_items": "inventory",

    # banking
    "get_bank_balance": "banking",
    "get_bank_transactions": "banking",
    "get_cash_balance": "banking",
    "get_cash_flow_summary": "banking",
    "get_cash_transactions": "banking",

    # tax
    "get_gst_summary": "tax",
    "get_input_gst": "tax",
    "get_output_gst": "tax",
    "get_tax_liability": "tax",
    "get_tds_payable": "tax",
    "get_tds_receivable": "tax",
    "get_tds_summary": "tax",
    "get_tds_transactions": "tax",
}


def initialize_rbac_store() -> None:
    """
    Create RBAC tables if they do not exist and idempotently seed
    baseline roles, permissions, and tool-permission mappings.
    """
    connection = get_connection()
    cursor = connection.cursor()

    try:
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS roles (
                role_id INT NOT NULL AUTO_INCREMENT,
                role_name VARCHAR(50) NOT NULL UNIQUE,
                PRIMARY KEY (role_id)
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS permissions (
                permission_id INT NOT NULL AUTO_INCREMENT,
                permission_code VARCHAR(50) NOT NULL UNIQUE,
                permission_name VARCHAR(100) NOT NULL,
                category VARCHAR(100) NOT NULL,
                subcategory VARCHAR(100),
                description TEXT,
                PRIMARY KEY (permission_id)
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS tool_permissions (
                tool_name VARCHAR(150) NOT NULL PRIMARY KEY,
                permission_id INT NOT NULL,
                CONSTRAINT fk_tool_permissions_permission
                    FOREIGN KEY (permission_id)
                    REFERENCES permissions (permission_id)
                    ON DELETE CASCADE
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS user_roles (
                user_id VARCHAR(100) NOT NULL,
                role_id INT NOT NULL,
                PRIMARY KEY (user_id, role_id),
                CONSTRAINT fk_user_roles_user FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE,
                CONSTRAINT fk_user_roles_role FOREIGN KEY (role_id) REFERENCES roles (role_id) ON DELETE CASCADE
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS user_permissions (
                user_id VARCHAR(100) NOT NULL,
                permission_id INT NOT NULL,
                PRIMARY KEY (user_id, permission_id),
                CONSTRAINT fk_user_permissions_user FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE,
                CONSTRAINT fk_user_permissions_permission FOREIGN KEY (permission_id) REFERENCES permissions (permission_id) ON DELETE CASCADE
            )
            """
        )

        for role_name in DEFAULT_ROLES:
            cursor.execute(
                "INSERT IGNORE INTO roles (role_name) VALUES (%s)",
                (role_name,),
            )

        for code, name, cat, subcat, desc in DEFAULT_PERMISSIONS:
            cursor.execute(
                """
                INSERT INTO permissions (permission_code, permission_name, category, subcategory, description)
                VALUES (%s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    permission_name = VALUES(permission_name),
                    category = VALUES(category),
                    subcategory = VALUES(subcategory),
                    description = VALUES(description)
                """,
                (code, name, cat, subcat, desc),
            )

        for tool_name, perm_code in DEFAULT_TOOL_PERMISSIONS.items():
            cursor.execute(
                """
                INSERT INTO tool_permissions (tool_name, permission_id)
                SELECT %s, permission_id
                FROM permissions
                WHERE permission_code = %s
                ON DUPLICATE KEY UPDATE permission_id = VALUES(permission_id)
                """,
                (tool_name, perm_code),
            )

        connection.commit()

    except Exception:
        connection.rollback()
        raise

    finally:
        cursor.close()
        connection.close()