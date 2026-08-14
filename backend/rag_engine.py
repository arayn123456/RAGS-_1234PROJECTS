"""
RAG Engine Module
Core retrieval-augmented generation logic with free Gemini models.
"""
import json
from pathlib import Path
from typing import Dict, List, Optional, Generator, Any
from dataclasses import dataclass, field
from datetime import datetime

# from openai import OpenAI  # Commented out — using Gemini
# import google.generativeai as genai  # Deprecated — using google.genai
from google import genai as google_genai
from google.genai import types as genai_types
from tenacity import retry, stop_after_attempt, wait_exponential

from . import config
from .document_processor import DocumentProcessor, ProcessedDocument
from .vector_store import VectorStore, SearchResult, HybridSearch
from .logger import log_info, log_success, log_query, log_error, log_step


@dataclass
class Citation:
    """Represents a citation to source material."""
    document_name: str
    document_id: str
    start_line: int
    end_line: int
    page_numbers: List[int]
    content_preview: str
    relevance_score: float
    
    def format(self) -> str:
        """Format citation for display."""
        pages = f", Pages {', '.join(map(str, self.page_numbers))}" if self.page_numbers else ""
        return f"📄 {self.document_name} (Lines {self.start_line}-{self.end_line}{pages})"


@dataclass
class RAGResponse:
    """Response from the RAG engine."""
    answer: str
    citations: List[Citation]
    retrieved_chunks: List[SearchResult]
    model_used: str
    tokens_used: Dict[str, int]
    processing_time: float
    query: str
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def format_with_citations(self) -> str:
        """Format the response with inline citations."""
        response = f"## Answer\n\n{self.answer}\n\n"
        
        if self.citations:
            response += "## Sources\n\n"
            for i, citation in enumerate(self.citations, 1):
                response += f"{i}. {citation.format()}\n"
                response += f"   *Preview:* {citation.content_preview[:150]}...\n\n"
        
        return response
    
    def to_dict(self) -> dict:
        """Convert to dictionary for storage."""
        return {
            "answer": self.answer,
            "citations": [
                {
                    "document_name": c.document_name,
                    "document_id": c.document_id,
                    "start_line": c.start_line,
                    "end_line": c.end_line,
                    "page_numbers": c.page_numbers,
                    "content_preview": c.content_preview,
                    "relevance_score": c.relevance_score
                }
                for c in self.citations
            ],
            "model_used": self.model_used,
            "tokens_used": self.tokens_used,
            "query": self.query,
            "timestamp": self.timestamp
        }


SYSTEM_PROMPT = """You are an intelligent document assistant that provides accurate, well-cited answers based on the provided context.

## Your Responsibilities:
1. Answer questions ONLY based on the provided document context
2. Always cite your sources with specific line numbers
3. If the context doesn't contain enough information, say so clearly
4. Preserve the original meaning and terminology from the documents
5. Structure your answers clearly with headings when appropriate

## Citation Format:
When referencing information, use this format: [Document Name, Lines X-Y]
Example: "According to the analysis [Report.pdf, Lines 45-52], the main findings show..."

## Response Guidelines:
- Be precise and factual
- Use bullet points for lists
- Quote directly when exact wording is important (use quotation marks)
- If information spans multiple documents, cite each source
- Indicate confidence level if information is partial or unclear

## Context Information:
The following context was retrieved from uploaded documents. Each chunk includes:
- Document name
- Line numbers (start-end)
- Page numbers (if applicable)
- The actual content

Use this information to provide accurate, well-sourced answers."""


