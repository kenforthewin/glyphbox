"""Configuration for a single agent run.

Passed from the web API to whichever RunBackend executes the run.
Deliberately excludes the API key -- the worker decrypts it using user_id.
"""

from dataclasses import dataclass


@dataclass
class RunConfig:
    """Parameters for starting an agent run."""

    run_id: str = ""  # set by RunManager before dispatch
    user_id: int | None = None
    model: str = ""
    character: str = "random"
    temperature: float = 0.1
    reasoning: str = "none"
    max_turns: int = 10000
