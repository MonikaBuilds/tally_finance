from pydantic_settings import (
    BaseSettings,
    SettingsConfigDict
)


class Settings(BaseSettings):
    TALLY_HOST: str = "localhost"
    TALLY_PORT: int = 9000
    TALLY_VERSION: str = "prime"

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore"
    )

    @property
    def tally_url(self) -> str:
        return (
            f"http://{self.TALLY_HOST}:"
            f"{self.TALLY_PORT}"
        )


settings = Settings()