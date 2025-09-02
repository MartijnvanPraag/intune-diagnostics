import axios from 'axios'

const API_BASE_URL = '/api'

export interface ModelConfiguration {
  id?: number
  user_id: number
  name: string
  azure_endpoint: string
  azure_deployment: string
  model_name: string
  api_version: string
  is_default: boolean
  created_at?: string
  updated_at?: string
}

export interface ModelConfigurationCreate {
  user_id: number
  name: string
  azure_endpoint: string
  azure_deployment: string
  model_name: string
  api_version?: string
  is_default?: boolean
}

class SettingsService {
  async getModelConfigurations(userId: number): Promise<ModelConfiguration[]> {
    const response = await axios.get(`${API_BASE_URL}/settings/models`, {
      params: { user_id: userId }
    })
    return response.data
  }

  async createModelConfiguration(config: ModelConfigurationCreate): Promise<ModelConfiguration> {
    const response = await axios.post(`${API_BASE_URL}/settings/models`, config)
    return response.data
  }

  async updateModelConfiguration(configId: number, config: ModelConfigurationCreate): Promise<ModelConfiguration> {
    const response = await axios.put(`${API_BASE_URL}/settings/models/${configId}`, config)
    return response.data
  }

  async deleteModelConfiguration(configId: number): Promise<void> {
    await axios.delete(`${API_BASE_URL}/settings/models/${configId}`)
  }

  async getModelConfiguration(configId: number): Promise<ModelConfiguration> {
    const response = await axios.get(`${API_BASE_URL}/settings/models/${configId}`)
    return response.data
  }
}

export const settingsService = new SettingsService()