class RAGEngine:
    """
    Core RAG engine that combines retrieval and generation with free Gemini models.
    """
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        vector_store: Optional[VectorStore] = None,
        chat_model: str = config.CHAT_MODEL
    ):
        # OpenAI / deprecated generativeai clients commented out
        # self.client = OpenAI(api_key=api_key or config.OPENAI_API_KEY)
        # genai.configure(api_key=...)
        # self.model = genai.GenerativeModel(...)
        self.client = google_genai.Client(api_key=api_key or config.GEMINI_API_KEY)
        self.chat_model = chat_model or config.CHAT_MODEL
        self._gen_config = genai_types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            temperature=0.3,
            max_output_tokens=2000,
        )
        self.vector_store = vector_store or VectorStore()
        self.hybrid_search = HybridSearch(self.vector_store)
        self.document_processor = DocumentProcessor()
    
    def _generate(self, contents, stream: bool = False):
        """Call Gemini using the current configured free chat model."""
        # Always read from config so .env / config changes apply without stale init defaults
        model_name = config.CHAT_MODEL or self.chat_model
        self.chat_model = model_name
        log_info(f"Generating with Gemini model: {model_name}")
        if stream:
            return self.client.models.generate_content_stream(
                model=model_name,
                contents=contents,
                config=self._gen_config,
            )
        return self.client.models.generate_content(
            model=model_name,
            contents=contents,
            config=self._gen_config,
        )
    
    def _build_gemini_contents(
        self,
        user_message: str,
        chat_history: Optional[List[Dict[str, str]]] = None
    ) -> List[genai_types.Content]:
        """Build Gemini contents from chat history + current user message."""
        contents: List[genai_types.Content] = []
        if chat_history:
            for msg in chat_history[-10:]:
                role = msg.get("role", "user")
                gemini_role = "user" if role == "user" else "model"
                contents.append(
                    genai_types.Content(
                        role=gemini_role,
                        parts=[genai_types.Part(text=msg.get("content", ""))],
                    )
                )
        contents.append(
            genai_types.Content(
                role="user",
                parts=[genai_types.Part(text=user_message)],
            )
        )
        return contents
    
    def _usage_tokens(self, response) -> Dict[str, int]:
        """Extract token usage from a Gemini response."""
        usage = getattr(response, "usage_metadata", None)
        if not usage:
            return {"prompt": 0, "completion": 0, "total": 0}
        prompt = getattr(usage, "prompt_token_count", 0) or 0
        completion = getattr(usage, "candidates_token_count", 0) or 0
        total = getattr(usage, "total_token_count", 0) or (prompt + completion)
        return {"prompt": prompt, "completion": completion, "total": total}
    
    def add_document(
        self,
        file_path: str,
        force_reindex: bool = False,
        original_filename: str = None
    ) -> ProcessedDocument:
        """Process and index a document."""
        display_name = original_filename or Path(file_path).name
        log_info(f"Starting document processing: {display_name}")
        
        # Step 1: Extract text
        doc = self.document_processor.process_file(file_path)
        
        # Use original filename if provided
        if original_filename:
            doc.name = original_filename
            # Update chunk names too
            for chunk in doc.chunks:
                chunk.document_name = original_filename
        
        log_step(f"Text extracted: {doc.total_lines} lines, {len(doc.chunks)} chunks")
        
        # Step 2: Index in vector store
        log_step("Starting vector indexing...")
        chunks_added = self.vector_store.add_document(doc, force_reindex=force_reindex)
        log_success(f"Document indexed: {chunks_added} chunks added")
        
        return doc
    
    def _build_context(
        self,
        results: List[SearchResult],
        max_tokens: int = 8000
    ) -> str:
        """Build context string from search results."""
        context_parts = []
        current_tokens = 0
        
        for result in results:
            # Estimate tokens (rough: 4 chars per token)
            chunk_tokens = len(result.content) // 4
            
            if current_tokens + chunk_tokens > max_tokens:
                break
            
            pages = f", Pages {', '.join(map(str, result.page_numbers))}" if result.page_numbers else ""
            
            context_part = f"""
---
📄 **Document:** {result.document_name}
📍 **Lines:** {result.start_line}-{result.end_line}{pages}
🎯 **Relevance:** {result.score:.2%}

{result.content}
---
"""
            context_parts.append(context_part)
            current_tokens += chunk_tokens
        
        return "\n".join(context_parts)
    
    def _create_citations(self, results: List[SearchResult]) -> List[Citation]:
        """Create citation objects from search results."""
        citations = []
        seen = set()
        
        for result in results:
            # Deduplicate by document and line range
            key = (result.document_id, result.start_line, result.end_line)
            if key in seen:
                continue
            seen.add(key)
            
            citations.append(Citation(
                document_name=result.document_name,
                document_id=result.document_id,
                start_line=result.start_line,
                end_line=result.end_line,
                page_numbers=result.page_numbers,
                content_preview=result.content[:200],
                relevance_score=result.score
            ))
        
        return citations
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def query(
        self,
        question: str,
        chat_history: Optional[List[Dict[str, str]]] = None,
        top_k: int = config.TOP_K_RESULTS,
        document_filter: Optional[str] = None,
        use_hybrid_search: bool = True
    ) -> RAGResponse:
        """
        Process a query and generate a response with citations.
        
        Args:
            question: User's question
            chat_history: Previous conversation messages
            top_k: Number of chunks to retrieve
            document_filter: Optional document ID to filter results
            use_hybrid_search: Whether to use hybrid (semantic + keyword) search
            
        Returns:
            RAGResponse with answer and citations
        """
        import time
        start_time = time.time()
        
        log_info(f"Query: {question[:80]}...")
        log_step("Searching for relevant content...")
        
        # Retrieve relevant chunks
        if use_hybrid_search:
            results = self.hybrid_search.search(
                query=question,
                top_k=top_k,
                document_filter=document_filter
            )
        else:
            results = self.vector_store.search(
                query=question,
                top_k=top_k,
                document_filter=document_filter
            )
        
        if not results:
            return RAGResponse(
                answer="I couldn't find any relevant information in the uploaded documents to answer your question. Please make sure you've uploaded documents containing information related to your query.",
                citations=[],
                retrieved_chunks=[],
                model_used=self.chat_model,
                tokens_used={"prompt": 0, "completion": 0, "total": 0},
                processing_time=time.time() - start_time,
                query=question
            )
        
        # Build context from results
        context = self._build_context(results)
        
        user_message = f"""## Retrieved Context

{context}

## Question

{question}

Please provide a comprehensive answer based on the context above. Remember to cite specific line numbers from the documents."""
        
        # OpenAI chat.completions API (commented out)
        # response = self.client.chat.completions.create(...)
        
        # Deprecated google.generativeai chat (commented out)
        # history = self._build_gemini_history(chat_history)
        # chat = self.model.start_chat(history=history)
        # response = chat.send_message(user_message)
        
        contents = self._build_gemini_contents(user_message, chat_history)
        response = self._generate(contents)
        answer = response.text or ""
        tokens_used = self._usage_tokens(response)
        
        # Create citations
        citations = self._create_citations(results)
        
        processing_time = time.time() - start_time
        
        # Log the query
        log_success(f"Response generated in {processing_time:.2f}s")
        log_query(
            query=question,
            response_preview=answer[:100] if answer else "",
            tokens=tokens_used["total"],
            time_taken=processing_time
        )
        
        return RAGResponse(
            answer=answer,
            citations=citations,
            retrieved_chunks=results,
            model_used=self.chat_model,
            tokens_used=tokens_used,
            processing_time=processing_time,
            query=question
        )
    
    def query_stream(
        self,
        question: str,
        chat_history: Optional[List[Dict[str, str]]] = None,
        top_k: int = config.TOP_K_RESULTS,
        document_filter: Optional[str] = None,
        use_hybrid_search: bool = True
    ) -> Generator[str, None, RAGResponse]:
        """
        Stream the response for real-time display.
        
        Yields:
            Chunks of the response as they're generated
            
        Returns:
            Complete RAGResponse after streaming is done
        """
        import time
        start_time = time.time()
        
        # Retrieve relevant chunks
        if use_hybrid_search:
            results = self.hybrid_search.search(
                query=question,
                top_k=top_k,
                document_filter=document_filter
            )
        else:
            results = self.vector_store.search(
                query=question,
                top_k=top_k,
                document_filter=document_filter
            )
        
        if not results:
            yield "I couldn't find any relevant information in the uploaded documents."
            return RAGResponse(
                answer="No relevant information found.",
                citations=[],
                retrieved_chunks=[],
                model_used=self.chat_model,
                tokens_used={"prompt": 0, "completion": 0, "total": 0},
                processing_time=time.time() - start_time,
                query=question
            )
        
        # Build context
        context = self._build_context(results)
        
        user_message = f"""## Retrieved Context

{context}

## Question

{question}

Please provide a comprehensive answer based on the context above."""
        
        # OpenAI / deprecated generativeai streaming (commented out)
        # stream = self.client.chat.completions.create(..., stream=True)
        # chat = self.model.start_chat(history=history)
        # stream = chat.send_message(user_message, stream=True)
        
        full_answer = ""
        contents = self._build_gemini_contents(user_message, chat_history)
        stream = self._generate(contents, stream=True)
        
        for chunk in stream:
            text = getattr(chunk, "text", None)
            if text:
                full_answer += text
                yield text
        
        # Create final response
        citations = self._create_citations(results)
        
        return RAGResponse(
            answer=full_answer,
            citations=citations,
            retrieved_chunks=results,
            model_used=self.chat_model,
            tokens_used={"prompt": 0, "completion": 0, "total": 0},
            processing_time=time.time() - start_time,
            query=question
        )
    
    def get_line_context(
        self,
        document_id: str,
        line_number: int,
        context_lines: int = 5
    ) -> str:
        """Get lines around a specific line number for context."""
        lines, start, end = self.document_processor.get_context_around_line(
            document_id,
            line_number,
            context_lines
        )
        
        result = f"Lines {start}-{end}:\n\n"
        for line in lines:
            prefix = ">>> " if line.line_number == line_number else "    "
            result += f"{prefix}{line.line_number}: {line.content}\n"
        
        return result
    
    def get_document_summary(
        self,
        document_id: str,
        max_length: int = 500
    ) -> str:
        """Generate a brief summary of a document."""
        # Get first few chunks
        info = self.vector_store.get_document_info()
        
        if document_id not in info['documents']:
            return "Document not found."
        
        doc_info = info['documents'][document_id]
        
        # Search for overview content
        results = self.vector_store.search(
            query="introduction overview summary abstract purpose",
            top_k=3,
            document_filter=document_id
        )
        
        summary = f"**{doc_info['name']}**\n"
        summary += f"- Lines: {doc_info['total_lines']:,}\n"
        summary += f"- Words: {doc_info['total_words']:,}\n"
        summary += f"- Chunks: {doc_info['chunks']}\n\n"
        
        if results:
            summary += "**Overview:**\n"
            preview = results[0].content[:max_length]
            if len(results[0].content) > max_length:
                preview += "..."
            summary += preview
        
        return summary
    
    def compare_documents(
        self,
        question: str,
        document_ids: List[str]
    ) -> str:
        """Compare information across multiple documents."""
        comparisons = []
        
        for doc_id in document_ids:
            results = self.vector_store.search(
                query=question,
                top_k=3,
                document_filter=doc_id
            )
            
            if results:
                doc_name = results[0].document_name
                content = "\n".join([r.content[:300] for r in results])
                comparisons.append(f"### {doc_name}\n{content}")
        
        if not comparisons:
            return "No relevant information found in the specified documents."
        
        # OpenAI / deprecated generativeai comparison (commented out)
        # compare_model = genai.GenerativeModel(...)
        # response = compare_model.generate_content(prompt)
        
        prompt = f"Question: {question}\n\n" + "\n\n".join(comparisons)
        response = self.client.models.generate_content(
            model=config.CHAT_MODEL or self.chat_model,
            contents=prompt,
            config=genai_types.GenerateContentConfig(
                system_instruction=(
                    "You are a document analyst. Compare the information from different "
                    "documents and highlight similarities and differences."
                ),
                temperature=0.3,
            ),
        )
        return response.text or ""


