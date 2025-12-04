"""
Chat History Manager
Handles persistence and retrieval of conversation history.
"""
import json
import uuid
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field, asdict
from datetime import datetime
from collections import defaultdict

import config


@dataclass
class Message:
    """Represents a single chat message."""
    id: str
    role: str  # 'user' or 'assistant'
    content: str
    timestamp: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @classmethod
    def create(
        cls,
        role: str,
        content: str,
        metadata: Optional[Dict] = None
    ) -> 'Message':
        """Create a new message with auto-generated ID and timestamp."""
        return cls(
            id=str(uuid.uuid4())[:8],
            role=role,
            content=content,
            timestamp=datetime.now().isoformat(),
            metadata=metadata or {}
        )
    
    def to_dict(self) -> dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> 'Message':
        return cls(**data)


@dataclass
class Conversation:
    """Represents a complete conversation session."""
    id: str
    title: str
    created_at: str
    updated_at: str
    messages: List[Message]
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @classmethod
    def create(cls, title: Optional[str] = None) -> 'Conversation':
        """Create a new conversation."""
        now = datetime.now().isoformat()
        return cls(
            id=str(uuid.uuid4())[:12],
            title=title or f"Conversation {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            created_at=now,
            updated_at=now,
            messages=[],
            metadata={}
        )
    
    def add_message(self, role: str, content: str, metadata: Optional[Dict] = None) -> Message:
        """Add a message to the conversation."""
        message = Message.create(role, content, metadata)
        self.messages.append(message)
        self.updated_at = datetime.now().isoformat()
        
        # Auto-generate title from first user message
        if len(self.messages) == 1 and role == "user":
            self.title = content[:50] + ("..." if len(content) > 50 else "")
        
        return message
    
    def get_messages_for_context(self, max_messages: int = None) -> List[Dict[str, str]]:
        """Get messages formatted for LLM context."""
        messages = self.messages
        if max_messages:
            messages = messages[-max_messages:]
        
        return [
            {"role": msg.role, "content": msg.content}
            for msg in messages
        ]
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "messages": [msg.to_dict() for msg in self.messages],
            "metadata": self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'Conversation':
        messages = [Message.from_dict(m) for m in data.get("messages", [])]
        return cls(
            id=data["id"],
            title=data["title"],
            created_at=data["created_at"],
            updated_at=data["updated_at"],
            messages=messages,
            metadata=data.get("metadata", {})
        )
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get conversation statistics."""
        user_msgs = [m for m in self.messages if m.role == "user"]
        assistant_msgs = [m for m in self.messages if m.role == "assistant"]
        
        total_user_chars = sum(len(m.content) for m in user_msgs)
        total_assistant_chars = sum(len(m.content) for m in assistant_msgs)
        
        return {
            "total_messages": len(self.messages),
            "user_messages": len(user_msgs),
            "assistant_messages": len(assistant_msgs),
            "total_user_characters": total_user_chars,
            "total_assistant_characters": total_assistant_chars,
            "avg_user_message_length": total_user_chars / len(user_msgs) if user_msgs else 0,
            "avg_assistant_message_length": total_assistant_chars / len(assistant_msgs) if assistant_msgs else 0
        }


class ChatHistoryManager:
    """
    Manages chat history with persistence to disk.
    Supports multiple conversations, search, and export.
    """
    
    def __init__(self, storage_path: Optional[Path] = None):
        self.storage_path = storage_path or config.CHAT_HISTORY_PATH
        self.storage_path.mkdir(parents=True, exist_ok=True)
        
        self._conversations: Dict[str, Conversation] = {}
        self._current_conversation_id: Optional[str] = None
        self._index_file = self.storage_path / "index.json"
        
        # Load existing conversations
        self._load_index()
    
    def _load_index(self):
        """Load conversation index from disk."""
        if self._index_file.exists():
            with open(self._index_file, 'r', encoding='utf-8') as f:
                index = json.load(f)
                
            for conv_id in index.get("conversations", []):
                conv_file = self.storage_path / f"{conv_id}.json"
                if conv_file.exists():
                    try:
                        with open(conv_file, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                        self._conversations[conv_id] = Conversation.from_dict(data)
                    except Exception as e:
                        print(f"Warning: Could not load conversation {conv_id}: {e}")
    
    def _save_index(self):
        """Save conversation index to disk."""
        index = {
            "conversations": list(self._conversations.keys()),
            "current_conversation": self._current_conversation_id,
            "updated_at": datetime.now().isoformat()
        }
        
        with open(self._index_file, 'w', encoding='utf-8') as f:
            json.dump(index, f, indent=2)
    
    def _save_conversation(self, conversation: Conversation):
        """Save a single conversation to disk."""
        conv_file = self.storage_path / f"{conversation.id}.json"
        
        with open(conv_file, 'w', encoding='utf-8') as f:
            json.dump(conversation.to_dict(), f, indent=2, ensure_ascii=False)
    
    def create_conversation(self, title: Optional[str] = None) -> Conversation:
        """Create a new conversation and set it as current."""
        conversation = Conversation.create(title)
        self._conversations[conversation.id] = conversation
        self._current_conversation_id = conversation.id
        
        self._save_conversation(conversation)
        self._save_index()
        
        return conversation
    
    def get_current_conversation(self) -> Optional[Conversation]:
        """Get the current active conversation."""
        if self._current_conversation_id:
            return self._conversations.get(self._current_conversation_id)
        return None
    
    def set_current_conversation(self, conversation_id: str) -> bool:
        """Set a conversation as the current one."""
        if conversation_id in self._conversations:
            self._current_conversation_id = conversation_id
            self._save_index()
            return True
        return False
    
    def get_conversation(self, conversation_id: str) -> Optional[Conversation]:
        """Get a specific conversation by ID."""
        return self._conversations.get(conversation_id)
    
    def list_conversations(
        self,
        limit: int = 50,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """List all conversations with summary info."""
        conversations = sorted(
            self._conversations.values(),
            key=lambda c: c.updated_at,
            reverse=True
        )
        
        return [
            {
                "id": conv.id,
                "title": conv.title,
                "created_at": conv.created_at,
                "updated_at": conv.updated_at,
                "message_count": len(conv.messages),
                "is_current": conv.id == self._current_conversation_id
            }
            for conv in conversations[offset:offset + limit]
        ]
    
    def add_message(
        self,
        role: str,
        content: str,
        metadata: Optional[Dict] = None,
        conversation_id: Optional[str] = None
    ) -> Message:
        """Add a message to a conversation (current if not specified)."""
        conv_id = conversation_id or self._current_conversation_id
        
        if not conv_id or conv_id not in self._conversations:
            # Create new conversation if none exists
            conversation = self.create_conversation()
        else:
            conversation = self._conversations[conv_id]
        
        message = conversation.add_message(role, content, metadata)
        
        self._save_conversation(conversation)
        
        return message
    
    def add_exchange(
        self,
        user_content: str,
        assistant_content: str,
        user_metadata: Optional[Dict] = None,
        assistant_metadata: Optional[Dict] = None
    ) -> tuple:
        """Add a user-assistant exchange to the current conversation."""
        user_msg = self.add_message("user", user_content, user_metadata)
        assistant_msg = self.add_message("assistant", assistant_content, assistant_metadata)
        return user_msg, assistant_msg
    
    def delete_conversation(self, conversation_id: str) -> bool:
        """Delete a conversation."""
        if conversation_id not in self._conversations:
            return False
        
        # Remove from memory
        del self._conversations[conversation_id]
        
        # Remove file
        conv_file = self.storage_path / f"{conversation_id}.json"
        if conv_file.exists():
            conv_file.unlink()
        
        # Update current if deleted
        if self._current_conversation_id == conversation_id:
            self._current_conversation_id = None
            if self._conversations:
                # Set most recent as current
                most_recent = max(
                    self._conversations.values(),
                    key=lambda c: c.updated_at
                )
                self._current_conversation_id = most_recent.id
        
        self._save_index()
        return True
    
    def search_conversations(self, query: str) -> List[Dict[str, Any]]:
        """Search across all conversations."""
        query_lower = query.lower()
        results = []
        
        for conv in self._conversations.values():
            matches = []
            
            # Search in title
            if query_lower in conv.title.lower():
                matches.append({"type": "title", "content": conv.title})
            
            # Search in messages
            for msg in conv.messages:
                if query_lower in msg.content.lower():
                    preview = msg.content[:200]
                    matches.append({
                        "type": "message",
                        "role": msg.role,
                        "content": preview,
                        "timestamp": msg.timestamp
                    })
            
            if matches:
                results.append({
                    "conversation_id": conv.id,
                    "conversation_title": conv.title,
                    "matches": matches[:5],  # Limit matches per conversation
                    "total_matches": len(matches)
                })
        
        return results
    
    def get_context_messages(
        self,
        max_messages: int = config.MAX_HISTORY_MESSAGES,
        conversation_id: Optional[str] = None
    ) -> List[Dict[str, str]]:
        """Get messages formatted for LLM context."""
        conv_id = conversation_id or self._current_conversation_id
        
        if not conv_id or conv_id not in self._conversations:
            return []
        
        return self._conversations[conv_id].get_messages_for_context(max_messages)
    
    def export_conversation(
        self,
        conversation_id: str,
        format: str = "markdown"
    ) -> str:
        """Export a conversation to various formats."""
        conversation = self._conversations.get(conversation_id)
        if not conversation:
            return ""
        
        if format == "markdown":
            return self._export_markdown(conversation)
        elif format == "json":
            return json.dumps(conversation.to_dict(), indent=2, ensure_ascii=False)
        elif format == "text":
            return self._export_text(conversation)
        else:
            raise ValueError(f"Unsupported export format: {format}")
    
    def _export_markdown(self, conversation: Conversation) -> str:
        """Export conversation to markdown format."""
        lines = [
            f"# {conversation.title}",
            f"\n*Created: {conversation.created_at}*",
            f"\n*Last updated: {conversation.updated_at}*",
            "\n---\n"
        ]
        
        for msg in conversation.messages:
            if msg.role == "user":
                lines.append(f"### 🧑 User\n\n{msg.content}\n")
            else:
                lines.append(f"### 🤖 Assistant\n\n{msg.content}\n")
            lines.append(f"*{msg.timestamp}*\n")
            lines.append("---\n")
        
        return "\n".join(lines)
    
    def _export_text(self, conversation: Conversation) -> str:
        """Export conversation to plain text format."""
        lines = [
            conversation.title,
            "=" * len(conversation.title),
            f"Created: {conversation.created_at}",
            f"Updated: {conversation.updated_at}",
            "",
            "-" * 50,
            ""
        ]
        
        for msg in conversation.messages:
            role = "User" if msg.role == "user" else "Assistant"
            lines.append(f"[{role}] ({msg.timestamp})")
            lines.append(msg.content)
            lines.append("")
            lines.append("-" * 50)
            lines.append("")
        
        return "\n".join(lines)
    
    def clear_all(self):
        """Clear all conversations."""
        # Remove all conversation files
        for conv_id in list(self._conversations.keys()):
            conv_file = self.storage_path / f"{conv_id}.json"
            if conv_file.exists():
                conv_file.unlink()
        
        # Clear memory
        self._conversations = {}
        self._current_conversation_id = None
        
        # Update index
        self._save_index()
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get overall statistics across all conversations."""
        total_messages = 0
        total_user_messages = 0
        total_assistant_messages = 0
        
        for conv in self._conversations.values():
            stats = conv.get_statistics()
            total_messages += stats["total_messages"]
            total_user_messages += stats["user_messages"]
            total_assistant_messages += stats["assistant_messages"]
        
        return {
            "total_conversations": len(self._conversations),
            "total_messages": total_messages,
            "total_user_messages": total_user_messages,
            "total_assistant_messages": total_assistant_messages,
            "current_conversation": self._current_conversation_id
        }


