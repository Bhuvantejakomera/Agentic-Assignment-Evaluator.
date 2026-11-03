from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from backend.app.config import BASE_DIR
from backend.app.database import init_db
from backend.app.services.classroom_service import ClassroomService

from backend.app.api.auth_routes import router as auth_router
from backend.app.api.classroom_routes import router as classroom_router
from backend.app.api.assignment_routes import router as assignment_router
from backend.app.api.rubric_routes import router as rubric_router
from backend.app.api.evaluation_routes import router as evaluation_router
from backend.app.api.excel_routes import router as excel_router
from backend.app.api.publish_routes import router as publish_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize DB and seed demo classroom data
    init_db()
    ClassroomService.seed_initial_classrooms_if_empty()
    yield

app = FastAPI(
    title="Faculty-Controlled Assignment Evaluation & Grade Management System",
    description="Local-first AI-assisted assignment evaluation and Excel grade synchronization for multiple Google Classrooms.",
    version="1.0.0",
    lifespan=lifespan
)

# Enable CORS for local web access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routers
app.include_router(auth_router)
app.include_router(classroom_router)
app.include_router(assignment_router)
app.include_router(rubric_router)
app.include_router(evaluation_router)
app.include_router(excel_router)
app.include_router(publish_router)

# Health endpoint
@app.get("/api/health")
def health_check():
    return {
        "status": "healthy",
        "system": "Faculty-Controlled Assignment Evaluation System",
        "architecture": "Apple Silicon M-Series Optimized",
        "model_privacy": "100% Local Inference"
    }

# Mount Frontend static files
FRONTEND_DIR = BASE_DIR / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

@app.get("/")
def serve_index():
    index_file = FRONTEND_DIR / "index.html"
    if index_file.exists():
        return FileResponse(str(index_file))
    return {"message": "Frontend not yet generated."}

