import axios, { AxiosError } from 'axios'

// Allow override via VITE_API_BASE_URL; fallback to relative /api for proxy, else direct http://localhost:8000/api
const API_BASE_URL = (import.meta as any).env?.VITE_API_BASE_URL || '/api'

const client = axios.create({
  baseURL: API_BASE_URL,
  headers: { 'X-Requested-With': 'XMLHttpRequest' }
})

export interface DiagnosticRequest {
  device_id?: string
  query_type: string
  parameters?: Record<string, any>
}

export interface TableData {
  columns: string[]
  rows: any[][]
  total_rows: number
}

export interface AgentResponse {
  response: string
  table_data?: TableData
  tables?: TableData[]
  session_id: string
}

export interface DiagnosticResponse {
  session_id: string
  device_id?: string
  query_type: string
  results?: Record<string, any>
  status: string
  error_message?: string
  created_at: string
}

export interface QueryType {
  id: string
  name: string
  description: string
  required_params: string[]
  scenario_type?: 'simple' | 'advanced'
}

export interface ChatRequest {
  message: string
  parameters?: Record<string, any>
  session_id?: string
  strict?: boolean
}

export interface ChatResponse {
  response: string
  data?: any
  state?: Record<string, any>
  tables?: Array<{ columns: string[]; rows: any[][]; total_rows?: number }>
  clarification_needed?: boolean
  candidates?: Array<{ guid: string; window: string; scores: Record<string, number> }>
  session_id?: string
  user_message_id?: number
  agent_message_id?: number
}

export interface ChatSessionSummary {
  session_id: string
  created_at?: string
  updated_at?: string
  state_snapshot?: Record<string, any>
}

export interface ChatMessageRecord {
  id: number
  role: string
  content: string
  params?: Record<string, any>
  // Backend returns list[dict] for agent messages (each with columns, rows, total_rows)
  tables?: Array<{ columns: string[]; rows: any[][]; total_rows?: number }>
  intent?: string
  clarification_needed: boolean
  created_at?: string
  state_after?: Record<string, any>
}

class DiagnosticsService {
  async executeQuery(request: DiagnosticRequest, userId: number): Promise<AgentResponse> {
  const response = await client.post(`/diagnostics/query`, request, {
      params: { user_id: userId }
    })
    return response.data
  }

  async getQueryTypes(): Promise<{ query_types: QueryType[] }> {
  const response = await client.get(`/diagnostics/query-types`)
    return response.data
  }

  async getDiagnosticSessions(userId: number): Promise<DiagnosticResponse[]> {
  const response = await client.get(`/diagnostics/sessions`, {
      params: { user_id: userId }
    })
    return response.data
  }

  async getDiagnosticSession(sessionId: string): Promise<DiagnosticResponse> {
    const response = await client.get(`/diagnostics/sessions/${sessionId}`)
    return response.data
  }

  async deleteSession(sessionId: string, userId: number): Promise<{ message: string }> {
    try {
      const response = await client.delete(`/diagnostics/sessions/${sessionId}`, {
        params: { user_id: userId }
      })
      return response.data
    } catch (err) {
      const e = err as AxiosError<any>
      if (e.response?.status === 405) {
        // Fallback to POST delete endpoint
        const response = await client.post(`/diagnostics/sessions/${sessionId}/delete`, null, {
          params: { user_id: userId }
        })
        return response.data
      }
      throw err
    }
  }

  async deleteAllSessions(userId: number): Promise<{ message: string }> {
    const response = await client.delete(`/diagnostics/sessions`, {
      params: { user_id: userId }
    })
    return response.data
  }

  async deleteBulkSessions(sessionIds: string[], userId: number): Promise<{ message: string }> {
    const response = await client.post(`/diagnostics/sessions/bulk-delete`, {
      session_ids: sessionIds
    }, {
      params: { user_id: userId }
    })
    return response.data
  }

  async chat(request: ChatRequest, userId: number): Promise<ChatResponse> {
    const response = await client.post(`/diagnostics/chat`, request, {
      params: { user_id: userId }
    })
    return response.data
  }

  async listChatSessions(userId: number): Promise<ChatSessionSummary[]> {
    const response = await client.get(`/diagnostics/chat/sessions`, { params: { user_id: userId } })
    return response.data
  }

  async listChatMessages(sessionId: string, userId: number): Promise<ChatMessageRecord[]> {
    const response = await client.get(`/diagnostics/chat/sessions/${sessionId}/messages`, { params: { user_id: userId } })
    return response.data
  }

  async deleteChatSession(sessionId: string, userId: number): Promise<{ message: string }> {
    const response = await client.delete(`/diagnostics/chat/sessions/${sessionId}`, { params: { user_id: userId } })
    return response.data
  }
}

export const diagnosticsService = new DiagnosticsService()