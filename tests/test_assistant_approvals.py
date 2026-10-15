"""Chat sign-off: only the signed-in person's own step, and only when CLEAR's checks leave nothing to do."""
import os
import tempfile

os.environ["DEMO_MODE"] = "replay"
os.environ.pop("DEMO_PASSWORD", None)
os.environ.setdefault("STATE_DB", os.path.join(tempfile.mkdtemp(), "state.db"))

import pytest  # noqa: E402

from backend import app as app_module  # noqa: E402
from backend.agents.assistant import Assistant  # noqa: E402

ALEX = "E34120"


@pytest.fixture()
def svc():
    s = app_module.svc()
    s.reset()
    return s


def pid(s, name):
    return next(i for i, p in s.s.people.items() if p["name"] == name)


def test_clean_invoice_takes_each_persons_own_step(svc):
    a = Assistant(svc)
    iid = svc.by_key["telecoms"]
    svc.run(iid, "manual", ALEX, live=False)
    assert a.readiness({"intake_id": iid}, ALEX)["ready"]
    a._approve({"intake_id": iid}, ALEX)
    assert svc.result(iid)["status"] == "IN_APPROVAL"
    with pytest.raises(PermissionError):  # the director's step is not Alex's
        a._approve({"intake_id": iid}, ALEX)
    director = svc.result(iid)["decision"]["chain"][0]
    a._approve({"intake_id": iid}, director)
    assert svc.result(iid)["status"] == "APPROVED"


@pytest.mark.parametrize("key", ["bank_change", "duplicate", "legal"])
def test_anything_left_to_do_blocks_sign_off(svc, key):
    iid = svc.by_key[key]
    svc.run(iid, "manual", ALEX, live=False)
    with pytest.raises(ValueError, match="still needs a person"):
        Assistant(svc)._approve({"intake_id": iid}, ALEX)
    assert not svc.result(iid).get("decision")


def test_unworked_invoice_is_not_signed_off(svc):
    with pytest.raises(ValueError, match="hasn't worked it"):
        Assistant(svc)._approve({"intake_id": svc.by_key["dell"]}, ALEX)


def test_case_needs_clear_investigation_and_separate_preparer_and_approver(svc):
    a = Assistant(svc)
    hana, priya = pid(svc, "Hana Zhang"), pid(svc, "Priya Nair")
    cid = next(c["case_id"] for c in svc.cases.all() if c["type"] == "MISAPPLIED")
    with pytest.raises(ValueError, match="hasn't investigated"):
        a._approve({"case_id": cid}, hana)
    svc.investigate_case(cid, hana)
    with pytest.raises(PermissionError):  # Priya approves; she does not prepare
        a._approve({"case_id": cid}, priya)
    a._approve({"case_id": cid}, hana)
    assert svc.cases.get(cid)["status"] == "Pending approval"
    with pytest.raises(PermissionError):  # Hana prepared it, so she cannot approve it
        a._approve({"case_id": cid}, hana)
    a._approve({"case_id": cid}, priya)
    assert svc.cases.get(cid)["status"] == "Approved"


def test_case_whose_investigation_disagrees_with_the_fix_is_blocked(svc):
    a = Assistant(svc)
    hana = pid(svc, "Hana Zhang")
    cid = next(c["case_id"] for c in svc.cases.all() if c["type"] == "MISAPPLIED")
    svc.investigate_case(cid, hana)
    inv = svc.state.get(f"caseinv:{cid}")
    svc.state.put(f"caseinv:{cid}", {**inv, "next_action": "Escalate to the SOX control owner"})
    with pytest.raises(ValueError, match="not the drafted fix"):
        a._approve({"case_id": cid}, hana)
