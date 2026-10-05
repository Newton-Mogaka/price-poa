"""
Simple CLI to test the agent LLM router.
Usage: python -m api.app.agent.scripts.chat_cli
"""
import asyncio
import sys
import os

# Add the project root to the path so we can import api modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../../..'))

from api.app.agent.llm.router import llm_router
from api.app.agent.config import settings


async def test_llm_router():
    """Test the LLM router with a simple request."""
    print("Testing LLM router...")
    print(f"Agent enabled: {settings.AGENT_ENABLED}")
    print(f"Groq API key set: {bool(settings.GROQ_API_KEY)}")
    print(f"Anthropic API key set: {bool(settings.ANTHROPIC_API_KEY)}")
    print(f"Primary model: {settings.AGENT_PRIMARY_MODEL}")
    print(f"Fallback model: {settings.AGENT_FALLBACK_MODEL}")

    # Test messages
    messages = [
        {"role": "user", "content": "Hello, how are you? Respond in one short sentence."}
    ]

    try:
        print("\nSending test message to LLM router...")
        response = await llm_router.chat(messages=messages)
        print(f"Response received: {response}")
        print(f"Content: {response.get('content', 'No content')}")
        print(f"Tool calls: {response.get('tool_calls', [])}")
        print("\n✅ LLM router test successful!")
        return True
    except Exception as e:
        print(f"\n❌ LLM router test failed: {e}")
        return False


if __name__ == "__main__":
    # Run the test
    result = asyncio.run(test_llm_router())
    sys.exit(0 if result else 1)