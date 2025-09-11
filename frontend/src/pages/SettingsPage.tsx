import React, { useState, useEffect } from 'react'
import { useAuth } from '@/contexts/AuthContext'
import { settingsService, ModelConfiguration, ModelConfigurationCreate } from '@/services/settingsService'
import ModelConfigForm from '@/components/ModelConfigForm'
import { PlusIcon, PencilIcon, TrashIcon } from '@heroicons/react/24/outline'
import { StarIcon as StarSolidIcon } from '@heroicons/react/24/solid'
import toast from 'react-hot-toast'

const SettingsPage: React.FC = () => {
  const { user } = useAuth()
  const [configurations, setConfigurations] = useState<ModelConfiguration[]>([])
  const [loading, setLoading] = useState(true)
  const [showForm, setShowForm] = useState(false)
  const [editingConfig, setEditingConfig] = useState<ModelConfiguration | null>(null)

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