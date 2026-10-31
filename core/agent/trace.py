"""Operational execution trace for EmberRoute agent and pipeline.

Provides thread-safe tracking of execution steps, tool invocations, durations,
and status codes for full auditability and frontend visualization.
"""

from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import threading
import time
from typing import Any, Dict, Iterator, List, Optional


@dataclass
class TraceEntry:
    """Single execution step in an agent or pipeline operational trace."""

    ts_utc: str
    step: str
    tool: Optional[str]
    args_summary: Optional[str]
    status: str  # 'ok', 'retry', 'degraded', 'error'
    duration_ms: float
    note: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert entry to dictionary representation."""
        return asdict(self)


class Trace:
    """Thread-safe operational trace container."""

    def __init__(self) -> None:
        self._entries: List[TraceEntry] = []
        self._lock = threading.Lock()

    def append(
        self,
        step: str,
        tool: Optional[str] = None,
        args_summary: Optional[str] = None,
        status: str = "ok",
        duration_ms: float = 0.0,
        note: Optional[str] = None,
        ts_utc: Optional[str] = None,
    ) -> TraceEntry:
        """Append a trace entry in a thread-safe manner."""
        if ts_utc is None:
            ts_utc = datetime.now(timezone.utc).isoformat()
        entry = TraceEntry(
            ts_utc=ts_utc,
            step=step,
            tool=tool,
            args_summary=args_summary,
            status=status,
            duration_ms=round(duration_ms, 2),
            note=note,
        )
        with self._lock:
            self._entries.append(entry)
        return entry

    def to_list(self) -> List[Dict[str, Any]]:
        """Return a snapshot of all trace entries as serialisable dictionaries."""
        with self._lock:
            return [e.to_dict() for e in self._entries]

    @contextmanager
    def step(
        self,
        name: str,
        tool: Optional[str] = None,
        args_summary: Optional[str] = None,
        note: Optional[str] = None,
    ) -> Iterator["TraceStepContext"]:
        """Context manager measuring execution timing and recording completion status."""
        start = time.perf_counter()
        ctx = TraceStepContext(name=name, tool=tool, args_summary=args_summary, note=note)
        try:
            yield ctx
            duration_ms = (time.perf_counter() - start) * 1000.0
            self.append(
                step=ctx.name,
                tool=ctx.tool,
                args_summary=ctx.args_summary,
                status=ctx.status,
                duration_ms=duration_ms,
                note=ctx.note,
            )
        except Exception as exc:
            duration_ms = (time.perf_counter() - start) * 1000.0
            self.append(
                step=ctx.name,
                tool=ctx.tool,
                args_summary=ctx.args_summary,
                status="error",
                duration_ms=duration_ms,
                note=f"Exception: {exc}",
            )
            raise


class TraceStepContext:
    """Mutable context passed to trace.step() blocks."""

    def __init__(
        self,
        name: str,
        tool: Optional[str] = None,
        args_summary: Optional[str] = None,
        note: Optional[str] = None,
    ) -> None:
        self.name = name
        self.tool = tool
        self.args_summary = args_summary
        self.note = note
        self.status = "ok"

