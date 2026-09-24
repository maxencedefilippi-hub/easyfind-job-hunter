"""
FastAPI Backend for EasyFind — Supabase Multi-Tenant
Endpoints for frontend, background jobs, webhooks
"""
import os
import json
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends, HTTPException, Request, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr, Field
from pydantic_settings import BaseSettings
from supabase import create_client, Client
import httpx

# ============================================================
# CONFIG
# ============================================================

class Settings(BaseSettings):
    # Supabase
    SUPABASE_URL: str
    SUPABASE_ANON_KEY: str
    SUPABASE_SERVICE_ROLE_KEY: str
    
    # App
    APP_ENV: str = "development"
    FRONTEND_URL: str = "http://localhost:8787"
    ENCRYPTION_KEY: str  # 32 bytes for Fernet
    
    # Google OAuth
    GOOGLE_CLIENT_ID: str
    GOOGLE_CLIENT_SECRET: str
    GOOGLE_REDIRECT_URI: str
    
    # SerpApi (shared or BYOK)
    SERPAPI_SHARED_KEY: Optional[str] = None
    
    # Scheduler
    SCHEDULER_ENABLED: bool = True
    
    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()

# ============================================================
# SUPABASE CLIENTS
# ============================================================

# Public client (RLS)
supabase: Client = create_client(settings.SUPABASE_URL, settings.SUPABASE_ANON_KEY)

# Admin client (bypass RLS)
supabase_admin: Client = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)

# ============================================================
# ENCRYPTION
# ============================================================

from cryptography.fernet import Fernet

fernet = Fernet(settings.ENCRYPTION_KEY.encode() if isinstance(settings.ENCRYPTION_KEY, str) else settings.ENCRYPTION_KEY)

def encrypt(value: str) -> bytes:
    return fernet.encrypt(value.encode())

def decrypt(encrypted: bytes) -> str:
    return fernet.decrypt(encrypted).decode()

# ============================================================
# AUTH DEPENDENCIES
# ============================================================

security = HTTPBearer(auto_error=False)

async def get_current_user(credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)):
    """Validate JWT and return user"""
    if not credentials:
        raise HTTPException(401, "Authentication required")
    
    try:
        # Verify JWT with Supabase
        user = supabase.auth.get_user(credentials.credentials)
        if not user or not user.user:
            raise HTTPException(401, "Invalid token")
        return user.user
    except Exception as e:
        raise HTTPException(401, f"Authentication failed: {e}")

async def get_current_user_id(user=Depends(get_current_user)) -> str:
    return user.id

# ============================================================
# PYDANTIC MODELS
# ============================================================

# Auth
class SignUpRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    full_name: Optional[str] = None

class SignInRequest(BaseModel):
    email: EmailStr
    password: str

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    user: Dict[str, Any]

# Sessions
class SessionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    kind: str = Field(default="job_search", pattern="^(job_search|prospecting|networking)$")
    config: Dict = Field(default_factory=dict)

class SessionUpdate(BaseModel):
    name: Optional[str] = None
    status: Optional[str] = Field(default=None, pattern="^(active|paused|archived)$")
    config: Optional[Dict] = None
    autopilot_enabled: Optional[bool] = None

class SessionResponse(BaseModel):
    id: str
    name: str
    kind: str
    status: str
    config: Dict
    stats: Dict
    autopilot_enabled: bool
    last_run_at: Optional[datetime]
    next_run_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime

# Companies
class CompanyCreate(BaseModel):
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
    raw_data: Dict = Field(default_factory=dict)

class CompanyUpdate(BaseModel):
    status: Optional[str] = None
    qualification_notes: Optional[str] = None
    qualification_score: Optional[int] = None
    detected_email: Optional[str] = None
    contact_person: Optional[str] = None
    contact_role: Optional[str] = None
    contact_form_url: Optional[str] = None
    raw_data: Optional[Dict] = None

class CompanyResponse(BaseModel):
    id: str
    session_id: str
    company_name: str
    website: Optional[str]
    domain: Optional[str]
    status: str
    detected_email: Optional[str]
    qualification_score: Optional[int]
    latest_email_status: Optional[str]
    created_at: datetime
    updated_at: datetime

