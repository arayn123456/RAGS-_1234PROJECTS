"""
Chat History Database Module
Stores chat conversations in SQLite for persistence.
"""
import sqlite3
import json
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional
from . import config

DB_PATH = config.DATA_DIR / "chat_history.db"


def get_connection():
    """Get database connection."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Initialize the database tables."""
    conn = get_connection()
    cursor = conn.cursor()
    
    # Create conversations table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS conversations (
            id TEXT PRIMARY KEY,
            title TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Create messages table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            citations TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
        )
    """)
    
    conn.commit()
    conn.close()


def get_or_create_conversation(conversation_id: str = "default") -> str:
    """Get or create a conversation."""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT id FROM conversations WHERE id = ?", (conversation_id,))
    result = cursor.fetchone()
    
    if not result:
        cursor.execute(
            "INSERT INTO conversations (id, title) VALUES (?, ?)",
            (conversation_id, "New Chat")
        )
        conn.commit()
    
    conn.close()
    return conversation_id


def add_message(
    conversation_id: str,
    role: str,
    content: str,
    citations: Optional[List[Dict]] = None
) -> int:
    """Add a message to a conversation."""
    get_or_create_conversation(conversation_id)
    
    conn = get_connection()
    cursor = conn.cursor()
    
    citations_json = json.dumps(citations) if citations else None
    
    cursor.execute(
        """
        INSERT INTO messages (conversation_id, role, content, citations)
        VALUES (?, ?, ?, ?)
        """,
        (conversation_id, role, content, citations_json)
    )
    
    # Update conversation timestamp
    cursor.execute(
        "UPDATE conversations SET updated_at = ? WHERE id = ?",
        (datetime.now(), conversation_id)
    )
    
    # Update title from first user message if not set
    if role == 'user':
        cursor.execute(
            "SELECT title FROM conversations WHERE id = ?",
            (conversation_id,)
        )
        result = cursor.fetchone()
        if result and (not result['title'] or result['title'] == 'New Chat'):
            # Use first 50 chars of user message as title
            title = content[:50] + '...' if len(content) > 50 else content
            cursor.execute(
                "UPDATE conversations SET title = ? WHERE id = ?",
                (title, conversation_id)
            )
    
    conn.commit()
    message_id = cursor.lastrowid
    conn.close()
    
    return message_id


def get_messages(conversation_id: str = "default") -> List[Dict]:
    """Get all messages in a conversation."""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute(
        """
        SELECT role, content, citations, created_at
        FROM messages
        WHERE conversation_id = ?
        ORDER BY created_at ASC
        """,
        (conversation_id,)
    )
    
    messages = []
    for row in cursor.fetchall():
        msg = {
            "role": row["role"],
            "content": row["content"]
        }
        if row["citations"]:
            msg["citations"] = json.loads(row["citations"])
        messages.append(msg)
    
    conn.close()
    return messages


def clear_conversation(conversation_id: str = "default"):
    """Clear all messages in a conversation."""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("DELETE FROM messages WHERE conversation_id = ?", (conversation_id,))
    cursor.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))
    
    conn.commit()
    conn.close()


def get_all_conversations() -> List[Dict]:
    """Get all conversations."""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute(
        """
        SELECT c.id, c.title, c.updated_at,
               (SELECT content FROM messages WHERE conversation_id = c.id ORDER BY created_at ASC LIMIT 1) as first_message
        FROM conversations c
        ORDER BY c.updated_at DESC
        """
    )
    
    conversations = []
    for row in cursor.fetchall():
        conversations.append({
            "id": row["id"],
            "title": row["title"] or row["first_message"][:50] if row["first_message"] else "New Chat",
            "updated_at": row["updated_at"]
        })
    
    conn.close()
    return conversations


def delete_all_chat_history():
    """Delete all chat history."""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("DELETE FROM messages")
    cursor.execute("DELETE FROM conversations")
    
    conn.commit()
    conn.close()


def rename_conversation(conversation_id: str, title: str):
    """Rename a conversation."""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute(
        "UPDATE conversations SET title = ?, updated_at = ? WHERE id = ?",
        (title, datetime.now(), conversation_id)
    )
    
    conn.commit()
    conn.close()


# Initialize database on module load
init_db()

