"""
Central configuration for the AIAIC ML Foundation service.

All runtime behavior is driven from here (env-driven, no magic numbers
scattered in code). Every module imports `settings` from this file instead
of reading os.environ directly, so there is exactly one source of truth.
"""

from pathlib import Path
from typing import List
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    # --- Project paths ---
    project_root: Path = Path(__file__).resolve().parents[2]
    raw_data_dir: Path = project_root / "data" / "raw"
    processed_data_dir: Path = project_root / "data" / "processed"
    versions_dir: Path = project_root / "data" / "versions"
    models_dir: Path = project_root / "models"

    # --- Dataset scope ---
    target_crops: List[str] = Field(
        default=["Onion", "Potato", "Tomato", "Wheat", "Rice"]
    )
    target_states: List[str] = Field(
        default=["Maharashtra", "Uttar Pradesh", "Karnataka", "Madhya Pradesh", "Bihar"]
    )

    # --- Agmarknet (data.gov.in) source ---
    # Public resource id for the "Variety-wise Daily Market Prices" dataset
    # on data.gov.in. An API key is required (free registration).
    # agmarknet_resource_id: str = "9ef84268-d588-465a-a308-a864a43d0070"
    # agmarknet_base_url: str = "https://api.data.gov.in/resource"
    # agmarknet_api_key: str = Field(default="", description="Set via DATA_GOV_IN_API_KEY env var")

    

    # --- Fallback dataset (used if Agmarknet fetch fails / no API key) ---
    fallback_csv_name: str = "Agriculture_price_dataset.csv"

    # --- Determinism ---
    random_seed: int = 42

    # --- Validation thresholds ---
    max_null_fraction_per_column: float = 0.4  # column dropped/quarantined above this
    min_rows_required: int = 500

    # --- Preprocessing ---
    outlier_z_threshold: float = 4.0  # for price outlier flagging
    price_min_valid: float = 1.0      # INR per quintal, sanity floor
    price_max_valid: float = 500000.0 # INR per quintal, sanity ceiling

    # --- Feature engineering ---
    lag_days: List[int] = Field(default=[1, 7, 14])
    rolling_windows: List[int] = Field(default=[7, 14, 30])

    # --- Train/test split (time-based, not random) ---
    test_split_days: int = 30  # last N days held out as test set

    # --- Model ---
    model_type: str = "lightgbm"  # "lightgbm" | "xgboost"
    model_version_prefix: str = "price_predictor"

    # --- MongoDB (optional; falls back to local JSON if unreachable) ---
    mongo_uri: str = Field(default="mongodb://mongo:27017", description="Set via MONGO_URI env var")
    mongo_db_name: str = "aiaic_ml_foundation"
    mongo_connect_timeout_ms: int = 2000  # fail fast, don't hang the app

    # --- API ---
    api_title: str = "AIAIC ML Foundation - Crop Price Prediction Service"
    api_version: str = "0.1.0"
    log_level: str = "INFO"
    api_base: str = ""
    aiaic_api_base: str = ""
    vite_aqiaic_base_url: str = ""

    class Config:
        env_file = ".env"
        env_prefix = "AIAIC_"
        protected_namespaces = ()
        extra = "ignore"

    def ensure_dirs(self) -> None:
        for d in [self.raw_data_dir, self.processed_data_dir, self.versions_dir, self.models_dir]:
            d.mkdir(parents=True, exist_ok=True)


settings = Settings()
settings.ensure_dirs()