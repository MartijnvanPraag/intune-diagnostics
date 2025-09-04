import React, { useEffect, useState } from 'react'
import { useAuth } from '@/contexts/AuthContext'
import { useNavigate } from 'react-router-dom'

interface LocalChatSessionMeta {
  session_id: string
  title: string
  updated: string
  message_count: number
}

const DashboardPage: React.FC = () => {
  const { user } = useAuth()
  const navigate = useNavigate()
  const [recentChats, setRecentChats] = useState<LocalChatSessionMeta[]>([])

  // Load recent chat sessions from localStorage (populated by ChatPage modifications later)
  useEffect(() => {
    try {
      const raw = localStorage.getItem('chat.sessionMeta')
      if (raw) {
        const parsed: LocalChatSessionMeta[] = JSON.parse(raw)
        // Sort by updated desc and take first 5
        setRecentChats(parsed.sort((a,b)=> new Date(b.updated).getTime() - new Date(a.updated).getTime()).slice(0,5))
      }
    } catch {/* ignore */}
  }, [])

  const launchQuick = (id: string) => {
    navigate(`/scenarios?quick=${encodeURIComponent(id)}`)
  }

  const openChatSession = (session_id: string) => {
    navigate(`/chat?session=${encodeURIComponent(session_id)}`)
  }

  return (
    <div className="animate-fade-in">
      <div className="mb-6">
        <h1 className="text-3xl font-semibold text-win11-text-primary mb-2">
          Welcome, {user?.display_name}
        </h1>
        <p className="text-win11-text-secondary">
          Intune Diagnostics Portal - Powered by Agentic AI
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        <div className="win11-card p-6">
          <h3 className="text-lg font-medium text-win11-text-primary mb-2">
            Quick Actions
          </h3>
          <p className="text-win11-text-secondary text-sm mb-4">
            Common diagnostic operations
          </p>
          <div className="space-y-2">
            <button className="win11-button-secondary w-full text-sm" onClick={()=>launchQuick('device_details')}>
              Device Lookup
            </button>
            <button className="win11-button-secondary w-full text-sm" onClick={()=>launchQuick('compliance')}>
              Compliance Check
            </button>
          </div>
        </div>

        <div className="win11-card p-6">
          <h3 className="text-lg font-medium text-win11-text-primary mb-2">
            Recent Sessions
          </h3>
          <p className="text-win11-text-secondary text-sm mb-4">
            Your latest diagnostic queries
          </p>
          {recentChats.length === 0 ? (
            <div className="text-win11-text-tertiary text-sm">No recent sessions</div>
          ) : (
            <ul className="space-y-2 text-sm">
              {recentChats.map(rc => (
                <li key={rc.session_id} className="flex items-center justify-between">
                  <button
                    onClick={()=>openChatSession(rc.session_id)}
                    className="text-left flex-1 truncate hover:underline"
                    title={rc.title}
                  >{rc.title || rc.session_id.slice(0,8)}</button>
                  <span className="ml-2 text-[10px] text-win11-text-tertiary whitespace-nowrap">
                    {new Date(rc.updated).toLocaleTimeString([], {hour:'2-digit', minute:'2-digit'})}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="win11-card p-6">
          <h3 className="text-lg font-medium text-win11-text-primary mb-2">
            AI Agent Status
          </h3>
          <p className="text-win11-text-secondary text-sm mb-4">
            IntuneExpert agent availability
          </p>
          <div className="flex items-center space-x-2">
            <div className="w-2 h-2 bg-green-500 rounded-full"></div>
            <span className="text-sm text-win11-text-secondary">Ready</span>
          </div>
        </div>
      </div>
    </div>
  )
}

export default DashboardPage