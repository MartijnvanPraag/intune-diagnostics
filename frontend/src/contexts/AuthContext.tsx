import React, { createContext, useContext, useState, useEffect, ReactNode } from 'react'
import { useMsal } from '@azure/msal-react'
import { InteractionStatus } from '@azure/msal-browser'
import { loginRequest } from '@/config/authConfig'
import { authService } from '@/services/authService'
import { setTokenProvider } from '@/config/axiosConfig'

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
  login: () => Promise<void>
  logout: () => Promise<void>
  isAuthenticated: boolean
  getAccessToken: () => Promise<string>
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
  const { instance, accounts, inProgress } = useMsal()
  const [user, setUser] = useState<User | null>(null)
  const [isLoading, setIsLoading] = useState(true)

  // Register token provider for axios interceptor
  useEffect(() => {
    setTokenProvider(getAccessToken)
  }, [])

  // Check if user is already authenticated
  useEffect(() => {
    if (inProgress === InteractionStatus.None && accounts.length > 0) {
      // User is signed in with MSAL, sync with backend
      syncUserWithBackend()
    } else {
      setIsLoading(false)
    }
  }, [accounts, inProgress])

  /**
   * Sync MSAL-authenticated user with backend database
   */
  const syncUserWithBackend = async () => {
    try {
      setIsLoading(true)
      const account = accounts[0]
      
      // Get access token for backend API calls
      const tokenResponse = await instance.acquireTokenSilent({
        ...loginRequest,
        account: account,
      })

      // Extract user info from token claims
      const azureUserId = account.localAccountId // Unique Azure AD user ID
      const email = account.username // Email address
      const displayName = account.name || email.split('@')[0] // Display name

      // Register/update user in backend
      const backendUser = await authService.registerUser({
        azure_user_id: azureUserId,
        email: email,
        display_name: displayName,
      }, tokenResponse.accessToken)

      setUser(backendUser)
    } catch (error) {
      console.error('Failed to sync user with backend:', error)
      // If token acquisition fails, user needs to sign in again
      await instance.logoutPopup()
    } finally {
      setIsLoading(false)
    }
  }

  /**
   * Initiate login flow using popup (can switch to redirect if preferred)
   */
  const login = async () => {
    try {
      setIsLoading(true)
      
      // Login with popup (alternatively use loginRedirect for full page redirect)
      const loginResponse = await instance.loginPopup(loginRequest)
      
      // Set active account
      instance.setActiveAccount(loginResponse.account)
      
      // Sync with backend
      await syncUserWithBackend()
    } catch (error) {
      console.error('Login failed:', error)
      throw error
    } finally {
      setIsLoading(false)
    }
  }

  /**
   * Logout from both MSAL and backend
   */
  const logout = async () => {
    try {
      // Clear backend session (optional)
      await authService.logout()
    } catch (error) {
      console.warn('Backend logout failed:', error)
    } finally {
      // Always logout from MSAL (clears tokens)
      setUser(null)
      await instance.logoutPopup({
        postLogoutRedirectUri: window.location.origin,
      })
    }
  }

  /**
   * Get fresh access token for API calls
   * This handles automatic token refresh
   */
  const getAccessToken = async (): Promise<string> => {
    if (accounts.length === 0) {
      throw new Error('No authenticated user')
    }

    try {
      const response = await instance.acquireTokenSilent({
        ...loginRequest,
        account: accounts[0],
      })
      return response.accessToken
    } catch (error) {
      console.error('Token acquisition failed:', error)
      // If silent acquisition fails, try interactive
      const response = await instance.acquireTokenPopup(loginRequest)
      return response.accessToken
    }
  }

  const value: AuthContextType = {
    user,
    isLoading,
    login,
    logout,
    isAuthenticated: accounts.length > 0 && user !== null,
    getAccessToken,
  }

  return (
    <AuthContext.Provider value={value}>
      {children}
    </AuthContext.Provider>
  )
}