import axios, { InternalAxiosRequestConfig } from 'axios'

/**
 * Global variable to store the function that retrieves access tokens
 * This is set by AuthContext after MSAL initialization
 */
let tokenProvider: (() => Promise<string>) | null = null

/**
 * Register the token provider function
 * Called by AuthContext once MSAL is ready
 */
export const setTokenProvider = (provider: () => Promise<string>) => {
  tokenProvider = provider
}

/**
 * Axios request interceptor to add Bearer token to all API requests
 */
axios.interceptors.request.use(
  async (config: InternalAxiosRequestConfig) => {
    // Only add token for API requests (not for external URLs)
    if (config.url?.startsWith('/api') && tokenProvider) {
      try {
        const token = await tokenProvider()
        config.headers.Authorization = `Bearer ${token}`
      } catch (error) {
        console.warn('Failed to get access token:', error)
        // Continue without token - backend will return 401 if required
      }
    }
    return config
  },
  (error) => {
    return Promise.reject(error)
  }
)

/**
 * Axios response interceptor to handle 401 errors
 */
axios.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      // Token expired or invalid - user will be prompted to login again
      console.warn('Authentication failed - user needs to re-login')
      // You could dispatch a logout action here if needed
    }
    return Promise.reject(error)
  }
)
