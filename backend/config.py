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
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

# Validate API key on import
def validate_api_key():
    """Check if API key is configured."""
    if not OPENAI_API_KEY:
        print("=" * 60)
        print("ERROR: OpenAI API key not found!")
        print("=" * 60)
        print("\nPlease create a .env file in the project root with:")
        print('    OPENAI_API_KEY=sk-your-api-key-here')
        print(f"\nExpected location: {env_path}")
        print("=" * 60)
        return False
    return True

# =============================================================================
# Model Configuration
# =============================================================================
EMBEDDING_MODEL = "text-embedding-3-small"
CHAT_MODEL = "gpt-4o-mini"
CHAT_MODEL_ADVANCED = "gpt-4o"

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
VECTOR_STORE_PATH = PROJECT_ROOT / "data" / "vector_store"
COLLECTION_NAME = "documents"

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

# Create directories
for dir_path in [DATA_DIR, UPLOAD_DIR, PROCESSED_DIR, VECTOR_STORE_PATH, CHAT_HISTORY_PATH, LOG_DIR]:
    dir_path.mkdir(parents=True, exist_ok=True)
