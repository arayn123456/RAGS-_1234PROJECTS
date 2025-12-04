"""
Document Q&A - Run Backend & Frontend
Single script to start the entire application.
"""
import subprocess
import sys
import os
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
        print("Add your OpenAI API key:")
        print("    OPENAI_API_KEY=sk-your-key-here")
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


def run_backend():
    """Start the FastAPI backend server."""
    return subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"],
        cwd=PROJECT_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )


def run_frontend():
    """Start the React frontend dev server."""
    return subprocess.Popen(
        ["npm", "run", "dev"],
        cwd=FRONTEND_DIR,
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )


def print_output(process, prefix):
    """Print process output with prefix."""
    if process.stdout:
        line = process.stdout.readline()
        if line:
            print(f"[{prefix}] {line.strip()}")
            return True
    return False


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
    time.sleep(2)
    
    print("Starting Frontend (port 3000)...")
    frontend = run_frontend()
    
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
    time.sleep(3)
    webbrowser.open("http://localhost:3000")
    
    # Monitor both processes
    try:
        while True:
            # Check if processes are still running
            if backend.poll() is not None:
                print("\n[ERROR] Backend server stopped!")
                break
            if frontend.poll() is not None:
                print("\n[ERROR] Frontend server stopped!")
                break
            
            # Print output from both
            print_output(backend, "Backend")
            print_output(frontend, "Frontend")
            
            time.sleep(0.1)
            
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

