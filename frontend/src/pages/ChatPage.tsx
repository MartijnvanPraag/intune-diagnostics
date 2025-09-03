import React, { useState, useEffect } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { diagnosticsService, ChatResponse, ChatSessionSummary } from '@/services/diagnosticsService'
import { useAuth } from '@/contexts/AuthContext'

interface ChatMessage {
  role: 'user' | 'agent'
  content: string
  tables?: ChatResponse['tables']
  state?: Record<string, any>
  clarification?: ChatResponse['candidates']
  neededSlots?: string[]
}

const ChatPage: React.FC = () => {
  const { user } = useAuth()
  const location = useLocation()
  const navigate = useNavigate()
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [sessionId, setSessionId] = useState<string | undefined>(undefined)
  const [sessions, setSessions] = useState<ChatSessionSummary[]>([])
  const [strictMode, setStrictMode] = useState<boolean>(() => {
    try { return localStorage.getItem('chat.strictMode') === 'true' } catch { return false }
  })

  const loadSessions = async () => {
    if (!user) return
  // could add loading indicator later
    try {
      const s = await diagnosticsService.listChatSessions(user.id)
      setSessions(s)
      // Prune any local metadata entries that no longer exist server-side
      try {
        const metaKey = 'chat.sessionMeta'
        const raw = localStorage.getItem(metaKey)
        if (raw) {
          const existing: any[] = JSON.parse(raw)
          const validIds = new Set(s.map(ss => ss.session_id))
            const filtered = existing.filter(m => validIds.has(m.session_id))
            if (filtered.length !== existing.length) {
              localStorage.setItem(metaKey, JSON.stringify(filtered))
            }
        }
      } catch { /* ignore */ }
  } catch {/* ignore */} finally { /* no-op */ }
  }

  useEffect(() => { loadSessions() }, [user?.id])

  // Resume specific session via ?session= id
  useEffect(() => {
    if (!user) return
    const params = new URLSearchParams(location.search)
    const target = params.get('session')
    if (target) {
      ;(async () => {
        try {
          const msgs = await diagnosticsService.listChatMessages(target, user.id)
          const restored: ChatMessage[] = msgs.map(m => ({ role: m.role === 'agent' ? 'agent':'user', content: m.content, state: m.state_after, tables: m.tables }))
          setSessionId(target)
          setMessages(restored)
        } catch {/* ignore */}
      })()
      // Clean URL
      navigate('/chat', { replace: true })
    }
  }, [location.search, user?.id])

  // Persist lightweight session metadata locally for dashboard recent list
  useEffect(() => {
    if (!sessionId || messages.length === 0) return
    try {
      const metaKey = 'chat.sessionMeta'
      const existingRaw = localStorage.getItem(metaKey)
      let existing: any[] = existingRaw ? JSON.parse(existingRaw) : []
      const title = messages.find(m=>m.role==='user')?.content?.slice(0,60) || 'Chat Session'
      const updated = new Date().toISOString()
      existing = existing.filter(m => m.session_id !== sessionId)
      existing.unshift({ session_id: sessionId, title, updated, message_count: messages.length })
      // Cap stored sessions to 20
      if (existing.length > 20) existing = existing.slice(0,20)
      localStorage.setItem(metaKey, JSON.stringify(existing))
    } catch {/* ignore */}
  }, [messages, sessionId])

  const sendMessage = async () => {
    if (!input.trim() || !user) return
    setError(null)
    const userMsg: ChatMessage = { role: 'user', content: input }
    setMessages(prev => [...prev, userMsg])
    const toSend = input
    setInput('')
    setLoading(true)
    try {
      const resp = await diagnosticsService.chat({ message: toSend, session_id: sessionId, strict: strictMode }, user.id)
      const agentMsg: ChatMessage = { 
        role: 'agent', 
        content: resp.response, 
        tables: resp.tables, 
        state: resp.state,
        clarification: resp.clarification_needed ? resp.candidates : undefined,
        neededSlots: resp.data?.needed_slots || resp.data?.neededSlots
      }
      setMessages(prev => [...prev, agentMsg])
  if (!sessionId && resp.session_id) setSessionId(resp.session_id)
  if (resp.session_id) loadSessions()
    } catch (e: any) {
      setError(e?.response?.data?.detail || e.message || 'Request failed')
      setMessages(prev => prev.filter(m => m !== userMsg)) // rollback user message if failed
    } finally {
      setLoading(false)
    }
  }

  const handleKey = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      sendMessage()
    }
  }

  return (
    <div className="p-6 h-full flex flex-col">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-xl font-semibold text-win11-text-primary flex items-center gap-2">Agent Chat {strictMode && <span className="text-[10px] px-2 py-1 rounded-full bg-amber-500/20 text-amber-700 border border-amber-600/40">STRICT</span>}</h2>
        <div className="flex gap-2">
          <label className="flex items-center gap-1 text-xs cursor-pointer select-none px-2 py-1 rounded-win11-small border border-win11-border bg-win11-surface hover:bg-win11-surfaceHover">
            <input
              type="checkbox"
              checked={strictMode}
              onChange={e => { setStrictMode(e.target.checked); try { localStorage.setItem('chat.strictMode', String(e.target.checked)) } catch {} }}
              className="accent-win11-accent"
            />
            Strict
          </label>
          <button
            onClick={() => { setSessionId(undefined); setMessages([]) }}
            className="px-3 py-1 rounded-win11-small text-sm border border-win11-border bg-win11-surface hover:bg-win11-surfaceHover"
          >New Session</button>
          <button
            onClick={loadSessions}
            className="px-3 py-1 rounded-win11-small text-sm border border-win11-border bg-win11-surface hover:bg-win11-surfaceHover"
          >Refresh Sessions</button>
        </div>
      </div>
      {sessions.length > 0 && (
        <div className="mb-4 flex items-center gap-2 flex-wrap text-xs">
          <span className="text-win11-text-tertiary">Sessions:</span>
          {sessions.slice(0,8).map(s => (
            <div key={s.session_id} className="flex items-center gap-1">
              <button onClick={async () => {
                setSessionId(s.session_id); setMessages([])
                try {
                  const msgs = await diagnosticsService.listChatMessages(s.session_id, user!.id)
                  const restored: ChatMessage[] = msgs.map(m => ({ role: m.role === 'agent' ? 'agent':'user', content: m.content, state: m.state_after, tables: m.tables }))
                  setMessages(restored)
                } catch {/* ignore */}
              }} className={`px-2 py-1 rounded-win11-small border text-ellipsis overflow-hidden max-w-[120px] ${sessionId===s.session_id?'bg-win11-primary text-white border-transparent':'bg-win11-surface border-win11-border hover:bg-win11-surfaceHover'}`}>{s.session_id.slice(0,8)}…</button>
              <button onClick={async () => {
                if (!confirm('Delete this session?')) return
                try { 
                  await diagnosticsService.deleteChatSession(s.session_id, user!.id)
                  if (sessionId===s.session_id){ setSessionId(undefined); setMessages([])}
                  // Remove from localStorage meta immediately so dashboard is in sync
                  try {
                    const metaKey = 'chat.sessionMeta'
                    const raw = localStorage.getItem(metaKey)
                    if (raw) {
                      const arr = JSON.parse(raw).filter((m: any) => m.session_id !== s.session_id)
                      localStorage.setItem(metaKey, JSON.stringify(arr))
                    }
                  } catch { /* ignore */ }
                  loadSessions() 
                } catch {/* ignore */}
              }} className="px-1 py-1 rounded-win11-small border border-red-300 text-[10px] text-red-600 hover:bg-red-50">✕</button>
            </div>
          ))}
          {sessions.length > 8 && <span className="text-win11-text-tertiary">(+{sessions.length-8} more)</span>}
        </div>
      )}
      <div className="flex-1 overflow-y-auto space-y-4 pr-2">
        {messages.map((m, idx) => (
          <div key={idx} className={`p-4 rounded-win11-small shadow-win11-small border text-sm ${m.role === 'user' ? 'bg-win11-primary text-white border-transparent ml-auto max-w-[80%]' : 'bg-win11-card border-win11-border mr-auto max-w-[85%]'}`}> 
            <div className="whitespace-pre-wrap">{m.content}</div>
            {m.tables && m.tables.length > 0 && (
              <div className="mt-3 space-y-4">
                {m.tables.map((t, ti) => (
                  <div key={ti} className="overflow-x-auto border border-win11-border rounded">
                    <table className="min-w-full text-xs">
                      <thead className="bg-win11-surface">
                        <tr>
                          {t.columns.map(c => <th key={c} className="text-left px-2 py-1 font-medium border-b border-win11-border">{c}</th>)}
                        </tr>
                      </thead>
                      <tbody>
                        {t.rows.slice(0, 25).map((r, ri) => (
                          <tr key={ri} className="odd:bg-win11-surfaceHover/40">
                            {r.map((cell: any, ci: number) => <td key={ci} className="px-2 py-1 align-top border-b border-win11-border/50">{String(cell)}</td>)}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                    {t.rows.length > 25 && <div className="text-xs text-win11-text-tertiary px-2 py-1">Showing first 25 / {t.rows.length} rows</div>}
                  </div>
                ))}
              </div>
            )}
            {m.state && m.role === 'agent' && (
              <div className="mt-3 text-[10px] text-win11-text-tertiary">
                State: {Object.entries(m.state).filter(([_, v]) => v).map(([key, val]) => `${key}=${val}`).join(' | ')}
              </div>
            )}
            {m.clarification && m.clarification.length > 0 && (
              <div className="mt-3">
                <div className="text-xs font-medium mb-2 text-win11-text-secondary">Clarify which GUID maps to which slot:</div>
                <div className="flex flex-wrap gap-2">
                  {m.clarification.map(c => (
                    <button
                      key={c.guid}
                      onClick={() => handleClarificationSelection(c.guid, m.neededSlots || [])}
                      className="px-2 py-1 text-xs rounded-win11-small border border-win11-border bg-win11-surface hover:bg-win11-surfaceHover transition"
                      title={c.window}
                    >
                      {c.guid.slice(0,8)}… scores: {Object.entries(c.scores).map(([r,s])=>`${r}:${s}`).join(',')}
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>
        ))}
      </div>

      {error && <div className="text-sm text-red-600 mb-2">{error}</div>}

      <div className="border border-win11-border rounded-win11-small p-3 bg-win11-card shadow-win11 flex flex-col gap-2">
        <textarea
          value={input}
            onChange={e => setInput(e.target.value)}
          onKeyDown={handleKey}
          placeholder={loading ? 'Waiting for agent response...' : 'Type a message (Enter to send, Shift+Enter for newline)'}
          disabled={loading}
          className="w-full resize-none h-24 rounded-win11-small px-3 py-2 bg-win11-surface focus:outline-none focus:ring-2 focus:ring-win11-accent/60 disabled:opacity-60"
        />
        <div className="flex justify-between items-center">
          <div className="text-xs text-win11-text-tertiary">Press Enter to send</div>
          <button
            disabled={loading || !input.trim()}
            onClick={sendMessage}
            className="px-4 py-2 rounded-win11-small bg-win11-primary text-white text-sm font-medium disabled:opacity-50 disabled:cursor-not-allowed hover:bg-win11-primary/90 transition"
          >
            {loading ? 'Sending...' : 'Send'}
          </button>
        </div>
      </div>
    </div>
  )
}

// Clarification handler outside component previously; define inside
const handleClarificationSelection = (guid: string, needed: string[]) => {
  // This will be replaced by improved UX: open a small selector mapping slot->guid.
  // For now, naive: if only one slot needed set message prefill.
  if (needed.length === 1) {
    // Append structured hint
    const slot = needed[0]
    const textarea = document.querySelector('textarea') as HTMLTextAreaElement | null
    if (textarea) {
      textarea.value = `${slot}: ${guid}`
      textarea.focus()
    }
  } else {
    alert('Multiple slots need clarification; manual entry required: ' + needed.join(', '))
  }
}

export default ChatPage
