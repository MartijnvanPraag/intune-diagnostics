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

export interface LoginResponse {
  status: string
  message: string
  user: {
    azure_user_id: string
    email: string
    display_name: string
  }
  access_token?: string
}

export interface UserCreate {
  azure_user_id: string
  email: string
  display_name: string
}

class AuthService {
  async login(forceInteractive: boolean = false): Promise<LoginResponse> {
    const response = await axios.post(`${API_BASE_URL}/auth/login?force_interactive=${forceInteractive}`)
    return response.data
  }

  async logout(): Promise<void> {
    try {
      await axios.post(`${API_BASE_URL}/auth/logout`)
    } catch (error) {
      // Continue with logout even if backend call fails
      console.warn('Backend logout failed, continuing with local logout:', error)
    }
  }

  async registerUser(userData: UserCreate): Promise<User> {
    const response = await axios.post(`${API_BASE_URL}/auth/register`, userData)
    return response.data
  }

  async getCurrentUser(azureUserId: string): Promise<User> {
    const response = await axios.get(`${API_BASE_URL}/auth/me`, {
      params: { azure_user_id: azureUserId }
    })
    return response.data
  }
}

export const authService = new AuthService()