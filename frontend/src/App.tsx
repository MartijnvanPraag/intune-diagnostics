import { BrowserRouter as Router, Routes, Route } from 'react-router-dom'
import { Toaster } from 'react-hot-toast'
import Layout from './components/Layout'
import LoginPage from './pages/LoginPage'
import DashboardPage from './pages/DashboardPage'
import SettingsPage from './pages/SettingsPage'
import DiagnosticsPage from './pages/DiagnosticsPage'
import ChatPage from './pages/ChatPage'
import { AuthProvider } from './contexts/AuthContext'

function App() {
  return (
    <AuthProvider>
      <Router>
        <div className="min-h-screen bg-win11-background">
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route path="/" element={<Layout />}>
              <Route index element={<DashboardPage />} />
              <Route path="settings" element={<SettingsPage />} />
              <Route path="diagnostics" element={<DiagnosticsPage />} />
              <Route path="scenarios" element={<DiagnosticsPage />} />
              <Route path="chat" element={<ChatPage />} />
            </Route>
          </Routes>
          <Toaster 
            position="top-right"
            toastOptions={{
              duration: 4000,
              style: {
                background: '#FFFFFF',
                color: '#323130',
                border: '1px solid #E1DFDD',
                borderRadius: '8px',
                boxShadow: '0 8px 16px rgba(0, 0, 0, 0.14)',
              },
            }}
          />
        </div>
      </Router>
    </AuthProvider>
  )
}

export default App