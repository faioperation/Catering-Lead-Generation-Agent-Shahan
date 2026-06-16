from pathlib import Path
from typing import List, Optional

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from geopy.distance import geodesic

from app.apify_service import ApifyService
from app.auth import require_api_key
from app.database import (
    assign_leads_to_campaign,
    create_campaign,
    create_or_update_outreach_message,
    dashboard_summary,
    get_campaign,
    get_campaign_assigned_leads,
    get_lead,
    get_outreach_message,
    init_db,
    list_campaigns,
    list_leads,
    list_outreach_messages,
    now_iso,
    update_campaign,
    update_outreach_message,
    upsert_lead,
)
from app.email_service import EmailService
from app.lead_utils import is_valid_lead, normalize_lead, score_and_categorize_lead
from app.n8n_service import N8NService
from app.outreach_service import OutreachService
from app.schemas import (
    AssignLeadsRequest,
    AssignLeadsResponse,
    Campaign,
    CampaignCreate,
    CampaignUpdate,
    DashboardSummary,
    GenerateOutreachRequest,
    Lead,
    LeadSearchRequest,
    LeadSearchResponse,
    OutreachMessage,
    OutreachUpdate,
    SendResponse,
)


app = FastAPI(
    title="Catering Outreach Platform API",
    version="2.0.0",
    description="Lead discovery, scoring, campaign assignment, outreach review, and email delivery workflow.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

FRONTEND_PATH = Path(__file__).parent / "frontend" / "index.html"


@app.on_event("startup")
def startup_event() -> None:
    init_db()


@app.get("/", include_in_schema=False)
def root():
    if FRONTEND_PATH.exists():
        return FileResponse(FRONTEND_PATH)
    return {"message": "Catering Outreach Platform API is running", "docs": "/docs"}


@app.get("/health")
def health():
    return {"status": "ok"}


def _generate_outreach_for_leads(campaign_id: str, leads: List[dict]) -> List[dict]:
    campaign = get_campaign(campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found.")

    service = OutreachService()
    generated = []

    for lead in leads:
        if lead.get("qualification_status") != "Qualified":
            continue

        message = service.build_message(campaign, lead)
        generated.append(
            create_or_update_outreach_message(
                campaign_id=campaign_id,
                lead_id=lead["id"],
                subject=message["subject"],
                body=message["body"],
                status="review_required",
            )
        )

    return generated


@app.post(
    "/api/leads/generate",
    response_model=LeadSearchResponse,
    dependencies=[Depends(require_api_key)],
)
async def generate_leads(request: LeadSearchRequest, background_tasks: BackgroundTasks):
    apify_service = ApifyService()
    n8n_service = N8NService()

    if request.campaign_id and not get_campaign(request.campaign_id):
        raise HTTPException(status_code=404, detail="Campaign not found.")

    try:
        raw_results = await apify_service.run_google_places_scraper(
            location=request.location,
            search_terms=request.search_terms,
            max_results_per_search=request.max_results_per_search,
            scrape_contacts=request.scrape_contacts,
            max_leads_per_place=request.max_leads_per_place,
            verify_emails=True,
        )

        valid_leads = []
        stored_leads = []

        for item in raw_results:
            normalized = normalize_lead(item)

            if not is_valid_lead(
                normalized,
                require_email=request.require_email,
                require_phone=request.require_phone,
            ):
                continue

            scored = score_and_categorize_lead(normalized, search_terms=request.search_terms)
            valid_leads.append(scored)

        if request.reference_lat is not None and request.reference_lng is not None:
            ref_coords = (request.reference_lat, request.reference_lng)
            filtered_leads = []

            for lead in valid_leads:
                lat = lead.get("lat") or lead.get("latitude")
                lng = lead.get("lng") or lead.get("longitude")

                if lat and lng and geodesic(ref_coords, (lat, lng)).miles <= request.radius_miles:
                    filtered_leads.append(lead)

            valid_leads = filtered_leads

        for lead in valid_leads:
            stored_leads.append(upsert_lead(lead, raw=lead))

        assigned_ids: List[str] = []
        generated_messages: List[dict] = []

        if request.campaign_id:
            qualified_ids = [lead["id"] for lead in stored_leads if lead.get("qualification_status") == "Qualified"]
            assigned_ids = assign_leads_to_campaign(request.campaign_id, qualified_ids)

            if request.auto_generate_outreach:
                assigned_leads = [lead for lead in stored_leads if lead["id"] in assigned_ids]
                generated_messages = _generate_outreach_for_leads(request.campaign_id, assigned_leads)

        if request.send_to_n8n:
            async def send_to_n8n_task(leads):
                for lead in leads:
                    try:
                        await n8n_service.send_lead(lead)
                    except Exception as e:
                        print(f"[Warning] Failed to send lead to n8n: {e}")

            background_tasks.add_task(send_to_n8n_task, stored_leads)

        return LeadSearchResponse(
            status="success",
            total_raw_results=len(raw_results),
            total_valid_leads=len(valid_leads),
            total_stored_leads=len(stored_leads),
            total_assigned_to_campaign=len(assigned_ids),
            total_outreach_generated=len(generated_messages),
            total_sent_to_n8n=0,
            leads=[Lead(**lead) for lead in stored_leads],
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/leads", response_model=List[Lead], dependencies=[Depends(require_api_key)])
def get_leads(
    status: Optional[str] = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
):
    return [Lead(**lead) for lead in list_leads(status=status, limit=limit)]


@app.get("/api/dashboard/summary", response_model=DashboardSummary, dependencies=[Depends(require_api_key)])
def get_dashboard_summary():
    return dashboard_summary()


@app.post("/api/campaigns", response_model=Campaign, dependencies=[Depends(require_api_key)])
def create_campaign_endpoint(payload: CampaignCreate):
    return Campaign(**create_campaign(payload.model_dump()))


@app.get("/api/campaigns", response_model=List[Campaign], dependencies=[Depends(require_api_key)])
def list_campaigns_endpoint():
    return [Campaign(**campaign) for campaign in list_campaigns()]


@app.get("/api/campaigns/{campaign_id}", response_model=Campaign, dependencies=[Depends(require_api_key)])
def get_campaign_endpoint(campaign_id: str):
    campaign = get_campaign(campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found.")
    return Campaign(**campaign)


@app.put("/api/campaigns/{campaign_id}", response_model=Campaign, dependencies=[Depends(require_api_key)])
def update_campaign_endpoint(campaign_id: str, payload: CampaignUpdate):
    campaign = update_campaign(campaign_id, payload.model_dump(exclude_unset=True))
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found.")
    return Campaign(**campaign)


@app.post(
    "/api/campaigns/{campaign_id}/assign-leads",
    response_model=AssignLeadsResponse,
    dependencies=[Depends(require_api_key)],
)
def assign_leads_endpoint(campaign_id: str, payload: AssignLeadsRequest):
    if not get_campaign(campaign_id):
        raise HTTPException(status_code=404, detail="Campaign not found.")

    lead_ids = payload.lead_ids

    if payload.only_qualified:
        lead_ids = [
            lead_id
            for lead_id in lead_ids
            if (get_lead(lead_id) or {}).get("qualification_status") == "Qualified"
        ]

    assigned_ids = assign_leads_to_campaign(campaign_id, lead_ids)
    outreach_generated = []

    if payload.auto_generate_outreach and assigned_ids:
        assigned_leads = [get_lead(lead_id) for lead_id in assigned_ids]
        outreach_generated = _generate_outreach_for_leads(
            campaign_id,
            [lead for lead in assigned_leads if lead],
        )

    return AssignLeadsResponse(
        status="success",
        assigned_lead_ids=assigned_ids,
        outreach_generated=len(outreach_generated),
    )


@app.post(
    "/api/campaigns/{campaign_id}/generate-outreach",
    response_model=List[OutreachMessage],
    dependencies=[Depends(require_api_key)],
)
def generate_outreach_endpoint(campaign_id: str, payload: GenerateOutreachRequest):
    if not get_campaign(campaign_id):
        raise HTTPException(status_code=404, detail="Campaign not found.")

    if payload.lead_ids:
        leads = [get_lead(lead_id) for lead_id in payload.lead_ids]
        leads = [lead for lead in leads if lead]
    else:
        leads = get_campaign_assigned_leads(campaign_id)

    messages = _generate_outreach_for_leads(campaign_id, leads)
    return [OutreachMessage(**message) for message in messages]


@app.get(
    "/api/outreach/review-queue",
    response_model=List[OutreachMessage],
    dependencies=[Depends(require_api_key)],
)
def review_queue(
    status: Optional[str] = Query(default="review_required"),
    campaign_id: Optional[str] = Query(default=None),
):
    return [
        OutreachMessage(**message)
        for message in list_outreach_messages(status=status, campaign_id=campaign_id)
    ]


@app.put("/api/outreach/{message_id}", response_model=OutreachMessage, dependencies=[Depends(require_api_key)])
def update_outreach_endpoint(message_id: str, payload: OutreachUpdate):
    message = update_outreach_message(message_id, payload.model_dump(exclude_unset=True))
    if not message:
        raise HTTPException(status_code=404, detail="Outreach message not found.")
    return OutreachMessage(**message)


@app.post("/api/outreach/{message_id}/approve", response_model=OutreachMessage, dependencies=[Depends(require_api_key)])
def approve_outreach(message_id: str):
    message = update_outreach_message(
        message_id,
        {"status": "approved", "approved_at": now_iso()},
    )
    if not message:
        raise HTTPException(status_code=404, detail="Outreach message not found.")
    return OutreachMessage(**message)


@app.post("/api/outreach/{message_id}/send", response_model=SendResponse, dependencies=[Depends(require_api_key)])
async def send_outreach(message_id: str):
    message = get_outreach_message(message_id)
    if not message:
        raise HTTPException(status_code=404, detail="Outreach message not found.")

    if message.get("status") != "approved":
        raise HTTPException(status_code=400, detail="Approve the outreach message before sending.")

    provider_result = await EmailService().send_outreach(message)
    updated = update_outreach_message(
        message_id,
        {
            "status": "sent",
            "delivery_status": "sent",
            "provider_message_id": provider_result.get("provider_message_id"),
            "sent_at": now_iso(),
        },
    )

    return SendResponse(status="success", message=OutreachMessage(**updated), provider=provider_result)


@app.post("/api/sendgrid/events", dependencies=[Depends(require_api_key)])
async def sendgrid_events(request: Request):
    events = await request.json()
    if not isinstance(events, list):
        events = [events]

    updated = 0
    for event in events:
        message_id = event.get("outreach_message_id") or event.get("custom_args", {}).get("outreach_message_id")
        delivery_status = event.get("event")

        if not message_id or not delivery_status:
            continue

        message = update_outreach_message(
            message_id,
            {
                "delivery_status": delivery_status,
                "last_event_at": now_iso(),
            },
        )
        if message:
            updated += 1

    return {"status": "success", "updated": updated}


@app.get("/api/analytics", response_model=DashboardSummary, dependencies=[Depends(require_api_key)])
def analytics():
    return dashboard_summary()


@app.post("/api/leads/test-n8n", dependencies=[Depends(require_api_key)])
async def test_n8n():
    test_lead = {
        "business_name": "Test Business",
        "phone": "+1234567890",
        "email": "test@example.com",
        "website": "https://example.com",
        "address": "123 Main St, Test City",
        "category": "Law Office",
        "google_maps_url": "https://maps.google.com",
        "source": "test",
    }

    try:
        n8n_service = N8NService()
        await n8n_service.send_lead(test_lead)
        return {"status": "success", "message": "Test lead sent to n8n", "lead": test_lead}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
