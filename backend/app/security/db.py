import os
from pathlib import Path

from dotenv import load_dotenv
import mysql.connector

_BACKEND_ENV = Path(__file__).resolve().parent.parent.parent / ".env"
load_dotenv(_BACKEND_ENV)
load_dotenv()


def get_connection():
    """
    Create and return a MySQL connection using
    environment-based database configuration.
    """

    return mysql.connector.connect(
        host=os.getenv("DB_HOST", "127.0.0.1") or "127.0.0.1",
        port=int(os.getenv("DB_PORT", "3306")),
        user=os.getenv("DB_USER", "tally_app"),
        password=os.getenv("DB_PASSWORD", "infintrix123"),
        database=os.getenv("DB_NAME", "tally_financial_intelligence"),
        time_zone="+00:00",
    )