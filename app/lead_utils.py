from typing import Any, Dict, List, Optional, Tuple
import re
import socket


EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")
EMAIL_FIND_REGEX = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")

ROLE_EMAIL_PREFIXES = {
    "info",
    "contact",
    "hello",
    "admin",
    "support",
    "sales",
    "office",
    "team",
    "enquiries",
    "inquiries",
}

DISPOSABLE_DOMAINS = {
    "mailinator.com",
    "tempmail.com",
    "10minutemail.com",
    "guerrillamail.com",
    "yopmail.com",
}


QUALIFIED = "Qualified"
REVIEW_REQUIRED = "Review Required"
REJECTED = "Rejected"


def normalize_phone(value: Any) -> Optional[str]:
    if not value:
        return None

    phone = str(value).strip()

    if not phone:
        return None

    return phone


def extract_email_from_text(value: Any) -> Optional[str]:
    if not value:
        return None

    if isinstance(value, str):
        match = EMAIL_FIND_REGEX.search(value)
        return match.group(0).strip(".,;:()[]{}<>") if match else None

    return None


def extract_email_from_nested_data(item: Dict[str, Any]) -> Optional[str]:
    """
    Apify outputs can vary depending on enabled enrichment.
    This function tries multiple possible locations.
    """

    direct_fields = [
        "email",
        "emails",
        "contactEmail",
        "businessEmail",
        "leadEmail",
    ]

    for field in direct_fields:
        value = item.get(field)

        if isinstance(value, str):
            email = extract_email_from_text(value)
            if email:
                return email

        if isinstance(value, list):
            for entry in value:
                if isinstance(entry, str):
                    email = extract_email_from_text(entry)
                    if email:
                        return email

                if isinstance(entry, dict):
                    for key in ["email", "value", "address"]:
                        email = extract_email_from_text(entry.get(key))
                        if email:
                            return email

    possible_nested_lists = [
        "contacts",
        "contactDetails",
        "people",
        "leads",
        "leadsEnrichment",
        "emailsFromWebsite",
    ]

    for list_name in possible_nested_lists:
        nested = item.get(list_name)

        if isinstance(nested, list):
            for entry in nested:
                if isinstance(entry, dict):
                    for key in ["email", "workEmail", "personalEmail", "value"]:
                        email = extract_email_from_text(entry.get(key))
                        if email:
                            return email

                elif isinstance(entry, str):
                    email = extract_email_from_text(entry)
                    if email:
                        return email

        elif isinstance(nested, dict):
            for _, value in nested.items():
                email = extract_email_from_text(value)
                if email:
                    return email

    email = extract_email_from_text(str(item))
    return email


def normalize_lead(item: Dict[str, Any]) -> Dict[str, Any]:
    """
    Converts raw Apify item to the clean lead format used by this app.
    """

    business_name = (
        item.get("title")
        or item.get("name")
        or item.get("businessName")
        or item.get("placeName")
    )

    phone = normalize_phone(
        item.get("phone")
        or item.get("phoneNumber")
        or item.get("contactPhone")
        or item.get("internationalPhoneNumber")
    )

    email = extract_email_from_nested_data(item)

    website = (
        item.get("website")
        or item.get("url")
        or item.get("websiteUrl")
        or item.get("site")
    )

    address = (
        item.get("address")
        or item.get("street")
        or item.get("fullAddress")
        or item.get("location")
    )

    category = None

    if isinstance(item.get("categoryName"), str):
        category = item.get("categoryName")
    elif isinstance(item.get("categories"), list) and item.get("categories"):
        category = ", ".join([str(c) for c in item.get("categories")])

    google_maps_url = (
        item.get("url")
        or item.get("placeUrl")
        or item.get("googleMapsUrl")
        or item.get("mapsUrl")
    )

    lat = item.get("lat") or item.get("latitude")
    lng = item.get("lng") or item.get("longitude")

    if not lat and isinstance(item.get("location"), dict):
        lat = item.get("location", {}).get("lat")
    if not lng and isinstance(item.get("location"), dict):
        lng = item.get("location", {}).get("lng")

    return {
        "business_name": business_name,
        "phone": phone,
        "email": email,
        "website": website,
        "address": address if isinstance(address, str) else None,
        "category": category,
        "google_maps_url": google_maps_url,
        "source": "apify_google_places",
        "lat": lat,
        "lng": lng,
    }


def verify_email_basic(email: Optional[str]) -> Tuple[str, str]:
    """
    Lightweight email verification layer.
    This is intentionally not a paid verifier. It checks syntax, disposable domains,
    and whether the domain resolves. Real mailbox validation should be plugged in later.
    """

    if not email:
        return "missing", "No email found."

    email = email.strip().lower()

    if not EMAIL_REGEX.match(email):
        return "invalid", "Email syntax is invalid."

    local_part, domain = email.rsplit("@", 1)

    if domain in DISPOSABLE_DOMAINS:
        return "risky", "Disposable email domain."

    if local_part in ROLE_EMAIL_PREFIXES:
        return "valid_role", "Role-based business email."

    try:
        socket.gethostbyname(domain)
    except Exception:
        return "risky", "Email domain could not be resolved."

    return "valid", "Email syntax and domain look valid."


def score_and_categorize_lead(
    lead: Dict[str, Any],
    search_terms: Optional[List[str]] = None,
) -> Dict[str, Any]:
    score = 0
    reasons: List[str] = []

    if lead.get("business_name"):
        score += 15
        reasons.append("Business name found")

    if lead.get("email"):
        score += 25
        reasons.append("Email found")

    if lead.get("phone"):
        score += 20
        reasons.append("Phone found")

    if lead.get("website"):
        score += 15
        reasons.append("Website found")

    if lead.get("address"):
        score += 10
        reasons.append("Address found")

    if lead.get("google_maps_url"):
        score += 5
        reasons.append("Google Maps profile found")

    category = (lead.get("category") or "").lower()
    business_name = (lead.get("business_name") or "").lower()
    terms = [term.lower() for term in (search_terms or [])]

    if any(term in category or term in business_name for term in terms):
        score += 10
        reasons.append("Matches campaign/search intent")

    email_status, email_reason = verify_email_basic(lead.get("email"))
    lead["email_verification_status"] = email_status
    lead["email_verification_reason"] = email_reason

    if email_status in {"valid", "valid_role"}:
        score += 5
        reasons.append(email_reason)
    elif email_status == "risky":
        score -= 5
        reasons.append(email_reason)

    score = max(0, min(score, 100))

    if score >= 70:
        status = QUALIFIED
    elif score >= 45:
        status = REVIEW_REQUIRED
    else:
        status = REJECTED

    lead["score"] = score
    lead["qualification_status"] = status
    lead["qualification_reason"] = "; ".join(reasons) if reasons else "Insufficient lead data."

    return lead


def is_valid_lead(
    lead: Dict[str, Any],
    require_email: bool = True,
    require_phone: bool = True,
) -> bool:
    if not lead.get("business_name"):
        return False

    if require_phone and not lead.get("phone"):
        return False

    if require_email and not lead.get("email"):
        return False

    return True
