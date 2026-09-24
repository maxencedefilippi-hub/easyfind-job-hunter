// EasyFind - Job Hunter Web UI (Production - Supabase Backend)
// Configuration
const CONFIG = {
  API_BASE: (typeof NEXT_PUBLIC_API_URL !== 'undefined' ? NEXT_PUBLIC_API_URL : 'http://127.0.0.1:8000'),
  SUPABASE_URL: (typeof NEXT_PUBLIC_SUPABASE_URL !== 'undefined' ? NEXT_PUBLIC_SUPABASE_URL : ''),
  SUPABASE_ANON_KEY: (typeof NEXT_PUBLIC_SUPABASE_ANON_KEY !== 'undefined' ? NEXT_PUBLIC_SUPABASE_ANON_KEY : ''),
  IS_PRODUCTION: typeof NEXT_PUBLIC_API_URL !== 'undefined'
};

// État global
const state = {
  companies: [],
  emails: [],
  sessions: [],
  session: null,
  connections: {},
  prompts: {},
  parameters: {},
  stats: {},
  job: null,
  copy: {}
};

let selectedCompanyId = "";
let selectedEmailId = "";
let actionInProgress = false;
let companiesVisibleLimit = 20;
let emailsVisibleLimit = 20;
const COMPANIES_PAGE_SIZE = 20;
const EMAILS_PAGE_SIZE = 20;
let emailsCollapsed = false;
let lastUserInteractionAt = Date.now();
let promptState = null;
let authToken = null;

