from typing import Any, Dict, List
import httpx
from app.config import settings

class ApifyService:
    def __init__(self):
        self.base_url = "https://api.apify.com/v2"
        self.actor_id = settings.APIFY_ACTOR_ID
        self.token = settings.APIFY_TOKEN

    async def run_google_places_scraper(
        self,
        location: str,
        search_terms: List[str],
        max_results_per_search: int = 20,
        scrape_contacts: bool = True,
        max_leads_per_place: int = 1,
        verify_emails: bool = True
    ) -> List[Dict[str, Any]]:

        url = (
            f"{self.base_url}/acts/{self.actor_id}/run-sync-get-dataset-items"
            f"?token={self.token}"
        )

        payload = {
            "searchStringsArray": search_terms,
            "locationQuery": location,
            "maxCrawledPlacesPerSearch": max_results_per_search,
            "language": "en",
            "scrapeContacts": scrape_contacts,
            "maximumLeadsEnrichmentRecords": max_leads_per_place,
            "verifyLeadsEnrichmentEmails": verify_emails,  # ENABLE email extraction
            "maxReviews": 0
        }

        timeout = httpx.Timeout(600.0, connect=30.0)

        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()

        if not isinstance(data, list):
            raise Exception(f"Unexpected Apify response: {data}")

        return data