"""
Logging Module
Centralized logging for the RAG system with file and console output.
"""
import logging
import sys
from pathlib import Path
from datetime import datetime
from logging.handlers import RotatingFileHandler

# =============================================================================
# Log Directory Setup
# =============================================================================
LOG_DIR = Path(__file__).parent.parent / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

# Log file paths
MAIN_LOG = LOG_DIR / "rag_system.log"
ERROR_LOG = LOG_DIR / "errors.log"
QUERY_LOG = LOG_DIR / "queries.log"
DOCUMENT_LOG = LOG_DIR / "documents.log"


# =============================================================================
# Custom Formatter
# =============================================================================
class ColoredFormatter(logging.Formatter):
    """Colored console output formatter."""
    
    COLORS = {
        'DEBUG': '\033[36m',     # Cyan
        'INFO': '\033[32m',      # Green
        'WARNING': '\033[33m',   # Yellow
        'ERROR': '\033[31m',     # Red
        'CRITICAL': '\033[35m',  # Magenta
    }
    RESET = '\033[0m'
    
    def format(self, record):
        color = self.COLORS.get(record.levelname, self.RESET)
        record.levelname = f"{color}{record.levelname}{self.RESET}"
        return super().format(record)


# =============================================================================
# Logger Setup
# =============================================================================
def setup_logger(
    name: str,
    log_file: Path = MAIN_LOG,
    level: int = logging.INFO,
    console: bool = True
) -> logging.Logger:
    """
    Set up a logger with file and optional console handlers.
    
    Args:
        name: Logger name
        log_file: Path to log file
        level: Logging level
        console: Whether to also log to console
        
    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    # Avoid duplicate handlers
    if logger.handlers:
        return logger
    
    # File handler with rotation (10MB max, keep 5 backups)
    file_formatter = logging.Formatter(
        '%(asctime)s | %(levelname)-8s | %(name)s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5,
        encoding='utf-8'
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)
    
    # Console handler
    if console:
        console_formatter = ColoredFormatter(
            '%(levelname)s | %(message)s'
        )
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(level)
        console_handler.setFormatter(console_formatter)
        logger.addHandler(console_handler)
    
    return logger


# =============================================================================
# Pre-configured Loggers
# =============================================================================

# Main application logger
app_logger = setup_logger('rag_app', MAIN_LOG)

# Error-only logger (also logs to error file)
error_logger = setup_logger('rag_errors', ERROR_LOG, level=logging.ERROR)

# Query logger (tracks all user queries)
query_logger = setup_logger('rag_queries', QUERY_LOG, console=False)

# Document processing logger
doc_logger = setup_logger('rag_documents', DOCUMENT_LOG)


# =============================================================================
# Convenience Functions
# =============================================================================

def log_info(message: str):
    """Log info message."""
    app_logger.info(message)
    print(f"[INFO] {message}", flush=True)


def log_success(message: str):
    """Log success message."""
    app_logger.info(f"SUCCESS: {message}")
    print(f"[SUCCESS] {message}", flush=True)


def log_warning(message: str):
    """Log warning message."""
    app_logger.warning(message)
    print(f"[WARNING] {message}", flush=True)


def log_error(message: str, exc_info: bool = False):
    """Log error message."""
    app_logger.error(message, exc_info=exc_info)
    error_logger.error(message, exc_info=exc_info)
    print(f"[ERROR] {message}", flush=True)


def log_debug(message: str):
    """Log debug message."""
    app_logger.debug(message)


def log_query(query: str, response_preview: str = "", tokens: int = 0, time_taken: float = 0):
    """Log a user query with metadata."""
    query_logger.info(
        f"Query: {query[:100]}... | "
        f"Response: {response_preview[:50]}... | "
        f"Tokens: {tokens} | "
        f"Time: {time_taken:.2f}s"
    )


def log_document(action: str, doc_name: str, details: str = ""):
    """Log document operations."""
    doc_logger.info(f"{action} | {doc_name} | {details}")


def log_step(step: str):
    """Log a processing step."""
    app_logger.info(step)
    print(f"   [STEP] {step}", flush=True)


def log_progress(current: int, total: int, message: str = "Processing"):
    """Log progress."""
    percentage = (current / total * 100) if total > 0 else 0
    app_logger.info(f"{message}: {current}/{total} ({percentage:.1f}%)")
    print(f"   [PROGRESS] {message}: {current}/{total} ({percentage:.1f}%)", flush=True)


# =============================================================================
# Session Logger
# =============================================================================
class SessionLogger:
    """Logs a complete session with timing."""
    
    def __init__(self, session_name: str):
        self.session_name = session_name
        self.start_time = datetime.now()
        self.events = []
        
        log_info(f"Session started: {session_name}")
    
    def log_event(self, event: str, details: str = ""):
        """Log an event in the session."""
        elapsed = (datetime.now() - self.start_time).total_seconds()
        self.events.append({
            "time": elapsed,
            "event": event,
            "details": details
        })
        log_step(f"[{elapsed:.2f}s] {event}")
    
    def end_session(self, summary: str = ""):
        """End the session and log summary."""
        total_time = (datetime.now() - self.start_time).total_seconds()
        
        app_logger.info(f"Session ended: {self.session_name}")
        app_logger.info(f"Total time: {total_time:.2f}s")
        app_logger.info(f"Events: {len(self.events)}")
        
        if summary:
            app_logger.info(f"Summary: {summary}")
        
        log_success(f"Session complete in {total_time:.2f}s")
        
        return {
            "session": self.session_name,
            "total_time": total_time,
            "events": self.events,
            "summary": summary
        }


# =============================================================================
# Write initial log entry
# =============================================================================
app_logger.info("=" * 60)
app_logger.info("RAG Document Assistant - Logging Initialized")
app_logger.info(f"Log directory: {LOG_DIR.absolute()}")
app_logger.info("=" * 60)

