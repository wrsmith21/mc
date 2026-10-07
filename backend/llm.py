"""Claude reads the invoice PDF and writes the plain-English reason. It never picks the account.

Results are cached by content hash so replay mode is deterministic and works offline.
"""
import base64
import hashlib
import json
import os
import time
from pathlib import Path

from .store import CACHE

MODEL = os.environ.get("CLAUDE_MODEL", "claude-opus-5-5")
EXTRACT_DIR = CACHE / "extractions"
EXPLAIN_DIR = CACHE / "explanations"
RUNTIME_DIR = Path(os.environ.get("RUNTIME_CACHE_DIR", "/tmp/mc-demo-cache"))
FALLBACK_BETA = "server-side-fallback-2026-07-01"

_money = {"type": "number"}
_str = {"type": "string"}
_nstr = {"type": ["string", "null"]}
INVOICE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["vendor_name", "vendor_tax_id", "invoice_num", "invoice_date", "due_date", "currency", "bill_to",
                 "po_reference", "service_period_start", "service_period_end", "matter", "named_contact",
                 "remit_account_last4", "remit_routing_number", "lines", "subtotal", "tax", "total", "notes"],
    "properties": {
        "vendor_name": _str, "vendor_tax_id": _nstr, "invoice_num": _str,
        "invoice_date": {"type": "string", "description": "ISO date YYYY-MM-DD"},
        "due_date": {"type": ["string", "null"], "description": "ISO date YYYY-MM-DD"},
        "currency": {"type": "string", "description": "ISO 4217 code"}, "bill_to": _nstr,
        "po_reference": {"type": ["string", "null"], "description": "Customer PO number if printed, else null"},
        "service_period_start": _nstr, "service_period_end": _nstr,
        "matter": {"type": ["string", "null"], "description": "Legal matter reference if present"},
        "named_contact": {"type": ["string", "null"],
                          "description": "Person named as orderer, client contact or 'prepared for'"},
        "remit_account_last4": _nstr, "remit_routing_number": _nstr,
        "lines": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": ["description", "qty", "unit_price", "amount"],
            "properties": {"description": _str, "qty": _money, "unit_price": _money, "amount": _money}}},
        "subtotal": _money, "tax": _money, "total": _money,
        "notes": {"type": ["string", "null"], "description": "Anything unusual printed on the invoice"},
    },
}

EXTRACT_PROMPT = ("Extract the fields from this supplier invoice exactly as printed. Use ISO dates. "
                  "Use null for anything not printed. Do not infer accounting codes.")

EXPLAIN_SYSTEM = (
    "You write the reason line for an accounts-payable reviewer at a payments company. You are given the "
    "deterministic findings of a recommendation engine (scores, history counts, policy checks). Write 2-3 short "
    "sentences in plain English for a finance audience: what the agent recommends and why, citing the numbers "
    "given. Say 'recommends', never 'decided'. Do not add facts that are not in the findings.")


def _key(*parts) -> str:
    h = hashlib.sha256()
    for p in parts:
        h.update(p if isinstance(p, bytes) else json.dumps(p, sort_keys=True).encode())
    return h.hexdigest()[:24]


def _cache_get(folder: Path, key: str):
    for base in (RUNTIME_DIR / folder.name, folder):
        p = base / f"{key}.json"
        if p.exists():
            return json.loads(p.read_text())
    return None


def _cache_put(folder: Path, key: str, value):
    for base in (folder, RUNTIME_DIR / folder.name):
        try:
            base.mkdir(parents=True, exist_ok=True)
            (base / f"{key}.json").write_text(json.dumps(value, indent=1))
            return
        except OSError:
            continue


def live_enabled() -> bool:
    return os.environ.get("DEMO_MODE", "live") == "live" and os.environ.get("DEMO_OFFLINE") != "1"


def _client():
    import anthropic
    return anthropic.Anthropic(timeout=45.0, max_retries=1)


def _text(response):
    if response.stop_reason == "refusal":
        raise RuntimeError("Model declined the request")
    return next(b.text for b in response.content if b.type == "text")


def extract_pdf(pdf_bytes: bytes, force_live=False):
    """Returns (fields, meta). meta says whether this was a live Claude call or a cached replay."""
    key = _key(pdf_bytes, MODEL, INVOICE_SCHEMA)
    cached = _cache_get(EXTRACT_DIR, key)
    if cached and not force_live:
        return cached["fields"], {**cached["meta"], "source": "cache"}
    if not live_enabled():
        return None, {"source": "unavailable", "reason": "Replay mode and no cached extraction"}
    t = time.time()
    response = _client().beta.messages.create(
        model=MODEL, max_tokens=8000, betas=[FALLBACK_BETA], fallbacks="default",
        output_config={"effort": "low", "format": {"type": "json_schema", "schema": INVOICE_SCHEMA}},
        messages=[{"role": "user", "content": [
            {"type": "document", "source": {"type": "base64", "media_type": "application/pdf",
                                            "data": base64.standard_b64encode(pdf_bytes).decode()}},
            {"type": "text", "text": EXTRACT_PROMPT}]}],
    )
    fields = json.loads(_text(response))
    meta = {"source": "live", "model": response.model, "latency_ms": round((time.time() - t) * 1000),
            "input_tokens": response.usage.input_tokens, "output_tokens": response.usage.output_tokens,
            "request_id": getattr(response, "_request_id", None)}
    _cache_put(EXTRACT_DIR, key, {"fields": fields, "meta": meta})
    return fields, meta


def explain(findings: dict, fallback_text: str):
    """Plain-English reason from the engine's findings. Falls back to the deterministic template text."""
    key = _key(findings, MODEL, EXPLAIN_SYSTEM)
    cached = _cache_get(EXPLAIN_DIR, key)
    if cached:
        return cached["text"], {**cached["meta"], "source": "cache"}
    if not live_enabled():
        return fallback_text, {"source": "template"}
    try:
        t = time.time()
        response = _client().beta.messages.create(
            model=MODEL, max_tokens=2000, betas=[FALLBACK_BETA], fallbacks="default",
            output_config={"effort": "low"}, system=EXPLAIN_SYSTEM,
            messages=[{"role": "user", "content": json.dumps(findings, indent=1)}],
        )
        text = _text(response).strip()
        meta = {"source": "live", "model": response.model, "latency_ms": round((time.time() - t) * 1000)}
        _cache_put(EXPLAIN_DIR, key, {"text": text, "meta": meta})
        return text, meta
    except Exception as e:  # network, auth or refusal: the deterministic reason is always available
        return fallback_text, {"source": "template", "error": type(e).__name__}
