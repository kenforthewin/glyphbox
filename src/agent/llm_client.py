"""
LLM client for the NetHack agent.

Supports OpenRouter (default) and direct Anthropic API.
"""

import json
import logging
import os
from dataclasses import dataclass
from typing import Any, Optional

from openai import AsyncOpenAI

from src.tui.logging import LLMLogger

logger = logging.getLogger(__name__)
llm_logger = LLMLogger()


# Base tool - always available
EXECUTE_CODE_TOOL = {
    "type": "function",
    "function": {
        "name": "execute_code",
        "description": "Run Python code that interacts with the game. Use for ad-hoc commands like moving, fighting, picking up items. Batch multiple operations together.",
        "parameters": {
            "type": "object",
            "properties": {
                "reasoning": {
                    "type": "string",
                    "description": "1-2 sentence explanation of what the code will do. Be concise - do NOT repeat map analysis or game state here."
                },
                "code": {
                    "type": "string",
                    "description": "Python code to execute. Has access to 'nh' (game API) and Direction enum. All calls are synchronous - do NOT use await. Do NOT include lengthy comments repeating your reasoning - the code should be clean and minimal."
                }
            },
            "required": ["reasoning", "code"]
        }
    }
}

# View full map tool - only when local_map_mode is enabled
VIEW_FULL_MAP_TOOL = {
    "type": "function",
    "function": {
        "name": "view_full_map",
        "description": "View the ENTIRE dungeon level map (all 21 rows). Use ONLY when the local view is insufficient - e.g. to plan exploration routes, remember distant item locations, or understand overall level layout. Do NOT use every turn - it's expensive. The local view shown each turn is enough for tactical decisions.",
        "parameters": {
            "type": "object",
            "properties": {
                "reasoning": {
                    "type": "string",
                    "description": "Why you need the full map view right now"
                }
            },
            "required": ["reasoning"]
        }
    }
}

# Core tools (for backward compatibility)
CORE_TOOLS = [EXECUTE_CODE_TOOL, VIEW_FULL_MAP_TOOL]

# Skill tool definitions (only when skills_enabled=True)
SKILL_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "write_skill",
            "description": "Save reusable code as a named skill for later use. Use when you find yourself repeating patterns.",
            "parameters": {
                "type": "object",
                "properties": {
                    "reasoning": {
                        "type": "string",
                        "description": "Brief explanation of what this skill does"
                    },
                    "skill_name": {
                        "type": "string",
                        "description": "Name for the skill (snake_case)"
                    },
                    "code": {
                        "type": "string",
                        "description": "Python code for the skill. MUST be an async function: async def skill_name(nh, **params):"
                    }
                },
                "required": ["reasoning", "skill_name", "code"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "invoke_skill",
            "description": "Run a previously saved skill.",
            "parameters": {
                "type": "object",
                "properties": {
                    "reasoning": {
                        "type": "string",
                        "description": "Brief explanation of why you're invoking this skill"
                    },
                    "skill_name": {
                        "type": "string",
                        "description": "Name of the skill to invoke"
                    },
                    "params": {
                        "type": "object",
                        "description": "Parameters to pass to the skill"
                    }
                },
                "required": ["reasoning", "skill_name"]
            }
        }
    }
]

# All tools combined (for backward compatibility)
AGENT_TOOLS = CORE_TOOLS + SKILL_TOOLS


def get_agent_tools(skills_enabled: bool = False, local_map_mode: bool = False) -> list[dict]:
    """Get the list of tools based on configuration.

    Args:
        skills_enabled: Whether skill tools (write_skill, invoke_skill) are enabled
        local_map_mode: Whether agent sees local map (True) or full map (False).
                        view_full_map tool is only included when local_map_mode=True.

    Returns:
        List of tool definitions for the LLM
    """
    tools = [EXECUTE_CODE_TOOL]

    # Only include view_full_map when agent sees local map (needs way to see full)
    if local_map_mode:
        tools.append(VIEW_FULL_MAP_TOOL)

    if skills_enabled:
        tools.extend(SKILL_TOOLS)

    return tools


@dataclass
class ToolCall:
    """A tool call from the LLM."""

    name: str
    arguments: dict


@dataclass
class LLMResponse:
    """Response from the LLM."""

    content: str
    model: str
    usage: Optional[dict] = None
    finish_reason: Optional[str] = None
    tool_call: Optional[ToolCall] = None  # Tool call if model invoked a tool
    # Extended thinking / reasoning support (OpenRouter)
    reasoning: Optional[str] = None  # The model's thinking/reasoning text
    reasoning_details: Optional[list] = None  # Full reasoning blocks for re-feeding


