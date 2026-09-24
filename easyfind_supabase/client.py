"""
Supabase Client Wrapper for EasyFind
Handles: database, auth, storage, realtime
"""
import os
import json
from typing import Optional, Any, Dict, List
from datetime import datetime
from dataclasses import dataclass
from functools import lru_cache

from supabase import create_client, Client
from postgrest import APIError

# Load from environment
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

if not SUPABASE_URL or not SUPABASE_ANON_KEY:
    raise ValueError("SUPABASE_URL and SUPABASE_ANON_KEY must be set")

# ============================================================
# CLIENTS
# ============================================================

# Public client (for user operations with RLS)
@lru_cache(maxsize=1)
def get_supabase() -> Client:
    """Get Supabase client with anon key (RLS enforced)"""
    return create_client(SUPABASE_URL, SUPABASE_ANON_KEY)

# Admin client (for migrations, bypasses RLS)
@lru_cache(maxsize=1)
def get_supabase_admin() -> Client:
    """Get Supabase client with service role key (bypasses RLS)"""
    if not SUPABASE_SERVICE_ROLE_KEY:
        raise ValueError("SUPABASE_SERVICE_ROLE_KEY required for admin operations")
    return create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)


# ============================================================
# ENCRYPTION HELPERS (for API keys, OAuth tokens)
# ============================================================

ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY")  # 32-byte key for AES-256

def encrypt_value(value: str) -> bytes:
    """Encrypt a string value for storage"""
    if not ENCRYPTION_KEY:
        raise ValueError("ENCRYPTION_KEY not set")
    # In production, use proper AES-GCM or libsodium
    # This is a placeholder - implement proper encryption
    from cryptography.fernet import Fernet
    f = Fernet(ENCRYPTION_KEY)
    return f.encrypt(value.encode())

def decrypt_value(encrypted: bytes) -> str:
    """Decrypt a stored value"""
    if not ENCRYPTION_KEY:
        raise ValueError("ENCRYPTION_KEY not set")
    from cryptography.fernet import Fernet
    f = Fernet(ENCRYPTION_KEY)
    return f.decrypt(encrypted).decode()


# ============================================================
# DATA CLASSES
# ============================================================

@dataclass
class UserProfile:
    id: str
    email: str
    full_name: Optional[str] = None
    avatar_url: Optional[str] = None
    created_at: Optional[datetime] = None
    timezone: str = "Europe/Paris"
    language: str = "fr"
    daily_limit: int = 20
    autopilot_enabled: bool = False

@dataclass
class Session:
    id: str
    user_id: str
    name: str
    kind: str  # job_search, prospecting, networking
    status: str = "active"
    config: Dict = None
    stats: Dict = None
    autopilot_enabled: bool = False
    last_run_at: Optional[datetime] = None
    next_run_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

@dataclass
class Company:
    id: str
    user_id: str
    session_id: str
    company_name: str
    website: Optional[str] = None
    domain: Optional[str] = None
    linkedin_url: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    country: str = "France"
    postal_code: Optional[str] = None
    detected_email: Optional[str] = None
    detected_phone: Optional[str] = None
    contact_form_url: Optional[str] = None
    contact_person: Optional[str] = None
    contact_role: Optional[str] = None
    status: str = "new"
    qualification_notes: Optional[str] = None
    qualification_score: Optional[int] = None
    source: Optional[str] = None
    source_url: Optional[str] = None
    search_query: Optional[str] = None
    raw_data: Dict = None
    latest_email_id: Optional[str] = None
    latest_email_status: Optional[str] = None
    latest_email_sent_at: Optional[datetime] = None
    latest_reply_received_at: Optional[datetime] = None
    latest_reply_status: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    contacted_at: Optional[datetime] = None
    qualified_at: Optional[datetime] = None

