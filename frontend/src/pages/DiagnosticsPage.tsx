import React, { useState, useEffect } from 'react'
import { useAuth } from '@/contexts/AuthContext'
import { diagnosticsService, QueryType, DiagnosticRequest, AgentResponse, DiagnosticResponse } from '@/services/diagnosticsService'
import DataTable from '@/components/DataTable'
import { useForm } from 'react-hook-form'
import { MagnifyingGlassIcon, ClockIcon, ExclamationTriangleIcon, TrashIcon, XMarkIcon } from '@heroicons/react/24/outline'
import toast from 'react-hot-toast'

const DiagnosticsPage: React.FC = () => {
  const { user } = useAuth()
  const [queryTypes, setQueryTypes] = useState<QueryType[]>([])
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<AgentResponse | null>(null)
  const [recentSessions, setRecentSessions] = useState<DiagnosticResponse[]>([])
  const [selectedQueryType, setSelectedQueryType] = useState<QueryType | null>(null)
  const [selectedSessions, setSelectedSessions] = useState<Set<string>>(new Set())
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false)

  const { register, handleSubmit, watch, reset, formState: { errors } } = useForm<{
    query_type: string
    device_id?: string
    account_id?: string
    context_id?: string
    policy_id?: string
    effective_group_id?: string
  }>()

  const watchedQueryType = watch('query_type')

  useEffect(() => {
    loadQueryTypes()
    if (user) {
      loadRecentSessions()
    }
  }, [user])

  useEffect(() => {
    if (watchedQueryType) {
      const selected = queryTypes.find(qt => qt.id === watchedQueryType)
      setSelectedQueryType(selected || null)
    }
  }, [watchedQueryType, queryTypes])

  const loadQueryTypes = async () => {
    try {
      const response = await diagnosticsService.getQueryTypes()
      setQueryTypes(response.query_types)
    } catch (error) {
      console.error('Failed to load query types:', error)
      toast.error('Failed to load available query types')
    }
  }

  const loadRecentSessions = async () => {
    try {
      const sessions = await diagnosticsService.getDiagnosticSessions(user!.id)
      setRecentSessions(sessions.slice(0, 5)) // Show last 5 sessions
    } catch (error) {
      console.error('Failed to load recent sessions:', error)
    }
  }

  const onSubmit = async (data: any) => {
    if (!selectedQueryType) return

    try {
      setLoading(true)
      setResult(null)

      // Build parameters based on query type requirements
      const parameters: Record<string, any> = {}
      selectedQueryType.required_params.forEach(param => {
        if (data[param]) {
          parameters[param.replace('_', '')] = data[param] // Remove underscores for backend
        }
      })

      const request: DiagnosticRequest = {
        query_type: data.query_type,
        device_id: data.device_id,
        parameters
      }

      const response = await diagnosticsService.executeQuery(request, user!.id)
      setResult(response)
      await loadRecentSessions()
      toast.success('Query executed successfully!')
    } catch (error) {
      console.error('Query failed:', error)
      toast.error(`Failed to execute diagnostic query: ${error.response?.data?.detail || error.message}`)
    } finally {
      setLoading(false)
    }
  }

  const handleNewQuery = () => {
    setResult(null)
    reset()
    setSelectedQueryType(null)
  }

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleString()
  }

  return (
    <div className="animate-fade-in">
      <div className="mb-6">
        <h1 className="text-3xl font-semibold text-win11-text-primary mb-2">
          Intune Diagnostics
        </h1>
        <p className="text-win11-text-secondary">
          Query Intune device information using AI-powered diagnostic tools
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Query Form */}
        <div className="lg:col-span-2">
          <div className="win11-card p-6">
            <div className="flex items-center justify-between mb-6">
              <h2 className="text-xl font-medium text-win11-text-primary">
                Diagnostic Query
              </h2>
              {result && (
                <button
                  onClick={handleNewQuery}
                  className="win11-button-secondary text-sm"
                >
                  New Query
                </button>
              )}
            </div>

            {!result ? (
              <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-win11-text-primary mb-2">
                    Query Type
                  </label>
                  <select
                    {...register('query_type', { required: 'Please select a query type' })}
                    className="win11-input w-full"
                  >
                    <option value="">Select a diagnostic query...</option>
                    {queryTypes.map(qt => (
                      <option key={qt.id} value={qt.id}>{qt.name}</option>
                    ))}
                  </select>
                  {errors.query_type && (
                    <p className="text-red-500 text-xs mt-1">{errors.query_type.message}</p>
                  )}
                </div>

                {selectedQueryType && (
                  <>
                    <div className="bg-win11-surface p-4 rounded-win11">
                      <h4 className="font-medium text-win11-text-primary mb-2">
                        {selectedQueryType.name}
                      </h4>
                      <p className="text-sm text-win11-text-secondary mb-3">
                        {selectedQueryType.description}
                      </p>
                      <div className="text-xs text-win11-text-tertiary">
                        <strong>Required parameters:</strong> {selectedQueryType.required_params.join(', ')}
                      </div>
                    </div>

                    {/* Dynamic form fields based on query type */}
                    {selectedQueryType.required_params.includes('device_id') && (
                      <div>
                        <label className="block text-sm font-medium text-win11-text-primary mb-2">
                          Device ID
                        </label>
                        <input
                          {...register('device_id', { required: 'Device ID is required' })}
                          className="win11-input w-full"
                          placeholder="e.g., 12345678-1234-1234-1234-123456789012"
                        />
                        {errors.device_id && (
                          <p className="text-red-500 text-xs mt-1">{errors.device_id.message}</p>
                        )}
                      </div>
                    )}

                    {selectedQueryType.required_params.includes('account_id') && (
                      <div>
                        <label className="block text-sm font-medium text-win11-text-primary mb-2">
                          Account ID
                        </label>
                        <input
                          {...register('account_id', { required: 'Account ID is required' })}
                          className="win11-input w-full"
                          placeholder="Account ID from device details"
                        />
                        {errors.account_id && (
                          <p className="text-red-500 text-xs mt-1">{errors.account_id.message}</p>
                        )}
                      </div>
                    )}

                    {selectedQueryType.required_params.includes('context_id') && (
                      <div>
                        <label className="block text-sm font-medium text-win11-text-primary mb-2">
                          Context ID
                        </label>
                        <input
                          {...register('context_id', { required: 'Context ID is required' })}
                          className="win11-input w-full"
                          placeholder="Context ID from tenant information"
                        />
                        {errors.context_id && (
                          <p className="text-red-500 text-xs mt-1">{errors.context_id.message}</p>
                        )}
                      </div>
                    )}

                    <button
                      type="submit"
                      disabled={loading}
                      className="win11-button w-full disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      {loading ? (
                        <span className="flex items-center justify-center space-x-2">
                          <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin"></div>
                          <span>Executing Query...</span>
                        </span>
                      ) : (
                        <span className="flex items-center justify-center space-x-2">
                          <MagnifyingGlassIcon className="w-4 h-4" />
                          <span>Execute Query</span>
                        </span>
                      )}
                    </button>
                  </>
                )}
              </form>
            ) : (
              <div className="space-y-6">
                {/* Query Results */}
                <div>
                  <h3 className="text-lg font-medium text-win11-text-primary mb-4">
                    Query Results
                  </h3>
                  
                  {result.table_data ? (
                    <DataTable data={result.table_data} />
                  ) : (
                    <div className="win11-card p-4">
                      <div className="flex items-center space-x-2 text-win11-text-tertiary">
                        <ExclamationTriangleIcon className="w-5 h-5" />
                        <span>No table data available</span>
                      </div>
                    </div>
                  )}
                </div>

                {/* AI Summary */}
                <div>
                  <h3 className="text-lg font-medium text-win11-text-primary mb-4">
                    AI Analysis Summary
                  </h3>
                  <div className="win11-card p-4">
                    <div className="prose prose-sm max-w-none">
                      <p className="text-win11-text-primary whitespace-pre-wrap">
                        {result.response}
                      </p>
                    </div>
                  </div>
                </div>

                <div className="text-xs text-win11-text-tertiary">
                  Session ID: {result.session_id}
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Recent Sessions Sidebar */}
        <div className="lg:col-span-1">
          <div className="win11-card p-6">
            <h3 className="text-lg font-medium text-win11-text-primary mb-4">
              Recent Sessions
            </h3>
            
            {recentSessions.length === 0 ? (
              <div className="text-center py-8">
                <ClockIcon className="w-12 h-12 text-win11-text-tertiary mx-auto mb-3" />
                <p className="text-win11-text-tertiary text-sm">
                  No recent sessions
                </p>
              </div>
            ) : (
              <>
                {/* Bulk delete controls */}
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center space-x-2">
                    <input
                      type="checkbox"
                      checked={selectedSessions.size === recentSessions.length && recentSessions.length > 0}
                      onChange={(e) => {
                        if (e.target.checked) {
                          setSelectedSessions(new Set(recentSessions.map(s => s.session_id)))
                        } else {
                          setSelectedSessions(new Set())
                        }
                      }}
                      className="w-4 h-4 text-blue-600 bg-gray-100 border-gray-300 rounded focus:ring-blue-500"
                    />
                    <span className="text-xs text-win11-text-secondary">Select All</span>
                  </div>
                  
                  <div className="flex items-center space-x-1">
                    {selectedSessions.size > 0 && (
                      <button
                        onClick={() => setShowDeleteConfirm(true)}
                        className="p-1.5 rounded-win11-small hover:bg-win11-surfaceHover text-red-600 hover:text-red-700"
                        title="Delete Selected Sessions"
                      >
                        <TrashIcon className="w-4 h-4" />
                      </button>
                    )}
                    <button
                      onClick={async () => {
                        if (confirm('Are you sure you want to delete all sessions? This cannot be undone.')) {
                          try {
                            await diagnosticsService.deleteAllSessions(user!.id)
                            await loadRecentSessions()
                            setSelectedSessions(new Set())
                            toast.success('All sessions deleted successfully')
                          } catch (error) {
                            console.error('Delete all sessions error:', error)
                            toast.error(`Failed to delete all sessions: ${error.response?.data?.detail || error.message}`)
                          }
                        }
                      }}
                      className="p-1.5 rounded-win11-small hover:bg-win11-surfaceHover text-red-600 hover:text-red-700"
                      title="Delete All Sessions"
                    >
                      <XMarkIcon className="w-4 h-4" />
                    </button>
                  </div>
                </div>
                
                <div className="space-y-3">
                  {recentSessions.map((session) => (
                    <div
                      key={session.session_id}
                      className="border border-win11-border rounded-win11-small p-3 hover:bg-win11-surfaceHover transition-colors"
                    >
                      <div className="flex items-center justify-between mb-2">
                        <div className="flex items-center space-x-2">
                          <input
                            type="checkbox"
                            checked={selectedSessions.has(session.session_id)}
                            onChange={(e) => {
                              const newSelected = new Set(selectedSessions)
                              if (e.target.checked) {
                                newSelected.add(session.session_id)
                              } else {
                                newSelected.delete(session.session_id)
                              }
                              setSelectedSessions(newSelected)
                            }}
                            className="w-4 h-4 text-blue-600 bg-gray-100 border-gray-300 rounded focus:ring-blue-500"
                          />
                          <span className="text-sm font-medium text-win11-text-primary">
                            {queryTypes.find(qt => qt.id === session.query_type)?.name || session.query_type}
                          </span>
                        </div>
                        
                        <div className="flex items-center space-x-2">
                          <span className={`text-xs px-2 py-1 rounded-full ${
                            session.status === 'completed' ? 'bg-green-100 text-green-800' :
                            session.status === 'failed' ? 'bg-red-100 text-red-800' :
                            'bg-yellow-100 text-yellow-800'
                          }`}>
                            {session.status}
                          </span>
                          <button
                            onClick={async () => {
                              if (confirm('Are you sure you want to delete this session?')) {
                                try {
                                  await diagnosticsService.deleteSession(session.session_id, user!.id)
                                  await loadRecentSessions()
                                  setSelectedSessions(prev => {
                                    const newSet = new Set(prev)
                                    newSet.delete(session.session_id)
                                    return newSet
                                  })
                                  toast.success('Session deleted successfully')
                                } catch (error) {
                                  console.error('Delete session error:', error)
                                  toast.error(`Failed to delete session: ${error.response?.data?.detail || error.message}`)
                                }
                              }
                            }}
                            className="p-1 rounded-win11-small hover:bg-win11-surfaceHover text-red-600 hover:text-red-700"
                            title="Delete Session"
                          >
                            <TrashIcon className="w-3 h-3" />
                          </button>
                        </div>
                      </div>
                      {session.device_id && (
                        <div className="text-xs text-win11-text-secondary mb-1">
                          Device: {session.device_id.slice(0, 8)}...
                        </div>
                      )}
                      <div className="text-xs text-win11-text-tertiary">
                        {formatDate(session.created_at)}
                      </div>
                    </div>
                  ))}
                </div>
                
                {/* Bulk delete confirmation modal */}
                {showDeleteConfirm && (
                  <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
                    <div className="win11-card p-6 max-w-md w-full mx-4">
                      <h3 className="text-lg font-medium text-win11-text-primary mb-4">
                        Confirm Delete
                      </h3>
                      <p className="text-win11-text-secondary mb-6">
                        Are you sure you want to delete {selectedSessions.size} selected session{selectedSessions.size > 1 ? 's' : ''}? This action cannot be undone.
                      </p>
                      <div className="flex justify-end space-x-3">
                        <button
                          onClick={() => setShowDeleteConfirm(false)}
                          className="win11-button-secondary px-4 py-2"
                        >
                          Cancel
                        </button>
                        <button
                          onClick={async () => {
                            try {
                              await diagnosticsService.deleteBulkSessions(Array.from(selectedSessions), user!.id)
                              await loadRecentSessions()
                              setSelectedSessions(new Set())
                              setShowDeleteConfirm(false)
                              toast.success(`${selectedSessions.size} session${selectedSessions.size > 1 ? 's' : ''} deleted successfully`)
                            } catch (error) {
                              console.error('Delete bulk sessions error:', error)
                              toast.error(`Failed to delete selected sessions: ${error.response?.data?.detail || error.message}`)
                            }
                          }}
                          className="win11-button bg-red-600 hover:bg-red-700 text-white px-4 py-2"
                        >
                          Delete
                        </button>
                      </div>
                    </div>
                  </div>
                )}
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

export default DiagnosticsPage