# Emails
class EmailCreate(BaseModel):
    company_id: str
    session_id: str
    direction: str = Field(pattern="^(outbound|inbound)$")
    subject: str
    body_text: Optional[str] = None
    body_html: Optional[str] = None
    from_email: str
    to_emails: List[str]
    cc_emails: List[str] = []
    bcc_emails: List[str] = []
    gmail_message_id: Optional[str] = None
    gmail_thread_id: Optional[str] = None
    generated_by_ai: bool = False
    prompt_used: Optional[str] = None

class EmailUpdate(BaseModel):
    status: Optional[str] = None
    body_text: Optional[str] = None
    body_html: Optional[str] = None
    sent_at: Optional[datetime] = None

# Settings
class SettingsUpdate(BaseModel):
    search_query: Optional[str] = None
    search_location: Optional[str] = None
    search_radius_km: Optional[int] = None
    search_experience: Optional[str] = None
    search_contract_type: Optional[List[str]] = None
    search_salary_min: Optional[int] = None
    search_remote: Optional[bool] = None
    prompts: Optional[Dict] = None
    autopilot_enabled: Optional[bool] = None
    autopilot_schedule: Optional[str] = None
    autopilot_max_per_run: Optional[int] = None
    blacklisted_domains: Optional[List[str]] = None
    whitelisted_domains: Optional[List[str]] = None
    notify_on_reply: Optional[bool] = None
    notify_on_new_match: Optional[bool] = None
    notify_daily_summary: Optional[bool] = None

# OAuth / SerpApi
class OAuthTokenRequest(BaseModel):
    provider: str = Field(pattern="^(google)$")
    access_token: str
    refresh_token: Optional[str] = None
    expires_at: Optional[datetime] = None
    scope: Optional[str] = None

class SerpApiKeyRequest(BaseModel):
    api_key: str
    monthly_quota: int = 100

# State (for dashboard)
class DashboardState(BaseModel):
    companies: List[CompanyResponse]
    emails: List[Dict]
    sessions: List[SessionResponse]
    active_session_id: Optional[str]
    stats: Dict
    connections: Dict
    parameters: Dict
    prompts: Dict
    copy: Dict

# ============================================================
# LIFESPAN
# ============================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logging.info("🚀 Starting EasyFind Backend")
    
    # Start scheduler if enabled
    if settings.SCHEDULER_ENABLED:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        from apscheduler.triggers.cron import CronTrigger
        
        scheduler = AsyncIOScheduler()
        
        # Daily autopilot job
        @scheduler.scheduled_job(CronTrigger.from_crontab("0 9 * * *"))
        async def daily_autopilot():
            await run_autopilot_for_all_users()
        
        scheduler.start()
        app.state.scheduler = scheduler
        logging.info("⏰ Scheduler started")
    
    yield
    
    # Shutdown
    if hasattr(app.state, "scheduler"):
        app.state.scheduler.shutdown()
    logging.info("👋 Shutting down")

# ============================================================
# APP
# ============================================================

app = FastAPI(
    title="EasyFind API",
    description="Multi-tenant job hunting assistant",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_URL, "http://localhost:8787", "http://127.0.0.1:8787"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================
# HEALTH
# ============================================================

@app.get("/health")
async def health():
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}

# ============================================================
# AUTH ENDPOINTS
# ============================================================

@app.post("/auth/signup", response_model=TokenResponse)
async def signup(data: SignUpRequest):
    try:
        res = supabase.auth.sign_up({
            "email": data.email,
            "password": data.password,
            "options": {"data": {"full_name": data.full_name}}
        })
        if not res.session:
            raise HTTPException(400, "Signup failed - check email confirmation")
        return {
            "access_token": res.session.access_token,
            "refresh_token": res.session.refresh_token,
            "user": {"id": res.user.id, "email": res.user.email}
        }
    except Exception as e:
        raise HTTPException(400, str(e))

@app.post("/auth/signin", response_model=TokenResponse)
async def signin(data: SignInRequest):
    try:
        res = supabase.auth.sign_in_with_password({
            "email": data.email,
            "password": data.password
        })
        return {
            "access_token": res.session.access_token,
            "refresh_token": res.session.refresh_token,
            "user": {"id": res.user.id, "email": res.user.email}
        }
    except Exception as e:
        raise HTTPException(401, str(e))

