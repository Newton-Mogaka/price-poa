#!/usr/bin/env python3
"""
Verification script for Stage 1 of the PricePoa LLM agent module.
This script tests that the basic components are working correctly.
"""
import asyncio
import sys
import os

# Add the project root to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

from api.app.agent.config import settings
from api.app.agent.llm.router import llm_router
from api.app.agent.schemas import AgentReply
from api.app.agent.service import handle_message


async def test_config_loading():
    """Test that configuration loads correctly."""
    print("Testing configuration loading...")
    print(f"AGENT_ENABLED: {settings.AGENT_ENABLED}")
    print(f"GROQ_API_KEY set: {bool(settings.GROQ_API_KEY)}")
    print(f"ANTHROPIC_API_KEY set: {bool(settings.ANTHROPIC_API_KEY)}")
    print(f"PRIMARY_MODEL: {settings.AGENT_PRIMARY_MODEL}")
    print(f"FALLBACK_MODEL: {settings.AGENT_FALLBACK_MODEL}")
    print(f"HISTORY_LIMIT: {settings.AGENT_HISTORY_LIMIT}")
    print(f"MAX_TOOL_ITERATIONS: {settings.AGENT_MAX_TOOL_ITERATIONS}")
    print(f"LLM_TIMEOUT_S: {settings.AGENT_LLM_TIMEOUT_S}")
    print(f"SESSION_TTL_DAYS: {settings.AGENT_SESSION_TTL_DAYS}")
    print("✅ Configuration test passed\n")
    return True


async def test_llm_router_initialization():
    """Test that the LLM router initializes correctly."""
    print("Testing LLM router initialization...")
    print(f"Primary client initialized: {llm_router.primary_client is not None}")
    print(f"Fallback client initialized: {llm_router.fallback_client is not None}")

    # If we have API keys, test that clients are properly initialized
    if settings.GROQ_API_KEY:
        assert llm_router.primary_client is not None, "Primary client should be initialized when GROQ_API_KEY is set"
        print("✅ Primary client initialized correctly")

    if settings.ANTHROPIC_API_KEY:
        assert llm_router.fallback_client is not None, "Fallback client should be initialized when ANTHROPIC_API_KEY is set"
        print("✅ Fallback client initialized correctly")

    print("✅ LLM router initialization test passed\n")
    return True


async def test_schemas():
    """Test that schemas work correctly."""
    print("Testing Pydantic schemas...")

    # Test AgentReply schema
    reply = AgentReply(
        text="Test response",
        used_tools=["search_products", "compare_variants"]
    )
    assert reply.text == "Test response"
    assert reply.used_tools == ["search_products", "compare_variants"]
    assert reply.image_path is None
    print("✅ AgentReply schema works")

    # Test ToolResult schema
    from api.app.agent.schemas import ToolResult
    tool_result = ToolResult(
        name="search_products",
        success=True,
        result={"test": "data"}
    )
    assert tool_result.name == "search_products"
    assert tool_result.success is True
    print("✅ ToolResult schema works")

    print("✅ Schemas test passed\n")
    return True


async def test_service_import():
    """Test that the service module can be imported and basic functions exist."""
    print("Testing service module import...")

    # Check that the handle_message function exists
    assert callable(handle_message), "handle_message should be a callable function"
    print("✅ handle_message function exists")

    # Check that we can import other key modules
    from api.app.agent.loop import AgentLoop
    from api.app.agent.memory.store import ChatMemoryStore
    from api.app.agent.tools.registry import ToolRegistry

    assert AgentLoop is not None
    assert ChatMemoryStore is not None
    assert ToolRegistry is not None
    print("✅ Key modules can be imported")

    print("✅ Service module test passed\n")
    return True


async def test_directory_structure():
    """Test that the directory structure is correct."""
    print("Testing directory structure...")

    base_path = os.path.join(os.path.dirname(__file__), "api", "app", "agent")

    # List of directories that should exist
    required_dirs = [
        "prompts",
        "llm",
        "tools",
        "adapters",
        "memory",
        "guardrails",
        "scripts",
        "tests"
    ]

    for dir_name in required_dirs:
        dir_path = os.path.join(base_path, dir_name)
        assert os.path.isdir(dir_path), f"Directory {dir_path} should exist"
        # Check that it has an __init__.py file
        init_file = os.path.join(dir_path, "__init__.py")
        assert os.path.isfile(init_file), f"File {init_file} should exist"

    # Check that key files exist
    key_files = [
        "__init__.py",
        "config.py",
        "schemas.py",
        "service.py",
        "loop.py",
        "README.md"
    ]

    for file_name in key_files:
        file_path = os.path.join(base_path, file_name)
        assert os.path.isfile(file_path), f"File {file_path} should exist"

    print("✅ Directory structure test passed\n")
    return True


async def main():
    """Run all verification tests."""
    print("=" * 60)
    print("PricePoa LLM Agent Module - Stage 1 Verification")
    print("=" * 60)
    print()

    tests = [
        test_directory_structure,
        test_config_loading,
        test_llm_router_initialization,
        test_schemas,
        test_service_import
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            result = await test()
            if result:
                passed += 1
            else:
                failed += 1
        except Exception as e:
            print(f"❌ {test.__name__} failed with exception: {e}")
            failed += 1

    print("=" * 60)
    print(f"Verification Results: {passed} passed, {failed} failed")
    print("=" * 60)

    if failed == 0:
        print("🎉 All Stage 1 verification tests passed!")
        print("The agent module skeleton, config, schemas, and LLM clients are ready.")
        return True
    else:
        print("❌ Some verification tests failed.")
        return False


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)