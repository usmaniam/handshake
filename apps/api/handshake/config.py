from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass
class Settings:
    paypal_base_url: str = ""
    paypal_client_id: str = ""
    paypal_secret: str = ""
    paypal_webhook_id: str = ""
    payout_rail: str = "paypal"  # paypal | fake
    gemini_api_key: str = ""
    gemini_model: str = ""
    gemini_model_lite: str = ""
    gemini_thinking_level: str = ""
    llm_verifier: str = "auto"  # auto | on | off
    database_url: str = ""
    admin_token: str = ""
    allowed_origins: list[str] = field(default_factory=list)
    expiry_grace_days: int = 2
    auto_create_tables: bool = False


def settings() -> Settings:
    """Read env at call time so tests can monkeypatch."""
    e = os.environ.get
    return Settings(
        paypal_base_url=e("PAYPAL_BASE_URL", "https://api-m.sandbox.paypal.com"),
        paypal_client_id=e("PAYPAL_OWNER_CLIENT_ID", ""),
        paypal_secret=e("PAYPAL_OWNER_SECRET", ""),
        paypal_webhook_id=e("PAYPAL_WEBHOOK_ID", ""),
        payout_rail=e("PAYOUT_RAIL", "paypal"),
        gemini_api_key=e("GEMINI_API_KEY", ""),
        gemini_model=e("GEMINI_MODEL", "gemini-3.8-flash"),
        gemini_model_lite=e("GEMINI_MODEL_LITE", "gemini-3.5-flash-lite"),
        gemini_thinking_level=e("GEMINI_THINKING_LEVEL", ""),
        llm_verifier=e("LLM_VERIFIER", "auto"),
        database_url=e("DATABASE_URL", "sqlite:///./handshake.db"),
        admin_token=e("ADMIN_TOKEN", ""),
        allowed_origins=[o for o in e("ALLOWED_ORIGINS", "http://localhost:3000").split(",") if o],
        expiry_grace_days=int(e("EXPIRY_GRACE_DAYS", "2")),
        auto_create_tables=e("AUTO_CREATE_TABLES", "") == "1",
    )
