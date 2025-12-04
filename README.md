# Document Q&A - RAG System

A professional RAG (Retrieval-Augmented Generation) system with React frontend and FastAPI backend.

## Project Structure

```
RAGs/
├── backend/                  # Python backend (FastAPI + RAG Engine)
│   ├── __init__.py
│   ├── main.py              # FastAPI routes
│   ├── rag_engine.py        # Core RAG logic
│   ├── vector_store.py      # ChromaDB vector storage
│   ├── document_processor.py # PDF/Word/Text processing
│   ├── chat_history.py      # Conversation management
│   ├── config.py            # Configuration settings
│   └── logger.py            # Logging utilities
│
├── frontend/                 # React frontend (Vite)
│   ├── src/
│   │   ├── App.jsx          # Main React component
│   │   ├── main.jsx         # Entry point
│   │   └── styles.css       # ChatGPT-style CSS
│   ├── index.html
│   ├── package.json
│   └── vite.config.js
│
├── data/                     # Data storage
│   ├── vector_store/        # ChromaDB database
│   ├── chat_history/        # Chat sessions
│   └── processed/           # Processed documents
│
├── logs/                     # Application logs
│   ├── rag_system.log
│   ├── queries.log
│   ├── documents.log
│   └── errors.log
│
├── myvenv/                   # Python virtual environment
├── .env                      # API keys (create from template)
├── env_template.txt          # Environment template
├── requirements.txt          # Python dependencies
└── run_all.py               # Start backend + frontend
```

## Quick Start

### 1. Setup Environment

```bash
# Create .env file from template
copy env_template.txt .env

# Edit .env and add your OpenAI API key
```

### 2. Install Dependencies

```bash
# Activate virtual environment
myvenv\Scripts\activate

# Install Python dependencies
pip install -r requirements.txt

# Install frontend dependencies
cd frontend
npm install
cd ..
```

### 3. Run the Application

```bash
python run_all.py
```

This single command starts:
- Backend server at http://localhost:8000
- Frontend at http://localhost:3000
- Opens browser automatically

### 4. Access the App

- **Frontend**: http://localhost:3000
- **Backend API**: http://localhost:8000
- **API Docs**: http://localhost:8000/docs

## Features

- ChatGPT-style UI
- PDF, Word, Text, Markdown support
- Line-level citations
- Hybrid search (semantic + keyword)
- Chat history
- Dark sidebar theme

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/documents` | List all documents |
| POST | `/api/upload` | Upload a document |
| DELETE | `/api/documents/{id}` | Delete a document |
| POST | `/api/query` | Query documents |

## Configuration

Edit `backend/config.py` to customize settings.

## License

MIT
