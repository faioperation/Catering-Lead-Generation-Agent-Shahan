from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence
import json
import sqlite3
import uuid

from app.config import settings


DB_PATH = Path(settings.DATABASE_URL.replace("sqlite:///", "")) if settings.DATABASE_URL.startswith("sqlite:///") else Path(settings.DATABASE_URL)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:14]}"


def get_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def row_to_dict(row: sqlite3.Row | None) -> Optional[Dict[str, Any]]:
    if row is None:
        return None
    return dict(row)


def rows_to_dicts(rows: Iterable[sqlite3.Row]) -> List[Dict[str, Any]]:
    return [dict(row) for row in rows]


def init_db() -> None:
    with get_connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS leads (
                id TEXT PRIMARY KEY,
                business_name TEXT,
                phone TEXT,
                email TEXT,
                website TEXT,
                address TEXT,
                category TEXT,
                google_maps_url TEXT,
                source TEXT DEFAULT 'apify_google_places',
                lat REAL,
                lng REAL,
                score INTEGER DEFAULT 0,
                qualification_status TEXT DEFAULT 'Review Required',
                qualification_reason TEXT,
                email_verification_status TEXT DEFAULT 'missing',
                email_verification_reason TEXT,
                raw_json TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_leads_email ON leads(email);
            CREATE INDEX IF NOT EXISTS idx_leads_status ON leads(qualification_status);

            CREATE TABLE IF NOT EXISTS campaigns (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT,
                offer TEXT,
                tone TEXT DEFAULT 'professional',
                target_audience TEXT,
                status TEXT DEFAULT 'draft',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS campaign_leads (
                campaign_id TEXT NOT NULL,
                lead_id TEXT NOT NULL,
                assigned_at TEXT NOT NULL,
                PRIMARY KEY (campaign_id, lead_id),
                FOREIGN KEY (campaign_id) REFERENCES campaigns(id) ON DELETE CASCADE,
                FOREIGN KEY (lead_id) REFERENCES leads(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS outreach_messages (
                id TEXT PRIMARY KEY,
                campaign_id TEXT NOT NULL,
                lead_id TEXT NOT NULL,
                subject TEXT NOT NULL,
                body TEXT NOT NULL,
                status TEXT DEFAULT 'review_required',
                delivery_status TEXT DEFAULT 'not_sent',
                provider_message_id TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                approved_at TEXT,
                sent_at TEXT,
                last_event_at TEXT,
                FOREIGN KEY (campaign_id) REFERENCES campaigns(id) ON DELETE CASCADE,
                FOREIGN KEY (lead_id) REFERENCES leads(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_outreach_status ON outreach_messages(status);
            CREATE INDEX IF NOT EXISTS idx_outreach_campaign ON outreach_messages(campaign_id);
            CREATE UNIQUE INDEX IF NOT EXISTS idx_outreach_unique_draft
            ON outreach_messages(campaign_id, lead_id);
            """
        )
        conn.commit()


def upsert_lead(lead: Dict[str, Any], raw: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    timestamp = now_iso()

    with get_connection() as conn:
        existing = None

        if lead.get("email"):
            existing = conn.execute(
                "SELECT * FROM leads WHERE lower(email) = lower(?) LIMIT 1",
                (lead.get("email"),),
            ).fetchone()

        if existing is None and lead.get("phone"):
            existing = conn.execute(
                "SELECT * FROM leads WHERE phone = ? LIMIT 1",
                (lead.get("phone"),),
            ).fetchone()

        if existing is None and lead.get("business_name") and lead.get("address"):
            existing = conn.execute(
                """
                SELECT * FROM leads
                WHERE lower(business_name) = lower(?) AND lower(address) = lower(?)
                LIMIT 1
                """,
                (lead.get("business_name"), lead.get("address")),
            ).fetchone()

        lead_id = existing["id"] if existing else new_id("lead")
        created_at = existing["created_at"] if existing else timestamp

        data = {
            "id": lead_id,
            "business_name": lead.get("business_name"),
            "phone": lead.get("phone"),
            "email": lead.get("email"),
            "website": lead.get("website"),
            "address": lead.get("address"),
            "category": lead.get("category"),
            "google_maps_url": lead.get("google_maps_url"),
            "source": lead.get("source", "apify_google_places"),
            "lat": lead.get("lat"),
            "lng": lead.get("lng"),
            "score": lead.get("score", 0),
            "qualification_status": lead.get("qualification_status", "Review Required"),
            "qualification_reason": lead.get("qualification_reason"),
            "email_verification_status": lead.get("email_verification_status", "missing"),
            "email_verification_reason": lead.get("email_verification_reason"),
            "raw_json": json.dumps(raw or lead, ensure_ascii=False),
            "created_at": created_at,
            "updated_at": timestamp,
        }

        conn.execute(
            """
            INSERT INTO leads (
                id, business_name, phone, email, website, address, category,
                google_maps_url, source, lat, lng, score, qualification_status,
                qualification_reason, email_verification_status,
                email_verification_reason, raw_json, created_at, updated_at
            ) VALUES (
                :id, :business_name, :phone, :email, :website, :address, :category,
                :google_maps_url, :source, :lat, :lng, :score, :qualification_status,
                :qualification_reason, :email_verification_status,
                :email_verification_reason, :raw_json, :created_at, :updated_at
            )
            ON CONFLICT(id) DO UPDATE SET
                business_name=excluded.business_name,
                phone=excluded.phone,
                email=excluded.email,
                website=excluded.website,
                address=excluded.address,
                category=excluded.category,
                google_maps_url=excluded.google_maps_url,
                source=excluded.source,
                lat=excluded.lat,
                lng=excluded.lng,
                score=excluded.score,
                qualification_status=excluded.qualification_status,
                qualification_reason=excluded.qualification_reason,
                email_verification_status=excluded.email_verification_status,
                email_verification_reason=excluded.email_verification_reason,
                raw_json=excluded.raw_json,
                updated_at=excluded.updated_at
            """,
            data,
        )
        conn.commit()

        return get_lead(lead_id)  # type: ignore[return-value]


def list_leads(status: Optional[str] = None, limit: int = 200) -> List[Dict[str, Any]]:
    with get_connection() as conn:
        if status:
            rows = conn.execute(
                "SELECT * FROM leads WHERE qualification_status = ? ORDER BY updated_at DESC LIMIT ?",
                (status, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM leads ORDER BY updated_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
    return rows_to_dicts(rows)


def get_lead(lead_id: str) -> Optional[Dict[str, Any]]:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM leads WHERE id = ?", (lead_id,)).fetchone()
    return row_to_dict(row)


def create_campaign(data: Dict[str, Any]) -> Dict[str, Any]:
    timestamp = now_iso()
    campaign_id = new_id("camp")
    payload = {
        "id": campaign_id,
        "name": data["name"],
        "description": data.get("description"),
        "offer": data.get("offer"),
        "tone": data.get("tone", "professional"),
        "target_audience": data.get("target_audience"),
        "status": data.get("status", "active"),
        "created_at": timestamp,
        "updated_at": timestamp,
    }

    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO campaigns (
                id, name, description, offer, tone, target_audience, status, created_at, updated_at
            ) VALUES (
                :id, :name, :description, :offer, :tone, :target_audience, :status, :created_at, :updated_at
            )
            """,
            payload,
        )
        conn.commit()

    return get_campaign(campaign_id)  # type: ignore[return-value]


def list_campaigns() -> List[Dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT c.*,
                   COUNT(DISTINCT cl.lead_id) AS assigned_leads,
                   COUNT(DISTINCT om.id) AS outreach_messages
            FROM campaigns c
            LEFT JOIN campaign_leads cl ON cl.campaign_id = c.id
            LEFT JOIN outreach_messages om ON om.campaign_id = c.id
            GROUP BY c.id
            ORDER BY c.created_at DESC
            """
        ).fetchall()
    return rows_to_dicts(rows)


def get_campaign(campaign_id: str) -> Optional[Dict[str, Any]]:
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT c.*,
                   COUNT(DISTINCT cl.lead_id) AS assigned_leads,
                   COUNT(DISTINCT om.id) AS outreach_messages
            FROM campaigns c
            LEFT JOIN campaign_leads cl ON cl.campaign_id = c.id
            LEFT JOIN outreach_messages om ON om.campaign_id = c.id
            WHERE c.id = ?
            GROUP BY c.id
            """,
            (campaign_id,),
        ).fetchone()
    return row_to_dict(row)


def update_campaign(campaign_id: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    allowed = ["name", "description", "offer", "tone", "target_audience", "status"]
    updates = {key: value for key, value in data.items() if key in allowed and value is not None}

    if not updates:
        return get_campaign(campaign_id)

    updates["updated_at"] = now_iso()
    assignments = ", ".join([f"{key} = :{key}" for key in updates])
    updates["id"] = campaign_id

    with get_connection() as conn:
        conn.execute(f"UPDATE campaigns SET {assignments} WHERE id = :id", updates)
        conn.commit()

    return get_campaign(campaign_id)


def assign_leads_to_campaign(campaign_id: str, lead_ids: Sequence[str]) -> List[str]:
    timestamp = now_iso()
    assigned: List[str] = []

    with get_connection() as conn:
        for lead_id in lead_ids:
            lead = conn.execute("SELECT id FROM leads WHERE id = ?", (lead_id,)).fetchone()
            if not lead:
                continue

            conn.execute(
                """
                INSERT OR IGNORE INTO campaign_leads (campaign_id, lead_id, assigned_at)
                VALUES (?, ?, ?)
                """,
                (campaign_id, lead_id, timestamp),
            )
            assigned.append(lead_id)

        conn.commit()

    return assigned


def get_campaign_assigned_leads(campaign_id: str) -> List[Dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT l.*
            FROM leads l
            INNER JOIN campaign_leads cl ON cl.lead_id = l.id
            WHERE cl.campaign_id = ?
            ORDER BY cl.assigned_at DESC
            """,
            (campaign_id,),
        ).fetchall()
    return rows_to_dicts(rows)


def create_or_update_outreach_message(
    campaign_id: str,
    lead_id: str,
    subject: str,
    body: str,
    status: str = "review_required",
) -> Dict[str, Any]:
    timestamp = now_iso()

    with get_connection() as conn:
        existing = conn.execute(
            "SELECT id, status FROM outreach_messages WHERE campaign_id = ? AND lead_id = ?",
            (campaign_id, lead_id),
        ).fetchone()

        if existing:
            message_id = existing["id"]
            if existing["status"] not in {"sent", "approved"}:
                conn.execute(
                    """
                    UPDATE outreach_messages
                    SET subject = ?, body = ?, status = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (subject, body, status, timestamp, message_id),
                )
        else:
            message_id = new_id("msg")
            conn.execute(
                """
                INSERT INTO outreach_messages (
                    id, campaign_id, lead_id, subject, body, status,
                    delivery_status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, 'not_sent', ?, ?)
                """,
                (message_id, campaign_id, lead_id, subject, body, status, timestamp, timestamp),
            )

        conn.commit()

    return get_outreach_message(message_id)  # type: ignore[return-value]


def list_outreach_messages(status: Optional[str] = None, campaign_id: Optional[str] = None) -> List[Dict[str, Any]]:
    clauses = []
    params: List[Any] = []

    if status:
        clauses.append("om.status = ?")
        params.append(status)

    if campaign_id:
        clauses.append("om.campaign_id = ?")
        params.append(campaign_id)

    where_sql = "WHERE " + " AND ".join(clauses) if clauses else ""

    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT om.*,
                   l.business_name,
                   l.email,
                   l.phone,
                   l.website,
                   l.address,
                   l.score,
                   l.qualification_status,
                   c.name AS campaign_name
            FROM outreach_messages om
            INNER JOIN leads l ON l.id = om.lead_id
            INNER JOIN campaigns c ON c.id = om.campaign_id
            {where_sql}
            ORDER BY om.updated_at DESC
            """,
            params,
        ).fetchall()
    return rows_to_dicts(rows)


def get_outreach_message(message_id: str) -> Optional[Dict[str, Any]]:
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT om.*,
                   l.business_name,
                   l.email,
                   l.phone,
                   l.website,
                   l.address,
                   l.score,
                   l.qualification_status,
                   c.name AS campaign_name
            FROM outreach_messages om
            INNER JOIN leads l ON l.id = om.lead_id
            INNER JOIN campaigns c ON c.id = om.campaign_id
            WHERE om.id = ?
            """,
            (message_id,),
        ).fetchone()
    return row_to_dict(row)


def update_outreach_message(message_id: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    allowed = ["subject", "body", "status", "delivery_status", "provider_message_id", "sent_at", "approved_at", "last_event_at"]
    updates = {key: value for key, value in data.items() if key in allowed and value is not None}

    if not updates:
        return get_outreach_message(message_id)

    updates["updated_at"] = now_iso()
    assignments = ", ".join([f"{key} = :{key}" for key in updates])
    updates["id"] = message_id

    with get_connection() as conn:
        conn.execute(f"UPDATE outreach_messages SET {assignments} WHERE id = :id", updates)
        conn.commit()

    return get_outreach_message(message_id)


def dashboard_summary() -> Dict[str, Any]:
    with get_connection() as conn:
        lead_counts = rows_to_dicts(
            conn.execute(
                "SELECT qualification_status AS status, COUNT(*) AS total FROM leads GROUP BY qualification_status"
            ).fetchall()
        )
        outreach_counts = rows_to_dicts(
            conn.execute(
                "SELECT status, COUNT(*) AS total FROM outreach_messages GROUP BY status"
            ).fetchall()
        )
        delivery_counts = rows_to_dicts(
            conn.execute(
                "SELECT delivery_status AS status, COUNT(*) AS total FROM outreach_messages GROUP BY delivery_status"
            ).fetchall()
        )
        totals = conn.execute(
            """
            SELECT
              (SELECT COUNT(*) FROM leads) AS total_leads,
              (SELECT COUNT(*) FROM campaigns) AS total_campaigns,
              (SELECT COUNT(*) FROM campaign_leads) AS assigned_leads,
              (SELECT COUNT(*) FROM outreach_messages) AS outreach_messages
            """
        ).fetchone()

    return {
        "totals": row_to_dict(totals),
        "lead_counts": lead_counts,
        "outreach_counts": outreach_counts,
        "delivery_counts": delivery_counts,
    }
