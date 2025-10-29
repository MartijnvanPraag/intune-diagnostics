#!/usr/bin/env node

/**
 * MCP Server for Intune Data Warehouse API
 */

import { Server } from '@modelcontextprotocol/sdk/server/index.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
  Tool
} from '@modelcontextprotocol/sdk/types.js';
import { DataWarehouseClient } from './client.js';
import { KNOWN_ENTITIES, ENTITY_DESCRIPTIONS } from './entities.js';
import { QueryEntityArgs, ExecuteODataQueryArgs } from './types.js';
import { z } from 'zod';

/**
 * Argument schemas for tools
 */
const QueryEntityArgsSchema = z.object({
  entity: z.string().describe('Entity name (e.g., devices, users, mobileApps)'),
  select: z.string().optional().describe('Comma-separated list of fields to select'),
  filter: z.string().optional().describe('OData filter expression (e.g., "deviceId eq \'abc-123\'")'),
  orderby: z.string().optional().describe('OData orderby expression (e.g., "lastContact desc")'),
  top: z.number().optional().describe('Maximum number of results to return'),
  skip: z.number().optional().describe('Number of results to skip (for pagination)'),
  expand: z.string().optional().describe('Comma-separated list of navigation properties to expand')
});

const ExecuteODataQueryArgsSchema = z.object({
  url: z.string().describe('Full OData query URL (relative to base URL)')
});

/**
 * Main server class
 */
class DataWarehouseServer {
  private server: Server;
  private client: DataWarehouseClient | null = null;

  constructor() {
    this.server = new Server(
      {
        name: 'intune-datawarehouse-mcp-server',
        version: '0.1.0',
      },
      {
        capabilities: {
          tools: {},
        },
      }
    );

    this.setupHandlers();
    this.setupErrorHandling();
  }

  private setupErrorHandling(): void {
    this.server.onerror = (error) => {
      console.error('[MCP Error]', error);
    };

    process.on('SIGINT', async () => {
      await this.server.close();
      process.exit(0);
    });
  }

  private setupHandlers(): void {
    // List available tools
    this.server.setRequestHandler(ListToolsRequestSchema, async () => {
      const tools: Tool[] = [
        {
          name: 'list_entities',
          description: 'List all available Data Warehouse entities with descriptions',
          inputSchema: {
            type: 'object',
            properties: {},
            required: []
          }
        },
        {
          name: 'get_entity_schema',
          description: 'Get schema information for a specific entity',
          inputSchema: {
            type: 'object',
            properties: {
              entity: {
                type: 'string',
                description: 'Entity name (e.g., devices, users, mobileApps)'
              }
            },
            required: ['entity']
          }
        },
        {
          name: 'query_entity',
          description: 'Query an entity with OData filters and options',
          inputSchema: {
            type: 'object',
            properties: {
              entity: {
                type: 'string',
                description: 'Entity name (e.g., devices, users, mobileApps)'
              },
              select: {
                type: 'string',
                description: 'Comma-separated list of fields to select'
              },
              filter: {
                type: 'string',
                description: 'OData filter expression (e.g., "deviceId eq \'abc-123\'")'
              },
              orderby: {
                type: 'string',
                description: 'OData orderby expression (e.g., "lastContact desc")'
              },
              top: {
                type: 'number',
                description: 'Maximum number of results to return'
              },
              skip: {
                type: 'number',
                description: 'Number of results to skip (for pagination)'
              },
              expand: {
                type: 'string',
                description: 'Comma-separated list of navigation properties to expand'
              }
            },
            required: ['entity']
          }
        },
        {
          name: 'execute_odata_query',
          description: 'Execute a raw OData query URL',
          inputSchema: {
            type: 'object',
            properties: {
              url: {
                type: 'string',
                description: 'Full OData query URL (relative to base URL)'
              }
            },
            required: ['url']
          }
        }
      ];

      return { tools };
    });

    // Handle tool calls
    this.server.setRequestHandler(CallToolRequestSchema, async (request) => {
      if (!this.client) {
        throw new Error('Data Warehouse client not initialized. Token must be provided via environment.');
      }

      try {
        switch (request.params.name) {
          case 'list_entities':
            return await this.handleListEntities();
          
          case 'get_entity_schema':
            return await this.handleGetEntitySchema(request.params.arguments);
          
          case 'query_entity':
            return await this.handleQueryEntity(request.params.arguments);
          
          case 'execute_odata_query':
            return await this.handleExecuteODataQuery(request.params.arguments);
          
          default:
            throw new Error(`Unknown tool: ${request.params.name}`);
        }
      } catch (error) {
        console.error(`[DataWarehouse MCP] Tool error for ${request.params.name}:`, error);
        
        // Extract detailed error information
        let errorDetails: any = { error: 'Unknown error' };
        
        if (error instanceof Error) {
          errorDetails = {
            error: error.message,
            name: error.name,
            stack: error.stack?.split('\n').slice(0, 5).join('\n') // First 5 lines of stack
          };
          
          // Check if it's our custom error object from handleError
          if ((error as any).code) {
            errorDetails.code = (error as any).code;
            errorDetails.details = (error as any).details;
          }
        } else if (typeof error === 'object' && error !== null) {
          errorDetails = error;
        } else {
          errorDetails.error = String(error);
        }
        
        return {
          content: [
            {
              type: 'text',
              text: JSON.stringify(errorDetails, null, 2)
            }
          ]
        };
      }
    });
  }

