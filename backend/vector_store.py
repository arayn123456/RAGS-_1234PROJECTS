"""
Vector Store Module
Handles document embeddings and semantic search with ChromaDB.
"""
import json
import os
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
import hashlib

import chromadb
from google import genai as google_genai
from google.genai import types as genai_types
from tenacity import retry, stop_after_attempt, wait_exponential
from tqdm import tqdm

from . import config
from .document_processor import DocumentChunk, ProcessedDocument
from .logger import log_info, log_success, log_step, log_document, log_error, log_warning


@dataclass
class SearchResult:
    """Represents a search result with relevance information."""
    chunk_id: str
    content: str
    score: float
    start_line: int
    end_line: int
    page_numbers: List[int]
    document_id: str
    document_name: str
    metadata: Dict[str, Any]
    
    def format_citation(self) -> str:
        """Format citation for display."""
        pages = f", Pages {self.page_numbers}" if self.page_numbers else ""
        return f"[{self.document_name}, Lines {self.start_line}-{self.end_line}{pages}]"


# One Chroma client per persist path (process-wide).
_chroma_clients: Dict[str, Any] = {}


def _get_chroma_client(persist_directory: str):
    """Create or reuse a PersistentClient, recovering from a corrupt empty store."""
    if persist_directory in _chroma_clients:
        return _chroma_clients[persist_directory]

    from chromadb.api.shared_system_client import SharedSystemClient

    persist_path = Path(persist_directory)

    # An empty persist folder makes Chroma's Rust client fail with
    # "Could not connect to tenant default_tenant".
    if persist_path.is_dir() and not any(persist_path.iterdir()):
        persist_path.rmdir()

    try:
        client = chromadb.PersistentClient(path=str(persist_path))
    except Exception as exc:
        log_warning(
            f"ChromaDB failed to open {persist_path} ({exc}). "
            "Resetting the persist directory and retrying."
        )
        SharedSystemClient.clear_system_cache()
        shutil.rmtree(persist_path, ignore_errors=True)
        client = chromadb.PersistentClient(path=str(persist_path))

    _chroma_clients[persist_directory] = client
    return client


class EmbeddingService:
    """Handles text embedding using the free Gemini embedding API."""
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = config.EMBEDDING_MODEL
    ):
        self.client = google_genai.Client(api_key=api_key or config.GEMINI_API_KEY)
        self.model = model
        self._cache = {}
        self._cache_file = config.DATA_DIR / "embedding_cache_gemini_768.json"
        self._load_cache()
    
    def _load_cache(self):
        """Load embedding cache from disk."""
        if self._cache_file.exists():
            try:
                with open(self._cache_file, 'r') as f:
                    self._cache = json.load(f)
            except Exception:
                self._cache = {}
    
    def _save_cache(self):
        """Save embedding cache to disk."""
        try:
            with open(self._cache_file, 'w') as f:
                json.dump(self._cache, f)
        except Exception:
            pass
    
    def _get_cache_key(self, text: str) -> str:
        """Generate cache key for text."""
        return hashlib.md5(
            f"{self.model}:{config.EMBEDDING_DIMENSIONS}:{text}".encode()
        ).hexdigest()

    def _embed_contents(
        self,
        texts: List[str],
        task_type: str = "RETRIEVAL_DOCUMENT",
    ) -> List[List[float]]:
        """Return one embedding vector per input text.

        gemini-embedding-2 silently aggregates a list of strings into fewer
        vectors, which then makes ChromaDB reject the add(). Always embed
        one text at a time.
        """
        embed_config = genai_types.EmbedContentConfig(
            task_type=task_type,
            output_dimensionality=config.EMBEDDING_DIMENSIONS,
        )
        vectors: List[List[float]] = []
        for text in texts:
            item_contents = [
                genai_types.Content(parts=[genai_types.Part(text=text)])
            ]
            try:
                result = self.client.models.embed_content(
                    model=self.model,
                    contents=item_contents,
                    config=embed_config,
                )
            except Exception:
                result = self.client.models.embed_content(
                    model=self.model,
                    contents=item_contents,
                )
            if not result.embeddings:
                raise RuntimeError(f"Gemini returned no embedding for model {self.model}")
            vectors.append([float(x) for x in result.embeddings[0].values])

        if len(vectors) != len(texts):
            raise RuntimeError(
                f"Expected {len(texts)} embeddings from {self.model}, got {len(vectors)}"
            )
        return vectors
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def embed_text(self, text: str, task_type: str = "RETRIEVAL_QUERY") -> List[float]:
        """Generate embedding for a single text."""
        cache_key = self._get_cache_key(text)
        
        if cache_key in self._cache:
            return self._cache[cache_key]
        
        embedding = self._embed_contents(
            [text],
            task_type=task_type,
        )[0]
        self._cache[cache_key] = embedding
        return embedding
    
    def embed_texts(
        self,
        texts: List[str],
        batch_size: int = 100,
        show_progress: bool = True
    ) -> List[List[float]]:
        """Generate embeddings for multiple texts with batching."""
        embeddings = []
        
        # Check cache first
        uncached_indices = []
        uncached_texts = []
        
        for i, text in enumerate(texts):
            cache_key = self._get_cache_key(text)
            if cache_key in self._cache:
                embeddings.append((i, self._cache[cache_key]))
            else:
                uncached_indices.append(i)
                uncached_texts.append(text)
        
        if not uncached_texts:
            # All cached - return immediately
            embeddings.sort(key=lambda x: x[0])
            return [e[1] for e in embeddings]
        
        log_step(f"Calling Gemini API for {len(uncached_texts)} embeddings ({self.model})...")
        
        for i, text in enumerate(uncached_texts):
            try:
                vector = self._embed_contents(
                    [text],
                    task_type="RETRIEVAL_DOCUMENT",
                )[0]
            except Exception as exc:
                log_error(f"Gemini embedding failed ({self.model}): {exc}")
                raise
            idx = uncached_indices[i]
            self._cache[self._get_cache_key(text)] = vector
            embeddings.append((idx, vector))
        
        # Save cache
        self._save_cache()
        
        # Sort by original index and extract embeddings
        embeddings.sort(key=lambda x: x[0])
        return [e[1] for e in embeddings]