@app.post("/auth/signout")
async def signout(user_id: str = Depends(get_current_user_id)):
    supabase.auth.sign_out()
    return {"ok": True}

@app.post("/auth/refresh", response_model=TokenResponse)
async def refresh_token(refresh_token: str):
    try:
        res = supabase.auth.refresh_session(refresh_token)
        return {
            "access_token": res.session.access_token,
            "refresh_token": res.session.refresh_token,
            "user": {"id": res.user.id, "email": res.user.email}
        }
    except Exception as e:
        raise HTTPException(401, str(e))

@app.get("/auth/oauth/{provider}")
async def oauth_login(provider: str, user_id: str = Depends(get_current_user_id)):
    """Initiate OAuth flow (Google)"""
    if provider != "google":
        raise HTTPException(400, "Only Google OAuth supported")
    
    redirect_to = f"{settings.FRONTEND_URL}/auth/callback"
    res = supabase.auth.sign_in_with_oauth({
        "provider": "google",
        "options": {
            "redirect_to": redirect_to,
            "scopes": "https://www.googleapis.com/auth/gmail.send https://www.googleapis.com/auth/userinfo.email https://www.googleapis.com/auth/userinfo.profile"
        }
    })
    return {"url": res.url}

@app.post("/auth/oauth/callback")
async def oauth_callback(provider: str, code: str, user_id: str = Depends(get_current_user_id)):
    """Handle OAuth callback - exchange code for tokens"""
    # Supabase handles the callback, we just store the tokens
    # In practice, Supabase handles this via the redirect
    return {"ok": True}

# ============================================================
# USER PROFILE
# ============================================================

@app.get("/user/profile")
async def get_profile(user_id: str = Depends(get_current_user_id)):
    res = supabase.table("users").select("*").eq("id", user_id).single().execute()
    if not res.data:
        raise HTTPException(404, "Profile not found")
    return res.data

@app.patch("/user/profile")
async def update_profile(data: Dict, user_id: str = Depends(get_current_user_id)):
    res = supabase.table("users").update(data).eq("id", user_id).execute()
    return res.data[0]

# ============================================================
# SETTINGS
# ============================================================

@app.get("/settings")
async def get_settings(user_id: str = Depends(get_current_user_id)):
    res = supabase.table("settings").select("*").eq("user_id", user_id).single().execute()
    if not res.data:
        # Create default settings
        default = {"user_id": user_id}
        res = supabase.table("settings").insert(default).execute()
        return res.data[0]
    return res.data

@app.patch("/settings")
async def update_settings(data: SettingsUpdate, user_id: str = Depends(get_current_user_id)):
    update_data = data.model_dump(exclude_unset=True)
    update_data["updated_at"] = datetime.utcnow().isoformat()
    res = supabase.table("settings").upsert({"user_id": user_id, **update_data}, on_conflict="user_id").execute()
    return res.data[0]

# ============================================================
# SESSIONS
# ============================================================

@app.get("/sessions", response_model=List[SessionResponse])
async def list_sessions(status: Optional[str] = None, user_id: str = Depends(get_current_user_id)):
    query = supabase.table("sessions").select("*").eq("user_id", user_id)
    if status:
        query = query.eq("status", status)
    res = query.order("created_at", desc=True).execute()
    return res.data

@app.post("/sessions", response_model=SessionResponse)
async def create_session(data: SessionCreate, user_id: str = Depends(get_current_user_id)):
    res = supabase.table("sessions").insert({
        "user_id": user_id,
        "name": data.name,
        "kind": data.kind,
        "config": data.config
    }).execute()
    return res.data[0]

@app.get("/sessions/{session_id}", response_model=SessionResponse)
async def get_session(session_id: str, user_id: str = Depends(get_current_user_id)):
    res = supabase.table("sessions").select("*").eq("id", session_id).eq("user_id", user_id).single().execute()
    if not res.data:
        raise HTTPException(404, "Session not found")
    return res.data

