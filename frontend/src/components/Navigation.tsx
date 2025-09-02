import React from 'react'
import { NavLink } from 'react-router-dom'
import { useAuth } from '@/contexts/AuthContext'
import { 
  HomeIcon, 
  Cog6ToothIcon, 
  ComputerDesktopIcon,
  ArrowRightOnRectangleIcon,
  UserIcon
} from '@heroicons/react/24/outline'

const Navigation: React.FC = () => {
  const { user, logout } = useAuth()

  const navItems = [
    { to: '/', icon: HomeIcon, label: 'Dashboard' },
    { to: '/diagnostics', icon: ComputerDesktopIcon, label: 'Diagnostics' },
  { to: '/chat', icon: ComputerDesktopIcon, label: 'Chat' },
    { to: '/settings', icon: Cog6ToothIcon, label: 'Settings' },
  ]

  return (
    <nav className="fixed left-0 top-0 h-full w-64 bg-win11-card border-r border-win11-border shadow-win11">
      <div className="p-6">
        <div className="flex items-center space-x-3 mb-8">
          <div className="w-8 h-8 bg-win11-primary rounded-win11-small flex items-center justify-center">
            <ComputerDesktopIcon className="w-5 h-5 text-white" />
          </div>
          <h1 className="text-xl font-semibold text-win11-text-primary">
            Intune Diagnostics
          </h1>
        </div>

        <div className="space-y-2">
          {navItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) =>
                `flex items-center space-x-3 px-3 py-2 rounded-win11-small text-sm font-medium transition-all duration-150 ${
                  isActive
                    ? 'bg-win11-primary text-white shadow-win11-small'
                    : 'text-win11-text-secondary hover:bg-win11-surfaceHover hover:text-win11-text-primary'
                }`
              }
            >
              <item.icon className="w-5 h-5" />
              <span>{item.label}</span>
            </NavLink>
          ))}
        </div>
      </div>

      {/* User section at bottom */}
      <div className="absolute bottom-0 left-0 right-0 p-6 border-t border-win11-border">
        <div className="flex items-center space-x-3 mb-4">
          <div className="w-8 h-8 bg-win11-accent rounded-full flex items-center justify-center">
            <UserIcon className="w-4 h-4 text-white" />
          </div>
          <div className="flex-1 min-w-0">
            <div className="text-sm font-medium text-win11-text-primary truncate">
              {user?.display_name}
            </div>
            <div className="text-xs text-win11-text-tertiary truncate">
              {user?.email}
            </div>
          </div>
        </div>
        
        <button
          onClick={logout}
          className="flex items-center space-x-2 w-full px-3 py-2 text-sm text-win11-text-secondary hover:text-win11-text-primary hover:bg-win11-surfaceHover rounded-win11-small transition-all duration-150"
        >
          <ArrowRightOnRectangleIcon className="w-4 h-4" />
          <span>Sign Out</span>
        </button>
      </div>
    </nav>
  )
}

export default Navigation