"""
EuGH Chatbot Configuration Module

Handles configuration for data paths, allowing storage in cloud-synced folders.
"""

import os
from pathlib import Path
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()


@dataclass
class Config:
    """
    Configuration for the EuGH Chatbot.

    Data paths can be configured via:
    1. Environment variables (ECJ_DATA_DIR)
    2. .env file
    3. Default: ./data relative to project root

    This allows storing case data in cloud-synced folders (OneDrive, Google Drive)
    for access from multiple devices.
    """

    # Base data directory - can be set to cloud folder
    data_dir: Path = field(default_factory=lambda: Path(
        os.getenv("ECJ_DATA_DIR", str(Path(__file__).parent.parent / "data"))
    ))

    # Subdirectories (relative to data_dir)
    cases_subdir: str = "cases"
    index_subdir: str = "index"

    # Download settings
    initial_year: int = 2020
    initial_limit: int = 500
    update_limit: int = 100
    download_delay: float = 1.0

    # Search settings
    n_results: int = 5
    relevance_threshold: float = 1.5
    enable_live_fallback: bool = True

    # Model settings
    embedding_model: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    llm_model: str = "claude-sonnet-4-20250514"

    @property
    def cases_dir(self) -> Path:
        """Path to case law JSON files."""
        return self.data_dir / self.cases_subdir

    @property
    def index_dir(self) -> Path:
        """Path to vector index."""
        return self.data_dir / self.index_subdir

    def ensure_directories(self):
        """Create data directories if they don't exist."""
        self.cases_dir.mkdir(parents=True, exist_ok=True)
        self.index_dir.mkdir(parents=True, exist_ok=True)

    def is_cloud_storage(self) -> bool:
        """Check if data is stored in a known cloud folder."""
        path_str = str(self.data_dir).lower()
        cloud_indicators = [
            "onedrive",
            "google drive",
            "googledrive",
            "dropbox",
            "icloud"
        ]
        return any(indicator in path_str for indicator in cloud_indicators)

    def get_status(self) -> dict:
        """Get configuration status for display."""
        cases_count = len(list(self.cases_dir.glob("*.json"))) if self.cases_dir.exists() else 0
        index_exists = self.index_dir.exists() and any(self.index_dir.iterdir()) if self.index_dir.exists() else False

        return {
            "data_dir": str(self.data_dir),
            "cases_dir": str(self.cases_dir),
            "index_dir": str(self.index_dir),
            "cases_count": cases_count,
            "index_exists": index_exists,
            "is_cloud_storage": self.is_cloud_storage()
        }

    @classmethod
    def from_env(cls) -> "Config":
        """Create config from environment variables."""
        config = cls()

        # Override with environment variables if set
        if os.getenv("ECJ_INITIAL_YEAR"):
            config.initial_year = int(os.getenv("ECJ_INITIAL_YEAR"))

        if os.getenv("ECJ_EMBEDDING_MODEL"):
            config.embedding_model = os.getenv("ECJ_EMBEDDING_MODEL")

        if os.getenv("ECJ_LLM_MODEL"):
            config.llm_model = os.getenv("ECJ_LLM_MODEL")

        if os.getenv("ECJ_ENABLE_LIVE_FALLBACK"):
            config.enable_live_fallback = os.getenv("ECJ_ENABLE_LIVE_FALLBACK").lower() == "true"

        return config


# Global default config
_config: Config | None = None


def get_config() -> Config:
    """Get the global configuration instance."""
    global _config
    if _config is None:
        _config = Config.from_env()
    return _config


def set_data_dir(path: str | Path):
    """
    Set the data directory at runtime.

    Args:
        path: Path to data directory (can be cloud-synced folder)
    """
    global _config
    if _config is None:
        _config = Config.from_env()
    _config.data_dir = Path(path)
    _config.ensure_directories()
