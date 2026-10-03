"""
Pydantic request/response schemas for the AIAIC ML Foundation v1 API.

v1 adds:
- request_id on every response (UUID for tracing)
- execution_status field
- versioned response model
- ready check response
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class PredictionRequest(BaseModel):
    commodity: str = Field(..., examples=["Onion"])
    state: str = Field(..., examples=["Maharashtra"])
    month: int = Field(..., ge=1, le=12)
    day_of_week: Optional[int] = Field(default=None, ge=0, le=6)
    is_weekend: Optional[int] = Field(default=None, ge=0, le=1)
    season: Optional[str] = Field(default=None, examples=["kharif", "rabi", "zaid"])
    month_sin: Optional[float] = None
    month_cos: Optional[float] = None
    grade: Optional[str] = Field(default="FAQ", examples=["FAQ", "Local"])

    modal_price_lag_1: Optional[float] = Field(default=None, description="Modal price 1 day ago")
    modal_price_lag_7: Optional[float] = Field(default=None, description="Modal price 7 days ago")
    modal_price_lag_14: Optional[float] = Field(default=None, description="Modal price 14 days ago")
    modal_price_roll_mean_7: Optional[float] = None
    modal_price_roll_std_7: Optional[float] = None
    modal_price_roll_mean_14: Optional[float] = None
    modal_price_roll_std_14: Optional[float] = None
    modal_price_roll_mean_30: Optional[float] = None
    modal_price_roll_std_30: Optional[float] = None
    min_price: Optional[float] = None
    max_price: Optional[float] = None


class PredictionResponse(BaseModel):
    request_id: str
    execution_status: str
    predicted_modal_price: float
    model_file: Optional[str]
    model_version: Optional[str]
    trained_at: Optional[str]
    data_hash: Optional[str]
    features_used: List[str]
    features_missing: List[str]
    replay_file: Optional[str] = None


class HealthResponse(BaseModel):
    """Describes the served FORECAST model (`/v1/forecast`). MongoDB is not part of the deployed service."""
    model_config = ConfigDict(protected_namespaces=())

    status: str
    model_loaded: bool
    model_file: Optional[str] = None
    model_version: Optional[str] = None
    trained_through: Optional[str] = None
    data_hash: Optional[str] = None
    api_version: str


class ReadyResponse(BaseModel):
    ready: bool
    reason: Optional[str] = None


class ErrorResponse(BaseModel):
    request_id: Optional[str]
    detail: str
    execution_status: str = "FAILED"