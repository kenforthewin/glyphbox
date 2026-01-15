#!/usr/bin/env python3
"""
Skill runner for sandbox container.

This script runs inside the Docker container and:
1. Loads the skill code from /sandbox/skill.py
2. Connects to the API proxy via Unix socket
3. Executes the skill function
4. Writes results to /sandbox/result.json
"""

import asyncio
import json
import sys
import traceback
from pathlib import Path

# Add current directory to path for imports
sys.path.insert(0, "/home/sandbox")
sys.path.insert(0, "/sandbox")

# Import the API stub
from api_stub import nh, SkillResult


def load_skill_code():
    """Load the skill code from file."""
    skill_path = Path("/sandbox/skill.py")
    if not skill_path.exists():
        raise FileNotFoundError("Skill file not found: /sandbox/skill.py")
    return skill_path.read_text()


def load_params():
    """Load execution parameters."""
    params_path = Path("/sandbox/params.json")
    if not params_path.exists():
        return {"skill_name": "skill", "params": {}}
    return json.loads(params_path.read_text())


def write_result(result: dict):
    """Write execution result to file."""
    result_path = Path("/sandbox/result.json")
    result_path.write_text(json.dumps(result, indent=2))


async def execute_skill(code: str, skill_name: str, params: dict) -> dict:
    """Execute the skill code and return results."""
    # Create execution namespace
    namespace = {
        "nh": nh,
        "SkillResult": SkillResult,
        "__builtins__": {
            # Limited builtins
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
        },
    }

    # Compile and execute the code to define the function
    compiled = compile(code, f"<skill:{skill_name}>", "exec")
    exec(compiled, namespace)

    # Find the skill function
    skill_func = None
    for name, obj in namespace.items():
        if asyncio.iscoroutinefunction(obj) and not name.startswith("_"):
            skill_func = obj
            break

    if skill_func is None:
        return {
            "success": False,
            "error": f"No async function found in skill code",
        }

    # Execute the skill
    try:
        result = await skill_func(nh, **params)

        # Convert SkillResult to dict
        if isinstance(result, SkillResult):
            return {
                "success": result.success,
                "result": {
                    "stopped_reason": result.stopped_reason,
                    "data": result.data,
                    "actions_taken": result.actions_taken,
                    "turns_elapsed": result.turns_elapsed,
                },
                "actions_taken": result.actions_taken,
                "turns_elapsed": result.turns_elapsed,
            }
        else:
            return {
                "success": True,
                "result": result,
            }

    except Exception as e:
        return {
            "success": False,
            "error": f"{type(e).__name__}: {str(e)}",
            "traceback": traceback.format_exc(),
        }


async def main():
    """Main entry point."""
    try:
        # Load skill and params
        code = load_skill_code()
        params_data = load_params()
        skill_name = params_data.get("skill_name", "skill")
        params = params_data.get("params", {})

        print(f"Executing skill: {skill_name}")

        # Execute
        result = await execute_skill(code, skill_name, params)

        # Write result
        write_result(result)

        if result.get("success"):
            print("Skill completed successfully")
            sys.exit(0)
        else:
            print(f"Skill failed: {result.get('error', 'unknown error')}")
            sys.exit(1)

    except Exception as e:
        error_result = {
            "success": False,
            "error": f"Runner error: {str(e)}",
            "traceback": traceback.format_exc(),
        }
        write_result(error_result)
        print(f"Runner error: {e}")
        traceback.print_exc()
        sys.exit(1)
    finally:
        # Clean up API connection
        nh.close()


if __name__ == "__main__":
    asyncio.run(main())
