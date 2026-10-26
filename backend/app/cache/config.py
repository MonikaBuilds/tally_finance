"""
Configuration settings for Redis caching and background refresh.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


from pathlib import Path

_BACKEND_ENV = Path(__file__).resolve().parent.parent.parent / ".env"


class CacheSettings(BaseSettings):
    REDIS_URL: str = "redis://127.0.0.1:6379/0"
    REDIS_HOST: str = "127.0.0.1"
    REDIS_PORT: int = 6379
    REDIS_PASSWORD: str | None = None
    REDIS_DB: int = 0
    REDIS_CACHE_ENABLED: bool = True
    REDIS_CACHE_DEFAULT_FRESH_TTL: int = 300  # 5 minutes fresh
    REDIS_CACHE_STALE_RETENTION_TTL: int = 86400  # 24 hours retention for failover
    REDIS_CACHE_KEY_PREFIX: str = "tally:cache"
    REDIS_CACHE_REFRESH_ENABLED: bool = True
    REDIS_CACHE_REFRESH_INTERVAL_SECONDS: int = 600  # 10 minutes background refresh
    REDIS_CONNECT_TIMEOUT: float = 2.0
    REDIS_PROTOCOL: int = 2  # RESP2 for maximum compatibility across Redis versions
    TALLY_UNAVAILABLE_COOLDOWN_SECONDS: int = 30
    TALLY_CONNECT_TIMEOUT: float = 2.5

    # Specific report freshness TTLs (in seconds)
    TTL_COMPANIES: int = 600
    TTL_DASHBOARD_SUMMARY: int = 300
    TTL_PROFIT_LOSS: int = 300
    TTL_BALANCE_SHEET: int = 300
    TTL_TRIAL_BALANCE: int = 300
    TTL_BILLS_RECEIVABLE: int = 180
    TTL_BILLS_PAYABLE: int = 180
    TTL_STOCK_SUMMARY: int = 300
    TTL_LEDGER_LIST: int = 600

    model_config = SettingsConfigDict(
        env_file=(".env", str(_BACKEND_ENV)),
        extra="ignore",
    )

    def get_fresh_ttl(self, report_name: str) -> int:
        """Return the specific fresh TTL for a report, or the default fresh TTL."""
        mapping = {
            "companies": self.TTL_COMPANIES,
            "dashboard_summary": self.TTL_DASHBOARD_SUMMARY,
            "dashboard_monthly": self.TTL_DASHBOARD_SUMMARY,
            "profit_loss": self.TTL_PROFIT_LOSS,
            "balance_sheet": self.TTL_BALANCE_SHEET,
            "trial_balance": self.TTL_TRIAL_BALANCE,
            "bills_receivable": self.TTL_BILLS_RECEIVABLE,
            "bills_payable": self.TTL_BILLS_PAYABLE,
            "stock_summary": self.TTL_STOCK_SUMMARY,
            "ledger_list": self.TTL_LEDGER_LIST,
        }
        return mapping.get(report_name, self.REDIS_CACHE_DEFAULT_FRESH_TTL)


cache_settings = CacheSettings()


def parse_refresh_flag(value: object) -> bool:
    """Parse refresh / force_refresh flags from bool, int, or string."""
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return False


def is_force_refresh(force_refresh: object = None, refresh: object = None) -> bool:
    """Determine whether force refresh was explicitly requested via either parameter."""
    return parse_refresh_flag(force_refresh) or parse_refresh_flag(refresh)
