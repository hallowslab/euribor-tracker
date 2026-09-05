from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Settings:
    database_path: Path = Path(os.getenv("EURIBORTRACKER_DB_PATH", PROJECT_ROOT / "data" / "euribor.db"))
    provider_base_url: str = os.getenv("EURIBORTRACKER_PROVIDER_URL", "https://euriborrates.com")
    provider_http_timeout: float = 40.0
    history_start_year: int = 1999
    default_tenor: str = "6M"
    user_agent: str = "euribortracker/0.1 (personal mortgage monitoring)"


def load_settings() -> Settings:
    return Settings()
