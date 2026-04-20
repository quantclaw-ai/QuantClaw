"""LLM tool-use loop: lets the model decide when and what to search.

Provides a provider-agnostic tool-use loop that:
1. Sends messages + tool definitions to the LLM
2. Detects tool_use requests in the response
3. Executes tools locally (web_search, available_fields, etc.)
4. Feeds results back to the LLM
5. Repeats until the LLM returns a final text response

Supports Anthropic Messages API, OpenAI Chat Completions API,
and the OpenAI Responses API (via sidecar).
"""
from __future__ import annotations

import json
import logging
from typing import Any, Callable, Awaitable

logger = logging.getLogger(__name__)

# Maximum tool-use rounds to prevent infinite loops
MAX_TOOL_ROUNDS = 8


# ── Tool definitions (provider-agnostic) ──

SEARCH_TOOL = {
    "name": "web_search",
    "description": (
        "Search the web for information. Use this to find research papers, "
        "market data sources, alpha factor ideas, financial news, or any "
        "other information relevant to your task. You can call this multiple "
        "times with different queries to build a complete picture."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The search query. Be specific and targeted.",
            },
        },
        "required": ["query"],
    },
}

DATA_FIELDS_TOOL = {
    "name": "available_data_fields",
    "description": (
        "List all available data fields that can be fetched for stocks. "
        "Returns field categories (ohlcv, fundamentals, sentiment, technical) "
        "with their column names. Use this to discover what data is available "
        "before making recommendations."
    ),
    "parameters": {
        "type": "object",
        "properties": {},
    },
}

ALL_TOOLS = [SEARCH_TOOL, DATA_FIELDS_TOOL]


# ── Provider-specific formatters ──

def tools_for_anthropic(tools: list[dict]) -> list[dict]:
    """Convert tool defs to Anthropic format."""
    return [
        {
            "name": t["name"],
            "description": t["description"],
            "input_schema": t["parameters"],
        }
        for t in tools
    ]


def tools_for_openai(tools: list[dict]) -> list[dict]:
    """Convert tool defs to OpenAI Chat Completions format."""
    return [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t["description"],
                "parameters": t["parameters"],
            },
        }
        for t in tools
    ]


def tools_for_responses_api(tools: list[dict]) -> list[dict]:
    """Convert tool defs to OpenAI Responses API format."""
    return [
        {
            "type": "function",
            "name": t["name"],
            "description": t["description"],
            "parameters": t["parameters"],
        }
        for t in tools
    ]


# ── Tool executor ──

async def execute_tool(
    tool_name: str,
    tool_input: dict,
    config: dict,
) -> str:
    """Execute a tool call and return the result as a string."""
    if tool_name == "web_search":
        from quantclaw.agents.tools.web_search import web_search
        query = tool_input.get("query", "")
        if not query:
            return json.dumps({"error": "No query provided"})
        results = await web_search(query, config=config, max_results=5)
        return json.dumps(results, default=str)

    elif tool_name == "available_data_fields":
        try:
            from quantclaw.plugins.manager import PluginManager
            data_plugin_names = config.get("plugins", {}).get("data", ["data_yfinance"])
            if isinstance(data_plugin_names, str):
                data_plugin_names = [data_plugin_names]
            pm = PluginManager()
            pm.discover()
            plugin = pm.get("data", data_plugin_names[0])
            if plugin:
                return json.dumps(plugin.available_fields())
        except Exception:
            pass
        return json.dumps({"ohlcv": ["open", "high", "low", "close", "volume"]})

    return json.dumps({"error": f"Unknown tool: {tool_name}"})


# ── Anthropic tool-use loop ──

async def _loop_anthropic(
    model: str,
    messages: list[dict],
    system: str,
    temperature: float,
    tools: list[dict],
    config: dict,
    api_key: str = "",
) -> str:
    """Tool-use loop for Anthropic Messages API."""
    import anthropic

    kwargs = {}
    if api_key:
        kwargs["api_key"] = api_key
    client = anthropic.AsyncAnthropic(**kwargs)

    anthropic_tools = tools_for_anthropic(tools)
    current_messages = list(messages)

    for _ in range(MAX_TOOL_ROUNDS):
        call_kwargs: dict[str, Any] = {
            "model": model,
            "max_tokens": 4096,
            "messages": current_messages,
            "tools": anthropic_tools,
            "temperature": temperature,
        }
        if system:
            call_kwargs["system"] = system

        response = await client.messages.create(**call_kwargs)

        # Check if the model wants to use tools
        if response.stop_reason == "tool_use":
            # Collect all text and tool_use blocks
            assistant_content = []
            tool_results = []

            for block in response.content:
                if block.type == "text":
                    assistant_content.append({"type": "text", "text": block.text})
                elif block.type == "tool_use":
                    assistant_content.append({
                        "type": "tool_use",
                        "id": block.id,
                        "name": block.name,
                        "input": block.input,
                    })
                    logger.info("Tool call: %s(%s)", block.name,
                                json.dumps(block.input, default=str)[:200])
                    result = await execute_tool(block.name, block.input, config)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result,
                    })

            current_messages.append({"role": "assistant", "content": assistant_content})
            current_messages.append({"role": "user", "content": tool_results})
            continue

        # Model returned final text
        text_parts = [b.text for b in response.content if b.type == "text"]
        return "\n".join(text_parts)

    # Max rounds exceeded — return whatever we have
    return ""


