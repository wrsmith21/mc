"""Policy as versioned data. The agent applies the approval matrix and thresholds it is given; it never invents them.

Version 1 is the seed (data/seed/policies.json). Each change by an admin is a new version with who, when, why and a
field-level diff. Runs record the version they used, so a result can always be traced to the rules in force.
"""
import copy

from .state import now_iso

# Editable settings: path -> (label, minimum, maximum)
EDITABLE = {
    "approval_matrix.tiers.0.max": ("Cost-centre owner approves below ($)", 1_000, 1_000_000),
    "approval_matrix.tiers.1.max": ("Director approves below ($)", 10_000, 5_000_000),
    "risk.amount_vs_norm_multiple": ("Hold when amount exceeds supplier median by (×)", 1.2, 10),
    "risk.bank_change_window_days": ("Bank change counts as recent for (days)", 1, 180),
    "risk.duplicate_window_days": ("Duplicate search window (days)", 7, 365),
    "risk.confidence_bands.fast_track": ("Fast-track at calibrated confidence ≥", 0.5, 0.999),
    "risk.confidence_bands.review": ("Needs a person below calibrated confidence", 0.0, 0.95),
    "risk.standing_receipt_tolerance": ("Standing receipt rule tolerance (share of average)", 0.0, 0.5),
    "capitalisation.rules.0.threshold_per_unit": ("Capitalise computer hardware at or above ($ per unit)", 100, 50_000),
    "po_policy.required.2.min": ("Consulting needs a PO from ($)", 0, 1_000_000),
    "po_policy.required.4.min": ("Marketing needs a PO from ($)", 0, 1_000_000),
    "cutoff.materiality_usd": ("Report unaccrued closed-period spend from ($)", 0, 1_000_000),
    "receipt.reminder_business_days": ("Remind requester after (business days)", 1, 20),
    "receipt.escalate_business_days": ("Escalate to cost-centre owner after (business days)", 1, 30),
    "price.matter_budget_warn_share": ("Warn when a matter budget is used beyond (share)", 0.5, 1.0),
}


def _get(d, path):
    for k in path.split("."):
        d = d[int(k)] if isinstance(d, list) else d[k]
    return d


def _set(d, path, value):
    keys = path.split(".")
    for k in keys[:-1]:
        d = d[int(k)] if isinstance(d, list) else d[k]
    last = keys[-1]
    if isinstance(d, list):
        d[int(last)] = value
    else:
        d[last] = value


class Policies:
    def __init__(self, store, state):
        self.s = store
        self.state = state
        self.seed = copy.deepcopy(store.policies)

    def versions(self):
        rows = sorted(self.state.prefix("policy:v").values(), key=lambda v: v["version"])
        return [{"version": 1, "by": "SEED", "at": f"{self.s.demo_date}T00:00:00", "reason": "Initial policy set",
                 "changes": []}] + [{k: v[k] for k in ("version", "by", "by_name", "at", "reason", "changes")}
                                    for v in rows]

    def current(self):
        rows = self.state.prefix("policy:v")
        if not rows:
            return 1, self.seed
        latest = max(rows.values(), key=lambda v: v["version"])
        return latest["version"], latest["policies"]

    def apply(self):
        """Point every engine at the current version (called on start and after any change)."""
        version, pol = self.current()
        self.s.policies.clear()
        self.s.policies.update(copy.deepcopy(pol))
        self.s.policy_version = version
        return version

    def editable(self):
        version, pol = self.current()
        return {"version": version, "fields": [{"path": p, "label": lab, "min": lo, "max": hi, "value": _get(pol, p)}
                                               for p, (lab, lo, hi) in EDITABLE.items()]}

    def update(self, by, by_name, changes, reason):
        if not reason or len(reason.strip()) < 5:
            raise ValueError("Say why the policy is changing")
        version, pol = self.current()
        new = copy.deepcopy(pol)
        diff = []
        for path, value in changes.items():
            if path not in EDITABLE:
                raise ValueError(f"{path} is not an editable setting")
            label, lo, hi = EDITABLE[path]
            value = float(value)
            if not lo <= value <= hi:
                raise ValueError(f"{label} must be between {lo} and {hi}")
            before = _get(new, path)
            value = int(value) if isinstance(before, int) and value.is_integer() else value
            if before != value:
                _set(new, path, value)
                diff.append({"path": path, "label": label, "before": before, "after": value})
        if not diff:
            raise ValueError("No change to save")
        tiers = new["approval_matrix"]["tiers"]
        tiers[1]["min"], tiers[2]["min"] = tiers[0]["max"], tiers[1]["max"]
        k = lambda v: f"${v / 1000:,.0f}k"  # noqa: E731
        tiers[0]["label"] = f"Under {k(tiers[0]['max'])}: cost-centre owner"
        tiers[1]["label"] = f"{k(tiers[1]['min'])}–{k(tiers[1]['max'])}: director"
        tiers[2]["label"] = f"Over {k(tiers[2]['min'])}: VP"
        if tiers[0]["max"] >= tiers[1]["max"]:
            raise ValueError("The director threshold must be above the cost-centre owner threshold")
        if new["risk"]["confidence_bands"]["review"] >= new["risk"]["confidence_bands"]["fast_track"]:
            raise ValueError("The review floor must be below the fast-track threshold")
        rec = {"version": version + 1, "by": by, "by_name": by_name, "at": now_iso(), "reason": reason.strip(),
               "changes": diff, "policies": new}
        self.state.put(f"policy:v{version + 1:03d}", rec)
        self.state.add_event("policy", by, "POLICY_CHANGED", {"version": version + 1, "reason": reason,
                                                              "changes": diff})
        self.apply()
        return {k: rec[k] for k in ("version", "by", "by_name", "at", "reason", "changes")}
