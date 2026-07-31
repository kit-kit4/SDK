import json
import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
 
DEFAULT_CONFIG_PATH = Path(".ubn/config.json")
GLOBAL_CONFIG_PATH = Path.home() / ".ubn/config.json"

class Config:
    def __init__(self):
        self.token: Optional[str] = None
        self.public_id: Optional[str] = None
        self.base_url: str = "https://kit.felixcard.online/net"
        self._loaded = False

    def load(self) -> None:
        if self._loaded:
            return
        # Спочатку .env
        load_dotenv()
        self.token = os.getenv("UBN_TOKEN")
        self.public_id = os.getenv("UBN_ID")
        self.base_url = os.getenv("UBN_BASE_URL", "https://kit.felixcard.online/net")

        # Потім файл конфігу (перезаписує)
        config_path = self._find_config()
        if config_path and config_path.exists():
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.token = data.get("token", self.token)
                self.public_id = data.get("public_id", self.public_id)
                self.base_url = data.get("base_url", self.base_url)
            except Exception:
                pass
        self._loaded = True

    def _find_config(self) -> Optional[Path]:
        if DEFAULT_CONFIG_PATH.exists():
            return DEFAULT_CONFIG_PATH
        if GLOBAL_CONFIG_PATH.exists():
            return GLOBAL_CONFIG_PATH
        return None

    def save(self, path: Optional[Path] = None) -> None:
        path = path or DEFAULT_CONFIG_PATH
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "token": self.token,
            "public_id": self.public_id,
            "base_url": self.base_url,
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def get_token(self) -> str:
        self.load()
        if not self.token:
            raise ValueError("UBN_TOKEN not set. Run 'ubn init' first.")
        return self.token

    def get_public_id(self) -> str:
        self.load()
        if not self.public_id:
            raise ValueError("UBN_ID not set. Run 'ubn init' first.")
        return self.public_id

    def get_base_url(self) -> str:
        self.load()
        return self.base_url