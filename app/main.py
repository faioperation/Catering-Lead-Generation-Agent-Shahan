# app/main.py
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from app.schemas import LeadSearchRequest, LeadSearchResponse, Lead
from app.apify_service import ApifyService
from app.n8n_service import N8NService
from app.lead_utils import normalize_lead, is_valid_lead

app = FastAPI(
    title="Google Places Lead Generation API",
    version="1.2.0",
    description="FastAPI API for generating business leads via Apify and sending them to n8n."
)

# CORS setup to allow testing from Swagger UI / browser
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # use specific domains in production
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
    """
    Generate leads via Apify actor and optionally send them to n8n asynchronously.
    """
    apify_service = ApifyService()
    n8n_service = N8NService()

    try:
        # Call Apify actor
        raw_results = await apify_service.run_google_places_scraper(
            location=request.location,
            search_terms=request.search_terms,
            max_results_per_search=request.max_results_per_search,
            scrape_contacts=request.scrape_contacts,
            max_leads_per_place=request.max_leads_per_place,
            verify_emails=True  # enable email extraction
        )

        # Normalize and filter leads
        valid_leads = []
        for item in raw_results:
            normalized = normalize_lead(item)
            if is_valid_lead(
                normalized,
                require_email=request.require_email,
                require_phone=request.require_phone,
            ):
                valid_leads.append(normalized)

        # Background task to send leads to n8n
        if request.send_to_n8n:
            async def send_to_n8n_task(leads):
                for lead in leads:
                    try:
                        await n8n_service.send_lead(lead)
                    except Exception as e:
                        print(f"[Warning] Failed to send lead to n8n: {e}")

            background_tasks.add_task(send_to_n8n_task, valid_leads)

        return LeadSearchResponse(
            status="success",
            total_raw_results=len(raw_results),
            total_valid_leads=len(valid_leads),
            total_sent_to_n8n=0,  # handled asynchronously
            leads=[Lead(**lead) for lead in valid_leads]
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/leads/test-n8n")
async def test_n8n():
    """
    Test endpoint for sending a dummy lead to n8n webhook.
    """
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
        return {"status": "success", "message": "Test lead sent to n8n", "lead": test_lead}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

