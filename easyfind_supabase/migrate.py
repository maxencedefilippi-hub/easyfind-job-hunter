#!/usr/bin/env python3
"""
Migration Script: SQLite → Supabase (Adapted for actual schema)
Maps existing job_hunter.sqlite data to new multi-tenant Supabase schema.
"""
import os
import sys
import sqlite3
import json
from datetime import datetime
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from easyfind_supabase.client import AdminService, get_supabase_admin

# ============================================================
# CONFIGURATION
# ============================================================

SQLITE_PATH = os.getenv("SQLITE_PATH", "/Users/maxence/Documents/New project/job-hunter-auto/data/job_hunter.sqlite")
TARGET_USER_ID = os.getenv("TARGET_USER_ID")
ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY")


import uuid
from datetime import datetime

# ============================================================
# STATUS MAPPING (SQLite -> Supabase)
# ============================================================
STATUS_MAP = {
    "enriched": "qualified",
    "new": "new",
    "qualified": "qualified",
    "disqualified": "disqualified",
    "contacted": "contacted",
    "sent": "sent",
    "replied": "replied",
    "rejected": "rejected",
    "blacklisted": "blacklisted",
    "formulaire_en_ligne": "formulaire_en_ligne",
}

EMAIL_STATUS_MAP = {
    "skipped": "draft",
    "draft": "draft",
    "queued": "queued",
    "sent": "sent",
    "delivered": "delivered",
    "opened": "opened",
    "clicked": "clicked",
    "replied": "replied",
    "bounced": "bounced",
    "failed": "failed",
}

def map_status(sqlite_status: str) -> str:
    """Map SQLite status to Supabase valid status"""
    return STATUS_MAP.get(sqlite_status, "new")

def map_email_status(sqlite_status: str) -> str:
    """Map SQLite email status to Supabase valid status"""
    return EMAIL_STATUS_MAP.get(sqlite_status, "draft")

# ============================================================
# UTILITIES
# ============================================================