// Utilitaires DOM
function $(id) { return document.getElementById(id); }
function safeAddListener(id, event, handler) { const el = $(id); if (el) el.addEventListener(event, handler); else console.warn("Element not found:", id); }
function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, function(c) {
    return {"&": "&", "<": "<", ">": ">", '"': """, "'": "'"}[c];
  });
}
function attr(s) { return escapeHtml(s); }
function shortDate(iso) { if (!iso) return ""; const d = new Date(iso); return d.toLocaleDateString("fr-FR"); }
function linkOrText(url) { if (!url) return ""; return '<a href="' + attr(url) + '" target="_blank" rel="noopener">' + attr(url) + '</a>'; }
function formatRecipient(email) { if (!email) return ""; return email.includes("@") ? email : '<span class="form-badge">Formulaire</span>'; }
function statusPill(s) { if (!s) return ""; const cls = 'status-pill status-' + s; return '<span class="' + cls + '">' + escapeHtml(s) + '</span>'; }
function currentCopy() { return state.copy || {}; }
function findCompany(id) { return state.companies?.find(function(c) { return c.id === id; }); }
function findEmail(id) { return state.emails?.find(function(e) { return e.id === id; }); }
function companyEmails(cid) { return state.emails?.filter(function(e) { return e.company_id === cid; }) || []; }
function isFormRecipient(email) { return !email || !email.includes("@"); }
function replyStatusLabel(key) { const c = currentCopy(); return c.replyStatusLabels?.[key] || key; }

// Status options
const companyStatuses = ["new", "qualified", "contacted", "formulaire_en_ligne", "sent", "replied", "rejected", "blacklisted", "no_email"];
const emailStatuses = ["generated", "draft_created", "sent", "replied", "skipped", "failed", "ignored"];
const replyStatuses = ["", "positive", "no_hiring_now", "recontact_after_date", "not_interested", "wrong_person", "auto_reply"];

function companyStatusOptions(selected) {
  const c = currentCopy();
  return companyStatuses.map(function(s) {
    return '<option value="' + s + '" ' + (s === selected ? 'selected' : '') + '>' + escapeHtml(c.statusLabels?.[s] || s) + '</option>';
  }).join("");
}

function emailStatusOptions(selected) {
  const c = currentCopy();
  return emailStatuses.map(function(s) {
    return '<option value="' + s + '" ' + (s === selected ? 'selected' : '') + '>' + escapeHtml(c.emailStatusLabels?.[s] || s) + '</option>';
  }).join("");
}

function replyStatusOptions(selected) {
  return replyStatuses.map(function(s) {
    return '<option value="' + s + '" ' + (s === selected ? 'selected' : '') + '>' + escapeHtml(s || "\u2014") + '</option>';
  }).join("");
}

// API calls with auth
async function apiFetch(path, options) {
  options = options || {};
  const headers = {
    "Content-Type": "application/json",
  };
  if (options.headers) {
    Object.keys(options.headers).forEach(function(k) {
      headers[k] = options.headers[k];
    });
  }
  
  if (authToken) {
    headers["Authorization"] = 'Bearer ' + authToken;
  }
  
  const url = CONFIG.API_BASE + path;
  
  try {
    const response = await fetch(url, {
      method: options.method || "GET",
      headers: headers,
      body: options.body
    });
    
    if (response.status === 401) {
      window.location.href = "/login.html";
      return null;
    }
    
    if (!response.ok) {
      const error = await response.json().catch(function() { return { detail: "Unknown error" }; });
      throw new Error(error.detail || 'HTTP ' + response.status);
    }
    
    if (response.status === 204) return null;
    return await response.json();
  } catch (error) {
    console.error('API ' + path + ' failed:', error);
    throw error;
  }
}

// Authentication
async function initAuth() {
  const storedToken = localStorage.getItem("sb-access-token");
  if (storedToken) {
    authToken = storedToken;
    try {
      await apiFetch("/auth/user");
      return true;
    } catch (e) {
      authToken = null;
      localStorage.removeItem("sb-access-token");
    }
  }
  return false;
}

async function signIn(email, password) {
  const data = await apiFetch("/auth/signin", {
    method: "POST",
    body: JSON.stringify({ email: email, password: password })
  });
  
  if (data) {
    authToken = data.access_token;
    localStorage.setItem("sb-access-token", authToken);
    return true;
  }
  return false;
}

function signOut() {
  authToken = null;
  localStorage.removeItem("sb-access-token");
  window.location.href = "/login.html";
}

// State fetching
async function fetchState(opts) {
  opts = opts || {};
  try {
    const data = await apiFetch("/api/state" + (opts.force ? "?force=1" : ""));
    if (data) {
      Object.assign(state, data);
      return true;
    }
  } catch (e) {
    console.warn("fetchState failed:", e);
  }
  return false;
}

async function fetchParameters() {
  try {
    const data = await apiFetch("/api/parameters");
    if (data) {
      state.parameters = data;
      return true;
    }
  } catch (e) {
    console.warn("fetchParameters failed:", e);
  }
  return false;
}

async function fetchPrompts() {
  try {
    const data = await apiFetch("/api/prompts");
    if (data) {
      state.prompts = data;
      return true;
    }
  } catch (e) {
    console.warn("fetchPrompts failed:", e);
  }
  return false;
}

// Actions
async function runAction(action, payload) {
  payload = payload || {};
  if (actionInProgress) return;
  actionInProgress = true;
  renderBusyOverlay();
  
  try {
    await apiFetch("/api/action", {
      method: "POST",
      body: JSON.stringify(Object.assign({ action: action }, payload))
    });
    await fetchState({ force: true });
  } finally {
    actionInProgress = false;
    renderBusyOverlay();
  }
}

// Session management
async function switchSession() {
  selectedCompanyId = "";
  selectedEmailId = "";
  $("pilotage").dataset.loaded = "";
  promptState = null;
  await runAction("set_active_session", { session_id: $("sessionSelect").value });
  await fetchParameters();
  await fetchPrompts();
}

async function createSessionFromForm() {
  const n = $("newSessionName").value.trim();
  if (!n) { alert("Donne un nom à la session."); return; }
  
  selectedCompanyId = "";
  selectedEmailId = "";
  $("pilotage").dataset.loaded = "";
  promptState = null;
  
  await runAction("create_session", { name: n, kind: $("newSessionKind").value });
  $("newSessionName").value = "";
  await fetchParameters();
  await fetchPrompts();
}

async function deleteSessionFromButton(b) {
  const sid = b.dataset.sessionDelete;
  const sn = b.dataset.sessionName || "";
  const cn = prompt('Pour supprimer la session "' + sn + '", retape exactement son nom :');
  if (cn === null) return;
  if (cn.trim() !== sn) { alert("Nom incorrect. Suppression annulée."); return; }
  if (!confirm('Confirmer la suppression de "' + sn + '" ? La session disparaîtra du site, mais ses fichiers seront archivés localement.')) return;
  
  selectedCompanyId = "";
  selectedEmailId = "";
  promptState = null;
  await runAction("delete_session", { session_id: sid, confirm_name: sn });
  await fetchParameters();
  await fetchPrompts();
}

// Initialize
async function init() {
  const authed = await initAuth();
  if (!authed && CONFIG.IS_PRODUCTION) {
    window.location.href = "/login.html";
    return;
  }
  
  await fetchState();
  await fetchParameters();
  await fetchPrompts();
  
  safeAddListener("refreshBtn", "click", function() { fetchState({ force: true }); });
  safeAddListener("savePromptsBtn", "click", async function() {
    await runAction("save_prompts", { prompts: collectPrompts() });
    await fetchPrompts();
  });
  
  setInterval(fetchState, 30000);
}

// Start when DOM ready
if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", init);
} else {
  init();
}

// Export for inline scripts
window.CONFIG = CONFIG;
window.apiFetch = apiFetch;
window.authToken = authToken;
window.signOut = signOut;

// ... rest of your existing render functions (renderCompanies, renderEmails, etc.)
// Keep all the existing render functions from the current app.js
// They work the same way, just using the new apiFetch instead of fetch