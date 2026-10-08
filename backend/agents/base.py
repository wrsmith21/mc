"""Agent runtime primitives: tools with typed contracts, a registry, and a run context that records every call.

A tool is the only way an agent touches data or policy. Each call is timed and recorded with its arguments and a
one-line result, so a run can be replayed, audited and shown step by step.
"""
import time
import uuid
from contextlib import contextmanager

from .. import clock

MAX_ARG_TEXT = 160


def now_iso():
    return clock.now_iso()


def compact(value, depth=0):
    """A readable, bounded view of tool arguments for the run record."""
    if isinstance(value, dict):
        if "invoice_num" in value and "lines" in value:
            return f"<invoice {value.get('invoice_num')} · {value.get('vendor_name')}>"
        if depth > 1:
            return "{…}"
        return {k: compact(v, depth + 1) for k, v in list(value.items())[:12]}
    if isinstance(value, (list, tuple)):
        if len(value) > 6:
            return [compact(v, depth + 1) for v in value[:5]] + [f"… {len(value) - 5} more"]
        return [compact(v, depth + 1) for v in value]
    if isinstance(value, str) and len(value) > MAX_ARG_TEXT:
        return value[:MAX_ARG_TEXT] + "…"
    if isinstance(value, float):
        return round(value, 4)
    return value


class Tool:
    def __init__(self, name, agent, description, fn, inputs, outputs, summary, kind="rules",
                 investigator=False, source=None):
        self.name = name
        self.agent = agent
        self.description = description
        self.fn = fn
        self.inputs = inputs
        self.outputs = outputs
        self.summary = summary
        self.kind = kind                  # rules | history | model | claude | external | state
        self.investigator = investigator  # read-only tools the Claude investigator may call
        self.source = source or (lambda result: "computed")

    def describe(self):
        return {"name": self.name, "agent": self.agent, "description": self.description, "kind": self.kind,
                "investigator": self.investigator,
                "input_schema": {"type": "object", "properties": self.inputs,
                                 "required": [k for k, v in self.inputs.items() if not v.get("optional")]},
                "output_schema": {"type": "object", "properties": self.outputs}}


class ToolRegistry:
    def __init__(self):
        self.tools = {}

    def add(self, tool: Tool):
        self.tools[tool.name] = tool
        return tool

    def __getitem__(self, name):
        return self.tools[name]

    def describe(self):
        return [t.describe() for t in self.tools.values()]


class RunContext:
    """Collects the steps and tool calls of one agent run and streams them as they happen."""

    def __init__(self, registry, intake_id, trigger, actor, on_event=None):
        self.registry = registry
        self.on_event = on_event
        self.trace = []
        self._step = None
        self._t0 = time.perf_counter()
        self._calls = 0
        self.run = {"run_id": f"RUN-{uuid.uuid4().hex[:10].upper()}", "intake_id": intake_id, "trigger": trigger,
                    "actor": actor, "started_at": now_iso(), "steps": self.trace, "tool_calls": 0,
                    "tokens": {"input": 0, "output": 0}}

    def emit(self, event):
        if self.on_event:
            self.on_event(event)

    @contextmanager
    def step(self, agent, key, label, process_step):
        rec = {"key": key, "label": label, "agent": agent, "process_step": process_step, "status": "ok",
               "detail": "", "facts": [], "tool_calls": []}
        self._step = rec
        self.emit({"type": "stage", "key": key, "agent": agent, "label": label})
        t = time.perf_counter()
        try:
            yield rec
        finally:
            rec["ms"] = round((time.perf_counter() - t) * 1000, 1)
            self.trace.append(rec)
            self._step = None
            self.emit({"type": "step", **rec})

    def call(self, tool_name, /, show=None, **args):
        tool = self.registry[tool_name]
        self._calls += 1
        tc = {"id": f"T{self._calls:02d}", "tool": tool_name, "kind": tool.kind, "args": show or compact(args)}
        t = time.perf_counter()
        try:
            result = tool.fn(**args)
        except Exception as e:  # recorded, then re-raised for the agent to decide
            tc.update(ms=round((time.perf_counter() - t) * 1000, 1), error=f"{type(e).__name__}: {e}",
                      source="error", summary="Call failed")
            self._record(tc)
            raise
        tc["ms"] = round((time.perf_counter() - t) * 1000, 1)
        tc["source"] = tool.source(result)
        try:
            tc["summary"] = tool.summary(result)
        except Exception:
            tc["summary"] = "Returned"
        self._record(tc)
        return result

    def _record(self, tc):
        if self._step is not None:
            self._step["tool_calls"].append(tc)
        self.run["tool_calls"] = self._calls
        self.emit({"type": "tool", "key": self._step["key"] if self._step else None, "call": tc})

    def add_tokens(self, usage):
        if usage:
            self.run["tokens"]["input"] += usage.get("input_tokens", 0) or 0
            self.run["tokens"]["output"] += usage.get("output_tokens", 0) or 0

    def finish(self):
        self.run["finished_at"] = now_iso()
        self.run["ms"] = round((time.perf_counter() - self._t0) * 1000, 1)
        return self.run
