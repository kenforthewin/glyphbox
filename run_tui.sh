#!/bin/bash
cd "$(dirname "$0")"
uv run python -m src.cli watch "$@"
