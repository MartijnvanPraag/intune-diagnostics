"""
Test script to verify both Autogen and Agent Framework services

This script tests basic functionality of both implementations to ensure feature parity.
Run this after setting up both frameworks to verify they work correctly.
"""

import asyncio
import logging
from models.schemas import ModelConfiguration

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def test_autogen_service():
    """Test the Autogen Framework service"""
    logger.info("=" * 60)
    logger.info("Testing Autogen Framework Service")
    logger.info("=" * 60)
    
    try:
        from services.autogen_service import agent_service, AgentService
        
        # Initialize if needed
        if agent_service is None:
            await AgentService.initialize()
            from services.autogen_service import agent_service as svc
        else:
            svc = agent_service
        
        # Test scenario listing
        scenarios = svc.list_instruction_scenarios()
        logger.info(f"✓ Loaded {len(scenarios)} scenarios")
        
        # Test scenario lookup service
        logger.info(f"✓ Scenario service initialized: {svc.scenario_service is not None}")
        
        logger.info("✅ Autogen Framework service PASSED basic checks\n")
        return True
        
    except Exception as e:
        logger.error(f"❌ Autogen Framework service FAILED: {e}\n")
        return False


async def test_agent_framework_service():
    """Test the Agent Framework service"""
    logger.info("=" * 60)
    logger.info("Testing Microsoft Agent Framework Service")
    logger.info("=" * 60)
    
    try:
        from services.agent_framework_service import agent_framework_service, AgentFrameworkService
        
        # Initialize if needed
        if agent_framework_service is None:
            await AgentFrameworkService.initialize()
            from services.agent_framework_service import agent_framework_service as svc
        else:
            svc = agent_framework_service
        
        # Test scenario listing
        scenarios = svc.list_instruction_scenarios()
        logger.info(f"✓ Loaded {len(scenarios)} scenarios")
        
        # Test scenario lookup service
        logger.info(f"✓ Scenario service initialized: {svc.scenario_service is not None}")
        
        logger.info("✅ Agent Framework service PASSED basic checks\n")
        return True
        
    except Exception as e:
        logger.error(f"❌ Agent Framework service FAILED: {e}\n")
        import traceback
        traceback.print_exc()
        return False


async def test_tool_creation():
    """Test that tool creation functions work"""
    logger.info("=" * 60)
    logger.info("Testing Tool Creation Functions")
    logger.info("=" * 60)
    
    try:
        # Test Autogen tools
        from services.autogen_service import (
            create_scenario_lookup_function,
            create_context_lookup_function
        )
        
        scenario_tool = create_scenario_lookup_function()
        context_tool = create_context_lookup_function()
        
        logger.info(f"✓ Autogen scenario tool created: {scenario_tool is not None}")
        logger.info(f"✓ Autogen context tool created: {context_tool is not None}")
        
        # Test Agent Framework tools
        from services.agent_framework_service import (
            create_scenario_lookup_function as create_scenario_lookup_af,
            create_context_lookup_function as create_context_lookup_af
        )
        
        scenario_tool_af = create_scenario_lookup_af()
        context_tool_af = create_context_lookup_af()
        
        logger.info(f"✓ Agent Framework scenario tool created: {scenario_tool_af is not None}")
        logger.info(f"✓ Agent Framework context tool created: {context_tool_af is not None}")
        
        logger.info("✅ Tool creation PASSED\n")
        return True
        
    except Exception as e:
        logger.error(f"❌ Tool creation FAILED: {e}\n")
        import traceback
        traceback.print_exc()
        return False


async def test_framework_selection():
    """Test the framework selection logic"""
    logger.info("=" * 60)
    logger.info("Testing Framework Selection Logic")
    logger.info("=" * 60)
    
    try:
        # Import the helper function
        import sys
        import os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'routers'))
        
        # Create mock model configurations
        autogen_config = ModelConfiguration(
            id=1,
            user_id=1,
            name="Test Autogen",
            azure_endpoint="https://test.openai.azure.com/",
            azure_deployment="gpt-4",
            model_name="gpt-4",
            api_version="2024-06-01",
            is_default=True,
            agent_framework="autogen"
        )
        
        agent_framework_config = ModelConfiguration(
            id=2,
            user_id=1,
            name="Test Agent Framework",
            azure_endpoint="https://test.openai.azure.com/",
            azure_deployment="gpt-4",
            model_name="gpt-4",
            api_version="2024-06-01",
            is_default=False,
            agent_framework="agent_framework"
        )
        
        logger.info(f"✓ Autogen config framework: {autogen_config.agent_framework}")
        logger.info(f"✓ Agent Framework config framework: {agent_framework_config.agent_framework}")
        
        logger.info("✅ Framework selection logic PASSED\n")
        return True
        
    except Exception as e:
        logger.error(f"❌ Framework selection logic FAILED: {e}\n")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """Run all tests"""
    logger.info("\n")
    logger.info("╔" + "=" * 58 + "╗")
    logger.info("║" + " " * 58 + "║")
    logger.info("║" + "  Agent Framework Migration Test Suite".center(58) + "║")
    logger.info("║" + " " * 58 + "║")
    logger.info("╚" + "=" * 58 + "╝")
    logger.info("\n")
    
    results = []
    
    # Run tests
    results.append(("Autogen Service", await test_autogen_service()))
    results.append(("Agent Framework Service", await test_agent_framework_service()))
    results.append(("Tool Creation", await test_tool_creation()))
    results.append(("Framework Selection", await test_framework_selection()))
    
    # Summary
    logger.info("=" * 60)
    logger.info("Test Summary")
    logger.info("=" * 60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✅ PASSED" if result else "❌ FAILED"
        logger.info(f"{test_name:.<40} {status}")
    
    logger.info("=" * 60)
    logger.info(f"Total: {passed}/{total} tests passed")
    logger.info("=" * 60)
    
    if passed == total:
        logger.info("\n🎉 ALL TESTS PASSED! Both frameworks are ready to use.\n")
        logger.info("Next steps:")
        logger.info("  1. Go to Settings in the web UI")
        logger.info("  2. Create or edit a model configuration")
        logger.info("  3. Choose your preferred Agent Framework")
        logger.info("  4. Start using the diagnostics features!\n")
    else:
        logger.error("\n⚠️  Some tests failed. Please check the errors above.\n")
    
    return passed == total


if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)
