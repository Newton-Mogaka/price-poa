"""
Test for the LLM router fallback mechanism.
"""
import pytest
from unittest.mock import AsyncMock, patch
from api.app.agent.llm.router import llm_router


@pytest.mark.asyncio
async def test_router_primary_success():
    """Test that router uses primary client when it succeeds."""
    # Mock the primary client to return a successful response
    mock_response = {
        "content": "Primary provider response",
        "tool_calls": []
    }

    with patch.object(llm_router.primary_client, 'chat', return_value=mock_response) as mock_primary:
        # Ensure fallback client is not called
        with patch.object(llm_router.fallback_client, 'chat') as mock_fallback:
            messages = [{"role": "user", "content": "test"}]
            result = await llm_router.chat(messages=messages)

            # Verify primary was called
            mock_primary.assert_called_once()
            # Verify fallback was not called
            mock_fallback.assert_not_called()
            # Verify we got the primary response
            assert result["content"] == "Primary provider response"


@pytest.mark.asyncio
async def test_router_primary_fail_fallback_success():
    """Test that router falls back to fallback client when primary fails."""
    # Mock primary client to raise an exception
    with patch.object(llm_router.primary_client, 'chat', side_effect=Exception("Primary failed")):
        # Mock fallback client to return a successful response
        mock_response = {
            "content": "Fallback provider response",
            "tool_calls": []
        }
        with patch.object(llm_router.fallback_client, 'chat', return_value=mock_response) as mock_fallback:
            messages = [{"role": "user", "content": "test"}]
            result = await llm_router.chat(messages=messages)

            # Verify primary was called
            llm_router.primary_client.chat.assert_called_once()
            # Verify fallback was called
            mock_fallback.assert_called_once()
            # Verify we got the fallback response
            assert result["content"] == "Fallback provider response"


@pytest.mark.asyncio
async def test_router_both_fail():
    """Test that router raises exception when both clients fail."""
    # Mock both clients to raise exceptions
    with patch.object(llm_router.primary_client, 'chat', side_effect=Exception("Primary failed")):
        with patch.object(llm_router.fallback_client, 'chat', side_effect=Exception("Fallback failed")):
            messages = [{"role": "user", "content": "test"}]

            # Should raise an exception
            with pytest.raises(Exception) as exc_info:
                await llm_router.chat(messages=messages)

            # Check that the error message indicates both failed
            assert "All LLM providers failed" in str(exc_info.value)


@pytest.mark.asyncio
async def test_router_with_tools():
    """Test that router correctly passes tools parameter."""
    mock_response = {
        "content": "Response with tools",
        "tool_calls": [{"id": "1", "name": "test_tool", "arguments": '{"param": "value"}'}]
    }

    with patch.object(llm_router.primary_client, 'chat', return_value=mock_response) as mock_primary:
        messages = [{"role": "user", "content": "test"}]
        tools = [{"type": "function", "function": {"name": "test_tool"}}]

        result = await llm_router.chat(messages=messages, tools=tools)

        # Verify the tools parameter was passed
        mock_primary.assert_called_once()
        call_args = mock_primary.call_args
        assert call_args[1]['tools'] == tools
        assert result["tool_calls"][0]["name"] == "test_tool"


if __name__ == "__main__":
    # Allow running directly for manual testing
    pytest.main([__file__, "-v"])