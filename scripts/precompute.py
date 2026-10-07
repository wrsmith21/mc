"""Run the agent over the whole intake queue once and cache the results (fast cold starts on Vercel).

    uv run --env-file .env python -m scripts.precompute          # live: warms Claude extraction/explanation caches
    DEMO_MODE=replay uv run python -m scripts.precompute         # offline: deterministic template reasons
"""
import json
import time

from backend.engine.pipeline import Agent
from backend.state import BufferedState
from backend.store import CACHE, get_store


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


if __name__ == "__main__":
    main()
