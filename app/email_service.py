from typing import Any, Dict
import httpx

from app.config import settings


class EmailService:
    def __init__(self):
        self.api_key = settings.SENDGRID_API_KEY
        self.from_email = settings.SENDGRID_FROM_EMAIL
        self.from_name = settings.SENDGRID_FROM_NAME
        self.base_url = "https://api.sendgrid.com/v3"

    def is_configured(self) -> bool:
        return bool(self.api_key and self.from_email)

    async def send_outreach(self, message: Dict[str, Any]) -> Dict[str, Any]:
        if not self.is_configured():
            raise Exception("SendGrid is not configured. Add SENDGRID_API_KEY and SENDGRID_FROM_EMAIL to .env")

        if not message.get("email"):
            raise Exception("Cannot send outreach because this lead has no email address.")

        payload = {
            "personalizations": [
                {
                    "to": [{"email": message["email"], "name": message.get("business_name") or ""}],
                    "subject": message["subject"],
                }
            ],
            "from": {"email": self.from_email, "name": self.from_name},
            "content": [{"type": "text/plain", "value": message["body"]}],
            "custom_args": {
                "outreach_message_id": message["id"],
                "campaign_id": message["campaign_id"],
                "lead_id": message["lead_id"],
            },
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(f"{self.base_url}/mail/send", headers=headers, json=payload)

        if response.status_code >= 400:
            raise Exception(f"SendGrid error {response.status_code}: {response.text}")

        return {
            "provider": "sendgrid",
            "status_code": response.status_code,
            "provider_message_id": response.headers.get("x-message-id"),
        }
