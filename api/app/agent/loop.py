"""
Agent tool-calling loop.
Handles the interaction between LLM, tools, and memory.
"""
import asyncio
import logging
from typing import Dict, Any, List, Optional
from .schemas import AgentReply, ToolResult, ChatTurn
from .memory.store import ChatMemoryStore
from .llm.router import llm_router
from .tools.registry import ToolRegistry
from .prompts.loader import load_system_prompt
from .guardrails.grounding import check_grounding
from .config import settings

logger = logging.getLogger(__name__)


class AgentLoop:
    """
    Main agent loop that handles tool usage and LLM interaction.
    """

    def __init__(self, memory_store: ChatMemoryStore):
        """
        Initialize the agent loop.

        Args:
            memory_store: Store for chat history and draft lists
        """
        self.memory_store = memory_store
        self.tool_registry = ToolRegistry()

    async def run(self, chat_id: int, text: str, user_ctx: Dict[str, Any]) -> AgentReply:
        """
        Run the agent loop for a single user message.

        Args:
            chat_id: Telegram chat ID
            text: User message text
            user_ctx: User context (location, etc.)

        Returns:
            AgentReply with the agent's response
        """
        try:
            # Load chat history and draft list from memory
            chat_session = await self.memory_store.load(chat_id)
            history = chat_session.get("messages", [])
            draft_list = chat_session.get("draft_list", [])

            # Build initial messages for the LLM
            messages = await self._build_initial_messages(
                chat_id, text, history, draft_list, user_ctx
            )

            # Get available tools
            tools = self.tool_registry.get_tool_specs()

            # Run the tool-calling loop
            final_response = await self._execute_tool_loop(
                messages, tools, chat_id
            )

            # Save the conversation to memory
            await self._save_conversation(
                chat_id, text, final_response, history, draft_list
            )

            return final_response

        except Exception as e:
            logger.error(f"Error in agent loop for chat_id {chat_id}: {e}", exc_info=True)
            return AgentReply(
                text="Sorry, I encountered an error. Please try again.",
                used_tools=[]
            )

    async def _build_initial_messages(
        self,
        chat_id: int,
        text: str,
        history: List[Dict[str, Any]],
        draft_list: List[Dict[str, Any]],
        user_ctx: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Build the initial message list for the LLM including system prompt and history.

        Args:
            chat_id: Telegram chat ID
            text: Current user message
            history: Previous chat messages
            draft_list: Current draft shopping list
            user_ctx: User context

        Returns:
            List of message dictionaries for the LLM
        """
        messages = []

        # Add system prompt
        system_prompt = load_system_prompt()
        messages.append({
            "role": "system",
            "content": system_prompt
        })

        # Add chat history (limited by AGENT_HISTORY_LIMIT)
        limited_history = history[-settings.AGENT_HISTORY_LIMIT:] if history else []
        for turn in limited_history:
            messages.append({
                "role": "user",
                "content": turn.get("user_message", "")
            })
            messages.append({
                "role": "assistant",
                "content": turn.get("agent_response", "")
            })

        # Add current user message
        messages.append({
            "role": "user",
            "content": text
        })

        return messages

    async def _execute_tool_loop(
        self,
        initial_messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        chat_id: int
    ) -> AgentReply:
        """
        Execute the tool-calling loop with the LLM.

        Args:
            initial_messages: Starting messages for the LLM
            tools: Available tool specifications
            chat_id: Telegram chat ID (for grounding context)

        Returns:
            AgentReply with final response
        """
        messages = initial_messages.copy()
        used_tools: List[str] = []
        iteration = 0

        while iteration < settings.AGENT_MAX_TOOL_ITERATIONS:
            iteration += 1
            logger.debug(f"Agent loop iteration {iteration} for chat_id {chat_id}")

            try:
                # Get response from LLM
                llm_response = await llm_router.chat(
                    messages=messages,
                    tools=tools if tools else None,
                    tool_choice="auto",
                    temperature=0.7,
                )

                # Extract content and tool calls
                content = llm_response.get("content", "")
                tool_calls = llm_response.get("tool_calls", [])

                # If no tool calls, we have a final response
                if not tool_calls:
                    # Check grounding before returning
                    grounded_content = await check_grounding(content, used_tools)
                    return AgentReply(
                        text=grounded_content,
                        used_tools=used_tools.copy()
                    )

                # Execute tool calls
                tool_results: List[ToolResult] = []
                for tool_call in tool_calls:
                    tool_name = tool_call["name"]
                    tool_args = tool_call["arguments"]

                    # Convert string arguments to dict if needed
                    if isinstance(tool_args, str):
                        import json
                        try:
                            tool_args = json.loads(tool_args)
                        except json.JSONDecodeError:
                            tool_args = {}

                    try:
                        logger.debug(f"Executing tool: {tool_name} with args: {tool_args}")
                        result = await self.tool_registry.execute_tool(tool_name, tool_args)

                        tool_result = ToolResult(
                            name=tool_name,
                            success=True,
                            result=result if isinstance(result, dict) else {"result": result},
                        )
                        tool_results.append(tool_result)
                        used_tools.append(tool_name)

                        logger.debug(f"Tool {tool_name} executed successfully")

                    except Exception as e:
                        logger.error(f"Error executing tool {tool_name}: {e}")
                        tool_result = ToolResult(
                            name=tool_name,
                            success=False,
                            result={},
                            error=str(e)
                        )
                        tool_results.append(tool_result)

                # Add LLM response and tool results to messages
                messages.append({
                    "role": "assistant",
                    "content": content,
                })

                # Add tool results as a user message for the next iteration
                if tool_results:
                    tool_results_text = self._format_tool_results(tool_results)
                    messages.append({
                        "role": "user",
                        "content": tool_results_text,
                    })

            except Exception as e:
                logger.error(f"Error in LLM call during iteration {iteration}: {e}")
                # If we've had at least one successful iteration, return what we have
                if iteration > 1 and used_tools:
                    grounded_content = await check_grounding("I encountered an error but here's what I found so far:", used_tools)
                    return AgentReply(
                        text=grounded_content,
                        used_tools=used_tools.copy()
                    )
                else:
                    # First iteration failed, return error message
                    return AgentReply(
                        text="Sorry, I encountered an error processing your request.",
                        used_tools=used_tools
                    )

        # If we've exhausted iterations, return a final response
        logger.warning(f"Agent loop exceeded max iterations ({settings.AGENT_MAX_TOOL_ITERATIONS}) for chat_id {chat_id}")
        final_content = "I've processed your request with the available information. Let me know if you need anything else."
        grounded_content = await check_grounding(final_content, used_tools)
        return AgentReply(
            text=grounded_content,
            used_tools=used_tools.copy()
        )

    def _format_tool_results(self, tool_results: List[ToolResult]) -> str:
        """
        Format tool results for feeding back to the LLM.

        Args:
            tool_results: List of tool execution results

        Returns:
            Formatted string representation of tool results
        """
        if not tool_results:
            return "No tool results."

        formatted_parts = []
        for result in tool_results:
            if result.success:
                formatted_parts.append(f"Tool '{result.name}' succeeded: {result.result}")
            else:
                formatted_parts.append(f"Tool '{result.name}' failed: {result.error}")

        return "\n".join(formatted_parts)

    async def _save_conversation(
        self,
        chat_id: int,
        user_message: str,
        agent_reply: AgentReply,
        history: List[Dict[str, Any]],
        draft_list: List[Dict[str, Any]]
    ):
        """
        Save the conversation turn to memory.

        Args:
            chat_id: Telegram chat ID
            user_message: The user's message
            agent_reply: The agent's response
            history: Previous chat history
            draft_list: Current draft list (may have been updated by tools)
        """
        # Create a new chat turn
        turn = ChatTurn(
            user_message=user_message,
            agent_response=agent_reply.text,
            used_tools=agent_reply.used_tools
        )

        # Append to history
        updated_history = history + [turn.dict()]

        # Save to memory store
        await self.memory_store.append_turn(chat_id, turn.dict())

        # Note: draft list updates are handled by individual tools that call memory_store directly