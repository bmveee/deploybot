# config.py
from typing import Dict, List
import pytz
from datetime import tzinfo


class Settings:
    def __init__(self):
        self.PROMOTION_RULES: Dict[str, List[str]] = {
            "dev": ["prod"],
        }
        self.ENV_DB_MAPPING: Dict[str, str] = {"dev": "dev.db", "prod": "prod.db"}
        self.ENV_DEFAULT_TZ: tzinfo = pytz.timezone("US/Eastern")


settings = Settings()
