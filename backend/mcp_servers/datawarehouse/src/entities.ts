/**
 * Entity definitions and metadata for Intune Data Warehouse
 */

export const KNOWN_ENTITIES = [
  // Device Entities
  'devices',
  'devicePropertyHistories',
  'deviceEnrollmentTypes',
  'managementAgentTypes',
  'managementStates',
  'ownerTypes',
  
  // User Entities
  'users',
  'userDeviceAssociations',
  
  // Application Entities
  'mobileApps',
  'mobileAppInstallStatuses',
  'mobileAppDeviceUserInstallStatuses',
  
  // Policy & Configuration Entities
  'deviceConfigurationPolicies',
  'deviceCompliancePolicies',
  'deviceCompliancePolicySettingStateSummaries',
  'deviceCompliancePolicyDeviceStateSummaries',
  
  // MAM Entities
  'mamApplications',
  'mamApplicationInstances',
  'mamApplicationHealthStates',
  
  // Reference/Dimension Tables
  'dates',
  'platforms'
] as const;

export type KnownEntity = typeof KNOWN_ENTITIES[number];

export function isKnownEntity(entity: string): entity is KnownEntity {
  return KNOWN_ENTITIES.includes(entity as KnownEntity);
}

export interface EntityDescription {
  name: string;
  description: string;
  category: 'device' | 'user' | 'application' | 'policy' | 'mam' | 'reference';
}

export const ENTITY_DESCRIPTIONS: Record<string, EntityDescription> = {
  devices: {
    name: 'devices',
    description: 'Device inventory and properties',
    category: 'device'
  },
  devicePropertyHistories: {
    name: 'devicePropertyHistories',
    description: 'Device property change history',
    category: 'device'
  },
  users: {
    name: 'users',
    description: 'User information',
    category: 'user'
  },
  userDeviceAssociations: {
    name: 'userDeviceAssociations',
    description: 'User-to-device mappings',
    category: 'user'
  },
  mobileApps: {
    name: 'mobileApps',
    description: 'Mobile application catalog',
    category: 'application'
  },
  mobileAppInstallStatuses: {
    name: 'mobileAppInstallStatuses',
    description: 'App installation status per device/user',
    category: 'application'
  },
  deviceConfigurationPolicies: {
    name: 'deviceConfigurationPolicies',
    description: 'Device configuration policies (v1)',
    category: 'policy'
  },
  deviceCompliancePolicies: {
    name: 'deviceCompliancePolicies',
    description: 'Device compliance policies',
    category: 'policy'
  },
  dates: {
    name: 'dates',
    description: 'Date dimension for time-based queries',
    category: 'reference'
  },
  platforms: {
    name: 'platforms',
    description: 'Platform reference (iOS, Android, Windows)',
    category: 'reference'
  }
};
