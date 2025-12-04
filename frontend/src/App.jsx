import { useState, useEffect, useRef } from 'react'
import axios from 'axios'
import ReactMarkdown from 'react-markdown'
import { Send, Plus, FileText, Trash2, Upload, PanelLeftClose, PanelLeft, Eraser, User, Bot, X, MessageSquare, ChevronDown, ChevronRight, MoreHorizontal, Pencil, Archive, Copy, Check, Paperclip } from 'lucide-react'

// Use relative URL - works on any server/port
const API_URL = 'http://localhost:8000'

// Generate unique ID for conversations
const generateId = () => Date.now().toString(36) + Math.random().toString(36).substr(2)

export default function App() {
  const [messages, setMessages] = useState([])
  const [conversations, setConversations] = useState([])
  const [currentConversationId, setCurrentConversationId] = useState(null)
  const [input, setInput] = useState('')
  const [documents, setDocuments] = useState([])
  const [selectedDoc, setSelectedDoc] = useState(null)
  const [loading, setLoading] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [uploadStatus, setUploadStatus] = useState('')
  const [sidebarOpen, setSidebarOpen] = useState(true)
  const [docsExpanded, setDocsExpanded] = useState(true)
  const [chatsExpanded, setChatsExpanded] = useState(true)
  const [menuOpen, setMenuOpen] = useState(null) // conversation id with open menu
  const [menuPos, setMenuPos] = useState({ top: 0, left: 0 })
  const [docMenuOpen, setDocMenuOpen] = useState(null) // document id with open menu
  const [docMenuPos, setDocMenuPos] = useState({ top: 0, left: 0 })
  const [renameId, setRenameId] = useState(null)
  const [renameValue, setRenameValue] = useState('')
  const [editingMsgIdx, setEditingMsgIdx] = useState(null)
  const [editingMsgValue, setEditingMsgValue] = useState('')
  const [copiedIdx, setCopiedIdx] = useState(null)
  const chatRef = useRef(null)
  const inputRef = useRef(null)
  const fileInputRef = useRef(null)
  const chatFileInputRef = useRef(null)

  // Fetch documents and conversations on load
  useEffect(() => {
    fetchDocuments()
    fetchConversations()
  }, [])

  // Auto-scroll to bottom
  useEffect(() => {
    if (chatRef.current) {
      chatRef.current.scrollTop = chatRef.current.scrollHeight
    }
  }, [messages])

  const fetchDocuments = async () => {
    try {
      const res = await axios.get(`${API_URL}/documents`)
      setDocuments(res.data.documents || [])
    } catch (err) {
      console.error('Failed to fetch documents:', err)
    }
  }

  const fetchConversations = async () => {
    try {
      const res = await axios.get(`${API_URL}/chat/conversations`)
      const convs = res.data.conversations || []
      setConversations(convs)
      
      // Load the most recent conversation if exists
      if (convs.length > 0 && !currentConversationId) {
        loadConversation(convs[0].id)
      }
    } catch (err) {
      console.error('Failed to fetch conversations:', err)
    }
  }

  const loadConversation = async (conversationId) => {
    try {
      const res = await axios.get(`${API_URL}/chat/messages?conversation_id=${conversationId}`)
      setMessages(res.data.messages || [])
      setCurrentConversationId(conversationId)
    } catch (err) {
      console.error('Failed to load conversation:', err)
    }
  }

  const saveChatMessage = async (message, conversationId) => {
    try {
      await axios.post(`${API_URL}/chat/messages?conversation_id=${conversationId}`, message)
    } catch (err) {
      console.error('Failed to save chat message:', err)
    }
  }

  const handleSend = async () => {
    if (!input.trim() || loading || documents.length === 0) return

    const userMessage = { role: 'user', content: input.trim() }
    setMessages(prev => [...prev, userMessage])
    setInput('')
    setLoading(true)

    // Create new conversation if needed
    let convId = currentConversationId
    if (!convId) {
      convId = generateId()
      setCurrentConversationId(convId)
    }

    // Save user message to database
    await saveChatMessage(userMessage, convId)

    try {
      const res = await axios.post(`${API_URL}/query`, {
        question: userMessage.content,
        chat_history: messages.slice(-10),
        document_filter: selectedDoc
      })

      const assistantMessage = {
        role: 'assistant',
        content: res.data.answer,
        citations: res.data.citations
      }

      setMessages(prev => [...prev, assistantMessage])
      
      // Save assistant message to database
      await saveChatMessage(assistantMessage, convId)
      
      // Refresh conversations list
      await fetchConversations()
    } catch (err) {
      const errorMessage = {
        role: 'assistant',
        content: 'Sorry, an error occurred. Please try again.'
      }
      setMessages(prev => [...prev, errorMessage])
      await saveChatMessage(errorMessage, convId)
    } finally {
      setLoading(false)
    }
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const handleNewChat = () => {
    setMessages([])
    setCurrentConversationId(null)
    setSelectedDoc(null)
  }

  const handleDeleteConversation = async (convId) => {
    setMenuOpen(null)
    try {
      await axios.delete(`${API_URL}/chat/messages?conversation_id=${convId}`)
      
      // If deleting current conversation, clear it
      if (convId === currentConversationId) {
        setMessages([])
        setCurrentConversationId(null)
      }
      
      await fetchConversations()
    } catch (err) {
      console.error('Failed to delete conversation:', err)
    }
  }

  const handleRenameStart = (conv) => {
    setMenuOpen(null)
    setRenameId(conv.id)
    setRenameValue(conv.title || 'New Chat')
  }

  const handleRenameSubmit = async (convId) => {
    if (!renameValue.trim()) return
    try {
      await axios.put(`${API_URL}/chat/conversations/${convId}`, { title: renameValue.trim() })
      await fetchConversations()
    } catch (err) {
      console.error('Failed to rename conversation:', err)
    }
    setRenameId(null)
    setRenameValue('')
  }

  const handleRenameCancel = () => {
    setRenameId(null)
    setRenameValue('')
  }

  const toggleMenu = (convId, e) => {
    e.stopPropagation()
    if (menuOpen === convId) {
      setMenuOpen(null)
    } else {
      const rect = e.currentTarget.getBoundingClientRect()
      setMenuPos({ top: rect.bottom + 4, left: rect.right - 140 })
      setMenuOpen(convId)
    }
    setDocMenuOpen(null)
  }

  const toggleDocMenu = (docId, e) => {
    e.stopPropagation()
    if (docMenuOpen === docId) {
      setDocMenuOpen(null)
    } else {
      const rect = e.currentTarget.getBoundingClientRect()
      setDocMenuPos({ top: rect.bottom + 4, left: rect.right - 120 })
      setDocMenuOpen(docId)
    }
    setMenuOpen(null)
  }

  // Close menus when clicking outside
  useEffect(() => {
    const handleClickOutside = () => {
      setMenuOpen(null)
      setDocMenuOpen(null)
    }
    if (menuOpen || docMenuOpen) {
      document.addEventListener('click', handleClickOutside)
      return () => document.removeEventListener('click', handleClickOutside)
    }
  }, [menuOpen, docMenuOpen])

  const handleFileUpload = async (e) => {
    const files = e.target.files
    if (!files || files.length === 0) return

    setUploading(true)
    setUploadStatus('Uploading...')
    
    let successCount = 0
    let lastError = ''

    for (const file of Array.from(files)) {
      try {
        setUploadStatus(`Processing ${file.name}...`)
        
        const formData = new FormData()
        formData.append('file', file)
        
        const response = await axios.post(`${API_URL}/upload`, formData)
        
        if (response.data.success) {
          successCount++
        }
      } catch (err) {
        console.error(`Failed to upload ${file.name}:`, err)
        lastError = err.response?.data?.detail || err.message || 'Unknown error'
      }
    }
    
    if (fileInputRef.current) {
      fileInputRef.current.value = ''
    }
    
    await fetchDocuments()
    setUploading(false)
    
    if (successCount > 0) {
      setUploadStatus(`${successCount} file(s) uploaded!`)
    } else {
      setUploadStatus(`Error: ${lastError}`)
    }
    
    setTimeout(() => setUploadStatus(''), 5000)
  }

  const handleDeleteDoc = async (docId) => {
    setDocMenuOpen(null)
    try {
      await axios.delete(`${API_URL}/documents/${docId}`)
      if (selectedDoc === docId) {
        setSelectedDoc(null)
      }
      await fetchDocuments()
    } catch (err) {
      console.error('Failed to delete document:', err)
    }
  }

  const handleClearAll = async () => {
    if (!confirm('This will delete all documents, embeddings, and chat history. Continue?')) {
      return
    }
    
    try {
      setUploadStatus('Clearing all data...')
      await axios.delete(`${API_URL}/clear-all`)
      setDocuments([])
      setMessages([])
      setConversations([])
      setCurrentConversationId(null)
      setSelectedDoc(null)
      setUploadStatus('All data cleared!')
      setTimeout(() => setUploadStatus(''), 3000)
    } catch (err) {
      console.error('Failed to clear data:', err)
      setUploadStatus('Error clearing data')
      setTimeout(() => setUploadStatus(''), 3000)
    }
  }

  const handleSelectDoc = (docId) => {
    setSelectedDoc(selectedDoc === docId ? null : docId)
  }

  const handleCopyMessage = async (content, idx) => {
    try {
      await navigator.clipboard.writeText(content)
      setCopiedIdx(idx)
      setTimeout(() => setCopiedIdx(null), 2000)
    } catch (err) {
      console.error('Failed to copy:', err)
    }
  }

  const handleEditMessage = (idx, content) => {
    setEditingMsgIdx(idx)
    setEditingMsgValue(content)
  }

  const handleEditSubmit = async () => {
    if (!editingMsgValue.trim() || editingMsgIdx === null) return
    
    // Remove messages from the edited one onwards
    const newMessages = messages.slice(0, editingMsgIdx)
    setMessages(newMessages)
    
    // Set input to the edited value and send
    setInput(editingMsgValue.trim())
    setEditingMsgIdx(null)
    setEditingMsgValue('')
  }

  const handleEditCancel = () => {
    setEditingMsgIdx(null)
    setEditingMsgValue('')
  }

  const getSelectedDocName = () => {
    if (!selectedDoc) return null
    const doc = documents.find(d => d.id === selectedDoc)
    return doc ? doc.name : null
  }

  // Get chat title from first user message
  const getChatTitle = (conv) => {
    if (conv.title && conv.title !== 'New Chat') {
      return conv.title.length > 30 ? conv.title.substring(0, 30) + '...' : conv.title
    }
    return 'New Chat'
  }

  return (
    <div className="app">
      {/* Sidebar */}
      <aside className={`sidebar ${sidebarOpen ? '' : 'collapsed'}`}>
        <div className="sidebar-header">
          <span className="sidebar-title">📄 Document Q&A</span>
          <button 
            className="sidebar-toggle"
            onClick={() => setSidebarOpen(false)}
            title="Close sidebar"
          >
            <PanelLeftClose size={18} />
          </button>
        </div>

        <button className="new-chat-btn" onClick={handleNewChat}>
          <Plus size={18} />
          <span>New chat</span>
        </button>

        {/* Your Chats Section */}
        <div className="sidebar-section">
          <div 
            className="sidebar-section-title clickable"
            onClick={() => setChatsExpanded(!chatsExpanded)}
          >
            <span className="section-toggle">
              {chatsExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
            </span>
            Your Chats ({conversations.length})
          </div>
          {chatsExpanded && (
            <div className="chat-list">
              {conversations.length === 0 ? (
                <div className="no-chats">No conversations yet</div>
              ) : (
                conversations.map(conv => (
                  <div 
                    key={conv.id} 
                    className={`chat-item ${currentConversationId === conv.id ? 'active' : ''}`}
                    onClick={() => loadConversation(conv.id)}
                  >
                    <span className="chat-item-icon">
                      <MessageSquare size={14} />
                    </span>
                    {renameId === conv.id ? (
                      <input
                        className="chat-rename-input"
                        value={renameValue}
                        onChange={(e) => setRenameValue(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter') handleRenameSubmit(conv.id)
                          if (e.key === 'Escape') handleRenameCancel()
                        }}
                        onBlur={() => handleRenameSubmit(conv.id)}
                        onClick={(e) => e.stopPropagation()}
                        autoFocus
                      />
                    ) : (
                      <span className="chat-item-title">{getChatTitle(conv)}</span>
                    )}
                    <div className="chat-item-menu-container">
                      <button 
                        className="chat-item-menu-btn" 
                        onClick={(e) => toggleMenu(conv.id, e)}
                        title="Options"
                      >
                        <MoreHorizontal size={16} />
                      </button>
                      {menuOpen === conv.id && (
                        <div 
                          className="chat-item-dropdown" 
                          style={{ top: menuPos.top, left: menuPos.left }}
                          onClick={(e) => e.stopPropagation()}
                        >
                          <button onClick={() => handleRenameStart(conv)}>
                            <Pencil size={14} />
                            <span>Rename</span>
                          </button>
                          <button onClick={() => handleDeleteConversation(conv.id)} className="danger">
                            <Trash2 size={14} />
                            <span>Delete</span>
                          </button>
                        </div>
                      )}
                    </div>
                  </div>
                ))
              )}
            </div>
          )}
        </div>

        {/* Spacer to push documents to bottom */}
        <div className="sidebar-spacer"></div>

        {/* Documents Section - at bottom */}
        <div className="sidebar-section sidebar-section-bottom">
          <div 
            className="sidebar-section-title clickable"
            onClick={() => setDocsExpanded(!docsExpanded)}
          >
            <span className="section-toggle">
              {docsExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
            </span>
            Documents ({documents.length})
            {selectedDoc && <span className="filter-hint"> • Filtered</span>}
          </div>
          {docsExpanded && (
            <>
              <div className="doc-list">
                {documents.length === 0 ? (
                  <div className="no-docs">No documents uploaded</div>
                ) : (
                  <>
                    <div 
                      className={`doc-item ${selectedDoc === null ? 'selected' : ''}`}
                      onClick={() => setSelectedDoc(null)}
                    >
                      <span className="doc-name">
                        <FileText size={14} />
                        <span className="doc-name-text">All Documents</span>
                      </span>
                    </div>
                    
                    {documents.map(doc => (
                      <div 
                        key={doc.id} 
                        className={`doc-item ${selectedDoc === doc.id ? 'selected' : ''}`}
                        onClick={() => handleSelectDoc(doc.id)}
                      >
                        <span className="doc-name">
                          <FileText size={14} />
                          <span className="doc-name-text">{doc.name}</span>
                        </span>
                        <div className="doc-menu-container">
                          <button 
                            className="doc-menu-btn" 
                            onClick={(e) => toggleDocMenu(doc.id, e)}
                            title="Options"
                          >
                            <MoreHorizontal size={16} />
                          </button>
                          {docMenuOpen === doc.id && (
                            <div 
                              className="doc-dropdown" 
                              style={{ top: docMenuPos.top, left: docMenuPos.left }}
                              onClick={(e) => e.stopPropagation()}
                            >
                              <button onClick={() => handleDeleteDoc(doc.id)} className="danger">
                                <Trash2 size={14} />
                                <span>Delete</span>
                              </button>
                            </div>
                          )}
                        </div>
                      </div>
                    ))}
                  </>
                )}
              </div>
              
              {documents.length > 0 && (
                <button className="clear-all-btn" onClick={handleClearAll}>
                  <Eraser size={14} />
                  <span>Clear All Data</span>
                </button>
              )}
            </>
          )}
        </div>
      </aside>

      {/* Main Content */}
      <main className="main-content">
        <header className="header">
          {!sidebarOpen && (
            <button 
              className="sidebar-open-btn"
              onClick={() => setSidebarOpen(true)}
              title="Open sidebar"
            >
              <PanelLeft size={20} />
            </button>
          )}
          
          {selectedDoc && (
            <div className="active-filter">
              <span>Searching in: <strong>{getSelectedDocName()}</strong></span>
              <button onClick={() => setSelectedDoc(null)} title="Clear filter">
                <X size={14} />
              </button>
            </div>
          )}
          
          <span className="header-title"></span>
          
          {uploadStatus && (
            <span className="upload-status">{uploadStatus}</span>
          )}
          
          <label className="upload-btn" style={{ cursor: uploading ? 'not-allowed' : 'pointer' }}>
            <Upload size={18} />
            {uploading ? 'Uploading...' : 'Upload'}
            <input
              ref={fileInputRef}
              type="file"
              multiple
              accept=".pdf,.docx,.doc,.txt,.md"
              onChange={handleFileUpload}
              disabled={uploading}
              style={{ display: 'none' }}
            />
          </label>
        </header>

        <div className={`chat-area ${messages.length === 0 ? 'centered' : ''}`} ref={chatRef}>
          {messages.length === 0 ? (
            <div className="welcome">
              <h1>What can I help with?</h1>
              <p>
                {documents.length > 0 
                  ? selectedDoc 
                    ? `Ask questions about "${getSelectedDocName()}"`
                    : 'Ask questions about your uploaded documents'
                  : 'Upload documents to get started'
                }
              </p>
              
              <div className="centered-input">
                <div className="input-wrapper">
                  <label className="attach-btn" title="Upload document">
                    <Paperclip size={18} />
                    <input
                      ref={chatFileInputRef}
                      type="file"
                      multiple
                      accept=".pdf,.docx,.doc,.txt,.md"
                      onChange={handleFileUpload}
                      disabled={uploading}
                      style={{ display: 'none' }}
                    />
                  </label>
                  <textarea
                    ref={inputRef}
                    className="chat-input"
                    placeholder={
                      documents.length === 0 
                        ? "Upload documents to start asking questions"
                        : selectedDoc 
                          ? `Ask about ${getSelectedDocName()}...`
                          : "Ask anything about your documents..."
                    }
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    onKeyDown={handleKeyDown}
                    rows={1}
                  />
                  <button 
                    className="send-btn" 
                    onClick={handleSend}
                    disabled={!input.trim() || loading || documents.length === 0}
                  >
                    <Send size={16} />
                  </button>
                </div>
              </div>
              
              {documents.length > 0 && !selectedDoc && (
                <p className="welcome-hint">💡 Tip: Click a document in the sidebar to filter your search</p>
              )}
            </div>
          ) : (
            <div className="messages">
              {messages.map((msg, idx) => (
                <div key={idx} className={`message ${msg.role}`}>
                  {msg.role === 'assistant' && (
                    <div className={`message-avatar ${msg.role}`}>
                      <Bot size={16} />
                    </div>
                  )}
                  <div className="message-content-wrapper">
                    <div className="message-content">
                      {editingMsgIdx === idx && msg.role === 'user' ? (
                        <div className="edit-message-form">
                          <textarea
                            className="edit-message-input"
                            value={editingMsgValue}
                            onChange={(e) => setEditingMsgValue(e.target.value)}
                            autoFocus
                          />
                          <div className="edit-message-actions">
                            <button className="edit-cancel-btn" onClick={handleEditCancel}>
                              Cancel
                            </button>
                            <button className="edit-submit-btn" onClick={handleEditSubmit}>
                              Send
                            </button>
                          </div>
                        </div>
                      ) : msg.role === 'assistant' ? (
                        <ReactMarkdown>{msg.content}</ReactMarkdown>
                      ) : (
                        <p>{msg.content}</p>
                      )}
                      {msg.citations && msg.citations.length > 0 && (
                        <div className="citations">
                          {msg.citations.map((c, i) => (
                            <span key={i} className="citation">
                              📄 {c.document_name} • Lines {c.start_line}-{c.end_line}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>
                    {editingMsgIdx !== idx && (
                      <div className="message-actions">
                        <button 
                          className="msg-action-btn"
                          onClick={() => handleCopyMessage(msg.content, idx)}
                          title="Copy"
                        >
                          {copiedIdx === idx ? <Check size={14} /> : <Copy size={14} />}
                        </button>
                        {msg.role === 'user' && (
                          <button 
                            className="msg-action-btn"
                            onClick={() => handleEditMessage(idx, msg.content)}
                            title="Edit"
                          >
                            <Pencil size={14} />
                          </button>
                        )}
                      </div>
                    )}
                  </div>
                  {msg.role === 'user' && (
                    <div className={`message-avatar ${msg.role}`}>
                      <User size={16} />
                    </div>
                  )}
                </div>
              ))}
              {loading && (
                <div className="message assistant">
                  <div className="message-avatar assistant">
                    <Bot size={16} />
                  </div>
                  <div className="message-content">
                    <div className="loading">
                      <div className="loading-dots">
                        <span></span>
                        <span></span>
                        <span></span>
                      </div>
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>

        {messages.length > 0 && (
          <div className="input-area">
            <div className="input-container">
              <div className="input-wrapper">
                <label className="attach-btn" title="Upload document">
                  <Paperclip size={18} />
                  <input
                    type="file"
                    multiple
                    accept=".pdf,.docx,.doc,.txt,.md"
                    onChange={handleFileUpload}
                    disabled={uploading}
                    style={{ display: 'none' }}
                  />
                </label>
                <textarea
                  className="chat-input"
                  placeholder={
                    documents.length === 0 
                      ? "Upload documents to start asking questions"
                      : selectedDoc 
                        ? `Ask about ${getSelectedDocName()}...`
                        : "Ask anything about your documents..."
                  }
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={handleKeyDown}
                  rows={1}
                />
                <button 
                  className="send-btn" 
                  onClick={handleSend}
                  disabled={!input.trim() || loading || documents.length === 0}
                >
                  <Send size={16} />
                </button>
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  )
}
