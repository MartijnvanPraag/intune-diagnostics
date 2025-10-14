"""
Test script for updated scenario lookup with metadata support
"""

import sys
from pathlib import Path

# Add backend to path
backend_path = Path(__file__).parent.parent / "backend"
sys.path.insert(0, str(backend_path))

from services.scenario_lookup_service import ScenarioLookupService
import logging

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

def test_metadata_parsing():
    """Test that metadata is correctly parsed from instructions.md"""
    print("\n" + "="*80)
    print("TEST 1: Metadata Parsing")
    print("="*80)
    
    instructions_path = Path(__file__).parent.parent / "instructions.md"
    service = ScenarioLookupService(instructions_path)
    
    # Check a few scenarios
    test_scenarios = [
        "Device Details",
        "Device Compliance Status (Last 10 Days)",
        "Autopilot Summary Investigation Workflow"
    ]
    
    for title in test_scenarios:
        normalized = service._normalize_title(title)
        scenario = service.scenarios_index.get(normalized)
        
        if scenario:
            print(f"\n✓ Scenario: {scenario.title}")
            print(f"  Slug: {scenario.slug}")
            print(f"  Domain: {scenario.domain}")
            print(f"  Aliases: {scenario.aliases}")
            print(f"  Required IDs: {scenario.required_identifiers}")
            print(f"  Keywords (first 10): {list(scenario.keywords)[:10]}")
        else:
            print(f"\n✗ Scenario not found: {title}")
    
    return service

def test_scenario_lookup(service):
    """Test scenario lookup with various queries"""
    print("\n" + "="*80)
    print("TEST 2: Scenario Lookup Accuracy")
    print("="*80)
    
    test_queries = [
        ("device compliance", "Device Compliance Status (Last 10 Days)"),
        ("device details", "Device Details"),
        ("device-details", "Device Details"),  # Test slug matching
        ("user id", "User ID Lookup"),
        ("tenant info", "Tenant Information"),
        ("autopilot", "Autopilot Summary Investigation Workflow"),
        ("esp", "Autopilot Summary Investigation Workflow"),
        ("dcv1 dcv2 conflict", "Identify conflicting DCv1 and DCv2 policies"),
        ("policy setting status", "Policy / Setting Status and Assignments"),
        ("application", "Applications"),
        ("mam", "MAM Policy"),
        ("effective groups", "Effective Group Memberships and Troubleshooting"),
        ("jamf", "Third Party Integration(JAMF)"),
        ("timeline", "Advanced Scenario: Device Timeline"),
    ]
    
    correct = 0
    total = len(test_queries)
    
    for query, expected_title in test_queries:
        results = service.find_scenarios_by_keywords(query, max_results=3)
        
        if results:
            top_match = service.scenario_lookup[results[0]].title
            is_correct = top_match == expected_title
            
            status = "✓" if is_correct else "✗"
            print(f"\n{status} Query: '{query}'")
            print(f"  Expected: {expected_title}")
            print(f"  Got:      {top_match}")
            
            if len(results) > 1:
                other_matches = [service.scenario_lookup[r].title for r in results[1:]]
                print(f"  Others:   {', '.join(other_matches)}")
            
            if is_correct:
                correct += 1
        else:
            print(f"\n✗ Query: '{query}'")
            print(f"  Expected: {expected_title}")
            print(f"  Got:      NO MATCHES")
    
    accuracy = (correct / total) * 100
    print(f"\n" + "="*80)
    print(f"ACCURACY: {correct}/{total} correct ({accuracy:.1f}%)")
    print("="*80)

def test_scenario_summary(service):
    """Test scenario summary generation"""
    print("\n" + "="*80)
    print("TEST 3: Scenario Summary (grouped by domain)")
    print("="*80)
    
    summary = service.get_scenario_summary()
    print(summary)

def test_edge_cases(service):
    """Test edge cases and special scenarios"""
    print("\n" + "="*80)
    print("TEST 4: Edge Cases")
    print("="*80)
    
    edge_cases = [
        "device",  # Ambiguous - could match multiple
        "compliance status",  # Should match Device Compliance
        "policy conflicts",  # Should match DCv1/DCv2
        "enrollment",  # Should match Autopilot
        "app status",  # Should match Applications
    ]
    
    for query in edge_cases:
        results = service.find_scenarios_by_keywords(query, max_results=3)
        matches = [service.scenario_lookup[r].title for r in results]
        print(f"\nQuery: '{query}'")
        print(f"  Matches: {matches if matches else 'NO MATCHES'}")

if __name__ == "__main__":
    try:
        service = test_metadata_parsing()
        test_scenario_lookup(service)
        test_scenario_summary(service)
        test_edge_cases(service)
        
        print("\n" + "="*80)
        print("ALL TESTS COMPLETED")
        print("="*80)
        
    except Exception as e:
        print(f"\n✗ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