@app.patch("/sessions/{session_id}", response_model=SessionResponse)
async def update_session(session_id: str, data: SessionUpdate, user_id: str = Depends(get_current_user_id)):
    update_data = data.model_dump(exclude_unset=True)
    update_data["updated_at"] = datetime.utcnow().isoformat()
    res = supabase.table("sessions").update(update_data).eq("id", session_id).eq("user_id", user_id).execute()
    if not res.data:
        raise HTTPException(404, "Session not found")
    return res.data[0]

@app.delete("/sessions/{session_id}")
async def delete_session(session_id: str, user_id: str = Depends(get_current_user_id)):
    res = supabase.table("sessions").delete().eq("id", session_id).eq("user_id", user_id).execute()
    return {"ok": True}

# ============================================================
# COMPANIES
# ============================================================

@app.get("/companies", response_model=List[CompanyResponse])
async def list_companies(
    session_id: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    user_id: str = Depends(get_current_user_id)
):
    query = supabase.table("companies").select("*").eq("user_id", user_id)
    if session_id:
        query = query.eq("session_id", session_id)
    if status:
        query = query.eq("status", status)
    res = query.order("created_at", desc=True).range(offset, offset + limit - 1).execute()
    return res.data

@app.post("/companies", response_model=CompanyResponse)
async def create_company(data: CompanyCreate, user_id: str = Depends(get_current_user_id)):
    # Verify session belongs to user
    session_check = supabase.table("sessions").select("id").eq("id", data.session_id).eq("user_id", user_id).execute()
    if not session_check.data:
        raise HTTPException(404, "Session not found")
    
    insert_data = data.model_dump()
    insert_data["user_id"] = user_id
    res = supabase.table("companies").insert(insert_data).execute()
    return res.data[0]

@app.get("/companies/{company_id}", response_model=CompanyResponse)
async def get_company(company_id: str, user_id: str = Depends(get_current_user_id)):
    res = supabase.table("companies").select("*").eq("id", company_id).eq("user_id", user_id).single().execute()
    if not res.data:
        raise HTTPException(404, "Company not found")
    return res.data

@app.patch("/companies/{company_id}", response_model=CompanyResponse)
async def update_company(company_id: str, data: CompanyUpdate, user_id: str = Depends(get_current_user_id)):
    update_data = data.model_dump(exclude_unset=True)
    update_data["updated_at"] = datetime.utcnow().isoformat()
    res = supabase.table("companies").update(update_data).eq("id", company_id).eq("user_id", user_id).execute()
    if not res.data:
        raise HTTPException(404, "Company not found")
    return res.data[0]

@app.delete("/companies/{company_id}")
async def delete_company(company_id: str, user_id: str = Depends(get_current_user_id)):
    res = supabase.table("companies").delete().eq("id", company_id).eq("user_id", user_id).execute()
    return {"ok": True}

# ============================================================
# EMAILS
# ============================================================

@app.get("/emails")
async def list_emails(
    company_id: Optional[str] = None,
    session_id: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    user_id: str = Depends(get_current_user_id)
):
    query = supabase.table("emails").select("*").eq("user_id", user_id)
    if company_id:
        query = query.eq("company_id", company_id)
    if session_id:
        query = query.eq("session_id", session_id)
    res = query.order("created_at", desc=True).range(offset, offset + limit - 1).execute()
    return res.data

@app.post("/emails")
async def create_email(data: EmailCreate, user_id: str = Depends(get_current_user_id)):
    # Verify company belongs to user
    company_check = supabase.table("companies").select("id").eq("id", data.company_id).eq("user_id", user_id).execute()
    if not company_check.data:
        raise HTTPException(404, "Company not found")
    
    insert_data = data.model_dump()
    insert_data["user_id"] = user_id
    res = supabase.table("emails").insert(insert_data).execute()
    return res.data[0]

@app.patch("/emails/{email_id}")
async def update_email(email_id: str, data: EmailUpdate, user_id: str = Depends(get_current_user_id)):
    update_data = data.model_dump(exclude_unset=True)
    update_data["updated_at"] = datetime.utcnow().isoformat()
    res = supabase.table("emails").update(update_data).eq("id", email_id).eq("user_id", user_id).execute()
    if not res.data:
        raise HTTPException(404, "Email not found")
    return res.data[0]

