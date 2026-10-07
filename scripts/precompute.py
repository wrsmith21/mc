"""Run the agent over the whole intake queue once and cache the results (fast cold starts on Vercel).

    uv run --env-file .env python -m scripts.precompute          # live: warms Claude extraction/explanation caches
    DEMO_MODE=replay uv run python -m scripts.precompute         # offline: deterministic template reasons
"""
import json
import os
import tempfile
import time

# The warm pass below seeds a throwaway state store, never the local or shared demo state.
os.environ["STATE_DB"] = os.path.join(tempfile.mkdtemp(), "state.db")
os.environ.pop("DATABASE_URL", None)

from backend.engine.pipeline import Agent  # noqa: E402
from backend.service import DemoService  # noqa: E402
from backend.state import BufferedState  # noqa: E402
from backend.store import CACHE, get_store  # noqa: E402


class _Empty:
    def bulk(self, *_):
        pass


def main():
    s = get_store()
    agent = Agent(s, BufferedState(_Empty()))
    t = time.time()
    results = {}
    for item in s.intake:
        results[item["intake_id"]] = agent.process(item, live=bool(item.get("storyboard_key")))
    CACHE.mkdir(parents=True, exist_ok=True)
    (CACHE / "agent_results.json").write_text(json.dumps(results, default=str))
    sources = {}
    for r in results.values():
        sources[r["extraction"]["source"]] = sources.get(r["extraction"]["source"], 0) + 1
    print(f"{len(results)} results in {time.time() - t:.1f}s · extraction sources {sources}")

    # Seeded receipts and corrections change some findings, so warm the cache from the state the demo starts in.
    t = time.time()
    svc = DemoService()
    svc.reset()
    reasons = {}
    for iid in svc.items:
        src = svc.result(iid)["explanation_meta"]["source"]
        reasons[src] = reasons.get(src, 0) + 1
    print(f"warmed {len(svc.items)} invoices from the starting state in {time.time() - t:.1f}s · reason sources {reasons}")


if __name__ == "__main__":
    main()
