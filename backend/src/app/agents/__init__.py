"""
LangGraph agents — each agent gets its own sub-package.

Each sub-package has:
  - agent.py   — the agent class
  - graph.py   — the LangGraph state graph
  - prompts.py — system/user prompt templates
"""

from app.agents.base import BaseAgent

__all__ = ["BaseAgent"]
