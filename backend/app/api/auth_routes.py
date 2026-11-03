import json
from pathlib import Path
from fastapi import APIRouter, HTTPException, Request, UploadFile, File
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from typing import Dict, Any, Optional
from backend.app.database import db_session
from backend.app.services.classroom_service import ClassroomService
from backend.app.services.google_oauth_service import GoogleOAuthService
from backend.app.services.audit_service import AuditService

router = APIRouter(prefix="/api/auth", tags=["Authentication"])

class FacultyProfileResponse(BaseModel):
    id: str
    name: str
    email: str
    is_connected_google: bool
    is_credentials_configured: bool
    client_id: Optional[str] = None

class CredentialsJsonPayload(BaseModel):
    client_id: Optional[str] = None
    client_secret: Optional[str] = None
    project_id: Optional[str] = None
    web: Optional[Dict[str, Any]] = None
    installed: Optional[Dict[str, Any]] = None

class DirectLoginPayload(BaseModel):
    name: Optional[str] = "Prof. Bhuvan Teja"
    email: Optional[str] = "chandragajjela2003@gmail.com"

@router.post("/direct-login")
def direct_login(payload: DirectLoginPayload = DirectLoginPayload()):
    """Allows instant direct sign-in as faculty without requiring Google Cloud Console setup."""
    name = (payload.name or "Prof. Bhuvan Teja").strip()
    email = (payload.email or "chandragajjela2003@gmail.com").strip()
    with db_session() as conn:
        conn.execute(
            """
            UPDATE faculty
            SET name = ?,
                email = ?,
                google_access_token = 'direct_faculty_session_token',
                token_expiry = '2099-12-31T23:59:59'
            WHERE id = ?
            """,
            (name, email, ClassroomService.DEFAULT_FACULTY_ID)
        )
    AuditService.log_event("DIRECT_FACULTY_LOGIN", faculty_id=ClassroomService.DEFAULT_FACULTY_ID, details={"name": name, "email": email, "mode": "direct"})
    return {
        "status": "success",
        "message": f"Successfully signed in as {name} ({email})",
        "faculty": {
            "id": ClassroomService.DEFAULT_FACULTY_ID,
            "name": name,
            "email": email,
            "is_connected_google": True
        }
    }

@router.get("/faculty", response_model=FacultyProfileResponse)
def get_current_faculty():
    with db_session() as conn:
        r = conn.execute(
            "SELECT id, name, email, google_access_token FROM faculty WHERE id = ?",
            (ClassroomService.DEFAULT_FACULTY_ID,)
        ).fetchone()

        if not r:
            ClassroomService.seed_initial_classrooms_if_empty()
            r = conn.execute(
                "SELECT id, name, email, google_access_token FROM faculty WHERE id = ?",
                (ClassroomService.DEFAULT_FACULTY_ID,)
            ).fetchone()

        client_info = GoogleOAuthService.get_client_info()

        return FacultyProfileResponse(
            id=r["id"],
            name=r["name"],
            email=r["email"],
            is_connected_google=bool(r["google_access_token"]),
            is_credentials_configured=client_info["configured"],
            client_id=client_info.get("client_id")
        )

@router.get("/google/client-info")
def get_google_client_info():
    """Returns status of Google OAuth client secrets configuration."""
    return GoogleOAuthService.get_client_info()

@router.post("/google/upload-credentials")
async def upload_credentials_file(file: UploadFile = File(...)):
    """Allows uploading credentials.json directly through the web UI."""
    try:
        content = await file.read()
        data = json.loads(content.decode("utf-8"))
        GoogleOAuthService.save_client_secrets(data)
        client_info = GoogleOAuthService.get_client_info()
        return {
            "status": "success",
            "message": "credentials.json uploaded and configured successfully.",
            "client_id": client_info.get("client_id")
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid credentials file: {str(e)}")

@router.post("/google/save-credentials")
def save_credentials_json(payload: Dict[str, Any]):
    """Allows submitting client_id and client_secret directly as JSON."""
    try:
        GoogleOAuthService.save_client_secrets(payload)
        client_info = GoogleOAuthService.get_client_info()
        return {
            "status": "success",
            "message": "Google OAuth configuration saved.",
            "client_id": client_info.get("client_id")
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error saving credentials: {str(e)}")

@router.get("/google/login")
def google_login(request: Request):
    """
    Initiates Google OAuth 2.0 flow.
    Redirects user to Google's consent screen.
    """
    if not GoogleOAuthService.is_credentials_file_configured():
        raise HTTPException(
            status_code=400,
            detail=(
                "Google OAuth credentials.json is not configured yet. "
                "Please configure credentials.json or enter your OAuth Client ID & Secret."
            )
        )

    # Construct redirect URI matching current host
    host = request.headers.get("host", "localhost:8000")
    proto = "https" if request.url.scheme == "https" else "http"
    redirect_uri = f"{proto}://{host}/api/auth/google/callback"

    auth_url = GoogleOAuthService.get_authorization_url(redirect_uri)
    return RedirectResponse(auth_url)

@router.get("/google/callback")
def google_callback(
    request: Request,
    code: Optional[str] = None,
    state: Optional[str] = None,
    error: Optional[str] = None
):
    """Handles Google OAuth callback, saves tokens, and syncs live classrooms."""
    if error:
        raise HTTPException(status_code=400, detail=f"Google authentication error: {error}")
    if not code:
        raise HTTPException(status_code=400, detail="Missing authorization code from Google.")

    host = request.headers.get("host", "localhost:8000")
    proto = "https" if request.url.scheme == "https" else "http"
    redirect_uri = f"{proto}://{host}/api/auth/google/callback"

    try:
        token_data, user_info = GoogleOAuthService.exchange_code_for_tokens(code, redirect_uri, state=state)
        GoogleOAuthService.save_tokens_for_faculty(ClassroomService.DEFAULT_FACULTY_ID, user_info, token_data)

        # Trigger live Classroom sync
        try:
            GoogleOAuthService.sync_live_google_classroom(ClassroomService.DEFAULT_FACULTY_ID)
        except Exception:
            pass

        return RedirectResponse(f"/?auth=google_success&email={user_info.get('email')}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"OAuth token exchange failed: {str(e)}")

@router.post("/google/sync-live")
def sync_live_google():
    """Manually triggers live Google Classroom synchronization."""
    try:
        res = GoogleOAuthService.sync_live_google_classroom(ClassroomService.DEFAULT_FACULTY_ID)
        return res
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/disconnect")
def disconnect_google():
    """Disconnects Google account and clears tokens."""
    with db_session() as conn:
        conn.execute(
            """
            UPDATE faculty
            SET google_access_token = NULL,
                google_refresh_token = NULL,
                token_expiry = NULL
            WHERE id = ?
            """,
            (ClassroomService.DEFAULT_FACULTY_ID,)
        )
    AuditService.log_event("GOOGLE_DISCONNECTED", faculty_id=ClassroomService.DEFAULT_FACULTY_ID)
    return {"status": "disconnected", "message": "Google account disconnected."}
