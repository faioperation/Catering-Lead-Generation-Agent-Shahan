from fastapi import Header, HTTPException
from app.config import settings


async def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    """
    Lightweight access control.
    If API_KEY is empty in .env, local development remains open.
    If API_KEY is set, all protected endpoints require X-API-Key.
    """

    if not settings.API_KEY:
        return

    if x_api_key != settings.API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing API key.")
