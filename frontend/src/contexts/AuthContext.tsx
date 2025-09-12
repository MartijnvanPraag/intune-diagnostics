import React, { createContext, useContext, useState, useEffect, ReactNode } from 'react'
import { authService } from '@/services/authService'

interface User {
  id: number
  azure_user_id: string
  email: string
  display_name: string
  is_active: boolean
}

interface AuthContextType {
  user: User | null
  isLoading: boolean
  login: (forceInteractive?: boolean) => Promise<void>
  logout: () => Promise<void>
  isAuthenticated: boolean
}

const AuthContext = createContext<AuthContextType | undefined>(undefined)

export const useAuth = () => {
  const context = useContext(AuthContext)
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider')
  }
  return context
}

interface AuthProviderProps {
  children: ReactNode
}

export const AuthProvider: React.FC<AuthProviderProps> = ({ children }) => {
  const [user, setUser] = useState<User | null>(null)
  const [isLoading, setIsLoading] = useState(true)

  useEffect(() => {
    checkAuthStatus()
  }, [])

  const checkAuthStatus = async () => {
    try {
      const storedUser = localStorage.getItem('user')
      if (storedUser) {
        const userData = JSON.parse(storedUser)
        const currentUser = await authService.getCurrentUser(userData.azure_user_id)
        setUser(currentUser)
      }
    } catch (error) {
      localStorage.removeItem('user')
      localStorage.removeItem('access_token')
    } finally {
      setIsLoading(false)
    }
  }

  const login = async (forceInteractive: boolean = false) => {
    try {
      setIsLoading(true)
      const authResult = await authService.login(forceInteractive)
      
      // Register user in database
      const user = await authService.registerUser({
        azure_user_id: authResult.user.azure_user_id,
        email: authResult.user.email,
        display_name: authResult.user.display_name
      })
      
      setUser(user)
      localStorage.setItem('user', JSON.stringify(user))
      localStorage.setItem('access_token', authResult.access_token || '')
    } catch (error) {
      throw error
    } finally {
      setIsLoading(false)
    }
  }

  const logout = async () => {
    try {
      // Call backend logout to clear server-side cache
      await authService.logout()
    } catch (error) {
      // Continue with logout even if backend fails
      console.warn('Backend logout failed:', error)
    } finally {
      // Always clear frontend state
      setUser(null)
      localStorage.removeItem('user')
      localStorage.removeItem('access_token')
    }
  }

  const value: AuthContextType = {
    user,
    isLoading,
    login,
    logout,
    isAuthenticated: !!user
  }

  return (
    <AuthContext.Provider value={value}>
      {children}
    </AuthContext.Provider>
  )
}