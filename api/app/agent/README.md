# PricePoa LLM Agent Module

This module adds conversational LLM capabilities to the PricePoa Telegram bot while maintaining compatibility with existing functionality.

## Features

- **Grounded Responses**: The agent never invents prices, stores, or comparisons - all claims must come from tool results
- **Tool Usage**: Can search products, compare variants, manage shopping lists, and generate basket comparisons
- **Fallback LLM Providers**: Primary (Groq) with automatic fallback to Anthropic on errors/timeouts/rate limits
- **Session Memory**: Maintains chat history and draft shopping lists per user
- **Grounding Validation**: Verifies that numerical claims in responses are supported by tool results from the same turn
- **Telegram Integration**: Works as a drop-in replacement for free-text handling when enabled

## Environment Variables

Add these to your `.env` file:

```bash
# Agent configuration
AGENT_ENABLED=false
GROQ_API_KEY=your_groq_api_key_here
ANTHROPIC_API_KEY=your_anthropic_api_key_here
AGENT_PRIMARY_MODEL=groq:llama3-8b-8192
AGENT_FALLBACK_MODEL=anthropic:claude-3-haiku-20240307
AGENT_HISTORY_LIMIT=10
AGENT_MAX_TOOL_ITERATIONS=5
AGENT_LLM_TIMEOUT_S=20
AGENT_SESSION_TTL_DAYS=14
```

## Module Structure

```
api/app/agent/
├── __init__.py              # Exports handle_message only
├── README.md                # This file
├── config.py                # AgentSettings from environment
├── schemas.py               # Pydantic models for agent data structures
├── service.py               # handle_message(chat_id, text, user_ctx) -> AgentReply (main entry point)
├── loop.py                  # Tool-calling loop with max iterations and timeouts
├── prompts/
│   ├── __init__.py
│   ├── loader.py
│   └── system.md            # Runtime system prompt for the agent
├── llm/
│   ├── __init__.py
│   ├── base.py              # LLMClient protocol interface
│   ├── groq_client.py       # Groq implementation
│   ├── anthropic_client.py  # Anthropic implementation
│   └── router.py            # Try primary, fallback on error/timeout/rate limit
├── tools/
│   ├── __init__.py
│   ├── registry.py          # Tool specifications + dispatcher
│   ├── search_products.py   # Product search tool
│   ├── compare_variants.py  # Variant comparison tool
│   ├── draft_list.py        # Shopping list management tools
│   └── build_basket.py      # Basket/infographic generation tool
├── adapters/                # ONLY place that imports existing PricePoa code
│   ├── __init__.py
│   ├── matching.py          # Wraps existing product matcher
│   ├── pricing.py           # Wraps existing price lookup
│   └── infographic.py       # Wraps existing infographic engine
├── memory/
│   ├── __init__.py
│   ├── models.py            # Pydantic models for MongoDB documents
│   └── store.py             # Mongo chat_sessions: capped history + draft list
├── guardrails/
│   ├── __init__.py
│   └── grounding.py         # Validates numerical claims in responses
├── scripts/
│   └── chat_cli.py          # Terminal-based chat for testing (no Telegram needed)
└── tests/
    ├── conftest.py          # Test fixtures (fake LLM client, fake adapters)
    ├── test_loop.py
    ├── test_tools.py
    ├── test_memory.py
    ├── test_grounding.py
    └── test_router_fallback.py
```

## How It Works

1. When `AGENT_ENABLED=true`, non-command text messages are routed to `agent.handle_message()`
2. The agent uses a tool-calling loop to interact with LLMs
3. All product/price/infographic functionality goes through adapters that wrap existing code
4. Responses are validated for grounding before being sent to the user
5. With `AGENT_ENABLED=false`, the bot behaves exactly as it did before

## Key Design Principles

- **Additive Only**: No existing files are modified except for small, approved patches in the webhook
- **Removable**: Setting `AGENT_ENABLED=false` restores original behavior exactly
- **Adapter Boundary**: Only `api/app/agent/adapters/` imports from the existing codebase
- **Tool-First**: All knowledge comes from tool execution, never from model internal knowledge