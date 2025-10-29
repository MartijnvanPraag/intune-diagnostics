import React, { useState, useEffect } from 'react'
import { useAuth } from '@/contexts/AuthContext'
import { useMsal } from '@azure/msal-react'
import { settingsService, ModelConfiguration, ModelConfigurationCreate } from '@/services/settingsService'
import ModelConfigForm from '@/components/ModelConfigForm'
import { PlusIcon, PencilIcon, TrashIcon, KeyIcon } from '@heroicons/react/24/outline'
import { StarIcon as StarSolidIcon } from '@heroicons/react/24/solid'
import toast from 'react-hot-toast'

const SettingsPage: React.FC = () => {
  const { user, getAccessToken } = useAuth()
  const { instance, accounts } = useMsal()
  const [configurations, setConfigurations] = useState<ModelConfiguration[]>([])
  const [loading, setLoading] = useState(true)
  const [showForm, setShowForm] = useState(false)
  const [editingConfig, setEditingConfig] = useState<ModelConfiguration | null>(null)
  const [cognitiveServicesToken, setCognitiveServicesToken] = useState<string | null>(null)
  const [acquiringToken, setAcquiringToken] = useState(false)

  useEffect(() => {
    if (user) {
      loadConfigurations()
    }
  }, [user])

  const loadConfigurations = async () => {
    try {
      setLoading(true)
      const configs = await settingsService.getModelConfigurations(user!.id)
      setConfigurations(configs)
    } catch (error) {
      console.error('Failed to load configurations:', error)
      toast.error('Failed to load model configurations')
    } finally {
      setLoading(false)
    }
  }

  const handleCreateConfig = async (data: ModelConfigurationCreate) => {
    try {
      await settingsService.createModelConfiguration(data)
      await loadConfigurations()
      setShowForm(false)
    } catch (error) {
      throw error
    }
  }

  const handleUpdateConfig = async (data: ModelConfigurationCreate) => {
    try {
      if (editingConfig) {
        await settingsService.updateModelConfiguration(editingConfig.id!, data)
        await loadConfigurations()
        setEditingConfig(null)
        setShowForm(false)
      }
    } catch (error) {
      throw error
    }
  }

  const handleDeleteConfig = async (configId: number) => {
    if (window.confirm('Are you sure you want to delete this configuration?')) {
      try {
        await settingsService.deleteModelConfiguration(configId)
        await loadConfigurations()
        toast.success('Configuration deleted')
      } catch (error) {
        console.error('Delete failed:', error)
        toast.error('Failed to delete configuration')
      }
    }
  }

  const handleEditConfig = (config: ModelConfiguration) => {
    setEditingConfig(config)
    setShowForm(true)
  }

  const handleCancelForm = () => {
    setEditingConfig(null)
    setShowForm(false)
  }

  const handleAcquireCognitiveServicesToken = async () => {
    try {
      setAcquiringToken(true)
      const account = accounts[0]
      
      if (!account) {
        toast.error('No account found. Please sign in first.')
        return
      }

      // Try multiple scope formats for Cognitive Services
      const scopeOptions = [
        ['https://cognitiveservices.azure.com/.default'],
        ['https://cognitiveservices.azure.com/user_impersonation'],
        // OpenAI-specific scope
        ['https://cognitiveservices.azure.com/openai/user_impersonation'],
      ]

      let tokenResponse = null
      let lastError = null

      for (const scopes of scopeOptions) {
        try {
          console.log(`Trying to acquire token with scopes: ${scopes.join(', ')}`)
          tokenResponse = await instance.acquireTokenPopup({
            scopes: scopes,
            account: account,
          })
          console.log(`Successfully acquired token with scopes: ${scopes.join(', ')}`)
          break
        } catch (error: any) {
          console.warn(`Failed with scopes ${scopes.join(', ')}: ${error.message}`)
          lastError = error
          continue
        }
      }

      if (!tokenResponse) {
        throw lastError || new Error('Failed to acquire token with all scope options')
      }

      setCognitiveServicesToken(tokenResponse.accessToken)
      
      // Get the user's app token for Authorization header
      const appToken = await getAccessToken()
      
      // Send token to backend
      try {
        const response = await fetch('/api/auth/set-cognitive-token', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${appToken}`,
          },
          body: JSON.stringify({
            cognitive_token: tokenResponse.accessToken,
          }),
        })

        if (!response.ok) {
          throw new Error(`Failed to send token to backend: ${response.statusText}`)
        }

        console.log('Token sent to backend successfully')
      } catch (backendError) {
        console.error('Failed to send token to backend:', backendError)
        toast.error('Token acquired but failed to send to backend')
        return
      }
      
      // Copy token to clipboard
      await navigator.clipboard.writeText(tokenResponse.accessToken)
      
      toast.success('Cognitive Services token acquired, sent to backend, and copied to clipboard!')
      console.log('Cognitive Services Token:', tokenResponse.accessToken)
      console.log('Token expires at:', tokenResponse.expiresOn)
      
    } catch (error) {
      console.error('Failed to acquire Cognitive Services token:', error)
      
      // Check if it's the specific permission error
      const errorMessage = error instanceof Error ? error.message : String(error)
      if (errorMessage.includes('AADSTS650057') || errorMessage.includes('invalid_resource')) {
        toast.error('Your app registration needs Cognitive Services API permission. Check console for instructions.')
        console.error(`
===========================================
PERMISSION ERROR: AADSTS650057
===========================================

Your Azure AD app registration doesn't have permission to request Cognitive Services tokens.

TO FIX:
1. Go to Azure Portal: https://portal.azure.com
2. Navigate to Azure Active Directory → App registrations
3. Find your app: mvanpraag-ai (Client ID: fbadc585-90b3-48ab-8052-c1fcc32ce3fe)
4. Click "API permissions" in the left menu
5. Click "+ Add a permission"
6. Search for "Cognitive Services" under "APIs my organization uses"
7. Select "Delegated permissions" → "user_impersonation"
8. Click "Add permissions"
9. Click "Grant admin consent" (requires admin privileges)

ALTERNATIVE (if you have access to the Cognitive Services resource):
You can also configure your app registration to use Managed Identity instead,
or set up the Cognitive Services resource to accept tokens from your tenant.

For more info: https://learn.microsoft.com/en-us/azure/ai-services/authentication
===========================================
        `)
      } else {
        toast.error('Failed to acquire token. See console for details.')
      }
    } finally {
      setAcquiringToken(false)
    }
  }

  if (loading) {
    return (
      <div className="animate-fade-in">
        <div className="mb-6">
          <h1 className="text-3xl font-semibold text-win11-text-primary mb-2">Settings</h1>
        </div>
        <div className="win11-card p-6">
          <div className="animate-pulse">
            <div className="h-4 bg-win11-surface rounded w-1/4 mb-4"></div>
            <div className="space-y-3">
              <div className="h-16 bg-win11-surface rounded"></div>
              <div className="h-16 bg-win11-surface rounded"></div>
            </div>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="animate-fade-in">
      <div className="mb-6">
        <h1 className="text-3xl font-semibold text-win11-text-primary mb-2">
          Settings
        </h1>
        <p className="text-win11-text-secondary">
          Configure your Azure AI models and agent preferences
        </p>
      </div>

      <div className="win11-card p-6">
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-xl font-medium text-win11-text-primary">
            Model Configurations
          </h2>
          <button
            onClick={() => setShowForm(true)}
            className="win11-button flex items-center space-x-2"
          >
            <PlusIcon className="w-4 h-4" />
            <span>Add Configuration</span>
          </button>
        </div>

        {configurations.length === 0 ? (
          <div className="text-center py-12">
            <div className="text-win11-text-tertiary mb-4">
              No model configurations found
            </div>
            <button
              onClick={() => setShowForm(true)}
              className="win11-button-secondary"
            >
              Create your first configuration
            </button>
          </div>
        ) : (
          <div className="space-y-4">
            {configurations.map((config) => (
              <div
                key={config.id}
                className="border border-win11-border rounded-win11 p-4 hover:bg-win11-surfaceHover transition-colors"
              >
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    <div className="flex items-center space-x-2 mb-2">
                      <h3 className="text-lg font-medium text-win11-text-primary">
                        {config.name}
                      </h3>
                      {config.is_default && (
                        <StarSolidIcon className="w-5 h-5 text-yellow-500" title="Default configuration" />
                      )}
                    </div>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">
                      <div>
                        <span className="text-win11-text-secondary">Endpoint:</span>
                        <div className="text-win11-text-primary font-mono text-xs break-all">
                          {config.azure_endpoint}
                        </div>
                      </div>
                      <div>
                        <span className="text-win11-text-secondary">Deployment:</span>
                        <div className="text-win11-text-primary">{config.azure_deployment}</div>
                      </div>
                      <div>
                        <span className="text-win11-text-secondary">Model:</span>
                        <div className="text-win11-text-primary">{config.model_name}</div>
                      </div>
                      <div>
                        <span className="text-win11-text-secondary">API Version:</span>
                        <div className="text-win11-text-primary">{config.api_version}</div>
                      </div>
                      <div>
                        <span className="text-win11-text-secondary">Agent Framework:</span>
                        <div className="text-win11-text-primary">
                          {config.agent_framework === 'agent_framework' ? 'Microsoft Agent Framework' : 'Autogen Framework'}
                        </div>
                      </div>
                    </div>
                  </div>
                  <div className="flex items-center space-x-2 ml-4">
                    <button
                      onClick={() => handleEditConfig(config)}
                      className="p-2 hover:bg-win11-surfaceHover rounded-win11-small transition-colors"
                      title="Edit configuration"
                    >
                      <PencilIcon className="w-4 h-4 text-win11-text-secondary" />
                    </button>
                    <button
                      onClick={() => handleDeleteConfig(config.id!)}
                      className="p-2 hover:bg-win11-surfaceHover rounded-win11-small transition-colors"
                      title="Delete configuration"
                    >
                      <TrashIcon className="w-4 h-4 text-red-500" />
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Azure Cognitive Services Authentication Section */}
      <div className="win11-card p-6 mt-6">
        <div className="mb-6">
          <h2 className="text-xl font-medium text-win11-text-primary mb-2">
            Azure Cognitive Services Authentication
          </h2>
          <p className="text-sm text-win11-text-secondary">
            Acquire an access token for Azure Cognitive Services (OpenAI) to enable AI features
          </p>
        </div>

        <div className="space-y-4">
          <div className="flex items-center justify-between p-4 border border-win11-border rounded-win11 bg-win11-surface">
            <div className="flex-1">
              <div className="flex items-center space-x-2 mb-1">
                <KeyIcon className="w-5 h-5 text-win11-accent" />
                <h3 className="font-medium text-win11-text-primary">
                  Interactive Token Acquisition
                </h3>
              </div>
              <p className="text-sm text-win11-text-secondary">
                Click to authenticate and get a token for https://cognitiveservices.azure.com
              </p>
              {cognitiveServicesToken && (
                <div className="mt-2 text-xs text-green-600">
                  ✓ Token acquired and copied to clipboard
                </div>
              )}
            </div>
            <button
              onClick={handleAcquireCognitiveServicesToken}
              disabled={acquiringToken}
              className="win11-button flex items-center space-x-2 ml-4"
            >
              <KeyIcon className="w-4 h-4" />
              <span>{acquiringToken ? 'Acquiring...' : 'Get Token'}</span>
            </button>
          </div>

          {cognitiveServicesToken && (
            <div className="p-4 border border-win11-border rounded-win11 bg-win11-surfaceHover">
              <div className="flex items-center justify-between mb-2">
                <span className="text-sm font-medium text-win11-text-primary">
                  Access Token (first 50 chars):
                </span>
                <button
                  onClick={() => {
                    navigator.clipboard.writeText(cognitiveServicesToken)
                    toast.success('Token copied to clipboard!')
                  }}
                  className="text-xs text-win11-accent hover:underline"
                >
                  Copy Full Token
                </button>
              </div>
              <code className="text-xs font-mono text-win11-text-secondary break-all">
                {cognitiveServicesToken.substring(0, 50)}...
              </code>
            </div>
          )}
        </div>
      </div>

      {showForm && (
        <ModelConfigForm
          userId={user!.id}
          onSubmit={editingConfig ? handleUpdateConfig : handleCreateConfig}
          onCancel={handleCancelForm}
          initialData={editingConfig || undefined}
          isEditing={!!editingConfig}
        />
      )}
    </div>
  )
}

export default SettingsPage