# ============================================================
# OAUTH TOKENS (Google)
# ============================================================

@app.post("/oauth/tokens")
async def save_oauth_token(data: OAuthTokenRequest, user_id: str = Depends(get_current_user_id)):
    insert_data = {
        "user_id": user_id,
        "provider": data.provider,
        "access_token_enc": encrypt(data.access_token),
        "expires_at": data.expires_at.isoformat() if data.expires_at else None,
        "scope": data.scope
    }
    if data.refresh_token:
        insert_data["refresh_token_enc"] = encrypt(data.refresh_token)
    
    res = supabase.table("oauth_tokens").upsert(insert_data, on_conflict="user_id,provider").execute()
    return {"ok": True}

@app.get("/oauth/tokens/{provider}")
async def get_oauth_token(provider: str, user_id: str = Depends(get_current_user_id)):
    res = supabase.table("oauth_tokens").select("*").eq("user_id", user_id).eq("provider", provider).single().execute()
    if not res.data:
        return {"connected": False}
    
    data = res.data
    return {
        "connected": True,
        "provider": provider,
        "access_token": decrypt(data["access_token_enc"]),
        "refresh_token": decrypt(data["refresh_token_enc"]) if data.get("refresh_token_enc") else None,
        "expires_at": data.get("expires_at"),
        "scope": data.get("scope")
    }

@app.delete("/oauth/tokens/{provider}")
async def delete_oauth_token(provider: str, user_id: str = Depends(get_current_user_id)):
    res = supabase.table("oauth_tokens").delete().eq("user_id", user_id).eq("provider", provider).execute()
    return {"ok": True}

# ============================================================
# SERPAPI
# ============================================================

@app.post("/serpapi/key")
async def save_serpapi_key(data: SerpApiKeyRequest, user_id: str = Depends(get_current_user_id)):
    res = supabase.table("serpapi_keys").upsert({
        "user_id": user_id,
        "api_key_enc": encrypt(data.api_key),
        "monthly_quota": data.monthly_quota
    }, on_conflict="user_id").execute()
    return {"ok": True}

@app.get("/serpapi/usage")
async def get_serpapi_usage(user_id: str = Depends(get_current_user_id)):
    res = supabase.rpc("get_serpapi_usage").execute()
    return res.data or {"used": 0, "quota": 100, "remaining": 100}

@app.delete("/serpapi/key")
async def delete_serpapi_key(user_id: str = Depends(get_current_user_id)):
    res = supabase.table("serpapi_keys").delete().eq("user_id", user_id).execute()
    return {"ok": True}

# ============================================================
# DASHBOARD STATE (single call for frontend)
# ============================================================

