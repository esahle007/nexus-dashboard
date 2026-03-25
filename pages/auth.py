"""
auth.py — Project Nexus Authentication
=======================================
Google OAuth via Supabase Auth.
Manages login state in st.session_state.

Usage in app.py:
    import auth
    user = auth.require_login()   # returns user dict or stops execution
    user_id = user["id"]
"""

import streamlit as st
import os
from typing import Optional


def get_supabase_client():
    """Get authenticated Supabase client."""
    try:
        url = st.secrets.get("SUPABASE_URL", "")
        key = st.secrets.get("SUPABASE_ANON_KEY", "")
    except Exception:
        url = os.getenv("SUPABASE_URL", "")
        key = os.getenv("SUPABASE_ANON_KEY", "")

    if not url or not key:
        return None

    from supabase import create_client
    return create_client(url, key)


def get_current_user() -> Optional[dict]:
    """Return current user from session state, or None if not logged in."""
    return st.session_state.get("nexus_user", None)


def logout():
    """Clear session and log out."""
    client = get_supabase_client()
    if client:
        try:
            client.auth.sign_out()
        except Exception:
            pass
    st.session_state.pop("nexus_user", None)
    st.session_state.pop("nexus_access_token", None)
    st.rerun()


def handle_oauth_callback():
    """
    Handle the OAuth redirect from Google.
    Supabase redirects back to the app with tokens in the URL fragment.
    We use Streamlit's query params to detect the callback.
    """
    params = st.query_params
    # Supabase sends access_token and refresh_token as query params on redirect
    access_token  = params.get("access_token", "")
    refresh_token = params.get("refresh_token", "")

    if access_token and not st.session_state.get("nexus_user"):
        client = get_supabase_client()
        if client:
            try:
                session = client.auth.set_session(access_token, refresh_token)
                if session and session.user:
                    st.session_state["nexus_user"] = {
                        "id":    session.user.id,
                        "email": session.user.email,
                        "name":  (session.user.user_metadata or {}).get("full_name", ""),
                        "avatar":(session.user.user_metadata or {}).get("avatar_url", ""),
                    }
                    st.session_state["nexus_access_token"] = access_token
                    # Clean tokens from URL
                    st.query_params.clear()
                    st.rerun()
            except Exception as e:
                st.error(f"Login error: {e}")


def show_login_page():
    """Render the full-screen login page."""
    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@300;400;500;600;700&display=swap');
    html, body, [class*="css"] { font-family: 'DM Sans', sans-serif; }
    [data-testid="stSidebar"] { display: none; }
    .login-wrap {
        max-width: 420px; margin: 80px auto 0;
        background: #111318; border: 1px solid #1e2130;
        border-radius: 24px; padding: 48px 40px;
        text-align: center;
    }
    .login-logo { font-size: 3rem; margin-bottom: 12px; }
    .login-title {
        font-size: 1.8rem; font-weight: 700;
        letter-spacing: -0.03em; margin-bottom: 6px; color: #e5e7eb;
    }
    .login-sub { font-size: 0.88rem; color: #6b7280; margin-bottom: 36px; }
    .google-btn {
        display: flex; align-items: center; justify-content: center;
        gap: 12px; width: 100%; padding: 14px 20px;
        background: #ffffff; color: #1f2937;
        border: none; border-radius: 12px;
        font-size: 0.95rem; font-weight: 600;
        cursor: pointer; text-decoration: none;
        transition: background 0.2s;
    }
    .google-btn:hover { background: #f3f4f6; }
    .google-icon { width: 20px; height: 20px; }
    .login-footer { font-size: 0.72rem; color: #374151; margin-top: 24px; }
    </style>
    """, unsafe_allow_html=True)

    # Get the Google OAuth URL from Supabase
    client = get_supabase_client()
    oauth_url = ""

    if client:
        try:
            # Get the app's public URL for the redirect
            try:
                app_url = st.secrets.get("APP_URL", "http://localhost:8501")
            except Exception:
                app_url = "http://localhost:8501"

            res = client.auth.sign_in_with_oauth({
                "provider": "google",
                "options": {
                    "redirect_to": app_url,
                    "scopes": "openid email profile",
                }
            })
            oauth_url = res.url if res else ""
        except Exception as e:
            oauth_url = ""

    google_svg = """<svg class="google-icon" viewBox="0 0 24 24">
        <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
        <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
        <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/>
        <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
    </svg>"""

    if oauth_url:
        btn_html = f'<a href="{oauth_url}" class="google-btn">{google_svg} Continue with Google</a>'
    else:
        btn_html = '<p style="color:#f87171;font-size:0.85rem">⚠ Google login not configured yet.<br>Add APP_URL to Streamlit secrets.</p>'

    st.markdown(f"""
    <div class="login-wrap">
        <div class="login-logo">🧬</div>
        <div class="login-title">Nexus Health</div>
        <div class="login-sub">Your personal health intelligence platform</div>
        {btn_html}
        <div class="login-footer">
            By signing in you agree to keep your health data private.<br>
            Nexus does not sell or share your data.
        </div>
    </div>
    """, unsafe_allow_html=True)


def require_login() -> dict:
    """
    Call at the top of every page.
    Returns the current user dict if logged in.
    Shows login page and stops execution if not.
    """
    # Check for OAuth callback first
    handle_oauth_callback()

    user = get_current_user()
    if user:
        return user

    # Not logged in — show login page and stop
    show_login_page()
    st.stop()
