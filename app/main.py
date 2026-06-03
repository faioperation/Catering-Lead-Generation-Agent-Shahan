# app/main.py
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from app.schemas import LeadSearchRequest, LeadSearchResponse, Lead
from app.apify_service import ApifyService
from app.n8n_service import N8NService
from app.lead_utils import normalize_lead, is_valid_lead

from geopy.distance import geodesic

app = FastAPI(
    title="Google Places Lead Generation API",
    version="1.4.0",
    description="FastAPI API for generating business leads via Apify and sending them to n8n."
)

# CORS setup
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def root():
    return {"message": "Lead Generation API is running", "docs": "/docs"}

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/api/leads/generate", response_model=LeadSearchResponse)
async def generate_leads(request: LeadSearchRequest, background_tasks: BackgroundTasks):
    apify_service = ApifyService()
    n8n_service = N8NService()

    try:
        # -------------------------
        # 1. Send only valid fields to Apify
        # -------------------------
        raw_results = await apify_service.run_google_places_scraper(
            location=request.location,
            search_terms=request.search_terms,
            max_results_per_search=request.max_results_per_search,
            scrape_contacts=request.scrape_contacts,
            max_leads_per_place=request.max_leads_per_place,
            verify_emails=True
        )

        # -------------------------
        # 2. Normalize & filter by phone/email
        # -------------------------
        valid_leads = []
        for item in raw_results:
            normalized = normalize_lead(item)
            if is_valid_lead(
                normalized,
                require_email=request.require_email,
                require_phone=request.require_phone,
            ):
                valid_leads.append(normalized)

        # -------------------------
        # 3. Apply radius filter locally (optional)
        # -------------------------
        if request.reference_lat is not None and request.reference_lng is not None:
            ref_coords = (request.reference_lat, request.reference_lng)
            filtered_leads = []
            for lead in valid_leads:
                lat = lead.get("lat") or lead.get("latitude")
                lng = lead.get("lng") or lead.get("longitude")
                if lat and lng:
                    if geodesic(ref_coords, (lat, lng)).miles <= request.radius_miles:
                        filtered_leads.append(lead)
            valid_leads = filtered_leads

        # -------------------------
        # 4. Send to n8n asynchronously
        # -------------------------
        if request.send_to_n8n:
            async def send_to_n8n_task(leads):
                for lead in leads:
                    try:
                        await n8n_service.send_lead(lead)
                    except Exception as e:
                        print(f"[Warning] Failed to send lead to n8n: {e}")

            background_tasks.add_task(send_to_n8n_task, valid_leads)

        # -------------------------
        # 5. Return response
        # -------------------------
        return LeadSearchResponse(
            status="success",
            total_raw_results=len(raw_results),
            total_valid_leads=len(valid_leads),
            total_sent_to_n8n=0,  # async
            leads=[Lead(**lead) for lead in valid_leads]
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# -------------------------
# n8n test endpoint
# -------------------------
@app.post("/api/leads/test-n8n")
async def test_n8n():
    test_lead = {
        "business_name": "Test Business",
        "phone": "+1234567890",
        "email": "test@example.com",
        "website": "https://example.com",
        "address": "123 Main St, Test City",
        "category": "Law Office",
        "google_maps_url": "https://maps.google.com",
        "source": "test"
    }

    try:
        n8n_service = N8NService()
        await n8n_service.send_lead(test_lead)
        return {
            "status": "success",
            "message": "Test lead sent to n8n",
            "lead": test_lead
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))