class VectorStore:
    """
    Vector store for document chunks using ChromaDB.
    Supports semantic search with metadata filtering.
    """
    
    def __init__(
        self,
        collection_name: str = config.COLLECTION_NAME,
        persist_directory: Optional[str] = None,
        embedding_service: Optional[EmbeddingService] = None
    ):
        self.collection_name = collection_name
        self.persist_directory = persist_directory or str(config.VECTOR_STORE_PATH)
        
        # Reuse one PersistentClient per path. Creating a second client on a
        # failed/partial init is what triggers KeyError and RustBindingsAPI errors.
        self.client = _get_chroma_client(self.persist_directory)
        
        # Get or create collection
        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            metadata={"description": "RAG document chunks with line tracking"}
        )
        
        # Initialize embedding service
        self.embedding_service = embedding_service or EmbeddingService()
        
        # Track indexed documents
        self._indexed_docs_file = Path(self.persist_directory) / "indexed_docs.json"
        self._indexed_docs = self._load_indexed_docs()
    
    def _load_indexed_docs(self) -> Dict[str, Any]:
        """Load list of indexed documents."""
        if self._indexed_docs_file.exists():
            with open(self._indexed_docs_file, 'r') as f:
                return json.load(f)
        return {}
    
    def _save_indexed_docs(self):
        """Save list of indexed documents."""
        with open(self._indexed_docs_file, 'w') as f:
            json.dump(self._indexed_docs, f, indent=2)
    
    def add_document(
        self,
        document: ProcessedDocument,
        force_reindex: bool = False
    ) -> int:
        """
        Add a processed document to the vector store.
        
        Args:
            document: ProcessedDocument to add
            force_reindex: If True, reindex even if already indexed
            
        Returns:
            Number of chunks added
        """
        doc_id = document.document_id
        
        # Check if already indexed
        if doc_id in self._indexed_docs and not force_reindex:
            log_info(f"Document already indexed: {document.name}")
            return 0
        
        # Remove old chunks if reindexing
        if doc_id in self._indexed_docs:
            self.remove_document(doc_id)
        
        chunks = document.chunks
        if not chunks:
            return 0
        
        log_step(f"Created {len(chunks)} chunks")
        log_step("Generating embeddings (this may take a moment)...")
        
        # Generate embeddings for all chunks
        texts = [chunk.content for chunk in chunks]
        embeddings = self.embedding_service.embed_texts(texts)
        embeddings = [[float(x) for x in vec] for vec in embeddings]
        if len(embeddings) != len(chunks):
            raise RuntimeError(
                f"Embedding count mismatch: got {len(embeddings)} vectors for {len(chunks)} chunks"
            )
        sizes = {len(vec) for vec in embeddings}
        if len(sizes) != 1:
            raise RuntimeError(f"Mixed embedding sizes in one document: {sizes}")
        log_step("Embeddings generated!")
        
        # Prepare data for ChromaDB
        ids = [chunk.chunk_id for chunk in chunks]
        documents = [chunk.content for chunk in chunks]
        metadatas = [
            {
                "document_id": str(chunk.document_id),
                "document_name": str(chunk.document_name),
                "start_line": int(chunk.start_line),
                "end_line": int(chunk.end_line),
                "page_numbers": json.dumps(chunk.page_numbers or []),
                "char_start": int(chunk.char_start),
                "char_end": int(chunk.char_end),
                "chunk_index": int(chunk.metadata.get("chunk_index", 0)),
                "total_chunks": int(chunk.metadata.get("total_chunks", len(chunks))),
            }
            for chunk in chunks
        ]
        
        log_step("Saving to vector database...")
        try:
            self.collection.add(
                ids=ids,
                embeddings=embeddings,
                documents=documents,
                metadatas=metadatas,
            )
        except Exception as exc:
            log_error(f"ChromaDB add failed: {exc}")
            raise
        
        # Track indexed document
        self._indexed_docs[doc_id] = {
            "name": document.name,
            "chunks": len(chunks),
            "total_lines": document.total_lines,
            "total_words": document.total_words,
            "indexed_at": document.processed_at
        }
        self._save_indexed_docs()
        
        log_success(f"Indexed {len(chunks)} chunks from {document.name}")
        log_document("INDEXED", document.name, f"chunks={len(chunks)}, lines={document.total_lines}")
        return len(chunks)
    
    def remove_document(self, document_id: str) -> bool:
        """Remove a document and all its chunks from the store."""
        if document_id not in self._indexed_docs:
            return False
        
        doc_name = self._indexed_docs[document_id].get('name', 'Unknown')
        
        # Get all chunk IDs for this document
        results = self.collection.get(
            where={"document_id": document_id}
        )
        
        if results['ids']:
            self.collection.delete(ids=results['ids'])
        
        # Remove from tracking
        del self._indexed_docs[document_id]
        self._save_indexed_docs()
        
        # Delete processed line mapping file
        processed_file = config.PROCESSED_DIR / f"{document_id}_lines.json"
        if processed_file.exists():
            processed_file.unlink()
            log_info(f"Deleted processed file: {processed_file.name}")
        
        log_document("DELETED", doc_name, f"id={document_id}")
        return True
    
    def search(
        self,
        query: str,
        top_k: int = config.TOP_K_RESULTS,
        document_filter: Optional[str] = None,
        min_score: float = 0.0
    ) -> List[SearchResult]:
        """
        Search for relevant chunks using semantic similarity.
        
        Args:
            query: Search query
            top_k: Number of results to return
            document_filter: Optional document ID to filter by
            min_score: Minimum similarity score threshold
            
        Returns:
            List of SearchResult objects sorted by relevance
        """
        # Generate query embedding
        query_embedding = self.embedding_service.embed_text(query)
        
        # Build where clause for filtering
        where_clause = None
        if document_filter:
            where_clause = {"document_id": document_filter}
        
        # Query the collection
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            where=where_clause,
            include=["documents", "metadatas", "distances"]
        )
        
        # Convert to SearchResult objects
        search_results = []
        
        if results['ids'] and results['ids'][0]:
            for i, chunk_id in enumerate(results['ids'][0]):
                # Convert distance to similarity score (ChromaDB uses L2 distance)
                distance = results['distances'][0][i]
                score = 1.0 / (1.0 + distance)  # Convert to similarity
                
                if score < min_score:
                    continue
                
                metadata = results['metadatas'][0][i]
                
                search_results.append(SearchResult(
                    chunk_id=chunk_id,
                    content=results['documents'][0][i],
                    score=score,
                    start_line=metadata['start_line'],
                    end_line=metadata['end_line'],
                    page_numbers=json.loads(metadata['page_numbers']),
                    document_id=metadata['document_id'],
                    document_name=metadata['document_name'],
                    metadata={
                        "chunk_index": metadata.get('chunk_index', 0),
                        "total_chunks": metadata.get('total_chunks', 0)
                    }
                ))
        
        # Sort by score descending
        search_results.sort(key=lambda x: x.score, reverse=True)
        
        return search_results
    
    def get_document_info(self) -> Dict[str, Any]:
        """Get information about all indexed documents."""
        return {
            "total_documents": len(self._indexed_docs),
            "total_chunks": self.collection.count(),
            "documents": self._indexed_docs
        }
    
    def get_chunk_by_id(self, chunk_id: str) -> Optional[SearchResult]:
        """Retrieve a specific chunk by ID."""
        results = self.collection.get(
            ids=[chunk_id],
            include=["documents", "metadatas"]
        )
        
        if not results['ids']:
            return None
        
        metadata = results['metadatas'][0]
        
        return SearchResult(
            chunk_id=chunk_id,
            content=results['documents'][0],
            score=1.0,
            start_line=metadata['start_line'],
            end_line=metadata['end_line'],
            page_numbers=json.loads(metadata['page_numbers']),
            document_id=metadata['document_id'],
            document_name=metadata['document_name'],
            metadata={
                "chunk_index": metadata.get('chunk_index', 0),
                "total_chunks": metadata.get('total_chunks', 0)
            }
        )
    
    def clear(self):
        """Clear all data from the vector store."""
        # Delete and recreate collection
        self.client.delete_collection(self.collection_name)
        self.collection = self.client.create_collection(
            name=self.collection_name,
            metadata={"description": "RAG document chunks with line tracking"}
        )
        
        # Clear indexed docs tracking
        self._indexed_docs = {}
        self._save_indexed_docs()


