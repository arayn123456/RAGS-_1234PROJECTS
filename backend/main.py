"""
FastAPI Backend for Document Q&A RAG System
"""
from pathlib import Path
from typing import List, Optional
import tempfile

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import config
from .rag_engine import RAGEngine
from . import chat_db

# =============================================================================
# FastAPI App
# =============================================================================
app = FastAPI(title="Document Q&A API", version="1.0.0")

# CORS for React frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =============================================================================
# Models
# =============================================================================
class QueryRequest(BaseModel):
    question: str
    chat_history: Optional[List[dict]] = []
    document_filter: Optional[str] = None

class QueryResponse(BaseModel):
    answer: str
    citations: List[dict]

class DocumentInfo(BaseModel):
    id: str
    name: str
    chunks: int

class ChatMessage(BaseModel):
    role: str
    content: str
    citations: Optional[List[dict]] = None

class RenameRequest(BaseModel):
    title: str

# =============================================================================
# Global Engine
# =============================================================================
engine: Optional[RAGEngine] = None

def get_engine() -> RAGEngine:
    global engine
    if engine is None:
        if not config.OPENAI_API_KEY:
            raise HTTPException(status_code=500, detail="OpenAI API key not configured")
        engine = RAGEngine()
    return engine

# =============================================================================
# Check if frontend is built (for production)
# =============================================================================
FRONTEND_DIST = Path(__file__).parent.parent / "frontend" / "dist"
SERVE_FRONTEND = FRONTEND_DIST.exists()

if SERVE_FRONTEND:
    from fastapi.responses import FileResponse

# =============================================================================
# Routes
# =============================================================================
@app.get("/")
def root():
    """Serve frontend in production, API info in development"""
    if SERVE_FRONTEND:
        return FileResponse(FRONTEND_DIST / "index.html")
    return {"status": "ok", "message": "Document Q&A API"}

@app.get("/health")
def health():
    return {"status": "healthy"}

@app.get("/documents")
def get_documents():
    """Get all indexed documents"""
    eng = get_engine()
    doc_info = eng.vector_store.get_document_info()
    
    documents = []
    for doc_id, info in doc_info.get('documents', {}).items():
        documents.append({
            "id": doc_id,
            "name": info['name'],
            "chunks": info.get('chunks', 0)
        })
    
    return {
        "documents": documents,
        "total": doc_info.get('total_documents', 0),
        "total_chunks": doc_info.get('total_chunks', 0)
    }

@app.post("/upload")
async def upload_document(file: UploadFile = File(...)):
    """Upload and index a document"""
    eng = get_engine()
    
    # Check file type
    allowed = ['.pdf', '.docx', '.doc', '.txt', '.md']
    suffix = Path(file.filename).suffix.lower()
    if suffix not in allowed:
        raise HTTPException(status_code=400, detail=f"File type {suffix} not supported")
    
    # Save temp file
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            content = await file.read()
            tmp.write(content)
            tmp_path = tmp.name
        
        # Process document
        doc = eng.add_document(tmp_path, original_filename=file.filename)
        
        # Cleanup
        Path(tmp_path).unlink(missing_ok=True)
        
        return {
            "success": True,
            "document": {
                "id": doc.document_id,
                "name": file.filename,
                "chunks": len(doc.chunks)
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/documents/{doc_id}")
def delete_document(doc_id: str):
    """Delete a document"""
    eng = get_engine()
    try:
        eng.vector_store.remove_document(doc_id)
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/query", response_model=QueryResponse)
def query_documents(request: QueryRequest):
    """Query documents with RAG"""
    eng = get_engine()
    
    try:
        response = eng.query(
            question=request.question,
            chat_history=request.chat_history or [],
            document_filter=request.document_filter
        )
        
        citations = []
        for c in response.citations:
            citations.append({
                "document_name": c.document_name,
                "start_line": c.start_line,
                "end_line": c.end_line,
                "page_numbers": c.page_numbers,
                "text_preview": c.content_preview[:200] + "..." if len(c.content_preview) > 200 else c.content_preview
            })
        
        return QueryResponse(
            answer=response.answer,
            citations=citations
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/chat")
def clear_chat():
    """Clear chat endpoint (frontend handles state)"""
    return {"success": True}

@app.delete("/clear-all")
def clear_all_data():
    """Clear all data - documents, vector store, processed files, and chat history"""
    import shutil
    
    try:
        # Reset vector store
        eng = get_engine()
        eng.vector_store.reset()
        
        # Clear processed directory
        if config.PROCESSED_DIR.exists():
            for f in config.PROCESSED_DIR.iterdir():
                f.unlink()
        
        # Clear uploads directory
        if config.UPLOAD_DIR.exists():
            for f in config.UPLOAD_DIR.iterdir():
                f.unlink()
        
        # Clear embedding cache
        cache_file = config.DATA_DIR / "embedding_cache.json"
        if cache_file.exists():
            cache_file.unlink()
        
        # Clear chat history
        chat_db.delete_all_chat_history()
        
        return {"success": True, "message": "All data cleared successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# =============================================================================
# Chat History Routes
# =============================================================================
@app.get("/chat/messages")
def get_chat_messages(conversation_id: str = "default"):
    """Get chat messages for a conversation"""
    try:
        messages = chat_db.get_messages(conversation_id)
        return {"messages": messages, "conversation_id": conversation_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/chat/messages")
def add_chat_message(message: ChatMessage, conversation_id: str = "default"):
    """Add a message to chat history"""
    try:
        message_id = chat_db.add_message(
            conversation_id=conversation_id,
            role=message.role,
            content=message.content,
            citations=message.citations
        )
        return {"success": True, "message_id": message_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/chat/messages")
def clear_chat_messages(conversation_id: str = "default"):
    """Clear chat messages for a conversation"""
    try:
        chat_db.clear_conversation(conversation_id)
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/chat/conversations")
def get_conversations():
    """Get all conversations"""
    try:
        conversations = chat_db.get_all_conversations()
        return {"conversations": conversations}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/chat/conversations/{conversation_id}")
def rename_conversation(conversation_id: str, request: RenameRequest):
    """Rename a conversation"""
    try:
        chat_db.rename_conversation(conversation_id, request.title)
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# =============================================================================
# Static Files (Production - serve built frontend)
# =============================================================================
if SERVE_FRONTEND:
    # Serve static assets
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")
    
    # Catch-all route for SPA - must be last!
    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        """Serve the React SPA for all non-API routes"""
        file_path = FRONTEND_DIST / full_path
        if file_path.exists() and file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(FRONTEND_DIST / "index.html")
