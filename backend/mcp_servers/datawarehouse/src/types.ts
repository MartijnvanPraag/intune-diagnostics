/**
 * Type definitions for Intune Data Warehouse MCP Server
 */

export interface DataWarehouseConfig {
  baseUrl: string;
  apiVersion: string;
  token: string;
}

export interface ODataQueryOptions {
  select?: string[];
  filter?: string;
  orderby?: string;
  top?: number;
  skip?: number;
  expand?: string[];
  count?: boolean;
}

export interface EntityMetadata {
  name: string;
  namespace: string;
  properties: PropertyMetadata[];
  navigationProperties?: NavigationPropertyMetadata[];
}

export interface PropertyMetadata {
  name: string;
  type: string;
  nullable: boolean;
  maxLength?: number;
}

export interface NavigationPropertyMetadata {
  name: string;
  type: string;
  isCollection: boolean;
}

export interface ODataResponse<T = any> {
  '@odata.context'?: string;
  '@odata.count'?: number;
  '@odata.nextLink'?: string;
  value: T[];
}

export interface DataWarehouseError {
  code: string;
  message: string;
  details?: any;
}

export interface QueryEntityArgs {
  entity: string;
  select?: string;
  filter?: string;
  orderby?: string;
  top?: number;
  skip?: number;
  expand?: string;
}

export interface ExecuteODataQueryArgs {
  url: string;
}
