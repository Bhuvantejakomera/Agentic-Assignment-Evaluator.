#!/usr/bin/env python3
import sys
import uvicorn
from pathlib import Path

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

if __name__ == "__main__":
    print("=" * 70)
    print("  Faculty-Controlled Assignment Evaluation & Grade Management System")
    print("  Local-first LLM evaluation on Apple Silicon Mac")
    print("  Server starting at: http://localhost:8000")
    print("=" * 70)
    uvicorn.run("backend.app.main:app", host="0.0.0.0", port=8000, reload=True)