class ConversationalRAG:
    """
    RAG engine with conversation memory and context management.
    """
    
    def __init__(self, rag_engine: Optional[RAGEngine] = None):
        self.engine = rag_engine or RAGEngine()
        self.conversation_context = []
        self.follow_up_keywords = [
            "what about", "how about", "also", "additionally",
            "more about", "elaborate", "explain more", "tell me more",
            "can you", "could you", "what else", "anything else"
        ]
    
    def _is_follow_up(self, question: str) -> bool:
        """Detect if a question is a follow-up to previous context."""
        question_lower = question.lower()
        
        # Check for follow-up keywords
        for keyword in self.follow_up_keywords:
            if keyword in question_lower:
                return True
        
        # Check for pronouns that reference previous context
        pronouns = ["it", "this", "that", "these", "those", "they", "them"]
        words = question_lower.split()
        if words and words[0] in pronouns:
            return True
        
        return False
    
    def _enhance_query(self, question: str) -> str:
        """Enhance query with context from previous conversation."""
        if not self.conversation_context:
            return question
        
        if self._is_follow_up(question):
            # Get last few exchanges for context
            recent_context = self.conversation_context[-4:]
            context_summary = " ".join([
                msg["content"][:100] 
                for msg in recent_context 
                if msg["role"] == "user"
            ])
            
            return f"{context_summary} {question}"
        
        return question
    
    def chat(
        self,
        question: str,
        document_filter: Optional[str] = None
    ) -> RAGResponse:
        """
        Process a chat message with conversation context.
        """
        # Enhance query if it's a follow-up
        enhanced_query = self._enhance_query(question)
        
        # Get response
        response = self.engine.query(
            question=enhanced_query,
            chat_history=self.conversation_context,
            document_filter=document_filter
        )
        
        # Update conversation context
        self.conversation_context.append({
            "role": "user",
            "content": question
        })
        self.conversation_context.append({
            "role": "assistant",
            "content": response.answer
        })
        
        # Trim context if too long
        if len(self.conversation_context) > config.MAX_HISTORY_MESSAGES * 2:
            self.conversation_context = self.conversation_context[-config.MAX_HISTORY_MESSAGES * 2:]
        
        return response
    
    def reset_conversation(self):
        """Reset conversation context."""
        self.conversation_context = []
    
    def get_conversation_summary(self) -> str:
        """Get a summary of the current conversation."""
        if not self.conversation_context:
            return "No conversation history."
        
        summary = f"**Conversation ({len(self.conversation_context) // 2} exchanges)**\n\n"
        
        for i in range(0, len(self.conversation_context), 2):
            if i + 1 < len(self.conversation_context):
                q = self.conversation_context[i]["content"][:100]
                a = self.conversation_context[i + 1]["content"][:150]
                summary += f"**Q:** {q}{'...' if len(self.conversation_context[i]['content']) > 100 else ''}\n"
                summary += f"**A:** {a}{'...' if len(self.conversation_context[i + 1]['content']) > 150 else ''}\n\n"
        
        return summary


if __name__ == "__main__":
    # Test the RAG engine
    import sys
    
    engine = RAGEngine()
    
    # Check for documents
    info = engine.vector_store.get_document_info()
    print(f"📚 Indexed documents: {info['total_documents']}")
    print(f"📦 Total chunks: {info['total_chunks']}")
    
    if info['total_documents'] > 0:
        # Interactive query
        print("\n💬 Enter your question (or 'quit' to exit):")
        
        while True:
            question = input("\n> ")
            if question.lower() in ['quit', 'exit', 'q']:
                break
            
            response = engine.query(question)
            print(f"\n{response.format_with_citations()}")
            print(f"\n⏱️ Processing time: {response.processing_time:.2f}s")
            print(f"🔢 Tokens used: {response.tokens_used['total']}")
    else:
        print("\n⚠️ No documents indexed. Add a document first:")
        print("   python rag_engine.py path/to/document.pdf")
