from typing import Dict, Any
import httpx

from app.config import settings


class N8NService:
    def __init__(self):
        self.webhook_url = settings.N8N_WEBHOOK_URL

    async def send_lead(self, lead: Dict[str, Any]) -> bool:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(self.webhook_url, json=lead)

        if response.status_code >= 400:
            raise Exception(
                f"n8n webhook error {response.status_code}: {response.text}"
            )

        return True