# ── OpenAI Chat Completions tool-use loop ──

async def _loop_openai(
    model: str,
    messages: list[dict],
    system: str,
    temperature: float,
    tools: list[dict],
    config: dict,
    api_key: str = "",
) -> str:
    """Tool-use loop for OpenAI Chat Completions API."""
    import openai

    kwargs = {}
    if api_key:
        kwargs["api_key"] = api_key
    client = openai.AsyncOpenAI(**kwargs)

    openai_tools = tools_for_openai(tools)
    current_messages: list[dict] = []
    if system:
        current_messages.append({"role": "system", "content": system})
    current_messages.extend(messages)

    for _ in range(MAX_TOOL_ROUNDS):
        response = await client.chat.completions.create(
            model=model,
            messages=current_messages,
            tools=openai_tools,
            temperature=temperature,
        )
        choice = response.choices[0]

        if choice.finish_reason == "tool_calls" and choice.message.tool_calls:
            # Add the assistant message with tool calls
            current_messages.append(choice.message.model_dump())

            for tool_call in choice.message.tool_calls:
                fn = tool_call.function
                logger.info("Tool call: %s(%s)", fn.name, fn.arguments[:200])
                try:
                    tool_input = json.loads(fn.arguments)
                except json.JSONDecodeError:
                    tool_input = {}
                result = await execute_tool(fn.name, tool_input, config)
                current_messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": result,
                })
            continue

        # Final text response
        return choice.message.content or ""

    return ""


# ── Sidecar (OpenAI Responses API) tool-use loop ──

async def _loop_sidecar_openai(
    model: str,
    messages: list[dict],
    system: str,
    temperature: float,
    tools: list[dict],
    config: dict,
    oauth_token: str,
    sidecar_url: str = "http://localhost:24122",
) -> str:
    """Tool-use loop via sidecar using OpenAI Responses API.

    The sidecar currently doesn't forward tools, so we handle tool-use
    by pre-prompting the LLM to emit structured JSON tool requests,
    then parsing and executing them locally.
    """
    import httpx

    # Build a tool-aware system prompt that instructs the LLM to emit
    # tool calls as JSON blocks we can parse
    tool_descriptions = "\n".join(
        f"- {t['name']}: {t['description']} "
        f"Parameters: {json.dumps(t['parameters'].get('properties', {}))}"
        for t in tools
    )

    tool_system = (
        f"{system}\n\n"
        f"You have access to these tools:\n{tool_descriptions}\n\n"
        f"To use a tool, output EXACTLY this JSON on its own line:\n"
        f'{{"tool": "<tool_name>", "args": {{...}}}}\n\n'
        f"You may call multiple tools (one per line). After each tool call, "
        f"you will receive the results. When you have enough information, "
        f"provide your final answer WITHOUT any tool call JSON."
    )

    current_messages = [m for m in messages if m["role"] != "system"]
    accumulated_context: list[str] = []

    for round_num in range(MAX_TOOL_ROUNDS):
        # Build messages with accumulated tool results
        msgs = list(current_messages)
        if accumulated_context:
            msgs.append({
                "role": "user",
                "content": "Tool results:\n" + "\n\n".join(accumulated_context)
                + "\n\nContinue your analysis. Call more tools or provide your final answer.",
            })

        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                resp = await client.post(
                    f"{sidecar_url}/chat/openai",
                    json={
                        "model": model,
                        "messages": msgs,
                        "system_prompt": tool_system,
                        "access_token": oauth_token,
                    },
                )
                data = resp.json()
                if data.get("error"):
                    raise RuntimeError(f"Sidecar error: {data['error']}")
                response_text = data.get("response", "")
        except httpx.ConnectError:
            raise RuntimeError("Node.js sidecar not running")

        # Parse tool calls from response
        tool_calls_found = False
        lines = response_text.strip().split("\n")
        non_tool_lines = []

        for line in lines:
            line = line.strip()
            if not line:
                continue
            # Try to parse as tool call
            try:
                parsed = json.loads(line)
                if isinstance(parsed, dict) and "tool" in parsed:
                    tool_name = parsed["tool"]
                    tool_args = parsed.get("args", {})
                    logger.info("Sidecar tool call: %s(%s)", tool_name,
                                json.dumps(tool_args, default=str)[:200])
                    result = await execute_tool(tool_name, tool_args, config)
                    accumulated_context.append(
                        f"[{tool_name}({json.dumps(tool_args)})]\n{result}"
                    )
                    tool_calls_found = True
                    continue
            except (json.JSONDecodeError, TypeError):
                pass
            non_tool_lines.append(line)

        if not tool_calls_found:
            # No tool calls — this is the final response
            return response_text

    # Max rounds — return last response
    return response_text