def connect_sqlite():
    if not os.path.exists(SQLITE_PATH):
        raise FileNotFoundError(f"SQLite database not found: {SQLITE_PATH}")
    conn = sqlite3.connect(SQLITE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def fetch_all(conn, table: str):
    cursor = conn.execute(f"SELECT * FROM {table}")
    return [dict(row) for row in cursor.fetchall()]


# ============================================================
# MIGRATION FUNCTIONS
# ============================================================

def migrate_settings(conn, admin: AdminService, user_id: str) -> dict:
    """Create default settings for user (no settings table in SQLite)"""
    default_settings = {
        "user_id": user_id,
        "search_query": "développeur web",
        "search_location": "France",
        "search_radius_km": 50,
        "search_experience": None,
        "search_contract_type": [],
        "search_salary_min": None,
        "search_remote": False,
        "prompts": {
            "qualification": "Analyse cette offre et dis si elle correspond à un profil développeur web fullstack...",
            "email_generation": "Rédige un email de candidature personnalisé...",
            "follow_up": "Rédige un email de relance poli..."
        },
        "autopilot_enabled": False,
        "autopilot_schedule": "0 9 * * *",
        "autopilot_max_per_run": 10,
        "blacklisted_domains": [],
        "whitelisted_domains": [],
        "notify_on_reply": True,
        "notify_on_new_match": True,
        "notify_daily_summary": False,
    }
    res = admin.client.table("settings").upsert(default_settings, on_conflict="user_id").execute()
    return {"settings": len(res.data)}


def migrate_sessions(conn, admin: AdminService, user_id: str) -> dict:
    """Create a default session from existing companies/emails"""
    companies = fetch_all(conn, "companies")
    if not companies:
        return {"sessions": 0}
    
    # Create one session grouping all imported data
    import uuid
    session_id = str(uuid.uuid4())
    session = {
        "id": session_id,
        "user_id": user_id,
        "name": "Import SQLite",
        "kind": "job_search",
        "status": "active",
        "config": {},
        "stats": {
            "total_companies": len(companies),
            "qualified": 0,
            "contacted": 0,
            "replied": 0,
            "emails_sent": 0
        },
        "autopilot_enabled": False,
        "last_run_at": None,
        "next_run_at": None,
        "created_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat(),
    }
    
    res = admin.client.table("sessions").upsert(session, on_conflict="id").execute()
    return {"sessions": len(res.data), "session_id": session_id}


def safe_timestamp(val):
    if not val or val == "":
        return None
    return val

def migrate_companies(conn, admin: AdminService, user_id: str, session_id: str) -> dict:
    """Migrate companies with column mapping"""
    rows = fetch_all(conn, "companies")
    if not rows:
        return {"companies": 0}
    
    import uuid
    companies = []
    id_mapping = {}  # old_id -> new_uuid
    for row in rows:
        old_id = row.get("id")
        new_id = str(uuid.uuid4())
        id_mapping[old_id] = new_id
        companies.append({
            "id": new_id,
            "user_id": user_id,
            "session_id": session_id,
            "company_name": row.get("company_name"),
            "website": row.get("website_url"),
            "domain": row.get("domain"),
            "linkedin_url": None,
            "address": None,
            "city": row.get("city"),
            "country": row.get("country", "France"),
            "postal_code": None,
            "detected_email": row.get("detected_email"),
            "detected_phone": None,
            "contact_form_url": row.get("contact_page_url"),
            "contact_person": None,
            "contact_role": None,
            "status": map_status(row.get("status", "new")),
            "qualification_notes": row.get("notes"),
            "qualification_score": row.get("relevance_score"),
            "source": "sqlite_import",
            "source_url": row.get("source_url"),
            "search_query": row.get("source_query"),
            "raw_data": {k: v for k, v in row.items() if k not in [
                "id", "company_name", "domain", "website_url", "city", "region", "country",
                "source_query", "source_url", "contact_page_url", "careers_page_url",
                "detected_email", "email_confidence", "company_summary", "relevance_score",
                "relevance_reason", "matched_keywords", "status", "created_at", "updated_at",
                "last_contacted_at", "next_followup_at", "notes"
            ]},
            "latest_email_id": None,
            "latest_email_status": None,
            "latest_email_sent_at": None,
            "latest_reply_received_at": None,
            "latest_reply_status": None,
            "created_at": safe_timestamp(row.get("created_at")),
            "updated_at": safe_timestamp(row.get("updated_at")),
            "contacted_at": safe_timestamp(row.get("last_contacted_at")),
            "qualified_at": None,
        })
    
    chunk_size = 100
    total = 0
    for i in range(0, len(companies), chunk_size):
        chunk = companies[i:i + chunk_size]
        res = admin.client.table("companies").upsert(chunk, on_conflict="id").execute()
        total += len(res.data)
    
    # Store mapping for emails migration
    return {"companies": total, "id_mapping": id_mapping}


def migrate_emails(conn, admin: AdminService, user_id: str, session_id: str, id_mapping: dict = None) -> dict:
    """Migrate emails with column mapping"""
    rows = fetch_all(conn, "emails")
    if not rows:
        return {"emails": 0}
    
    import uuid
    emails = []
    for row in rows:
        # Map old company_id to new UUID
        old_company_id = row.get("company_id")
        new_company_id = id_mapping.get(old_company_id) if id_mapping else old_company_id
        
        # Handle timestamps: convert empty strings to None
        def safe_timestamp(val):
            if val is None or val == "":
                return None
            return val
        
        emails.append({
            "id": str(uuid.uuid4()),
            "user_id": user_id,
            "company_id": new_company_id,
            "session_id": session_id,
            "direction": "outbound",
            "gmail_message_id": row.get("gmail_draft_id"),
            "gmail_thread_id": None,
            "gmail_label_ids": [],
            "subject": row.get("subject", ""),
            "body_text": row.get("body"),
            "body_html": None,
            "from_email": "me",
            "to_emails": [row.get("email_to")] if row.get("email_to") else [],
            "cc_emails": [],
            "bcc_emails": [],
            "status": map_email_status(row.get("status", "draft")),
            "generated_by_ai": False,
            "prompt_used": row.get("personalization_notes"),
            "sent_at": safe_timestamp(row.get("sent_at")),
            "opened_at": None,
            "clicked_at": None,
            "replied_at": None,
            "error_message": None,
            "retry_count": 0,
            "created_at": safe_timestamp(row.get("created_at")),
            "updated_at": safe_timestamp(row.get("updated_at")),
        })
    
    chunk_size = 100
    total = 0
    for i in range(0, len(emails), chunk_size):
        chunk = emails[i:i + chunk_size]
        res = admin.client.table("emails").upsert(chunk, on_conflict="id").execute()
        total += len(res.data)
    
    return {"emails": total}


def migrate_blacklist(conn, admin: AdminService, user_id: str) -> dict:
    """Migrate blacklist entries"""
    rows = fetch_all(conn, "blacklist")
    if not rows:
        return {"blacklist": 0}
    
    domains = [row.get("value") for row in rows if row.get("type") == "domain"]
    if not domains:
        return {"blacklist": 0}
    
    # Update settings with blacklisted domains
    res = admin.client.table("settings").update({
        "blacklisted_domains": domains
    }).eq("user_id", user_id).execute()
    
    return {"blacklist": len(domains)}


def migrate_serpapi_key(conn, admin: AdminService, user_id: str) -> dict:
    """Migrate SerpApi key from cache"""
    rows = fetch_all(conn, "serpapi_cache")
    if not rows:
        return {"serpapi_keys": 0}
    
    # We don't have the actual API key in cache, just search results
    # Skip - user will need to add their key manually
    return {"serpapi_keys": 0}


def migrate_job_log(conn, admin: AdminService, user_id: str) -> dict:
    """Migrate logs as job_log entries"""
    rows = fetch_all(conn, "logs")
    if not rows:
        return {"job_log": 0}
    
    import uuid
    logs = []
    for row in rows:
        logs.append({
            "id": str(uuid.uuid4()),
            "user_id": user_id,
            "session_id": None,
            "company_id": None,
            "email_id": None,
            "action": row.get("action", "import"),
            "details": row.get("metadata", {}) if isinstance(row.get("metadata"), dict) else {"message": str(row.get("metadata"))},
            "status": "success" if row.get("level") != "error" else "error",
            "error_message": row.get("message") if row.get("level") == "error" else None,
            "created_at": row.get("timestamp"),
        })
    
    chunk_size = 200
    total = 0
    for i in range(0, len(logs), chunk_size):
        chunk = logs[i:i + chunk_size]
        res = admin.client.table("job_log").upsert(chunk, on_conflict="id").execute()
        total += len(res.data)
    
    return {"job_log": total}


def migrate_oauth_tokens(conn, admin: AdminService, user_id: str) -> dict:
    """No OAuth tokens in old schema"""
    return {"oauth_tokens": 0}


# ============================================================
# MAIN
# ============================================================

def main():
    if not TARGET_USER_ID:
        print("❌ TARGET_USER_ID environment variable required")
        sys.exit(1)
    if not ENCRYPTION_KEY:
        print("❌ ENCRYPTION_KEY environment variable required")
        sys.exit(1)
    
    print(f"🔄 Starting migration for user: {TARGET_USER_ID}")
    print(f"📁 SQLite: {SQLITE_PATH}")
    
    conn = connect_sqlite()
    admin = AdminService()
    
    # Verify/create user in public.users
    user_check = admin.client.table("users").select("id").eq("id", TARGET_USER_ID).execute()
    if not user_check.data:
        auth_user = admin.client.auth.admin.get_user_by_id(TARGET_USER_ID)
        if auth_user and auth_user.user:
            admin.client.table("users").insert({
                "id": TARGET_USER_ID,
                "email": auth_user.user.email,
                "full_name": auth_user.user.user_metadata.get("full_name"),
                "avatar_url": auth_user.user.user_metadata.get("avatar_url")
            }).execute()
            print(f"✅ Created public.users entry for {TARGET_USER_ID}")
        else:
            print(f"❌ User {TARGET_USER_ID} not found in Supabase Auth.")
            sys.exit(1)
    
    results = {}
    
    print("\n📦 Migrating settings...")
    results.update(migrate_settings(conn, admin, TARGET_USER_ID))
    
    print("📦 Migrating sessions...")
    sess_result = migrate_sessions(conn, admin, TARGET_USER_ID)
    results.update(sess_result)
    session_id = sess_result.get("session_id")
    
    if session_id:
        print("📦 Migrating companies...")
        companies_result = migrate_companies(conn, admin, TARGET_USER_ID, session_id)
        results.update(companies_result)
        id_mapping = companies_result.get("id_mapping", {})
        
        print("📦 Migrating emails...")
        results.update(migrate_emails(conn, admin, TARGET_USER_ID, session_id, id_mapping))
    
    print("📦 Migrating blacklist...")
    results.update(migrate_blacklist(conn, admin, TARGET_USER_ID))
    
    print("📦 Migrating SerpApi...")
    results.update(migrate_serpapi_key(conn, admin, TARGET_USER_ID))
    
    print("📦 Migrating job log...")
    results.update(migrate_job_log(conn, admin, TARGET_USER_ID))
    
    print("📦 Migrating OAuth tokens...")
    results.update(migrate_oauth_tokens(conn, admin, TARGET_USER_ID))
    
    print("\n✅ Migration complete!")
    print(f"Results: {json.dumps(results, indent=2)}")
    
    conn.close()


if __name__ == "__main__":
    main()