  private async handleListEntities() {
    const entities = KNOWN_ENTITIES.map(entity => {
      const desc = ENTITY_DESCRIPTIONS[entity];
      return {
        name: entity,
        description: desc?.description || 'No description available',
        category: desc?.category || 'unknown'
      };
    });

    return {
      content: [
        {
          type: 'text',
          text: JSON.stringify({ entities }, null, 2)
        }
      ]
    };
  }

  private async handleGetEntitySchema(args: any) {
    const entity = args.entity as string;
    
    if (!this.client) {
      throw new Error('Client not initialized');
    }

    const schema = await this.client.getEntitySchema(entity);
    
    return {
      content: [
        {
          type: 'text',
          text: JSON.stringify(schema, null, 2)
        }
      ]
    };
  }

  private async handleQueryEntity(args: any) {
    const validated = QueryEntityArgsSchema.parse(args);
    
    if (!this.client) {
      throw new Error('Client not initialized');
    }

    const options = {
      select: validated.select ? validated.select.split(',').map(s => s.trim()) : undefined,
      filter: validated.filter,
      orderby: validated.orderby,
      top: validated.top,
      skip: validated.skip,
      expand: validated.expand ? validated.expand.split(',').map(s => s.trim()) : undefined
    };

    const result = await this.client.queryEntity(validated.entity, options);
    
    return {
      content: [
        {
          type: 'text',
          text: JSON.stringify(result, null, 2)
        }
      ]
    };
  }

  private async handleExecuteODataQuery(args: any) {
    const validated = ExecuteODataQueryArgsSchema.parse(args);
    
    if (!this.client) {
      throw new Error('Client not initialized');
    }

    const result = await this.client.executeRawQuery(validated.url);
    
    return {
      content: [
        {
          type: 'text',
          text: JSON.stringify(result, null, 2)
        }
      ]
    };
  }

  async run(): Promise<void> {
    // Initialize client with config from environment
    const baseUrl = process.env.INTUNE_DATAWAREHOUSE_URL;
    const token = process.env.INTUNE_DATAWAREHOUSE_TOKEN;
    const apiVersion = process.env.INTUNE_DATAWAREHOUSE_API_VERSION || 'v1.0';

    if (!baseUrl || !token) {
      console.error('Error: INTUNE_DATAWAREHOUSE_URL and INTUNE_DATAWAREHOUSE_TOKEN must be set');
      process.exit(1);
    }

    this.client = new DataWarehouseClient({
      baseUrl,
      apiVersion,
      token
    });

    // Test connection
    const connected = await this.client.testConnection();
    if (!connected) {
      console.error('Warning: Failed to connect to Data Warehouse API');
    }

    const transport = new StdioServerTransport();
    await this.server.connect(transport);
    
    console.error('Intune Data Warehouse MCP server running on stdio');
  }
}

// Start server
const server = new DataWarehouseServer();
server.run().catch(console.error);
