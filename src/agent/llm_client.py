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


# Core tool definitions (always available)
CORE_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "look_around",
            "description": "Get full visual context including screen, monsters, and items. Use sparingly - only when you need spatial awareness.",
            "parameters": {
                "type": "object",
                "properties": {
                    "reasoning": {
                        "type": "string",
                        "description": "Brief explanation of why you need to look around"
                    }
                },
                "required": ["reasoning"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "execute_code",
            "description": "Run Python code that interacts with the game. Use for ad-hoc commands like moving, fighting, picking up items. Batch multiple operations together.",
            "parameters": {
                "type": "object",
                "properties": {
                    "reasoning": {
                        "type": "string",
                        "description": "Brief explanation of what the code will do"
                    },
                    "code": {
                        "type": "string",
                        "description": "Python code to execute. Has access to 'nh' (game API) and Direction enum. All calls are synchronous - do NOT use await."
                    }
                },
                "required": ["reasoning", "code"]
            }
        }
    },
]

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


def get_agent_tools(skills_enabled: bool = False) -> list[dict]:
    """Get the list of tools based on configuration.

    Args:
        skills_enabled: Whether skill tools (write_skill, invoke_skill) are enabled

    Returns:
        List of tool definitions for the LLM
    """
    if skills_enabled:
        return AGENT_TOOLS
    return CORE_TOOLS


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
    ):
        """
        Initialize the LLM client.

        Args:
            provider: LLM provider ("openrouter" or "anthropic")
            model: Model identifier
            base_url: API base URL
            temperature: Sampling temperature
            api_key: API key (defaults to OPENROUTER_API_KEY env var)
        """
        self.provider = provider
        self.model = model
        self.temperature = temperature

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

        logger.info(f"LLMClient initialized: provider={provider}, model={model}")

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
    ) -> LLMResponse:
        """
        Generate a completion with tool calling.

        Args:
            messages: List of {"role": "user"|"assistant", "content": "..."}
            tools: List of tool definitions (use AGENT_TOOLS for agent actions)
            system: Optional system message
            temperature: Override default temperature
            max_tokens: Maximum tokens to generate

        Returns:
            LLMResponse with tool_call populated if model invoked a tool
        """
        full_messages = []

        if system:
            full_messages.append({"role": "system", "content": system})

        full_messages.extend(messages)

        # GPT-5.2+ may need different tool_choice handling on OpenRouter
        # Use "auto" which is universally supported, model will still use tools
        if "gpt-5.2" in self.model.lower() or "gpt-5-2" in self.model.lower():
            tool_choice = "auto"
        else:
            tool_choice = "required"  # Legacy format for older models

        kwargs = {
            "model": self.model,
            "messages": full_messages,
            "temperature": temperature if temperature is not None else self.temperature,
            "tools": tools,
            "tool_choice": tool_choice,
        }

        # For non-GPT-5.2 models, require strict parameter support
        # GPT-5.2 needs more flexible routing due to new tool_choice format
        if "gpt-5.2" not in self.model.lower() and "gpt-5-2" not in self.model.lower():
            kwargs["extra_body"] = {
                "provider": {
                    "require_parameters": True,
                },
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

        # Log full response
        tool_info = f" [tool: {tool_call_result.name}]" if tool_call_result else ""
        llm_logger.log_response(
            content=content + tool_info,
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
        )


def create_client_from_config(config) -> LLMClient:
    """Create an LLM client from configuration."""
    return LLMClient(
        provider=config.agent.provider,
        model=config.agent.model,
        base_url=config.agent.base_url,
        temperature=config.agent.temperature,
    )
