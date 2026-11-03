import os
from pathlib import Path

# Base Paths
BASE_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = BASE_DIR / "data"
DATABASE_PATH = DATA_DIR / "evaluation_system.db"
REPORTS_DIR = BASE_DIR / "reports"
WORKBOOKS_DIR = BASE_DIR / "workbooks"
SUBMISSIONS_DIR = DATA_DIR / "submissions"
SAMPLE_DATA_DIR = BASE_DIR / "sample_data"

# Create directories if not exist
DATA_DIR.mkdir(parents=True, exist_ok=True)
REPORTS_DIR.mkdir(parents=True, exist_ok=True)
WORKBOOKS_DIR.mkdir(parents=True, exist_ok=True)
SUBMISSIONS_DIR.mkdir(parents=True, exist_ok=True)
SAMPLE_DATA_DIR.mkdir(parents=True, exist_ok=True)

# Local LLM Configuration
# Supports Ollama, local OpenAI compatible endpoint (e.g. llama.cpp server, vLLM, LM Studio)
# or internal intelligent heuristic engine
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "ollama")  # "ollama", "openai_compatible", "internal"
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:latest")
LOCAL_OPENAI_URL = os.getenv("LOCAL_OPENAI_URL", "http://localhost:8000/v1")
LOCAL_OPENAI_MODEL = os.getenv("LOCAL_OPENAI_MODEL", "local-model")

# Google Classroom OAuth Configuration (Optional, for live Google Classroom integration)
GOOGLE_CLIENT_SECRETS_FILE = os.getenv("GOOGLE_CLIENT_SECRETS_FILE", str(BASE_DIR / "credentials.json"))
GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/classroom.courses.readonly",
    "https://www.googleapis.com/auth/classroom.coursework.students",
    "https://www.googleapis.com/auth/classroom.rosters.readonly",
    "https://www.googleapis.com/auth/classroom.profile.emails",
    "https://www.googleapis.com/auth/drive.readonly",
]

# Master Excel record filename
DEFAULT_EXCEL_TEMPLATE = BASE_DIR / "Lab_Marks_Record.xlsx"