class LLMClient:
    """
    Client for interacting with LLMs via OpenRouter or Anthropic.

    Uses the OpenAI-compatible API format supported by OpenRouter.
    """

    def __init__(
        self,
        provider: str = "openrouter",
        model: str = "anthropic/claude-opus-4.5",
        base_url: str = "https://openrouter.ai/api/v1",
        temperature: float = 0.2,
        api_key: Optional[str] = None,
        reasoning: Optional[str] = None,
    ):
        """
        Initialize the LLM client.

        Args:
            provider: LLM provider ("openrouter" or "anthropic")
            model: Model identifier
            base_url: API base URL
            temperature: Sampling temperature
            api_key: API key (defaults to OPENROUTER_API_KEY env var)
            reasoning: Reasoning effort level ("none", "minimal", "low", "medium", "high", "xhigh")
                      or None to disable. Maps to OpenRouter's reasoning.effort parameter.
        """
        self.provider = provider
        self.model = model
        self.temperature = temperature
        # Store reasoning effort (None or "none" means disabled)
        self.reasoning_effort = None
        if reasoning and reasoning.lower() != "none":
            self.reasoning_effort = reasoning.lower()

        # Get API key from env if not provided
        if api_key is None:
            if provider == "openrouter":
                api_key = os.environ.get("OPENROUTER_API_KEY") or os.environ.get("OPENROUTER_KEY")
            else:
                api_key = os.environ.get("ANTHROPIC_API_KEY")

        if not api_key:
            raise ValueError(
                f"No API key found. Set {'OPENROUTER_API_KEY or OPENROUTER_KEY' if provider == 'openrouter' else 'ANTHROPIC_API_KEY'} environment variable."
            )

        self.client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
        )

        reasoning_info = f", reasoning={self.reasoning_effort}" if self.reasoning_effort else ""
        logger.info(f"LLMClient initialized: provider={provider}, model={model}{reasoning_info}")

    async def complete(
        self,
        prompt: str,
        system: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> LLMResponse:
        """
        Generate a completion from the LLM.

        Args:
            prompt: The user prompt
            system: Optional system message
            temperature: Override default temperature
            max_tokens: Maximum tokens to generate (None for no limit)

        Returns:
            LLMResponse with the generated content
        """
        messages = []

        if system:
            messages.append({"role": "system", "content": system})

        messages.append({"role": "user", "content": prompt})

        kwargs = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature if temperature is not None else self.temperature,
        }

        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens

        # Log full request
        llm_logger.log_request(
            model=self.model,
            messages=messages,
            temperature=kwargs["temperature"],
            max_tokens=max_tokens,
        )

        try:
            response = await self.client.chat.completions.create(**kwargs)
        except Exception as e:
            llm_logger.log_error(str(e), {"model": self.model})
            raise

        choice = response.choices[0]
        content = choice.message.content or ""

        usage_dict = None
        if response.usage:
            usage_dict = {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            }

        # Log full response
        llm_logger.log_response(
            content=content,
            model=response.model,
            usage=usage_dict,
            finish_reason=choice.finish_reason,
        )

        return LLMResponse(
            content=content,
            model=response.model,
            usage=usage_dict,
            finish_reason=choice.finish_reason,
        )

    async def complete_with_history(
        self,
        messages: list[dict],
        system: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> LLMResponse:
        """
        Generate a completion with conversation history.

        Args:
            messages: List of {"role": "user"|"assistant", "content": "..."}
            system: Optional system message
            temperature: Override default temperature
            max_tokens: Maximum tokens to generate

        Returns:
            LLMResponse with the generated content
        """
        full_messages = []

        if system:
            full_messages.append({"role": "system", "content": system})

        full_messages.extend(messages)

        kwargs = {
            "model": self.model,
            "messages": full_messages,
            "temperature": temperature if temperature is not None else self.temperature,
        }

        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens

        # Log full request
        llm_logger.log_request(
            model=self.model,
            messages=full_messages,
            temperature=kwargs["temperature"],
            max_tokens=max_tokens,
        )

        try:
            response = await self.client.chat.completions.create(**kwargs)
        except Exception as e:
            llm_logger.log_error(str(e), {"model": self.model})
            raise

        choice = response.choices[0]
        content = choice.message.content or ""

        usage_dict = None
        if response.usage:
            usage_dict = {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            }

        # Log full response
        llm_logger.log_response(
            content=content,
            model=response.model,
            usage=usage_dict,
            finish_reason=choice.finish_reason,
        )

        return LLMResponse(
            content=content,
            model=response.model,
            usage=usage_dict,
            finish_reason=choice.finish_reason,
        )

    async def complete_with_tools(
        self,
        messages: list[dict],
        tools: list[dict],
        system: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        max_tool_retries: int = 5,
    ) -> LLMResponse:
        """
        Generate a completion with tool calling.

        Args:
            messages: List of {"role": "user"|"assistant", "content": "..."}
            tools: List of tool definitions (use AGENT_TOOLS for agent actions)
            system: Optional system message
            temperature: Override default temperature
            max_tokens: Maximum tokens to generate
            max_tool_retries: Max attempts to get a tool call (default 5)

        Returns:
            LLMResponse with tool_call populated if model invoked a tool
        """
        full_messages = []

        if system:
            full_messages.append({"role": "system", "content": system})

        full_messages.extend(messages)

        # Use "required" for models that support it (forces tool use, no text-only responses)
        # Fall back to "auto" for models that don't support it (GLM, some others)
        model_lower = self.model.lower()
        if "claude" in model_lower or "anthropic" in model_lower:
            tool_choice = "required"
        else:
            tool_choice = "auto"

        # Retry loop to ensure we get a tool call
        for attempt in range(max_tool_retries):
            kwargs: dict[str, Any] = {
                "model": self.model,
                "messages": full_messages,
                "temperature": temperature if temperature is not None else self.temperature,
                "tools": tools,
                "tool_choice": tool_choice,
            }

            if max_tokens is not None:
                kwargs["max_tokens"] = max_tokens

            # Add reasoning configuration if enabled (OpenRouter)
            if self.reasoning_effort:
                kwargs["extra_body"] = {"reasoning": {"effort": self.reasoning_effort}}

            # Log full request (only on first attempt)
            if attempt == 0:
                llm_logger.log_request(
                    model=self.model,
                    messages=full_messages,
                    temperature=kwargs["temperature"],
                    max_tokens=max_tokens,
                )

            try:
                response = await self.client.chat.completions.create(**kwargs)
            except Exception as e:
                llm_logger.log_error(str(e), {"model": self.model})
                raise

            choice = response.choices[0]
            content = choice.message.content or ""

            # Extract reasoning/thinking tokens if present (OpenRouter)
            # These are returned as extra attributes on the message object
            reasoning_text = getattr(choice.message, "reasoning", None)
            reasoning_details = getattr(choice.message, "reasoning_details", None)

            # Extract tool call if present
            tool_call_result = None
            if choice.message.tool_calls and len(choice.message.tool_calls) > 0:
                tc = choice.message.tool_calls[0]
                try:
                    arguments = json.loads(tc.function.arguments)
                    tool_call_result = ToolCall(
                        name=tc.function.name,
                        arguments=arguments,
                    )
                except json.JSONDecodeError as e:
                    logger.warning(f"Failed to parse tool call arguments: {e}")

            usage_dict = None
            if response.usage:
                usage_dict = {
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                    "total_tokens": response.usage.total_tokens,
                }

            # If we got a tool call, log and return
            if tool_call_result:
                reasoning_info = f" [reasoning: {len(reasoning_text)} chars]" if reasoning_text else ""
                llm_logger.log_response(
                    content=content + f" [tool: {tool_call_result.name}]{reasoning_info}",
                    model=response.model,
                    usage=usage_dict,
                    finish_reason=choice.finish_reason,
                )
                return LLMResponse(
                    content=content,
                    model=response.model,
                    usage=usage_dict,
                    finish_reason=choice.finish_reason,
                    tool_call=tool_call_result,
                    reasoning=reasoning_text,
                    reasoning_details=reasoning_details,
                )

            # No tool call - log and retry
            logger.warning(
                f"Model did not call a tool (attempt {attempt + 1}/{max_tool_retries}). "
                f"Response: {content[:200]}{'...' if len(content) > 200 else ''}"
            )

            # Add the assistant's response and a nudge to use tools
            # Include reasoning_details if present to preserve thinking context
            assistant_msg: dict[str, Any] = {"role": "assistant", "content": content}
            if reasoning_details:
                assistant_msg["reasoning_details"] = reasoning_details
            full_messages.append(assistant_msg)
            full_messages.append({
                "role": "user",
                "content": "You must use the execute_code tool to take an action. Please call the tool now."
            })

        # Exhausted retries - return last response without tool call
        logger.error(f"Failed to get tool call after {max_tool_retries} attempts")
        llm_logger.log_response(
            content=content + " [NO TOOL CALL]",
            model=response.model,
            usage=usage_dict,
            finish_reason=choice.finish_reason,
        )
        return LLMResponse(
            content=content,
            model=response.model,
            usage=usage_dict,
            finish_reason=choice.finish_reason,
            tool_call=None,
            reasoning=reasoning_text,
            reasoning_details=reasoning_details,
        )


def create_client_from_config(config) -> LLMClient:
    """Create an LLM client from configuration."""
    return LLMClient(
        provider=config.agent.provider,
        model=config.agent.model,
        base_url=config.agent.base_url,
        temperature=config.agent.temperature,
        reasoning=config.agent.reasoning,
    )
