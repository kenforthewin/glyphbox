"""
Docker sandbox manager for skill execution.

Manages Docker containers that execute agent-generated skill code
in a secure, isolated environment.
"""

import asyncio
import json
import logging
import os
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from .exceptions import (
    SandboxCommunicationError,
    SandboxError,
    SandboxStartupError,
    SkillExecutionError,
    SkillTimeoutError,
)
from .validation import validate_skill, validate_adhoc_code

logger = logging.getLogger(__name__)


class APIFailureTracker:
    """
    Wrapper that tracks failed API calls for better feedback to the agent.

    When API methods return ActionResult with success=False, this wrapper
    captures those failures so they can be reported even if the code doesn't
    check or print the return value.
    """

    def __init__(self, api):
        self._api = api
        self._failed_calls: list[dict] = []

    def _translate_error(self, error_msg: str, method: str) -> str:
        """Translate technical errors to actionable guidance for the agent."""
        translations = {
            "ord() expected a character":
                f"Invalid item letter for {method}(). Use single char like 'a', not a string. "
                f"For eating from ground, use nh.eat() with no arguments.",
            "expected str of length 1":
                f"Invalid argument to {method}(). Expected single character (e.g., 'a'), got string.",
            "No path through explored territory":
                "Path goes through unexplored areas. Explore corridors/rooms between you and target first.",
            "Hostile monsters in view":
                "Cannot pathfind while hostiles visible. Fight or flee first, or use allow_with_hostiles=True.",
            "is not walkable":
                "Target position is blocked (wall, boulder, closed door, or monster).",
            "item_letter must be a single character":
                f"Use a single inventory letter like 'a', not a full name. "
                f"For eating from ground, use nh.eat() with no arguments.",
        }
        for pattern, translation in translations.items():
            if pattern in error_msg:
                return translation
        return error_msg

    def __getattr__(self, name):
        """Proxy attribute access to wrapped API, tracking failed calls."""
        attr = getattr(self._api, name)

        # Only wrap callable methods
        if not callable(attr):
            return attr

        def wrapper(*args, **kwargs):
            result = attr(*args, **kwargs)

            # Track failed ActionResults
            if hasattr(result, 'success'):
                # This looks like an ActionResult
                if not result.success:
                    # Capture error message from either 'error' or 'messages' field
                    error_msg = getattr(result, 'error', None)
                    messages = getattr(result, 'messages', [])
                    # Build a clear failure description
                    if error_msg:
                        failure_detail = error_msg
                    elif messages:
                        failure_detail = "; ".join(messages)
                    else:
                        failure_detail = "unknown error"

                    # Translate technical errors to actionable guidance
                    failure_detail = self._translate_error(failure_detail, name)

                    self._failed_calls.append({
                        "method": name,
                        "success": False,
                        "error": failure_detail,
                    })

            return result

        return wrapper

    def get_failed_calls(self) -> list[dict]:
        """Get list of failed API calls."""
        return self._failed_calls

    def clear_failures(self):
        """Clear the failure list."""
        self._failed_calls.clear()


# Default resource limits
DEFAULT_MEMORY_LIMIT = "256m"
DEFAULT_CPU_PERIOD = 100000
DEFAULT_CPU_QUOTA = 50000  # 50% of one CPU
DEFAULT_TIMEOUT_SECONDS = 30.0

# Sandbox image name
SANDBOX_IMAGE = "nethack-skill-sandbox"


@dataclass
class ExecutionResult:
    """Result of skill execution in sandbox."""

    success: bool
    result: Optional[dict[str, Any]] = None
    error: Optional[str] = None
    stdout: str = ""
    stderr: str = ""
    execution_time: float = 0.0
    actions_taken: int = 0
    turns_elapsed: int = 0


@dataclass
class SandboxConfig:
    """Configuration for sandbox execution."""

    memory_limit: str = DEFAULT_MEMORY_LIMIT
    cpu_period: int = DEFAULT_CPU_PERIOD
    cpu_quota: int = DEFAULT_CPU_QUOTA
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    network_disabled: bool = True
    read_only: bool = True
    use_gvisor: bool = False  # Enable on Linux for production


