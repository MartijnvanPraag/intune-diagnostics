import React, { useState } from 'react'
import { Navigate } from 'react-router-dom'
import { useAuth } from '@/contexts/AuthContext'
import { ComputerDesktopIcon } from '@heroicons/react/24/outline'
import toast from 'react-hot-toast'

const LoginPage: React.FC = () => {
  const { login, isAuthenticated, isLoading } = useAuth()
  const [loggingIn, setLoggingIn] = useState(false)

  if (isAuthenticated) {
    return <Navigate to="/" replace />
  }

  const handleLogin = async () => {
    try {
      setLoggingIn(true)
      await login()
      toast.success('Successfully authenticated!')
    } catch (error) {
      console.error('Login failed:', error)
      toast.error(`Login failed: ${error instanceof Error ? error.message : 'Unknown error'}`)
    } finally {
      setLoggingIn(false)
    }
  }

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-win11-background">
        <div className="win11-card p-8">
          <div className="animate-pulse flex items-center space-x-3">
            <div className="w-8 h-8 bg-win11-primary rounded-full"></div>
            <div className="text-win11-text-secondary">Loading...</div>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-win11-background">
      <div className="w-full max-w-md">
        <div className="win11-card p-8 animate-fade-in">
          <div className="text-center mb-8">
            <div className="w-16 h-16 bg-win11-primary rounded-win11 mx-auto mb-4 flex items-center justify-center">
              <ComputerDesktopIcon className="w-8 h-8 text-white" />
            </div>
            <h1 className="text-2xl font-semibold text-win11-text-primary mb-2">
              Intune Diagnostics
            </h1>
            <p className="text-win11-text-secondary">
              Sign in with your Microsoft account to access Intune diagnostic tools
            </p>
          </div>

          <div className="space-y-4">
            <button
              onClick={handleLogin}
              disabled={loggingIn}
              className="w-full win11-button disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {loggingIn ? (
                <span className="flex items-center justify-center space-x-2">
                  <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin"></div>
                  <span>Signing in...</span>
                </span>
              ) : (
                'Sign in with Microsoft'
              )}
            </button>

            <div className="text-xs text-win11-text-tertiary text-center">
              This app uses Azure Active Directory for secure authentication.
              No credentials are stored locally.
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

export default LoginPage