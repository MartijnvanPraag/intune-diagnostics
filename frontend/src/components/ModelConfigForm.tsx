import React, { useState } from 'react'
import { useForm } from 'react-hook-form'
import { XMarkIcon } from '@heroicons/react/24/outline'
import { ModelConfigurationCreate } from '@/services/settingsService'
import toast from 'react-hot-toast'

interface ModelConfigFormProps {
  userId: number
  onSubmit: (data: ModelConfigurationCreate) => Promise<void>
  onCancel: () => void
  initialData?: Partial<ModelConfigurationCreate>
  isEditing?: boolean
}

const ModelConfigForm: React.FC<ModelConfigFormProps> = ({
  userId,
  onSubmit,
  onCancel,
  initialData,
  isEditing = false
}) => {
  const [isSubmitting, setIsSubmitting] = useState(false)
  
  const {
    register,
    handleSubmit,
    formState: { errors }
  } = useForm<ModelConfigurationCreate>({
    defaultValues: {
      user_id: userId,
      name: initialData?.name || '',
      azure_endpoint: initialData?.azure_endpoint || '',
      azure_deployment: initialData?.azure_deployment || '',
      model_name: initialData?.model_name || '',
      api_version: initialData?.api_version || '2024-06-01',
      is_default: initialData?.is_default || false,
      agent_framework: initialData?.agent_framework || 'autogen'
    }
  })

  const onFormSubmit = async (data: ModelConfigurationCreate) => {
    try {
      setIsSubmitting(true)
      await onSubmit(data)
      toast.success(isEditing ? 'Model configuration updated!' : 'Model configuration created!')
    } catch (error) {
      console.error('Form submission error:', error)
      toast.error(`Failed to ${isEditing ? 'update' : 'create'} model configuration`)
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="win11-card max-w-2xl w-full max-h-[90vh] overflow-y-auto m-4">
        <div className="p-6">
          <div className="flex items-center justify-between mb-6">
            <h2 className="text-xl font-semibold text-win11-text-primary">
              {isEditing ? 'Edit Model Configuration' : 'Add Model Configuration'}
            </h2>
            <button
              onClick={onCancel}
              className="p-2 hover:bg-win11-surfaceHover rounded-win11-small transition-colors"
            >
              <XMarkIcon className="w-5 h-5 text-win11-text-secondary" />
            </button>
          </div>

          <form onSubmit={handleSubmit(onFormSubmit)} className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-win11-text-primary mb-2">
                Configuration Name
              </label>
              <input
                {...register('name', { required: 'Name is required' })}
                className="win11-input w-full"
                placeholder="e.g., GPT-4 Production"
              />
              {errors.name && (
                <p className="text-red-500 text-xs mt-1">{errors.name.message}</p>
              )}
            </div>

            <div>
              <label className="block text-sm font-medium text-win11-text-primary mb-2">
                Azure Endpoint
              </label>
              <input
                {...register('azure_endpoint', { required: 'Azure endpoint is required' })}
                className="win11-input w-full"
                placeholder="https://your-resource.openai.azure.com/"
              />
              {errors.azure_endpoint && (
                <p className="text-red-500 text-xs mt-1">{errors.azure_endpoint.message}</p>
              )}
            </div>

            <div>
              <label className="block text-sm font-medium text-win11-text-primary mb-2">
                Azure Deployment
              </label>
              <input
                {...register('azure_deployment', { required: 'Deployment name is required' })}
                className="win11-input w-full"
                placeholder="e.g., gpt-4-deployment"
              />
              {errors.azure_deployment && (
                <p className="text-red-500 text-xs mt-1">{errors.azure_deployment.message}</p>
              )}
            </div>

            <div>
              <label className="block text-sm font-medium text-win11-text-primary mb-2">
                Model Name
              </label>
              <input
                {...register('model_name', { required: 'Model name is required' })}
                className="win11-input w-full"
                placeholder="e.g., gpt-4, gpt-4o, claude-3-sonnet, gpt-35-turbo"
              />
              <div className="text-xs text-win11-text-tertiary mt-1">
                Enter the exact model name as it appears in your Azure AI deployment
              </div>
              {errors.model_name && (
                <p className="text-red-500 text-xs mt-1">{errors.model_name.message}</p>
              )}
            </div>

            <div>
              <label className="block text-sm font-medium text-win11-text-primary mb-2">
                API Version
              </label>
              <input
                {...register('api_version')}
                className="win11-input w-full"
                placeholder="2024-06-01"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-win11-text-primary mb-2">
                Agent Framework
              </label>
              <select
                {...register('agent_framework')}
                className="win11-input w-full"
              >
                <option value="autogen">Autogen Framework (MagenticOne)</option>
                <option value="agent_framework">Microsoft Agent Framework</option>
              </select>
              <div className="text-xs text-win11-text-tertiary mt-1">
                Choose the multi-agent framework to use for diagnostics orchestration
              </div>
            </div>

            <div className="flex items-center space-x-3">
              <input
                {...register('is_default')}
                type="checkbox"
                id="is_default"
                className="w-4 h-4 text-win11-primary bg-win11-background border-win11-border rounded focus:ring-win11-primary"
              />
              <label htmlFor="is_default" className="text-sm text-win11-text-primary">
                Set as default model configuration
              </label>
            </div>

            <div className="flex space-x-3 pt-4">
              <button
                type="submit"
                disabled={isSubmitting}
                className="win11-button flex-1 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {isSubmitting ? (
                  <span className="flex items-center justify-center space-x-2">
                    <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin"></div>
                    <span>{isEditing ? 'Updating...' : 'Creating...'}</span>
                  </span>
                ) : (
                  isEditing ? 'Update Configuration' : 'Create Configuration'
                )}
              </button>
              <button
                type="button"
                onClick={onCancel}
                className="win11-button-secondary flex-1"
                disabled={isSubmitting}
              >
                Cancel
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  )
}

export default ModelConfigForm