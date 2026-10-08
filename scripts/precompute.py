"""Run the agent the way the overnight batch would, then warm every model cache the demo can touch.

    uv run --env-file .env python -m scripts.precompute          # live: Claude reads and explains, results cached
    DEMO_MODE=replay uv run python -m scripts.precompute         # offline: deterministic template reasons

1. Invoices received before this morning's mailbox are worked as the overnight batch and saved as their first run.
2. A throwaway demo state is reset and every invoice is run as a reviewer would run it, so opening or re-running any
   invoice is served from cache. The storyboard follow-ups (receipt confirmed, a correction learned) are run too.
"""
import json
import os
import tempfile
import time

# The warm pass seeds a throwaway state store, never the local or shared demo state.
os.environ["STATE_DB"] = os.path.join(tempfile.mkdtemp(), "state.db")
os.environ.pop("DATABASE_URL", None)

from backend.agents.supervisor import Supervisor  # noqa: E402
from backend.service import MAILBOX_CUTOFF, DemoService  # noqa: E402
from backend.state import BufferedState  # noqa: E402
from backend.store import CACHE, get_store  # noqa: E402


class _Empty:
    def bulk(self, *_):
        pass


def main():
    s = get_store()
    agent = Supervisor(s, BufferedState(_Empty()))
    t = time.time()
    results = {}
    for item in s.intake:
        if item["received_at"] < MAILBOX_CUTOFF:
            results[item["intake_id"]] = agent.process(item, live=bool(item.get("storyboard_key")), trigger="batch")
    CACHE.mkdir(parents=True, exist_ok=True)
    (CACHE / "agent_results.json").write_text(json.dumps(results, default=str))
    print(f"overnight batch: {len(results)} invoices in {time.time() - t:.1f}s")

    t = time.time()
    svc = DemoService()
    svc.reset()
    sources = {}
    for iid in svc.items:
        src = svc.run(iid, "manual")["explanation_meta"]["source"]
        sources[src] = sources.get(src, 0) + 1
    legal, l1, l2 = svc.by_key["legal"], svc.by_key["learning_1"], svc.by_key["learning_2"]
    svc.confirm_receipt(legal, svc.latest(legal)["requester"]["person"]["id"], "Contract review delivered")
    svc.run(legal)
    svc.submit(l1, "override", "E34120", "Chargers are for IT end-user laptops",
               {"account": "6360", "cost_centre": "CC4410"})
    svc.run(l2)
    # Investigations for the close cases a demo opens: every journal and cash finding, and the largest AP ones.
    cases = svc.cases.all()
    picks = [c for c in cases if c["source"] == "journals" or c["type"] in ("MISAPPLIED", "DOUBLE_APPLICATION")]
    picks += sorted([c for c in cases if c["source"] == "ap_ledger"], key=lambda c: -c["amount"])[:3]
    for c in picks:
        svc.investigate_case(c["case_id"], "E30233")
    print(f"investigated {len(picks)} close cases")
    print(f"warmed {len(svc.items)} invoices from the starting state in {time.time() - t:.1f}s · reason sources {sources}")


if __name__ == "__main__":
    main()