class ConversationContext:
    """
    Manages conversation context for a single session.
    Integrates with ChatHistoryManager for persistence.
    """
    
    def __init__(self, history_manager: Optional[ChatHistoryManager] = None):
        self.history_manager = history_manager or ChatHistoryManager()
        self._session_context: List[Dict[str, str]] = []
    
    def start_new_conversation(self, title: Optional[str] = None) -> str:
        """Start a new conversation and return its ID."""
        conversation = self.history_manager.create_conversation(title)
        self._session_context = []
        return conversation.id
    
    def continue_conversation(self, conversation_id: str) -> bool:
        """Continue an existing conversation."""
        if self.history_manager.set_current_conversation(conversation_id):
            self._session_context = self.history_manager.get_context_messages()
            return True
        return False
    
    def add_user_message(self, content: str, metadata: Optional[Dict] = None) -> str:
        """Add a user message and return its ID."""
        message = self.history_manager.add_message("user", content, metadata)
        self._session_context.append({"role": "user", "content": content})
        return message.id
    
    def add_assistant_message(self, content: str, metadata: Optional[Dict] = None) -> str:
        """Add an assistant message and return its ID."""
        message = self.history_manager.add_message("assistant", content, metadata)
        self._session_context.append({"role": "assistant", "content": content})
        return message.id
    
    def get_context_for_llm(self, max_messages: int = None) -> List[Dict[str, str]]:
        """Get context formatted for LLM."""
        if max_messages:
            return self._session_context[-max_messages:]
        return self._session_context
    
    def get_current_conversation_id(self) -> Optional[str]:
        """Get current conversation ID."""
        conv = self.history_manager.get_current_conversation()
        return conv.id if conv else None
    
    def get_conversation_title(self) -> str:
        """Get current conversation title."""
        conv = self.history_manager.get_current_conversation()
        return conv.title if conv else "New Conversation"


if __name__ == "__main__":
    # Test the chat history manager
    manager = ChatHistoryManager()
    
    # Create a test conversation
    conv = manager.create_conversation("Test Conversation")
    print(f"Created conversation: {conv.id}")
    
    # Add some messages
    manager.add_message("user", "What is RAG?")
    manager.add_message("assistant", "RAG stands for Retrieval-Augmented Generation...")
    manager.add_message("user", "How does it work?")
    manager.add_message("assistant", "RAG works by combining retrieval and generation...")
    
    # List conversations
    conversations = manager.list_conversations()
    print(f"\nConversations: {len(conversations)}")
    for c in conversations:
        print(f"  - {c['title']} ({c['message_count']} messages)")
    
    # Get statistics
    stats = manager.get_statistics()
    print(f"\nStatistics: {stats}")
    
    # Export
    export = manager.export_conversation(conv.id, "markdown")
    print(f"\nExported conversation:\n{export[:500]}...")

