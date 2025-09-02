import React from 'react'
import { Outlet, Navigate } from 'react-router-dom'
import { useAuth } from '@/contexts/AuthContext'
import Navigation from './Navigation'

const Layout: React.FC = () => {
  const { isAuthenticated, isLoading } = useAuth()

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

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />
  }

  return (
    <div className="min-h-screen bg-win11-background">
      <Navigation />
      <main className="pl-64">
        <div className="p-6">
          <Outlet />
        </div>
      </main>
    </div>
  )
}

export default Layout