@app.get("/api/state", response_model=DashboardState)
async def get_dashboard_state(user_id: str = Depends(get_current_user_id)):
    # Get all data in parallel-ish
    companies_res = supabase.table("companies").select("*").eq("user_id", user_id).order("created_at", desc=True).limit(500).execute()
    emails_res = supabase.table("emails").select("*").eq("user_id", user_id).order("created_at", desc=True).limit(100).execute()
    sessions_res = supabase.table("sessions").select("*").eq("user_id", user_id).order("created_at", desc=True).execute()
    settings_res = supabase.table("settings").select("*").eq("user_id", user_id).single().execute()
    oauth_res = supabase.table("oauth_tokens").select("provider").eq("user_id", user_id).execute()
    serpapi_res = supabase.table("serpapi_keys").select("used_this_month, monthly_quota, quota_reset_at").eq("user_id", user_id).single().execute()
    
    # Stats
    total_companies = len(companies_res.data)
    stats = {
        "total_companies": total_companies,
        "qualified": len([c for c in companies_res.data if c.get("status") == "qualified"]),
        "contacted": len([c for c in companies_res.data if c.get("status") in ("contacted", "sent")]),
        "replied": len([c for c in companies_res.data if c.get("status") == "replied"]),
        "emails_sent": len([e for e in emails_res.data if e.get("direction") == "outbound" and e.get("status") == "sent"])
    }
    
    # Connections status
    connections = {
        "google": {"connected": any(t["provider"] == "google" for t in oauth_res.data)},
        "serpapi": {"connected": bool(serpapi_res.data)}
    }
    
    # Active session
    active_session = next((s for s in sessions_res.data if s.get("status") == "active"), None)
    
    return {
        "companies": companies_res.data,
        "emails": emails_res.data,
        "sessions": sessions_res.data,
        "active_session_id": active_session["id"] if active_session else None,
        "stats": stats,
        "connections": connections,
        "parameters": settings_res.data or {},
        "prompts": (settings_res.data or {}).get("prompts", {}),
        "copy": {
            "targetMetric": "Cibles",
            "statusLabels": {
                "new": "Nouvelles",
                "qualified": "Qualifiées",
                "disqualified": "Disqualifiées",
                "contacted": "Contactées",
                "sent": "Envoyées",
                "replied": "Répondu",
                "rejected": "Refusées",
                "blacklisted": "Blacklistées",
                "formulaire_en_ligne": "Formulaire en ligne"
            },
            "qualificationMetric": "Qualifiées",
            "qualifiedHint": "Prêtes à contacter",
            "formReadyMetric": "Formulaires prêts",
            "formReadyHint": "Avec formulaire détecté",
            "sentMetric": "Envoyées",
            "sentHint": "Emails envoyés",
            "repliesMetric": "Réponses",
            "repliesHint": "À analyser",
            "noTargets": "Aucune entreprise correspondante.",
            "allMessagesFilter": "Tous les messages",
            "emailStatusLabels": {
                "draft": "Brouillon",
                "queued": "En file",
                "sent": "Envoyé",
                "delivered": "Distribué",
                "opened": "Ouvert",
                "clicked": "Cliqué",
                "replied": "Répondu",
                "bounced": "Échoué",
                "failed": "Erreur"
            }
        }
    }

# ============================================================
# SEARCH / SERPAPI PROXY
# ============================================================

@app.post("/search/companies")
async def search_companies(
    query: str,
    location: str = "France",
    radius_km: int = 50,
    session_id: Optional[str] = None,
    user_id: str = Depends(get_current_user_id)
):
    """Search companies via SerpApi (uses user's key or shared)"""
    
    # Get user's SerpApi key
    serpapi_res = supabase.table("serpapi_keys").select("api_key_enc, used_this_month, monthly_quota").eq("user_id", user_id).single().execute()
    
    if not serpapi_res.data and not settings.SERPAPI_SHARED_KEY:
        raise HTTPException(400, "No SerpApi key configured. Add your key in Settings.")
    
    if serpapi_res.data:
        if serpapi_res.data["used_this_month"] >= serpapi_res.data["monthly_quota"]:
            raise HTTPException(429, "Monthly SerpApi quota exceeded")
        api_key = decrypt(serpapi_res.data["api_key_enc"])
    else:
        api_key = settings.SERPAPI_SHARED_KEY
    
    # Call SerpApi
    async with httpx.AsyncClient() as client:
        params = {
            "engine": "google_maps",
            "q": f"{query} {location}",
            "api_key": api_key,
            "hl": "fr",
            "gl": "fr"
        }
        resp = await client.get("https://serpapi.com/search", params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
    
    # Increment usage
    if serpapi_res.data:
        supabase.rpc("increment_serpapi_usage").execute()
    
    # Parse results
    places = data.get("local_results", [])
    companies = []
    for place in places[:20]:
        companies.append({
            "company_name": place.get("title"),
            "website": place.get("website"),
            "address": place.get("address"),
            "city": location,
            "detected_email": None,
            "source": "serpapi",
            "source_url": place.get("place_id"),
            "search_query": query,
            "status": "new"
        })
    
    # Save to session if provided
    if session_id and companies:
        session_check = supabase.table("sessions").select("id").eq("id", session_id).eq("user_id", user_id).execute()
        if session_check.data:
            for c in companies:
                c["user_id"] = user_id
                c["session_id"] = session_id
            supabase.table("companies").upsert(companies, on_conflict="id").execute()
    
    return {"results": companies, "count": len(companies)}

# ============================================================
# GMAIL INTEGRATION
# ============================================================

@app.post("/gmail/send")
async def send_email(
    company_id: str,
    subject: str,
    body_text: str,
    body_html: Optional[str] = None,
    to_email: str = None,
    user_id: str = Depends(get_current_user_id)
):
    """Send email via Gmail API using user's OAuth token"""
    
    # Get OAuth token
    token_res = supabase.table("oauth_tokens").select("*").eq("user_id", user_id).eq("provider", "google").single().execute()
    if not token_res.data:
        raise HTTPException(400, "Google not connected")
    
    access_token = decrypt(token_res.data["access_token_enc"])
    
    # Get company for context
    company_res = supabase.table("companies").select("*").eq("id", company_id).eq("user_id", user_id).single().execute()
    if not company_res.data:
        raise HTTPException(404, "Company not found")
    
    company = company_res.data
    to = to_email or company.get("detected_email")
    if not to:
        raise HTTPException(400, "No recipient email")
    
    # Create email message
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart
    import base64
    
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = "me"
    msg["To"] = to
    msg.attach(MIMEText(body_text, "plain", "utf-8"))
    if body_html:
        msg.attach(MIMEText(body_html, "html", "utf-8"))
    
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    
    # Send via Gmail API
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
            headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
            json={"raw": raw}
        )
        
        if resp.status_code == 401:
            # Token expired, try refresh
            raise HTTPException(401, "Google token expired, reconnect")
        
        resp.raise_for_status()
        gmail_data = resp.json()
    
    # Save email record
    email_data = {
        "user_id": user_id,
        "company_id": company_id,
        "session_id": company.get("session_id"),
        "direction": "outbound",
        "gmail_message_id": gmail_data.get("id"),
        "gmail_thread_id": gmail_data.get("threadId"),
        "subject": subject,
        "body_text": body_text,
        "body_html": body_html,
        "from_email": "me",
        "to_emails": [to],
        "status": "sent",
        "sent_at": datetime.utcnow().isoformat()
    }
    
    email_res = supabase.table("emails").insert(email_data).execute()
    
    # Update company
    supabase.table("companies").update({
        "status": "sent",
        "latest_email_id": email_res.data[0]["id"],
        "latest_email_status": "sent",
        "latest_email_sent_at": datetime.utcnow().isoformat(),
        "contacted_at": datetime.utcnow().isoformat()
    }).eq("id", company_id).execute()
    
    return {"ok": True, "gmail_id": gmail_data.get("id"), "email_id": email_res.data[0]["id"]}

