# Intune Diagnostics: Engineering Demo Script

## 1. Introduction: The Observability Challenge
"Current Intune diagnostic workflows are often fragmented. Engineers are required to context-switch between the Endpoint Manager portal, Data Warehouse entities, and raw Kusto logs to triage device state. This lack of unified observability increases cognitive load and extends Mean Time to Resolution. The Intune Diagnostics application addresses this by implementing an agentic architecture designed to unify these disparate data streams into a coherent investigative interface."

## 2. Architectural Overview
"The system is built upon a robust Agent Framework. Requests are handled by a Magentic Orchestrator which manages the lifecycle of an AI Agent. This agent leverages the Model Context Protocol, or MCP, to abstract data retrieval. We utilize specialized MCP servers: an Instructions MCP for deterministic query retrieval, a Data Warehouse MCP for historical state, and a Kusto MCP for real-time telemetry. This decoupled architecture allows the agent to dynamically select the appropriate toolchain based on the semantic intent of the user's query."

## 3. Deterministic Execution via Scenarios
"For standard diagnostic tasks, the system utilizes a 'Scenario' pattern. When a user queries for device compliance, the Orchestrator identifies the intent and retrieves a pre-validated execution plan from the Instructions MCP. This ensures that queries are executed deterministically against the OData endpoints or Kusto clusters, returning structured, strongly-typed data tables. This eliminates syntax errors and ensures consistency in diagnostic reporting."

## 4. Advanced Device Timeline Aggregation
"For complex troubleshooting, we employ the Advanced Device Timeline scenario. This demonstrates the agent's ability to perform multi-step reasoning. The system aggregates data from orthogonal sources—correlating compliance state changes, policy propagation events, and application installation telemetry. It constructs a unified temporal view, normalizing timestamps across different logging subsystems to reconstruct the exact sequence of events on the endpoint."

## 5. Visual Synthesis and Root Cause Analysis
"To facilitate rapid root cause analysis, the system synthesizes this aggregated data into a visual representation. By rendering the event stream as a Gantt chart, engineers can visually correlate concurrent activities. This allows for the immediate identification of race conditions—such as a compliance check failing simultaneously with a policy application—transforming raw log data into actionable engineering insights."
