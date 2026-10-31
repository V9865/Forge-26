"""EmberRoute Agent Package: LLM client, orchestration, tools, and operational briefings."""

from core.agent.briefing import briefing_messages, build_facts, facts_hash, template_briefing
from core.agent.guard import GuardResult, verify
from core.agent.llm import LLMResponse, LLMUnavailable, chat, is_available
from core.agent.orchestrator import CycleResult, Orchestrator, TickResult, WorldState, detect_change, diff
from core.agent.tools import TOOL_SCHEMAS, compact
from core.agent.trace import Trace, TraceEntry

__all__ = [
    "LLMResponse",
    "LLMUnavailable",
    "chat",
    "is_available",
    "Orchestrator",
    "WorldState",
    "CycleResult",
    "TickResult",
    "detect_change",
    "diff",
    "Trace",
    "TraceEntry",
    "TOOL_SCHEMAS",
    "compact",
    "build_facts",
    "briefing_messages",
    "template_briefing",
    "facts_hash",
    "verify",
    "GuardResult",
]

