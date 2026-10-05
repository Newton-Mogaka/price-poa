"""
Test configuration and fixtures for the agent module.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock

# Mock LLM client for testing
class MockLLMClient:
    """Mock LLM client that returns predefined responses."""

    def __init__(self, response_content: str = "Test response", tool_calls: List[Dict] = None):
        self.response_content = response_content
        self.tool_calls = tool_calls or []

    async def chat(self, messages: List[Dict[str, Any]], tools: Optional[List[Dict[str, Any]]] = None,
                   tool_choice: str = "auto", temperature: float = 0.7, max_tokens: Optional[int] = None) -> Dict[str, Any]:
        return {
            "content": self.response_content,
            "tool_calls": self.tool_calls
        }

# Mock tool registry for testing
class MockToolRegistry:
    """Mock tool registry for testing."""

    def __init__(self):
        self.tools = {}

    def get_tool_specs(self) -> List[Dict[str, Any]]:
        return []

    async def execute_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        # Return success by default
        return {"success": True, "result": f"Mock result for {tool_name}"}

# Mock memory store for testing
class MockMemoryStore:
    """Mock memory store for testing."""

    def __init__(self):
        self.sessions = {}

    async def load(self, chat_id: int) -> Dict[str, Any]:
        return self.sessions.get(chat_id, {
            "chat_id": chat_id,
            "messages": [],
            "draft_list": [],
            "location": None,
            "updated_at": None
        })

    async def append_turn(self, chat_id: int, turn_data: Dict[str, Any]) -> None:
        if chat_id not in self.sessions:
            self.sessions[chat_id] = await self.load(chat_id)
        self.sessions[chat_id]["messages"].append(turn_data)

    async def set_draft_list(self, chat_id: int, draft_list: List[Dict[str, Any]]) -> None:
        if chat_id not in self.sessions:
            self.sessions[chat_id] = await self.load(chat_id)
        self.sessions[chat_id]["draft_list"] = draft_list

    async def get_draft_list(self, chat_id: int) -> List[Dict[str, Any]]:
        if chat_id not in self.sessions:
            self.sessions[chat_id] = await self.load(chat_id)
        return self.sessions[chat_id]["draft_list"]

    async def clear(self, chat_id: int) -> None:
        if chat_id in self.sessions:
            del self.sessions[chat_id]

# Test fixtures
@pytest.fixture
def mock_llm_client():
    """Fixture providing a mock LLM client."""
    return MockLLMClient()

@pytest.fixture
def mock_tool_registry():
    """Fixture providing a mock tool registry."""
    return MockToolRegistry()

@pytest.fixture
def mock_memory_store():
    """Fixture providing a mock memory store."""
    return MockMemoryStore()

# Sample test data
@pytest.fixture
def sample_product_data():
    """Sample product data for testing."""
    return [
        {
            "product_id": "1",
            "product_name": "Unga wa 2kg",
            "final_score": 0.95,
            "match_type": "exact"
        },
        {
            "product_id": "2",
            "product_name": "Sukari white 1kg",
            "final_score": 0.87,
            "match_type": "hybrid"
        }
    ]

@pytest.fixture
def sample_price_data():
    """Sample price data for testing."""
    return {
        "product_name": "Unga wa 2kg",
        "stores": [
            {
                "name": "Naivas - Nairobi",
                "price": "115 KES",
                "offer": False
            },
            {
                "name": "Carrefour - Nairobi",
                "price": "120 KES",
                "offer": True
            }
        ],
        "date": "2026-10-05"
    }