@dataclass
class Email:
    id: str
    user_id: str
    company_id: str
    session_id: str
    direction: str  # outbound, inbound
    gmail_message_id: Optional[str] = None
    gmail_thread_id: Optional[str] = None
    gmail_label_ids: List[str] = None
    subject: str = ""
    body_text: Optional[str] = None
    body_html: Optional[str] = None
    from_email: str = ""
    to_emails: List[str] = None
    cc_emails: List[str] = None
    bcc_emails: List[str] = None
    status: str = "draft"
    generated_by_ai: bool = False
    prompt_used: Optional[str] = None
    sent_at: Optional[datetime] = None
    opened_at: Optional[datetime] = None
    clicked_at: Optional[datetime] = None
    replied_at: Optional[datetime] = None
    error_message: Optional[str] = None
    retry_count: int = 0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


# ============================================================
# USER OPERATIONS (with RLS)
# ============================================================

class UserService:
    """User-facing operations (RLS enforced)"""
    
    def __init__(self, access_token: Optional[str] = None):
        self.client = get_supabase()
        if access_token:
            self.client.auth.set_session(access_token, "")
    
    # --- Profile ---
    def get_profile(self) -> Optional[UserProfile]:
        res = self.client.table("users").select("*").eq("id", self.client.auth.get_user().id).single().execute()
        return UserProfile(**res.data) if res.data else None
    
    def update_profile(self, **kwargs) -> UserProfile:
        res = self.client.table("users").update(kwargs).eq("id", self.client.auth.get_user().id).execute()
        return UserProfile(**res.data[0])
    
    # --- Settings ---
    def get_settings(self) -> Optional[Dict]:
        user_id = self.client.auth.get_user().id
        res = self.client.table("settings").select("*").eq("user_id", user_id).single().execute()
        return res.data
    
    def update_settings(self, settings: Dict) -> Dict:
        user_id = self.client.auth.get_user().id
        res = self.client.table("settings").upsert({"user_id": user_id, **settings}).execute()
        return res.data[0]
    
    # --- Sessions ---
    def list_sessions(self, status: Optional[str] = None) -> List[Session]:
        query = self.client.table("sessions").select("*").eq("user_id", self.client.auth.get_user().id)
        if status:
            query = query.eq("status", status)
        res = query.order("created_at", desc=True).execute()
        return [Session(**r) for r in res.data]
    
    def get_session(self, session_id: str) -> Optional[Session]:
        res = self.client.table("sessions").select("*").eq("id", session_id).eq("user_id", self.client.auth.get_user().id).single().execute()
        return Session(**res.data) if res.data else None
    
    def create_session(self, name: str, kind: str = "job_search", config: Dict = None) -> Session:
        user_id = self.client.auth.get_user().id
        res = self.client.table("sessions").insert({
            "user_id": user_id,
            "name": name,
            "kind": kind,
            "config": config or {}
        }).execute()
        return Session(**res.data[0])
    
    def update_session(self, session_id: str, **kwargs) -> Session:
        res = self.client.table("sessions").update(kwargs).eq("id", session_id).eq("user_id", self.client.auth.get_user().id).execute()
        return Session(**res.data[0])
    
    def delete_session(self, session_id: str) -> bool:
        res = self.client.table("sessions").delete().eq("id", session_id).eq("user_id", self.client.auth.get_user().id).execute()
        return len(res.data) > 0
    
    # --- Companies ---
    def list_companies(self, session_id: Optional[str] = None, status: Optional[str] = None, limit: int = 50, offset: int = 0) -> List[Company]:
        query = self.client.table("companies").select("*").eq("user_id", self.client.auth.get_user().id)
        if session_id:
            query = query.eq("session_id", session_id)
        if status:
            query = query.eq("status", status)
        res = query.order("created_at", desc=True).range(offset, offset + limit - 1).execute()
        return [Company(**r) for r in res.data]
    
    def get_company(self, company_id: str) -> Optional[Company]:
        res = self.client.table("companies").select("*").eq("id", company_id).eq("user_id", self.client.auth.get_user().id).single().execute()
        return Company(**res.data) if res.data else None
    
    def create_company(self, session_id: str, data: Dict) -> Company:
        user_id = self.client.auth.get_user().id
        data["user_id"] = user_id
        data["session_id"] = session_id
        res = self.client.table("companies").insert(data).execute()
        return Company(**res.data[0])
    
    def update_company(self, company_id: str, **kwargs) -> Company:
        res = self.client.table("companies").update(kwargs).eq("id", company_id).eq("user_id", self.client.auth.get_user().id).execute()
        return Company(**res.data[0])
    
    def delete_company(self, company_id: str) -> bool:
        res = self.client.table("companies").delete().eq("id", company_id).eq("user_id", self.client.auth.get_user().id).execute()
        return len(res.data) > 0
    
    # --- Emails ---
    def list_emails(self, company_id: Optional[str] = None, session_id: Optional[str] = None, limit: int = 50, offset: int = 0) -> List[Email]:
        query = self.client.table("emails").select("*").eq("user_id", self.client.auth.get_user().id)
        if company_id:
            query = query.eq("company_id", company_id)
        if session_id:
            query = query.eq("session_id", session_id)
        res = query.order("created_at", desc=True).range(offset, offset + limit - 1).execute()
        return [Email(**r) for r in res.data]
    
    def get_email(self, email_id: str) -> Optional[Email]:
        res = self.client.table("emails").select("*").eq("id", email_id).eq("user_id", self.client.auth.get_user().id).single().execute()
        return Email(**res.data) if res.data else None
    
    def create_email(self, data: Dict) -> Email:
        user_id = self.client.auth.get_user().id
        data["user_id"] = user_id
        res = self.client.table("emails").insert(data).execute()
        return Email(**res.data[0])
    
    def update_email(self, email_id: str, **kwargs) -> Email:
        res = self.client.table("emails").update(kwargs).eq("id", email_id).eq("user_id", self.client.auth.get_user().id).execute()
        return Email(**res.data[0])
    
    # --- OAuth Tokens ---
    def save_oauth_token(self, provider: str, access_token: str, refresh_token: Optional[str] = None, expires_at: Optional[datetime] = None, scope: Optional[str] = None):
        user_id = self.client.auth.get_user().id
        data = {
            "user_id": user_id,
            "provider": provider,
            "access_token_enc": encrypt_value(access_token),
            "expires_at": expires_at.isoformat() if expires_at else None,
            "scope": scope
        }
        if refresh_token:
            data["refresh_token_enc"] = encrypt_value(refresh_token)
        res = self.client.table("oauth_tokens").upsert(data, on_conflict="user_id,provider").execute()
        return res.data[0]
    
    def get_oauth_token(self, provider: str) -> Optional[Dict]:
        user_id = self.client.auth.get_user().id
        res = self.client.table("oauth_tokens").select("*").eq("user_id", user_id).eq("provider", provider).single().execute()
        if not res.data:
            return None
        data = res.data
        return {
            "access_token": decrypt_value(data["access_token_enc"]),
            "refresh_token": decrypt_value(data["refresh_token_enc"]) if data.get("refresh_token_enc") else None,
            "expires_at": data.get("expires_at"),
            "scope": data.get("scope")
        }
    
    # --- SerpApi Key ---
    def save_serpapi_key(self, api_key: str, monthly_quota: int = 100):
        user_id = self.client.auth.get_user().id
        res = self.client.table("serpapi_keys").upsert({
            "user_id": user_id,
            "api_key_enc": encrypt_value(api_key),
            "monthly_quota": monthly_quota
        }).execute()
        return res.data[0]
    
    def get_serpapi_usage(self) -> Dict:
        user_id = self.client.auth.get_user().id
        res = self.client.rpc("get_serpapi_usage").execute()
        return res.data or {"used": 0, "quota": 100, "remaining": 100, "reset_at": None}
    
    def increment_serpapi_usage(self):
        self.client.rpc("increment_serpapi_usage").execute()
    
    # --- Job Log ---
    def get_job_log(self, session_id: Optional[str] = None, limit: int = 100) -> List[Dict]:
        query = self.client.table("job_log").select("*").eq("user_id", self.client.auth.get_user().id)
        if session_id:
            query = query.eq("session_id", session_id)
        res = query.order("created_at", desc=True).limit(limit).execute()
        return res.data


