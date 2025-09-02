import React from 'react'
import { useAuth } from '@/contexts/AuthContext'

const DashboardPage: React.FC = () => {
  const { user } = useAuth()

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
            <button className="win11-button-secondary w-full text-sm">
              Device Lookup
            </button>
            <button className="win11-button-secondary w-full text-sm">
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
          <div className="text-win11-text-tertiary text-sm">
            No recent sessions
          </div>
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