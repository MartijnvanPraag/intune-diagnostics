import React from 'react'
import ReactDOM from 'react-dom/client'
import { PublicClientApplication } from '@azure/msal-browser'
import { MsalProvider } from '@azure/msal-react'
import { msalConfig } from './config/authConfig'
import './config/axiosConfig' // Initialize axios interceptors
import App from './App.tsx'
import './index.css'

// Initialize MSAL instance (handles all OAuth flows)
const msalInstance = new PublicClientApplication(msalConfig)

// Handle redirect promise (required for redirect flow)
msalInstance.initialize().then(async () => {
  // Handle any pending redirect operations
  try {
    await msalInstance.handleRedirectPromise()
  } catch (error) {
    console.error('Error handling redirect:', error)
  }
  
  ReactDOM.createRoot(document.getElementById('root')!).render(
    <React.StrictMode>
      <MsalProvider instance={msalInstance}>
        <App />
      </MsalProvider>
    </React.StrictMode>,
  )
})