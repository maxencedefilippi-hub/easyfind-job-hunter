// EasyFind - Job Hunter Web UI with Supabase Auth
// État global
const state = {
  companies: [],
  emails: [],
  sessions: [],
  session: null,
  connections: {},
  parameters: {},
  stats: {},
  job: null,
  copy: {}
};

// ============================================================
// SUPABASE AUTH INTEGRATION
// ============================================================
const SUPABASE_URL = 'https://nkhcdkvepcjyxpwiattc.supabase.co';
const SUPABASE_ANON_KEY = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im5raGNka3ZlcGNqeXhwd2lhdHRjIiwicm9sZSI6ImFub24iLCJpYXQiOjE3OTAwOTc1OTYsImV4cCI6MjEwNTY3MzU5Nn0.uKPoW5qg5x7U777nGdjVfCIPyu-D1gG61Z_9iCcXqgg';

let supabaseClient = null;
let supabaseAuth = { user: null, initialized: false };

function createSupabaseClient() {
  if (!supabaseClient) {
    if (typeof window.supabase === 'undefined') {
      const script = document.createElement('script');
      script.src = 'https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2';
      document.head.appendChild(script);
      return new Promise(resolve => {
        script.onload = () => {
          supabaseClient = window.supabase.createClient(SUPABASE_URL, SUPABASE_ANON_KEY);
          resolve(supabaseClient);
        };
      });
    }
    supabaseClient = window.supabase.createClient(SUPABASE_URL, SUPABASE_ANON_KEY);
  }
  return supabaseClient;
}

async function initSupabaseAuth() {
  if (supabaseAuth.initialized) return;
  
  const token = localStorage.getItem('sb-access-token');
  const userId = localStorage.getItem('sb-user-id');
  
  if (token && userId) {
    supabaseAuth.user = { id: userId, token };
    try {
      const client = await createSupabaseClient();
      const { data, error } = await client.auth.getUser(token);
      if (error || !data.user) throw error || new Error('Token invalide');
      supabaseAuth.user = { id: data.user.id, token, email: data.user.email };
    } catch (e) {
      console.warn('Token expiré, nettoyage');
      localStorage.removeItem('sb-access-token');
      localStorage.removeItem('sb-user-id');
      supabaseAuth.user = null;
    }
  }
  
  supabaseAuth.initialized = true;
}

function loginWithToken(token, userId) {
  supabaseAuth.user = { id: userId, token };
  localStorage.setItem('sb-access-token', token);
  localStorage.setItem('sb-user-id', userId);
  renderHomePage();
}

function logout() {
  supabaseAuth.user = null;
  localStorage.removeItem('sb-access-token');
  localStorage.removeItem('sb-user-id');
  state.session = null;
  renderHomePage();
}

async function showAuthScreen() {
  const app = $('app');
  if (app) {
    app.innerHTML = `
      <div class="auth-screen" style="
        display:flex;align-items:center;justify-content:center;
        min-height:100vh;background:var(--bg-page);
      ">
        <div class="auth-card" style="
          background:var(--bg-panel);padding:40px;border-radius:16px;
          box-shadow:var(--shadow-lg);max-width:400px;width:100%;
          text-align:center;border:1px solid var(--border-standard);
        ">
          <h2 style="margin-bottom:8px;">EasyFind</h2>
          <p style="color:var(--text-secondary);margin-bottom:24px;">
            Connectez-vous pour accéder à vos données
          </p>
          <button id="googleLogin" class="btn-primary" style="width:100%;margin-bottom:12px;">
            <svg width="20" height="20" viewBox="0 0 24 24" style="display:inline;margin-right:8px;vertical-align:middle;">
              <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
              <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
              <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/>
              <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
            </svg>
            Se connecter avec Google
          </button>
          <button id="emailLogin" class="btn-secondary" style="width:100%;">Se connecter avec email</button>
          <p style="margin-top:20px;font-size:12px;color:var(--text-tertiary);">
            ou inscrivez-vous depuis <a href="/settings.html" style="color:var(--accent);">l'onglet Paramétrage</a>
          </p>
        </div>
      </div>
    `;
    
    safeAddListener('googleLogin', 'click', async () => {
      const client = await createSupabaseClient();
      const { error } = await client.auth.signInWithOAuth({
        provider: 'google',
        options: { redirectTo: window.location.origin + '/settings.html' }
      });
      if (error) alert(error.message);
    });
    
    safeAddListener('emailLogin', 'click', () => {
      window.location.href = '/settings.html';
    });
  }
}

function hideAuthScreen() {
  const authScreen = document.querySelector('.auth-screen');
  if (authScreen) authScreen.remove();
}

// Wrapper fetch avec token d'auth
async function fetchWithAuth(url, options = {}) {
  const token = supabaseAuth.user?.token;
  if (!token) throw new Error('Non connecté');
  
  const headers = {
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${token}`,
    ...(options.headers || {})
  };
  
  const res = await fetch(url, { ...options, headers });
  if (res.status === 401) {
    logout();
    throw new Error('Session expirée');
  }
  return res;
}

// ============================================================
// Utilitaires DOM
// ============================================================
let selectedCompanyId = "";