class HybridSearch:
    """
    Combines semantic search with keyword matching for better results.
    """
    
    def __init__(self, vector_store: VectorStore):
        self.vector_store = vector_store
    
    def search(
        self,
        query: str,
        top_k: int = config.TOP_K_RESULTS,
        document_filter: Optional[str] = None,
        keyword_boost: float = 0.3
    ) -> List[SearchResult]:
        """
        Perform hybrid search combining semantic and keyword matching.
        """
        # Get semantic search results
        results = self.vector_store.search(
            query=query,
            top_k=top_k * 2,  # Get more results for reranking
            document_filter=document_filter
        )
        
        # Extract keywords from query
        keywords = set(query.lower().split())
        stop_words = {'the', 'a', 'an', 'is', 'are', 'was', 'were', 'what', 'how', 'why', 'when', 'where', 'which'}
        keywords = keywords - stop_words
        
        # Boost scores based on keyword matches
        for result in results:
            content_lower = result.content.lower()
            keyword_matches = sum(1 for kw in keywords if kw in content_lower)
            keyword_score = keyword_matches / len(keywords) if keywords else 0
            
            # Combine scores
            result.score = result.score * (1 - keyword_boost) + keyword_score * keyword_boost
        
        # Re-sort and limit
        results.sort(key=lambda x: x.score, reverse=True)
        return results[:top_k]


if __name__ == "__main__":
    # Test the vector store
    from document_processor import DocumentProcessor
    import sys
    
    if len(sys.argv) > 1:
        # Process and index a document
        processor = DocumentProcessor()
        doc = processor.process_file(sys.argv[1])
        
        store = VectorStore()
        store.add_document(doc)
        
        # Test search
        query = input("\nEnter search query: ")
        results = store.search(query, top_k=3)
        
        print(f"\n🔍 Found {len(results)} results:\n")
        for i, result in enumerate(results, 1):
            print(f"{i}. {result.format_citation()} (Score: {result.score:.3f})")
            print(f"   {result.content[:200]}...")
            print()