# ── Sidecar (Anthropic) tool-use loop ──

async def _loop_sidecar_anthropic(
    model: str,
    messages: list[dict],
    system: str,
    temperature: float,
    tools: list[dict],
    config: dict,
    oauth_token: str,
    sidecar_url: str = "http://localhost:24122",
) -> str:
    """Tool-use loop via sidecar for Anthropic.

    Same approach as OpenAI sidecar — prompt-based tool calling.
    """
    import httpx

    tool_descriptions = "\n".join(
        f"- {t['name']}: {t['description']} "
        f"Parameters: {json.dumps(t['parameters'].get('properties', {}))}"
        for t in tools
    )

    tool_system = (
        f"{system}\n\n"
        f"You have access to these tools:\n{tool_descriptions}\n\n"
        f"To use a tool, output EXACTLY this JSON on its own line:\n"
        f'{{"tool": "<tool_name>", "args": {{...}}}}\n\n'
        f"You may call multiple tools (one per line). After each tool call, "
        f"you will receive the results. When you have enough information, "
        f"provide your final answer WITHOUT any tool call JSON."
    )

    current_messages = [m for m in messages if m["role"] != "system"]
    accumulated_context: list[str] = []

    for round_num in range(MAX_TOOL_ROUNDS):
        msgs = list(current_messages)
        if accumulated_context:
            msgs.append({
                "role": "user",
                "content": "Tool results:\n" + "\n\n".join(accumulated_context)
                + "\n\nContinue your analysis. Call more tools or provide your final answer.",
            })

        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                resp = await client.post(
                    f"{sidecar_url}/chat/anthropic",
                    json={
                        "model": model,
                        "messages": msgs,
                        "system_prompt": tool_system,
                        "access_token": oauth_token,
                    },
                )
                data = resp.json()
                if data.get("error"):
                    raise RuntimeError(f"Sidecar error: {data['error']}")
                response_text = data.get("response", "")
        except httpx.ConnectError:
            raise RuntimeError("Node.js sidecar not running")

        # Parse tool calls
        tool_calls_found = False
        for line in response_text.strip().split("\n"):
            line = line.strip()
            try:
                parsed = json.loads(line)
                if isinstance(parsed, dict) and "tool" in parsed:
                    tool_name = parsed["tool"]
                    tool_args = parsed.get("args", {})
                    logger.info("Sidecar tool call: %s(%s)", tool_name,
                                json.dumps(tool_args, default=str)[:200])
                    result = await execute_tool(tool_name, tool_args, config)
                    accumulated_context.append(
                        f"[{tool_name}({json.dumps(tool_args)})]\n{result}"
                    )
                    tool_calls_found = True
            except (json.JSONDecodeError, TypeError):
                pass

        if not tool_calls_found:
            return response_text

    return response_text


# ── Public interface ──

async def call_with_tools(
    agent_name: str,
    messages: list[dict],
    system: str,
    config: dict,
    tools: list[dict] | None = None,
    temperature: float | None = None,
) -> str:
    """Call an LLM with tool-use support, routing to the right provider.

    Returns the final text response after all tool calls are resolved.
    """
    from quantclaw.execution.router import LLMRouter

    router = LLMRouter(config)
    provider_info = router.get_provider(agent_name)
    provider_name = provider_info.get("provider", "anthropic")
    model = provider_info.get("model", "claude-opus-4-6")
    temp = temperature if temperature is not None else router.get_temperature(agent_name)
    tool_defs = tools or ALL_TOOLS

    api_key = config.get("api_key", "")
    oauth_token = config.get("oauth_token", "")

    logger.info("call_with_tools: agent=%s, provider=%s, model=%s, tools=%s",
                agent_name, provider_name, model, [t["name"] for t in tool_defs])

    # OAuth path — route through sidecar
    if oauth_token and provider_name in ("openai", "anthropic"):
        if provider_name == "openai":
            return await _loop_sidecar_openai(
                model, messages, system, temp, tool_defs, config, oauth_token)
        else:
            return await _loop_sidecar_anthropic(
                model, messages, system, temp, tool_defs, config, oauth_token)

    # Direct API key path
    if provider_name == "anthropic":
        return await _loop_anthropic(
            model, messages, system, temp, tool_defs, config, api_key)
    elif provider_name == "openai":
        return await _loop_openai(
            model, messages, system, temp, tool_defs, config, api_key)
    elif provider_name == "ollama":
        # Ollama doesn't support tool use — fall back to regular call
        response = await router.call(agent_name, messages, system, temp)
        return response

    raise ValueError(f"Unknown provider: {provider_name}")