# ============================================================
# ADMIN OPERATIONS (bypass RLS - for migrations, cron jobs)
# ============================================================

class AdminService:
    """Admin operations (bypasses RLS with service role key)"""
    
    def __init__(self):
        self.client = get_supabase_admin()
    
    def migrate_user_data(self, user_id: str, data: Dict) -> Dict:
        """Migrate all data for a user (companies, emails, sessions, etc.)"""
        results = {}
        
        # Sessions
        if "sessions" in data:
            for s in data["sessions"]:
                s["user_id"] = user_id
            res = self.client.table("sessions").upsert(data["sessions"], on_conflict="id").execute()
            results["sessions"] = len(res.data)
        
        # Companies
        if "companies" in data:
            for c in data["companies"]:
                c["user_id"] = user_id
            res = self.client.table("companies").upsert(data["companies"], on_conflict="id").execute()
            results["companies"] = len(res.data)
        
        # Emails
        if "emails" in data:
            for e in data["emails"]:
                e["user_id"] = user_id
            res = self.client.table("emails").upsert(data["emails"], on_conflict="id").execute()
            results["emails"] = len(res.data)
        
        # Settings
        if "settings" in data:
            data["settings"]["user_id"] = user_id
            res = self.client.table("settings").upsert(data["settings"], on_conflict="user_id").execute()
            results["settings"] = 1
        
        return results
    
    def get_all_users(self) -> List[Dict]:
        return self.client.table("users").select("*").execute().data
    
    def get_user_stats(self, user_id: str) -> Dict:
        sessions = self.client.table("sessions").select("id", count="exact").eq("user_id", user_id).execute()
        companies = self.client.table("companies").select("id", count="exact").eq("user_id", user_id).execute()
        emails = self.client.table("emails").select("id", count="exact").eq("user_id", user_id).execute()
        return {
            "sessions": sessions.count,
            "companies": companies.count,
            "emails": emails.count
        }


