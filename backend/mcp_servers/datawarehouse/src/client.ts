/**
 * HTTP client for Intune Data Warehouse API
 */

import axios, { AxiosInstance, AxiosError } from 'axios';
import {
  DataWarehouseConfig,
  ODataQueryOptions,
  ODataResponse,
  EntityMetadata,
  DataWarehouseError
} from './types.js';

export class DataWarehouseClient {
  private client: AxiosInstance;
  private config: DataWarehouseConfig;
  private metadataCache: Map<string, any> = new Map();

  constructor(config: DataWarehouseConfig) {
    this.config = config;
    this.client = axios.create({
      baseURL: config.baseUrl,
      headers: {
        'Authorization': `Bearer ${config.token}`,
        'Accept': 'application/json',
        'Content-Type': 'application/json'
      },
      timeout: 30000
    });
  }

  /**
   * Update the bearer token
   */
  updateToken(token: string): void {
    this.config.token = token;
    this.client.defaults.headers.common['Authorization'] = `Bearer ${token}`;
  }

  /**
   * Build OData query string from options
   */
  private buildQueryString(options: ODataQueryOptions): string {
    const params = new URLSearchParams();
    params.append('api-version', this.config.apiVersion);

    if (options.select && options.select.length > 0) {
      params.append('$select', options.select.join(','));
    }
    if (options.filter) {
      params.append('$filter', options.filter);
    }
    if (options.orderby) {
      params.append('$orderby', options.orderby);
    }
    if (options.top !== undefined) {
      params.append('$top', options.top.toString());
    }
    if (options.skip !== undefined) {
      params.append('$skip', options.skip.toString());
    }
    if (options.expand && options.expand.length > 0) {
      params.append('$expand', options.expand.join(','));
    }
    if (options.count) {
      params.append('$count', 'true');
    }

    return params.toString();
  }

  /**
   * Query an entity with OData options
   */
  async queryEntity<T = any>(
    entity: string,
    options: ODataQueryOptions = {}
  ): Promise<ODataResponse<T>> {
    try {
      const queryString = this.buildQueryString(options);
      const url = `/${entity}?${queryString}`;
      
      const response = await this.client.get<ODataResponse<T>>(url);
      return response.data;
    } catch (error) {
      throw this.handleError(error);
    }
  }

  /**
   * Execute a raw OData query URL
   */
  async executeRawQuery<T = any>(url: string): Promise<ODataResponse<T>> {
    try {
      // Ensure api-version is included
      const separator = url.includes('?') ? '&' : '?';
      const fullUrl = url.includes('api-version') 
        ? url 
        : `${url}${separator}api-version=${this.config.apiVersion}`;
      
      const response = await this.client.get<ODataResponse<T>>(fullUrl);
      return response.data;
    } catch (error) {
      throw this.handleError(error);
    }
  }

  /**
   * Get entity metadata from $metadata endpoint
   */
  async getMetadata(): Promise<any> {
    if (this.metadataCache.has('$metadata')) {
      return this.metadataCache.get('$metadata');
    }

    try {
      const response = await this.client.get('/$metadata', {
        params: { 'api-version': this.config.apiVersion },
        headers: { 'Accept': 'application/xml' }
      });
      
      this.metadataCache.set('$metadata', response.data);
      return response.data;
    } catch (error) {
      throw this.handleError(error);
    }
  }

  /**
   * Get schema for a specific entity
   */
  async getEntitySchema(entity: string): Promise<any> {
    if (this.metadataCache.has(entity)) {
      return this.metadataCache.get(entity);
    }

    try {
      // First try to get full metadata
      const metadata = await this.getMetadata();
      
      // For now, return a simplified schema indication
      // Full XML parsing would require additional library
      const schema = {
        entity,
        note: 'Full schema available in $metadata endpoint',
        metadata_url: `${this.config.baseUrl}/$metadata?api-version=${this.config.apiVersion}`
      };
      
      this.metadataCache.set(entity, schema);
      return schema;
    } catch (error) {
      throw this.handleError(error);
    }
  }

  /**
   * Test connection to the API
   */
  async testConnection(): Promise<boolean> {
    try {
      // Try to query a lightweight entity
      await this.queryEntity('dates', { top: 1 });
      return true;
    } catch (error) {
      return false;
    }
  }

  /**
   * Handle and normalize errors
   */
  private handleError(error: unknown): DataWarehouseError {
    if (axios.isAxiosError(error)) {
      const axiosError = error as AxiosError;
      
      if (axiosError.response) {
        // Server responded with error
        const data = axiosError.response.data as any;
        return {
          code: `HTTP_${axiosError.response.status}`,
          message: data?.error?.message || axiosError.message,
          details: data
        };
      } else if (axiosError.request) {
        // Request made but no response
        return {
          code: 'NO_RESPONSE',
          message: 'No response received from server',
          details: axiosError.message
        };
      }
    }

    // Unknown error
    return {
      code: 'UNKNOWN_ERROR',
      message: error instanceof Error ? error.message : 'Unknown error occurred',
      details: error
    };
  }
}