# ============================================================
# WEBHOOKS
# ============================================================

@app.post("/webhooks/gmail")
async def gmail_webhook(request: Request, background_tasks: BackgroundTasks):
    """Gmail push notification webhook"""
    body = await request.json()
    # Process in background
    background_tasks.add_task(process_gmail_notification, body)
    return {"ok": True}

async def process_gmail_notification(notification: Dict):
    """Process Gmail push notification - check for new replies"""
    # Implementation: decode message, check if reply to our thread, update email/company status
    pass

# ============================================================
# AUTOPILOT / BACKGROUND JOBS
# ============================================================

async def run_autopilot_for_all_users():
    """Run autopilot for all users with active sessions"""
    users = supabase_admin.table("users").select("id").execute()
    
    for user in users.data:
        try:
            await run_user_autopilot(user["id"])
        except Exception as e:
            logging.error(f"Autopilot failed for user {user['id']}: {e}")

async def run_user_autopilot(user_id: str):
    """Run autopilot for a single user"""
    # Get active sessions
    sessions = supabase_admin.table("sessions").select("*").eq("user_id", user_id).eq("status", "active").eq("autopilot_enabled", True).execute()
    
    for session in sessions.data:
        # Get settings for search params
        settings = supabase_admin.table("settings").select("*").eq("user_id", user_id).single().execute()
        
        # Search and qualify companies
        # ... implementation depends on your qualification logic
        
        # Update last_run_at
        supabase_admin.table("sessions").update({"last_run_at": datetime.utcnow().isoformat()}).eq("id", session["id"]).execute()

# Manual trigger
@app.post("/autopilot/run")
async def trigger_autopilot(session_id: Optional[str] = None, user_id: str = Depends(get_current_user_id)):
    if session_id:
        # Run for specific session
        pass
    else:
        # Run for all active sessions
        await run_user_autopilot(user_id)
    return {"ok": True}

# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)