class SkillSandbox:
    """
    Manages skill execution in Docker containers.

    This class provides a secure sandbox for running agent-generated
    Python code. Skills are executed in isolated Docker containers
    with strict resource limits and no network access.

    Example usage:
        sandbox = SkillSandbox()

        # Validate and execute a skill
        result = await sandbox.execute(
            code=skill_code,
            skill_name="explore_room",
            params={"max_steps": 100},
            api_proxy=proxy_instance,
        )

        if result.success:
            print(f"Skill completed: {result.result}")
        else:
            print(f"Skill failed: {result.error}")
    """

    def __init__(self, config: Optional[SandboxConfig] = None):
        """
        Initialize the sandbox manager.

        Args:
            config: Sandbox configuration (uses defaults if not provided)
        """
        self.config = config or SandboxConfig()
        self._docker_client: Optional[Any] = None
        self._container_pool: list[Any] = []
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize Docker client and verify sandbox image exists."""
        if self._initialized:
            return

        try:
            import docker

            self._docker_client = docker.from_env()

            # Check if sandbox image exists
            try:
                self._docker_client.images.get(SANDBOX_IMAGE)
                logger.info(f"Sandbox image '{SANDBOX_IMAGE}' found")
            except docker.errors.ImageNotFound:
                logger.warning(
                    f"Sandbox image '{SANDBOX_IMAGE}' not found. "
                    "Build it with: docker build -t nethack-skill-sandbox docker/"
                )

            self._initialized = True
            logger.info("Sandbox manager initialized")

        except ImportError:
            raise SandboxError(
                "Docker SDK not installed. Install with: pip install docker"
            )
        except Exception as e:
            raise SandboxStartupError(f"Failed to initialize Docker client: {e}")

    async def execute(
        self,
        code: str,
        skill_name: str,
        params: dict[str, Any],
        api_proxy: Any,  # APIProxy instance
        timeout: Optional[float] = None,
    ) -> ExecutionResult:
        """
        Execute a skill in the sandbox.

        Args:
            code: Python source code of the skill
            skill_name: Name of the skill function to execute
            params: Parameters to pass to the skill
            api_proxy: API proxy for handling NetHack API calls
            timeout: Execution timeout in seconds (uses config default if not specified)

        Returns:
            ExecutionResult with success/failure status and results

        Raises:
            SkillTimeoutError: If execution exceeds timeout
            SkillExecutionError: If execution fails
            SandboxError: If sandbox infrastructure fails
        """
        if not self._initialized:
            await self.initialize()

        timeout = timeout or self.config.timeout_seconds

        # Validate code first
        validation = validate_skill(code, skill_name)
        if not validation.valid:
            return ExecutionResult(
                success=False,
                error=f"Validation failed: {'; '.join(validation.errors)}",
            )

        start_time = time.time()

        try:
            # Execute in sandbox
            result = await asyncio.wait_for(
                self._execute_in_container(code, skill_name, params, api_proxy),
                timeout=timeout,
            )
            result.execution_time = time.time() - start_time
            return result

        except asyncio.TimeoutError:
            raise SkillTimeoutError(
                f"Skill '{skill_name}' exceeded timeout of {timeout}s",
                skill_name=skill_name,
                timeout_seconds=timeout,
            )
        except Exception as e:
            logger.exception(f"Skill execution failed: {e}")
            return ExecutionResult(
                success=False,
                error=str(e),
                execution_time=time.time() - start_time,
            )

    async def _execute_in_container(
        self,
        code: str,
        skill_name: str,
        params: dict[str, Any],
        api_proxy: Any,
    ) -> ExecutionResult:
        """Execute skill code inside a Docker container."""
        import docker

        if not self._docker_client:
            raise SandboxError("Docker client not initialized")

        # Create temporary directory for skill code and communication
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)

            # Write skill code
            skill_file = tmppath / "skill.py"
            skill_file.write_text(code)

            # Write execution parameters
            params_file = tmppath / "params.json"
            params_file.write_text(json.dumps({
                "skill_name": skill_name,
                "params": params,
            }))

            # Create socket path for API communication
            socket_path = tmppath / "api.sock"

            # Start API proxy server (will communicate via socket)
            proxy_task = asyncio.create_task(
                api_proxy.serve(str(socket_path))
            )

            try:
                # Container configuration
                container_config = {
                    "image": SANDBOX_IMAGE,
                    "command": ["python", "/sandbox/run_skill.py"],
                    "volumes": {
                        str(tmppath): {"bind": "/sandbox", "mode": "rw"},
                    },
                    "mem_limit": self.config.memory_limit,
                    "cpu_period": self.config.cpu_period,
                    "cpu_quota": self.config.cpu_quota,
                    "network_disabled": self.config.network_disabled,
                    "read_only": self.config.read_only,
                    "security_opt": ["no-new-privileges"],
                    "detach": True,
                    "remove": True,
                }

                # Use gVisor runtime if configured (Linux only)
                if self.config.use_gvisor:
                    container_config["runtime"] = "runsc"

                # Create and start container
                container = self._docker_client.containers.run(**container_config)

                # Wait for container to complete
                exit_result = container.wait()
                exit_code = exit_result.get("StatusCode", -1)

                # Get container logs
                stdout = container.logs(stdout=True, stderr=False).decode("utf-8", errors="replace")
                stderr = container.logs(stdout=False, stderr=True).decode("utf-8", errors="replace")

                # Read result file
                result_file = tmppath / "result.json"
                if result_file.exists():
                    result_data = json.loads(result_file.read_text())
                    return ExecutionResult(
                        success=result_data.get("success", False),
                        result=result_data.get("result"),
                        error=result_data.get("error"),
                        stdout=stdout,
                        stderr=stderr,
                        actions_taken=result_data.get("actions_taken", 0),
                        turns_elapsed=result_data.get("turns_elapsed", 0),
                    )
                else:
                    return ExecutionResult(
                        success=False,
                        error=f"Container exited with code {exit_code}",
                        stdout=stdout,
                        stderr=stderr,
                    )

            finally:
                # Clean up proxy task
                proxy_task.cancel()
                try:
                    await proxy_task
                except asyncio.CancelledError:
                    pass

    async def execute_local(
        self,
        code: str,
        skill_name: str,
        params: dict[str, Any],
        api: Any,  # NetHackAPI instance
        timeout: Optional[float] = None,
    ) -> ExecutionResult:
        """
        Execute a skill locally (without Docker) for development/testing.

        WARNING: This executes code directly in the current process.
        Only use for testing with trusted code.

        Args:
            code: Python source code of the skill
            skill_name: Name of the skill function to execute
            params: Parameters to pass to the skill
            api: NetHackAPI instance
            timeout: Execution timeout in seconds

        Returns:
            ExecutionResult with success/failure status and results
        """
        timeout = timeout or self.config.timeout_seconds

        # Validate code first
        validation = validate_skill(code, skill_name)
        if not validation.valid:
            return ExecutionResult(
                success=False,
                error=f"Validation failed: {'; '.join(validation.errors)}",
            )

        start_time = time.time()

        try:
            # Import types to inject into namespace
            import random
            import re
            from src.api.models import SkillResult, Direction, Position, HungerState
            from src.api.pathfinding import PathResult, PathStopReason, TargetResult

            # Strip import statements since we pre-inject needed classes
            # This allows skill files to have imports for IDE support while
            # still working in the restricted sandbox
            processed_code = re.sub(
                r'^(?:from\s+\S+\s+)?import\s+.+$',
                '# import stripped by sandbox',
                code,
                flags=re.MULTILINE
            )

            # Compile the code
            compiled = compile(processed_code, f"<skill:{skill_name}>", "exec")

            # Create execution namespace with API and models available
            namespace = {
                "nh": api,
                "NetHackAPI": type(api),
                # Pre-inject commonly needed classes so skills don't need imports
                "SkillResult": SkillResult,
                "Direction": Direction,
                "Position": Position,
                "PathResult": PathResult,
                "PathStopReason": PathStopReason,
                "TargetResult": TargetResult,
                "HungerState": HungerState,
                "random": random,
                "__builtins__": {
                    # Limited builtins for safety
                    "True": True,
                    "False": False,
                    "None": None,
                    "print": print,
                    "len": len,
                    "range": range,
                    "enumerate": enumerate,
                    "zip": zip,
                    "map": map,
                    "filter": filter,
                    "sorted": sorted,
                    "reversed": reversed,
                    "list": list,
                    "dict": dict,
                    "set": set,
                    "tuple": tuple,
                    "str": str,
                    "int": int,
                    "float": float,
                    "bool": bool,
                    "abs": abs,
                    "min": min,
                    "max": max,
                    "sum": sum,
                    "any": any,
                    "all": all,
                    "round": round,
                    "isinstance": isinstance,
                    "hasattr": hasattr,
                    "getattr": getattr,
                    "Exception": Exception,
                    "ValueError": ValueError,
                    "TypeError": TypeError,
                    "KeyError": KeyError,
                    "IndexError": IndexError,
                    "StopIteration": StopIteration,
                    "RuntimeError": RuntimeError,
                    # Introspection (safe)
                    "dir": dir,
                    "type": type,
                    "repr": repr,
                    "id": id,
                    "callable": callable,
                    "hash": hash,
                    # Iteration
                    "iter": iter,
                    "next": next,
                    "slice": slice,
                    # Math
                    "pow": pow,
                    "divmod": divmod,
                    # String/Character
                    "format": format,
                    "ord": ord,
                    "chr": chr,
                    "ascii": ascii,
                    "hex": hex,
                    "oct": oct,
                    "bin": bin,
                    # Object
                    "object": object,
                },
            }

            # Execute the code to define the function
            exec(compiled, namespace)

            # Get the skill function
            func_name = validation.function_name or skill_name
            if func_name not in namespace:
                return ExecutionResult(
                    success=False,
                    error=f"Function '{func_name}' not found after execution",
                )

            skill_func = namespace[func_name]

            # Execute with timeout
            result = await asyncio.wait_for(
                skill_func(api, **params),
                timeout=timeout,
            )

            execution_time = time.time() - start_time

            # Convert SkillResult to dict
            if hasattr(result, "__dict__"):
                # Start with the data dict so all custom fields are accessible
                data = getattr(result, "data", {})
                result_dict = {
                    **data,  # Flatten data fields into top level
                    "stopped_reason": getattr(result, "stopped_reason", "unknown"),
                    "success": getattr(result, "success", False),
                    "data": data,  # Also keep original data for compatibility
                    "actions_taken": getattr(result, "actions_taken", 0),
                    "turns_elapsed": getattr(result, "turns_elapsed", 0),
                }
            else:
                result_dict = {"result": result}

            return ExecutionResult(
                success=True,
                result=result_dict,
                execution_time=execution_time,
                actions_taken=result_dict.get("actions_taken", 0),
                turns_elapsed=result_dict.get("turns_elapsed", 0),
            )

        except asyncio.TimeoutError:
            raise SkillTimeoutError(
                f"Skill '{skill_name}' exceeded timeout of {timeout}s",
                skill_name=skill_name,
                timeout_seconds=timeout,
            )
        except Exception as e:
            logger.exception(f"Local skill execution failed: {e}")
            return ExecutionResult(
                success=False,
                error=str(e),
                execution_time=time.time() - start_time,
            )

    async def execute_code(
        self,
        code: str,
        api: Any,  # NetHackAPI instance
        timeout: Optional[float] = None,
    ) -> ExecutionResult:
        """
        Execute ad-hoc code in sandbox (no async def wrapper required).

        The code runs directly with `nh` available in namespace.
        Example code: "nh.move(Direction.E); nh.pickup()"

        Uses signal.SIGALRM for hard timeout on synchronous code (Unix only).
        This catches infinite loops that asyncio.wait_for can't interrupt.

        Args:
            code: Python source code to execute
            api: NetHackAPI instance
            timeout: Execution timeout in seconds

        Returns:
            ExecutionResult with success/failure status and results
        """
        import signal
        import textwrap

        timeout = timeout or self.config.timeout_seconds

        # Set up signal-based timeout for synchronous code (Unix only)
        # asyncio.wait_for won't work for tight loops without await points
        old_handler = None
        use_signal_timeout = hasattr(signal, 'SIGALRM')

        def timeout_handler(signum, frame):
            raise TimeoutError(f"Code execution timed out after {timeout} seconds (possible infinite loop)")

        if use_signal_timeout:
            old_handler = signal.signal(signal.SIGALRM, timeout_handler)
            signal.alarm(int(timeout) + 1)  # +1 to let asyncio timeout fire first if possible

        # Validate code (security checks but no async def requirement)
        validation = validate_adhoc_code(code)
        if not validation.valid:
            return ExecutionResult(
                success=False,
                error=f"Validation failed: {'; '.join(validation.errors)}",
            )

        start_time = time.time()

        # Capture stdout
        import io
        import sys
        captured_output = io.StringIO()

        # Wrap API to track failed calls
        tracked_api = APIFailureTracker(api)

        # Capture TOTAL message history length BEFORE execution
        # We access _message_history directly to avoid the cap from get_messages()
        # This ensures we correctly slice new messages even after long autoexplore runs
        messages_before = len(api._message_history) if hasattr(api, '_message_history') else 0

        try:
            # Import models to inject into namespace
            import random
            from src.api.models import Direction, Position, HungerState
            from src.api.pathfinding import PathResult, PathStopReason, TargetResult

            # Wrap code in async function for asyncio execution
            # Indent the code properly
            indented_code = textwrap.indent(code, "    ")
            wrapped = f"async def __adhoc__():\n{indented_code}"

            # Compile the wrapped code
            compiled = compile(wrapped, "<execute_code>", "exec")

            # Custom print function that captures output
            def captured_print(*args, **kwargs):
                print(*args, file=captured_output, **kwargs)

            # Create execution namespace
            namespace = {
                "nh": tracked_api,
                "Direction": Direction,
                "Position": Position,
                "PathResult": PathResult,
                "PathStopReason": PathStopReason,
                "TargetResult": TargetResult,
                "HungerState": HungerState,
                "random": random,
                "__builtins__": {
                    # Limited builtins for safety
                    "True": True,
                    "False": False,
                    "None": None,
                    "print": captured_print,
                    "len": len,
                    "range": range,
                    "enumerate": enumerate,
                    "zip": zip,
                    "map": map,
                    "filter": filter,
                    "sorted": sorted,
                    "reversed": reversed,
                    "list": list,
                    "dict": dict,
                    "set": set,
                    "tuple": tuple,
                    "str": str,
                    "int": int,
                    "float": float,
                    "bool": bool,
                    "abs": abs,
                    "min": min,
                    "max": max,
                    "sum": sum,
                    "any": any,
                    "all": all,
                    "round": round,
                    "isinstance": isinstance,
                    "hasattr": hasattr,
                    "getattr": getattr,
                    "Exception": Exception,
                    "ValueError": ValueError,
                    "TypeError": TypeError,
                    "KeyError": KeyError,
                    "IndexError": IndexError,
                    "StopIteration": StopIteration,
                    "RuntimeError": RuntimeError,
                    # Introspection (safe)
                    "dir": dir,
                    "type": type,
                    "repr": repr,
                    "id": id,
                    "callable": callable,
                    "hash": hash,
                    # Iteration
                    "iter": iter,
                    "next": next,
                    "slice": slice,
                    # Math
                    "pow": pow,
                    "divmod": divmod,
                    # String/Character
                    "format": format,
                    "ord": ord,
                    "chr": chr,
                    "ascii": ascii,
                    "hex": hex,
                    "oct": oct,
                    "bin": bin,
                    # Object
                    "object": object,
                },
            }

            # Execute the wrapped code to define the function
            exec(compiled, namespace)

            # Execute the async function with timeout
            result = await asyncio.wait_for(
                namespace["__adhoc__"](),
                timeout=timeout,
            )

            execution_time = time.time() - start_time

            # Get captured output
            stdout = captured_output.getvalue()

            # Capture NEW game messages that occurred during execution
            # Slice from the full history to get all messages since execution started
            # Limit to last 200 messages to avoid context bloat, but keep ALL kill messages
            game_messages = []
            if hasattr(api, '_message_history'):
                new_messages = api._message_history[messages_before:]
                # Keep all kill messages regardless of position
                kill_messages = [m for m in new_messages if 'kill' in m.lower() or 'destroy' in m.lower()]
                # Take last 200 other messages
                if len(new_messages) > 200:
                    game_messages = kill_messages + new_messages[-200:]
                    # Deduplicate while preserving order
                    seen = set()
                    game_messages = [m for m in game_messages if not (m in seen or seen.add(m))]
                else:
                    game_messages = new_messages

            # Get any failed API calls
            failed_calls = tracked_api.get_failed_calls()

            result_dict = {}
            if result is not None:
                result_dict["return_value"] = result
            if stdout:
                result_dict["stdout"] = stdout
            if game_messages:
                result_dict["game_messages"] = game_messages
            if failed_calls:
                # Include failed calls prominently so agent sees what went wrong
                result_dict["failed_api_calls"] = failed_calls

            return ExecutionResult(
                success=True,
                result=result_dict if result_dict else {},
                execution_time=execution_time,
                stdout=stdout,
            )

        except asyncio.TimeoutError:
            raise SkillTimeoutError(
                f"Code execution exceeded timeout of {timeout}s",
                skill_name="<adhoc>",
                timeout_seconds=timeout,
            )
        except TimeoutError as e:
            # Signal-based timeout (catches synchronous infinite loops)
            logger.warning(f"Signal timeout triggered: {e}")
            return ExecutionResult(
                success=False,
                error=str(e),
                execution_time=time.time() - start_time,
            )
        except Exception as e:
            logger.exception(f"Code execution failed: {e}")
            return ExecutionResult(
                success=False,
                error=str(e),
                execution_time=time.time() - start_time,
            )
        finally:
            # Always cancel the alarm and restore old handler
            if use_signal_timeout:
                signal.alarm(0)  # Cancel alarm
                if old_handler is not None:
                    signal.signal(signal.SIGALRM, old_handler)

    def close(self) -> None:
        """Clean up resources."""
        # Clean up any pooled containers
        for container in self._container_pool:
            try:
                container.remove(force=True)
            except Exception:
                pass
        self._container_pool.clear()

        if self._docker_client:
            self._docker_client.close()
            self._docker_client = None

        self._initialized = False

    async def __aenter__(self) -> "SkillSandbox":
        await self.initialize()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()
