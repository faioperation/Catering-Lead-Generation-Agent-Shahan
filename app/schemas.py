from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class LeadSearchRequest(BaseModel):
    location: str = Field(..., example="New York, USA")
    search_terms: List[str] = Field(
        default=["law office", "school", "production studio", "insurance office", "corporate office"]
    )
    max_results_per_search: int = Field(default=20, ge=1, le=500)
    require_email: bool = True
    require_phone: bool = True
    send_to_n8n: bool = False
    scrape_contacts: bool = True
    max_leads_per_place: int = Field(default=1, ge=0, le=10)
    radius_miles: float = 10.0
    reference_lat: Optional[float] = None
    reference_lng: Optional[float] = None
    campaign_id: Optional[str] = Field(
        default=None,
        description="Optional. If provided, qualified leads are assigned to this campaign and outreach drafts are generated.",
    )
    auto_generate_outreach: bool = True


class Lead(BaseModel):
    id: Optional[str] = None
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
    score: int = 0
    qualification_status: str = "Review Required"
    qualification_reason: Optional[str] = None
    email_verification_status: str = "missing"
    email_verification_reason: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class LeadSearchResponse(BaseModel):
    status: str
    total_raw_results: int
    total_valid_leads: int
    total_stored_leads: int
    total_assigned_to_campaign: int = 0
    total_outreach_generated: int = 0
    total_sent_to_n8n: int
    leads: List[Lead]


class CampaignCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=160)
    description: Optional[str] = None
    offer: Optional[str] = None
    tone: str = "professional"
    target_audience: Optional[str] = None
    status: str = "active"


class CampaignUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    offer: Optional[str] = None
    tone: Optional[str] = None
    target_audience: Optional[str] = None
    status: Optional[str] = None


class Campaign(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    offer: Optional[str] = None
    tone: str = "professional"
    target_audience: Optional[str] = None
    status: str = "active"
    assigned_leads: int = 0
    outreach_messages: int = 0
    created_at: str
    updated_at: str


class AssignLeadsRequest(BaseModel):
    lead_ids: List[str] = Field(default_factory=list)
    only_qualified: bool = True
    auto_generate_outreach: bool = True


class AssignLeadsResponse(BaseModel):
    status: str
    assigned_lead_ids: List[str]
    outreach_generated: int


class GenerateOutreachRequest(BaseModel):
    lead_ids: Optional[List[str]] = None
    overwrite_existing: bool = False


class OutreachMessage(BaseModel):
    id: str
    campaign_id: str
    lead_id: str
    subject: str
    body: str
    status: str = "review_required"
    delivery_status: str = "not_sent"
    provider_message_id: Optional[str] = None
    created_at: str
    updated_at: str
    approved_at: Optional[str] = None
    sent_at: Optional[str] = None
    last_event_at: Optional[str] = None
    business_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    website: Optional[str] = None
    address: Optional[str] = None
    score: Optional[int] = None
    qualification_status: Optional[str] = None
    campaign_name: Optional[str] = None


class OutreachUpdate(BaseModel):
    subject: Optional[str] = None
    body: Optional[str] = None
    status: Optional[str] = None


class SendResponse(BaseModel):
    status: str
    message: OutreachMessage
    provider: Optional[Dict[str, Any]] = None


class DashboardSummary(BaseModel):
    totals: Dict[str, Any]
    lead_counts: List[Dict[str, Any]]
    outreach_counts: List[Dict[str, Any]]
    delivery_counts: List[Dict[str, Any]]
