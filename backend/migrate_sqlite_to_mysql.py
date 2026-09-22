import os
import sqlite3

import mysql.connector
from dotenv import load_dotenv


load_dotenv()


# -----------------------------
# Connect to existing SQLite DB
# -----------------------------
sqlite_connection = sqlite3.connect(
    "data/chat_auth.db"
)
sqlite_connection.row_factory = sqlite3.Row


# -----------------------------
# Connect to new MySQL DB
# -----------------------------
mysql_connection = mysql.connector.connect(
    host=os.getenv("DB_HOST"),
    port=int(os.getenv("DB_PORT", "3306")),
    user=os.getenv("DB_USER"),
    password=os.getenv("DB_PASSWORD"),
    database=os.getenv("DB_NAME"),
)

mysql_cursor = mysql_connection.cursor()


try:
    # Read existing users from SQLite
    users = sqlite_connection.execute(
        """
        SELECT
            user_id,
            username,
            password_hash,
            is_active
        FROM users
        """
    ).fetchall()

    # Insert users into MySQL
    for user in users:
        mysql_cursor.execute(
            """
            INSERT INTO users (
                user_id,
                username,
                password_hash,
                is_active
            )
            VALUES (%s, %s, %s, %s)
            """,
            (
                user["user_id"],
                user["username"],
                user["password_hash"],
                user["is_active"],
            ),
        )

    # Read company assignments
    companies = sqlite_connection.execute(
        """
        SELECT
            user_id,
            company_name
        FROM user_companies
        """
    ).fetchall()

    # Insert company assignments into MySQL
    for company in companies:
        mysql_cursor.execute(
            """
            INSERT INTO user_companies (
                user_id,
                company_name
            )
            VALUES (%s, %s)
            """,
            (
                company["user_id"],
                company["company_name"],
            ),
        )

    mysql_connection.commit()

    print(
        f"Migration successful: "
        f"{len(users)} users and "
        f"{len(companies)} company assignments migrated."
    )

except Exception:
    mysql_connection.rollback()
    raise

finally:
    mysql_cursor.close()
    mysql_connection.close()
    sqlite_connection.close()