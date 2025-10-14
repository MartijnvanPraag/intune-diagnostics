"""
Script to reformat instructions.md:
1. Change non-scenario ### headings to ####
2. Add metadata to scenario ### headings
"""

import re

# Define which sections are NOT scenarios (should be changed to ####)
NON_SCENARIOS = [
    "Output Rules (Mandatory)",
    "Scope Minimization Rule (Mandatory)",
    "Application Enforcement Status Legend",
    "Enrollment Type Legend",
    "Multi-Value Column Expansion Pattern (Readable Tables)"
]

# Define metadata for each scenario
SCENARIO_METADATA = {
    "Device Details": {
        "slug": "device-details",
        "domain": "device",
        "keywords": "device, details, os version, serial number, enrolled by, primary user, aad device, last contact, device name",
        "required_identifiers": "DeviceId",
        "aliases": "device info, device information, basic device data",
        "description": "Retrieves comprehensive device information including OS version, enrollment details, primary user, serial number, and Azure AD identifiers"
    },
    "User ID Lookup": {
        "slug": "user-id-lookup",
        "domain": "user",
        "keywords": "user, userid, user id, primary user, account",
        "required_identifiers": "DeviceId",
        "aliases": "find user, get user id, user association",
        "description": "Extracts the user ID(s) associated with a device from central Intune telemetry; prefer non-all-zero GUID as primary user"
    },
    "Tenant Information": {
        "slug": "tenant-information",
        "domain": "tenant",
        "keywords": "tenant, context id, flighting, scale unit, tenant name",
        "required_identifiers": "AccountId",
        "aliases": "tenant info, tenant details, context information",
        "description": "Retrieves tenant metadata including ContextId, flighting tags, tenant name, and scale unit assignment"
    },
    "Device Compliance Status (Last 10 Days)": {
        "slug": "device-compliance-status",
        "domain": "compliance",
        "keywords": "compliance, compliant, noncompliant, policy state change, compliance status",
        "required_identifiers": "DeviceId",
        "aliases": "compliance check, compliance history, device compliance",
        "description": "Retrieves device compliance status changes over the last 10 days including state transitions and timestamps"
    },
    "Policy / Setting Status and Assignments": {
        "slug": "policy-setting-status",
        "domain": "policy",
        "keywords": "policy, setting status, configuration, conflict, payload, policy assignment",
        "required_identifiers": "DeviceId, ContextId",
        "aliases": "policy status, settings check, configuration status",
        "description": "Retrieves policy and setting status per device including conflicts, errors, and policy assignments for the tenant"
    },
    "Effective Group Memberships and Troubleshooting": {
        "slug": "effective-groups",
        "domain": "group",
        "keywords": "group, effective group, targeting, assignment scope, group membership",
        "required_identifiers": "DeviceId, AccountId",
        "aliases": "group assignment, group targeting, effective group check",
        "description": "Retrieves effective group memberships and troubleshoots policy targeting by analyzing group assignments and deployments"
    },
    "MAM Policy": {
        "slug": "mam-policy",
        "domain": "mam",
        "keywords": "mam, mobile application management, app protection",
        "required_identifiers": "DeviceId, ContextId",
        "aliases": "app protection policy, mam status",
        "description": "Retrieves all MAM (Mobile Application Management) policies deployed to the device"
    },
    "Applications": {
        "slug": "applications",
        "domain": "application",
        "keywords": "app, application, install, deployment, application status",
        "required_identifiers": "DeviceId, ContextId",
        "aliases": "app status, application deployment, installed apps",
        "description": "Retrieves application status, deployment details, and installation attempts for the device"
    },
    "Third Party Integration(JAMF)": {
        "slug": "third-party-integration",
        "domain": "integration",
        "keywords": "jamf, third party, partner, integration",
        "required_identifiers": "AccountId",
        "aliases": "jamf integration, partner service",
        "description": "Retrieves third-party integration status (JAMF) for the tenant"
    },
    "Identify conflicting DCv1 and DCv2 policies": {
        "slug": "dcv1-dcv2-conflicts",
        "domain": "policy",
        "keywords": "dcv1, dcv2, conflict, device configuration, policy conflict",
        "required_identifiers": "DeviceId",
        "aliases": "configuration conflicts, dc conflicts",
        "description": "Identifies conflicting Device Configuration v1 and v2 policies affecting the device"
    },
    "Autopilot Summary Investigation Workflow": {
        "slug": "autopilot-summary",
        "domain": "autopilot",
        "keywords": "autopilot, esp, enrollment status page, ztd, zero touch, provisioning",
        "required_identifiers": "DeviceId",
        "aliases": "autopilot status, autopilot investigation, esp status",
        "description": "Comprehensive Autopilot workflow including ZTD registration, ESP policy, provisioning progress, and timeline"
    },
    "Advanced Scenario: Device Timeline": {
        "slug": "device-timeline",
        "domain": "device",
        "keywords": "timeline, chronological, history, events, trace, investigation",
        "required_identifiers": "DeviceId, StartTime, EndTime",
        "aliases": "event timeline, device history, chronological events",
        "description": "Aggregates chronological timeline of device events including compliance, policy, application, and management activities within a specified time range"
    }
}

def format_metadata(title):
    """Generate metadata HTML comment for a scenario."""
    if title not in SCENARIO_METADATA:
        return ""
    
    meta = SCENARIO_METADATA[title]
    metadata_lines = [
        "<!-- ",
        "Metadata:",
        f"- slug: {meta['slug']}",
        f"- domain: {meta['domain']}",
        f"- keywords: {meta['keywords']}",
        f"- required_identifiers: {meta['required_identifiers']}",
        f"- aliases: {meta['aliases']}",
        f"- description: {meta['description']}",
        "-->"
    ]
    return "\n".join(metadata_lines)

def process_file(input_path, output_path):
    """Process the instructions.md file."""
    with open(input_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    lines = content.split('\n')
    output_lines = []
    i = 0
    
    while i < len(lines):
        line = lines[i]
        
        # Check if this is a ### heading
        if line.startswith('### '):
            title = line[4:].strip()
            
            # Check if it's a non-scenario
            if title in NON_SCENARIOS:
                # Change to ####
                output_lines.append('####' + line[3:])
            else:
                # It's a scenario - add metadata
                output_lines.append(line)
                if title in SCENARIO_METADATA:
                    output_lines.append(format_metadata(title))
        else:
            output_lines.append(line)
        
        i += 1
    
    # Write output
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(output_lines))
    
    print(f"✓ Processed {input_path}")
    print(f"✓ Output written to {output_path}")
    
    # Count changes
    scenarios_with_metadata = len([t for t in SCENARIO_METADATA.keys()])
    non_scenarios_changed = len(NON_SCENARIOS)
    print(f"✓ Added metadata to {scenarios_with_metadata} scenarios")
    print(f"✓ Changed {non_scenarios_changed} non-scenario sections to #### level")

if __name__ == "__main__":
    process_file("instructions.md", "instructions.md")
