import axios from 'axios'

const API_BASE_URL = '/api'

export interface User {
  id: number
  azure_user_id: string
  email: string
  display_name: string
  is_active: boolean
  created_at: string
  updated_at: string
}

export interface UserCreate {
  azure_user_id: string
  email: string
  display_name: string
}

class AuthService {
  /**
   * Register or update user in backend database
   * This is called after MSAL authentication succeeds
   * 
   * @param userData - User information from Azure AD token
   * @param accessToken - JWT token from MSAL (sent as Bearer token)
   */
  async registerUser(userData: UserCreate, accessToken?: string): Promise<User> {
    const response = await axios.post(`${API_BASE_URL}/auth/register`, userData, {
      headers: accessToken ? {
        Authorization: `Bearer ${accessToken}`,
      } : undefined,
    })
    return response.data
  }

  /**
   * Logout from backend (optional - mainly for clearing server-side cache)
   */
  async logout(): Promise<void> {
    try {
      await axios.post(`${API_BASE_URL}/auth/logout`)
    } catch (error) {
      console.warn('Backend logout failed, continuing with local logout:', error)
    }
  }

  /**
   * Get current user from backend
   */
  async getCurrentUser(azureUserId: string): Promise<User> {
    const response = await axios.get(`${API_BASE_URL}/auth/me`, {
      params: { azure_user_id: azureUserId }
    })
    return response.data
  }
}

export const authService = new AuthService()