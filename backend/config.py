"""
Configuration settings for the RAG system.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Project root directory
PROJECT_ROOT = Path(__file__).parent.parent

# Load environment variables from .env file (in project root)
env_path = PROJECT_ROOT / ".env"
load_dotenv(dotenv_path=env_path)

# =============================================================================
# API Configuration
# =============================================================================
# OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")  # Commented out — using Gemini
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

# Validate API key on import
def validate_api_key():
    """Check if API key is configured."""
    if not GEMINI_API_KEY:
        print("=" * 60)
        print("ERROR: Gemini API key not found!")
        print("=" * 60)
        print("\nPlease create a .env file in the project root with:")
        print('    GEMINI_API_KEY=your-gemini-api-key-here')
        print(f"\nExpected location: {env_path}")
        print("=" * 60)
        return False
    return True

# =============================================================================
# Model Configuration (free Gemini models)
# =============================================================================
# OpenAI models (commented out)
# EMBEDDING_MODEL = "text-embedding-3-small"
# CHAT_MODEL = "gpt-4o-mini"
# CHAT_MODEL_ADVANCED = "gpt-4o"

EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "gemini-embedding-2")
# gemini-2.5-flash is blocked for many new free keys; use flash-latest instead
CHAT_MODEL = os.getenv("CHAT_MODEL", "gemini-flash-latest")
CHAT_MODEL_ADVANCED = os.getenv("CHAT_MODEL_ADVANCED", "gemini-flash-latest")

# =============================================================================
# Document Processing
# =============================================================================
CHUNK_SIZE = 1000
CHUNK_OVERLAP = 200
MAX_DOCUMENT_SIZE_MB = 50
SUPPORTED_FORMATS = {
    ".pdf": "PDF Document",
    ".docx": "Word Document",
    ".doc": "Word Document (Legacy)",
    ".txt": "Text File",
    ".md": "Markdown File",
    ".csv": "CSV File",
}

# =============================================================================
# Vector Store Configuration
# =============================================================================
# ChromaDB's SQLite/Rust client breaks on OneDrive-locked folders.
_local_app = os.getenv("LOCALAPPDATA")
if _local_app and "onedrive" in str(PROJECT_ROOT).lower():
    VECTOR_STORE_PATH = Path(_local_app) / "RAGs" / "chroma"
else:
    VECTOR_STORE_PATH = PROJECT_ROOT / "data" / "vector_store"
VECTOR_STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
COLLECTION_NAME = "documents_gemini"
EMBEDDING_DIMENSIONS = 768

# =============================================================================
# Chat History Configuration
# =============================================================================
CHAT_HISTORY_PATH = PROJECT_ROOT / "data" / "chat_history"
MAX_HISTORY_MESSAGES = 50
HISTORY_SUMMARY_THRESHOLD = 20

# =============================================================================
# Retrieval Configuration
# =============================================================================
TOP_K_RESULTS = 10
SIMILARITY_THRESHOLD = 0.7

# =============================================================================
# UI Configuration
# =============================================================================
APP_TITLE = "Document Q&A"
APP_DESCRIPTION = """
**Intelligent Document Q&A with Line-Level Precision**

Upload your documents (PDF, Word, Text) and ask questions. 
Get precise answers with exact line numbers and source references.
"""

# =============================================================================
# Paths Setup
# =============================================================================
DATA_DIR = PROJECT_ROOT / "data"
UPLOAD_DIR = DATA_DIR / "uploads"
PROCESSED_DIR = DATA_DIR / "processed"
LOG_DIR = PROJECT_ROOT / "logs"

# Create directories. Do not pre-create VECTOR_STORE_PATH: an empty folder
# makes newer ChromaDB (Rust client) fail with "Could not connect to tenant".
for dir_path in [DATA_DIR, UPLOAD_DIR, PROCESSED_DIR, CHAT_HISTORY_PATH, LOG_DIR]:
    dir_path.mkdir(parents=True, exist_ok=True)
