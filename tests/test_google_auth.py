import tempfile
import json
from pathlib import Path
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.database import init_db, db_session
from backend.app.services.google_oauth_service import GoogleOAuthService
from backend.app.services.classroom_service import ClassroomService

client = TestClient(app)

ORIGINAL_CREDS_BACKUP = None
ORIGINAL_FACULTY_BACKUP = None

def setup_module():
    global ORIGINAL_CREDS_BACKUP, ORIGINAL_FACULTY_BACKUP
    init_db()
    
    # Backup faculty row
    with db_session() as conn:
        fac = conn.execute("SELECT * FROM faculty WHERE id = ?", (ClassroomService.DEFAULT_FACULTY_ID,)).fetchone()
        ORIGINAL_FACULTY_BACKUP = dict(fac) if fac else None

    creds_path = GoogleOAuthService.get_credentials_path()
    if creds_path.exists():
        ORIGINAL_CREDS_BACKUP = creds_path.read_text(encoding="utf-8")
    else:
        ORIGINAL_CREDS_BACKUP = None

def teardown_module():
    creds_path = GoogleOAuthService.get_credentials_path()
    if ORIGINAL_CREDS_BACKUP is not None:
        creds_path.write_text(ORIGINAL_CREDS_BACKUP, encoding="utf-8")
    elif creds_path.exists():
        creds_path.unlink()

    # Restore faculty row
    if ORIGINAL_FACULTY_BACKUP is not None:
        with db_session() as conn:
            conn.execute(
                """
                UPDATE faculty
                SET email = ?,
                    name = ?,
                    google_access_token = ?,
                    google_refresh_token = ?,
                    token_expiry = ?
                WHERE id = ?
                """,
                (
                    ORIGINAL_FACULTY_BACKUP["email"],
                    ORIGINAL_FACULTY_BACKUP["name"],
                    ORIGINAL_FACULTY_BACKUP["google_access_token"],
                    ORIGINAL_FACULTY_BACKUP["google_refresh_token"],
                    ORIGINAL_FACULTY_BACKUP["token_expiry"],
                    ORIGINAL_FACULTY_BACKUP["id"]
                )
            )

def test_faculty_profile_endpoint():
    res = client.get("/api/auth/faculty")
    assert res.status_code == 200
    data = res.json()
    assert "email" in data
    assert "is_connected_google" in data
    assert "is_credentials_configured" in data

def test_google_client_info_endpoint():
    res = client.get("/api/auth/google/client-info")
    assert res.status_code == 200
    data = res.json()
    assert "configured" in data
    assert "credentials_file" in data

def test_save_credentials_json():
    dummy_creds = {
        "web": {
            "client_id": "test-client-id-12345.apps.googleusercontent.com",
            "project_id": "test-project-101",
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "client_secret": "test-client-secret-xyz",
            "redirect_uris": ["http://localhost:8000/api/auth/google/callback"]
        }
    }
    res = client.post("/api/auth/google/save-credentials", json=dummy_creds)
    assert res.status_code == 200
    assert res.json()["status"] == "success"

    # Verify client info now reports configured True!
    info_res = client.get("/api/auth/google/client-info")
    assert info_res.status_code == 200
    assert info_res.json()["configured"] is True
    assert info_res.json()["client_id"] == "test-client-id-12345.apps.googleusercontent.com"

def test_google_login_generates_auth_url():
    # Calling login should redirect (status 307 or 302) to Google's OAuth URL
    res = client.get("/api/auth/google/login", follow_redirects=False)
    assert res.status_code in (302, 307)
    location = res.headers.get("location")
    assert "accounts.google.com" in location
    assert "test-client-id-12345" in location
    assert "classroom.courses.readonly" in location
    assert "redirect_uri=http%3A%2F%2Ftestserver%2Fapi%2Fauth%2Fgoogle%2Fcallback" in location or "redirect_uri=" in location

def test_disconnect_google():
    res = client.post("/api/auth/disconnect")
    assert res.status_code == 200
    assert res.json()["status"] == "disconnected"

    # Check faculty profile
    fac = client.get("/api/auth/faculty").json()
    assert fac["is_connected_google"] is False

