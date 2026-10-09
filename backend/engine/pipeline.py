"""Compatibility entry point: the CLEAR agent is a supervisor over specialist agents (backend/agents)."""
from ..agents.supervisor import AGENT_MINUTES, BASELINE_MINUTES, STATUS_LABEL, Supervisor

Agent = Supervisor

__all__ = ["Agent", "AGENT_MINUTES", "BASELINE_MINUTES", "STATUS_LABEL"]
