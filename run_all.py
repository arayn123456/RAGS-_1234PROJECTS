"""
Document Q&A - Run Backend & Frontend
Single script to start the entire application.
"""
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

# Project paths
PROJECT_ROOT = Path(__file__).parent
FRONTEND_DIR = PROJECT_ROOT / "frontend"
ENV_FILE = PROJECT_ROOT / ".env"


def check_requirements():
    """Check if all requirements are met."""
    # Check .env file
    if not ENV_FILE.exists():
        print("=" * 60)
        print("ERROR: .env file not found!")
        print("=" * 60)
        print(f"\nPlease create: {ENV_FILE}")
        print("Add your Gemini API key:")
        print("    GEMINI_API_KEY=your-gemini-api-key-here")
        print("=" * 60)
        return False
    
    # Check node_modules
    if not (FRONTEND_DIR / "node_modules").exists():
        print("Installing frontend dependencies...")
        subprocess.run(
            ["npm", "install"],
            cwd=FRONTEND_DIR,
            shell=True
        )
        print("Frontend dependencies installed!\n")
    
    return True


def _popen_kwargs():
    """Keep child servers alive when the console gets Ctrl+C/reload noise."""
    kwargs = {}
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    return kwargs


def run_backend():
    """Start the FastAPI backend server.

    stdout/stderr are inherited (not piped). Piping + uvicorn --reload
    often causes the backend to exit immediately on Windows.
    """
    return subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "backend.main:app",
            "--host",
            "0.0.0.0",
            "--port",
            "8000",
            "--reload",
            "--reload-dir",
            "backend",
        ],
        cwd=PROJECT_ROOT,
        **_popen_kwargs(),
    )


def run_frontend():
    """Start the React frontend dev server."""
    return subprocess.Popen(
        ["npm", "run", "dev"],
        cwd=FRONTEND_DIR,
        shell=True,
        **_popen_kwargs(),
    )


def main():
    """Main entry point."""
    print("=" * 60)
    print("  Document Q&A - Starting Application")
    print("=" * 60)
    print()
    
    # Check requirements
    if not check_requirements():
        sys.exit(1)
    
    print("Starting Backend Server (port 8000)...")
    backend = run_backend()
    
    # Wait for backend to start
    time.sleep(3)
    
    if backend.poll() is not None:
        print("=" * 60)
        print(f"ERROR: Backend exited immediately (code {backend.returncode})")
        print("Try running manually to see the error:")
        print("  python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000")
        print("=" * 60)
        sys.exit(1)
    
    print("Starting Frontend (port 3000)...")
    frontend = run_frontend()
    
    time.sleep(2)
    if frontend.poll() is not None:
        print("=" * 60)
        print(f"ERROR: Frontend exited immediately (code {frontend.returncode})")
        print("Try: cd frontend && npm run dev")
        print("=" * 60)
        backend.terminate()
        sys.exit(1)
    
    print()
    print("=" * 60)
    print("  Application Started!")
    print("=" * 60)
    print()
    print("  Frontend:  http://localhost:3000")
    print("  Backend:   http://localhost:8000")
    print("  API Docs:  http://localhost:8000/docs")
    print()
    print("  Press Ctrl+C to stop all servers")
    print("=" * 60)
    print()
    
    # Open browser after a short delay
    time.sleep(2)
    webbrowser.open("http://localhost:3000")
    
    # Monitor both processes
    try:
        while True:
            # Check if processes are still running
            if backend.poll() is not None:
                print(f"\n[ERROR] Backend server stopped! (exit code {backend.returncode})")
                break
            if frontend.poll() is not None:
                print(f"\n[ERROR] Frontend server stopped! (exit code {frontend.returncode})")
                break
            
            time.sleep(0.5)
            
    except KeyboardInterrupt:
        print("\n\nShutting down servers...")
    finally:
        # Cleanup
        backend.terminate()
        frontend.terminate()
        
        try:
            backend.wait(timeout=5)
            frontend.wait(timeout=5)
        except subprocess.TimeoutExpired:
            backend.kill()
            frontend.kill()
        
        print("Servers stopped.")


if __name__ == "__main__":
    main()