# ============================================================
# AUTH HELPERS
# ============================================================

class AuthService:
    """Supabase Auth operations"""
    
    def __init__(self):
        self.client = get_supabase()
    
    def sign_up(self, email: str, password: str, metadata: Dict = None) -> Dict:
        res = self.client.auth.sign_up({
            "email": email,
            "password": password,
            "options": {"data": metadata or {}}
        })
        return {"user": res.user, "session": res.session}
    
    def sign_in(self, email: str, password: str) -> Dict:
        res = self.client.auth.sign_in_with_password({"email": email, "password": password})
        return {"user": res.user, "session": res.session}
    
    def sign_in_with_oauth(self, provider: str, redirect_to: str) -> Dict:
        res = self.client.auth.sign_in_with_oauth({
            "provider": provider,
            "options": {"redirect_to": redirect_to}
        })
        return {"url": res.url}
    
    def sign_out(self):
        self.client.auth.sign_out()
    
    def get_session(self) -> Optional[Dict]:
        session = self.client.auth.get_session()
        return {"access_token": session.access_token, "refresh_token": session.refresh_token} if session else None
    
    def refresh_session(self, refresh_token: str) -> Dict:
        res = self.client.auth.refresh_session(refresh_token)
        return {"access_token": res.session.access_token, "refresh_token": res.session.refresh_token}
    
    def reset_password(self, email: str, redirect_to: str):
        self.client.auth.reset_password_for_email(email, {"redirect_to": redirect_to})
    
    def update_password(self, new_password: str):
        self.client.auth.update_user({"password": new_password})


# ============================================================
# REALTIME SUBSCRIPTIONS
# ============================================================

def subscribe_to_companies(user_id: str, callback):
    """Subscribe to realtime changes for user's companies"""
    client = get_supabase()
    return client.channel(f"companies:{user_id}") \
        .on("postgres_changes", {"event": "*", "schema": "public", "table": "companies", "filter": f"user_id=eq.{user_id}"}, callback) \
        .subscribe()

def subscribe_to_emails(user_id: str, callback):
    client = get_supabase()
    return client.channel(f"emails:{user_id}") \
        .on("postgres_changes", {"event": "*", "schema": "public", "table": "emails", "filter": f"user_id=eq.{user_id}"}, callback) \
        .subscribe()

def subscribe_to_sessions(user_id: str, callback):
    client = get_supabase()
    return client.channel(f"sessions:{user_id}") \
        .on("postgres_changes", {"event": "*", "schema": "public", "table": "sessions", "filter": f"user_id=eq.{user_id}"}, callback) \
        .subscribe()