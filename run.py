"""
run.py
Convenience runner for SymphonyLang Studio.
Starts the FastAPI backend and serves the frontend application.
"""

import os
import sys
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENV_PYTHON = ROOT / "venv" / "Scripts" / "python.exe"
PYTHON_CMD = str(VENV_PYTHON) if VENV_PYTHON.is_file() else sys.executable

def main():
    print("=" * 65)
    print("   SymphonyLang Studio - AI-Powered Music Programming Studio")
    print("=" * 65)

    frontend_dist = ROOT / "frontend" / "dist"
    if not frontend_dist.is_dir():
        print("Frontend production build not found. Building with npm...")
        try:
            subprocess.run(["npm", "run", "build"], cwd=str(ROOT / "frontend"), shell=True, check=True)
            print("Frontend built successfully.")
        except Exception as e:
            print(f"Note: Could not build frontend automatically ({e}).")
            print("To build frontend manually: cd frontend && npm install && npm run build")

    print("Starting FastAPI backend server...")
    print("Web Interface URL: http://localhost:8000")
    print("Vite Dev Server (optional): http://localhost:5173")
    print("-" * 65)

    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "backend")
    env["PYTHONIOENCODING"] = "utf-8"

    backend_cmd = [
        PYTHON_CMD,
        "-m", "uvicorn",
        "server:app",
        "--app-dir", str(ROOT / "backend"),
        "--host", "0.0.0.0",
        "--port", "8000",
        "--reload"
    ]

    try:
        subprocess.run(backend_cmd, env=env)
    except KeyboardInterrupt:
        print("\nSymphonyLang Studio stopped.")

if __name__ == "__main__":
    main()

