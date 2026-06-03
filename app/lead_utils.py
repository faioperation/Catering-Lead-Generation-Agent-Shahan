from typing import Any, Dict, List, Optional
import re


EMAIL_REGEX = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")


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
        match = EMAIL_REGEX.search(value)
        return match.group(0) if match else None

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

    # Check contact details lists
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
            for key, value in nested.items():
                email = extract_email_from_text(value)
                if email:
                    return email

    # Final fallback: scan the whole item as text
    email = extract_email_from_text(str(item))
    return email


def normalize_lead(item: Dict[str, Any]) -> Dict[str, Any]:
    """
    Converts raw Apify item to our clean lead format.
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

    return {
        "business_name": business_name,
        "phone": phone,
        "email": email,
        "website": website,
        "address": address,
        "category": category,
        "google_maps_url": google_maps_url,
        "source": "apify_google_places",
    }


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