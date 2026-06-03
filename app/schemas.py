from typing import Optional, List
from pydantic import BaseModel, Field

class LeadSearchRequest(BaseModel):
    location: str = Field(
        ...,
        example="New York, USA",
        description="City or area where you want to search leads."
    )

    search_terms: List[str] = Field(
        default=[
            "law office",
            "school",
            "production studio",
            "insurance office",
            "corporate office"
        ],
        description="Google Maps search terms."
    )

    max_results_per_search: int = Field(
        default=20,
        ge=1,
        le=500,
        description="How many places to scrape per search term."
    )

    require_email: bool = Field(
        default=True,
        description="Only send leads that have an email."
    )

    require_phone: bool = Field(
        default=True,
        description="Only send leads that have a phone."
    )

    send_to_n8n: bool = Field(
        default=True,
        description="If false, only return leads in API response."
    )

    scrape_contacts: bool = Field(
        default=True,
        description="Enable website contact enrichment in Apify."
    )

    max_leads_per_place: int = Field(
        default=1,
        ge=0,
        le=10,
        description="Apify business lead enrichment records per place."
    )

    radius_miles: float = Field(
        default=10.0,
        description="Radius in miles from the reference location to filter leads."
    )

    reference_lat: Optional[float] = Field(
        None,
        description="Latitude of the reference location (e.g., restaurant)."
    )

    reference_lng: Optional[float] = Field(
        None,
        description="Longitude of the reference location (e.g., restaurant)."
    )


class Lead(BaseModel):
    business_name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    website: Optional[str] = None
    address: Optional[str] = None
    category: Optional[str] = None
    google_maps_url: Optional[str] = None
    source: str = "apify_google_places"
    lat: Optional[float] = None
    lng: Optional[float] = None


class LeadSearchResponse(BaseModel):
    status: str
    total_raw_results: int
    total_valid_leads: int
    total_sent_to_n8n: int
    leads: List[Lead]