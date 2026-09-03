"""Supabase Auth (GoTrue) via supabase-py + local JWT verification. The users table holds the CMS role."""
from functools import wraps

import jwt
from flask import abort, current_app, g, request
from supabase_auth.errors import AuthApiError, AuthError

from . import db

ROLES = {"editor": 1, "admin": 2}


def _session(res):
    s = res.session
    return {"access_token": s.access_token, "refresh_token": s.refresh_token, "expires_in": s.expires_in, "user_id": res.user.id}


def login(email, password):
    return _session(db.anon().auth.sign_in_with_password({"email": email, "password": password}))


def refresh(refresh_token):
    return _session(db.anon().auth.refresh_session(refresh_token))


def logout(token):
    db.sb().auth.admin.sign_out(token)


def verify_jwt(token):
    # ponytail: HS256 shared secret (self-hosted default). If the host enables JWT_KEYS (ES256), switch to
    # jwt.PyJWKClient(f"{SUPABASE_URL}/auth/v1/.well-known/jwks.json") and add pyjwt[crypto].
    return jwt.decode(token, current_app.config["SUPABASE_JWT_SECRET"], algorithms=["HS256"], audience="authenticated")


def _session_token():
    """Access token kept in the Flask session by the browser admin; refreshed once it has expired."""
    from flask import session

    token = session.get("access_token")
    if not token:
        return None
    try:
        verify_jwt(token)
        return token
    except jwt.ExpiredSignatureError:
        try:
            s = refresh(session.get("refresh_token", ""))
        except AuthError:
            session.clear()
            return None
        session["access_token"], session["refresh_token"] = s["access_token"], s["refresh_token"]
        return s["access_token"]
    except jwt.InvalidTokenError:
        session.clear()
        return None


def current_user():
    """CMS user row for the bearer token (API) or the session token (browser admin); None if absent/invalid/not a CMS user."""
    auth = request.headers.get("Authorization", "")
    token = auth[7:] if auth.startswith("Bearer ") else _session_token()
    if not token:
        return None
    try:
        claims = verify_jwt(token)
    except jwt.InvalidTokenError:
        return None
    return db.one(db.table("users").select("*").eq("id", claims["sub"]))


def require_role(min_role):
    def deco(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            user = current_user()
            if user is None:
                abort(401)
            if ROLES.get(user["role"], 0) < ROLES[min_role]:
                abort(403)
            g.user = user
            return fn(*args, **kwargs)
        return wrapper
    return deco


def create_auth_user(email, password, role="editor", name=""):
    """Create the GoTrue user (email pre-confirmed) and the matching CMS users row."""
    res = db.sb().auth.admin.create_user({"email": email, "password": password, "email_confirm": True})
    return db.insert("users", {"id": res.user.id, "email": email, "role": role, "name": name})


def delete_auth_user(user):
    try:
        db.sb().auth.admin.delete_user(user["id"])
    except (AuthApiError, AuthError):
        pass  # GoTrue user may already be gone; the CMS row is what gates access
    db.table("users").delete().eq("id", user["id"]).execute()
