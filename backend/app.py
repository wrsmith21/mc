"""HTTP API for the CLEAR demo (Coding, Ledger, Exceptions, Approvals, Reconciliation)."""
import hashlib
import hmac
import json
import os

from fastapi import Body, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse, StreamingResponse

from . import auth, brand, clock, llm
from . import model as ds
from .integrations import external
from .service import DemoService
from .store import ROOT

PASSWORD = os.environ.get("DEMO_PASSWORD")
TOKEN = hashlib.sha256(f"mc-nonpo::{PASSWORD}".encode()).hexdigest() if PASSWORD else None
WILDCARD = os.environ.get("ENABLE_WILDCARD", "1") == "1"

app = FastAPI(title=brand.PRODUCT, version="1.0")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5174", "http://127.0.0.1:5174"],
                   allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
_svc = None


def svc() -> DemoService:
    global _svc
    if _svc is None:
        _svc = DemoService()
    else:
        _svc.sync()
    return _svc


@app.middleware("http")
async def passcode(request: Request, call_next):
    path = request.url.path
    if TOKEN and path.startswith("/api/") and path not in ("/api/health", "/api/login", "/api/warm"):
        supplied = request.cookies.get("mc_demo") or request.headers.get("x-demo-token") or ""
        if not hmac.compare_digest(supplied, TOKEN):
            return JSONResponse({"detail": "passcode required"}, status_code=401)
    return await call_next(request)


@app.exception_handler(PermissionError)
async def forbidden(request: Request, exc: PermissionError):
    return JSONResponse({"detail": str(exc)}, status_code=403)


def who(request: Request, fallback=None):
    """The signed-in person acts; a body or query actor is only used when nobody is signed in (scripts, tests)."""
    user = auth.verify(request.cookies.get("mc_user"))
    if user:
        return user
    if fallback and not TOKEN:  # local scripts and tests only; the hosted app always needs a session
        return fallback
    raise HTTPException(401, "Sign in as a named person first")


def _bad(e: Exception):
    raise HTTPException(status_code=409, detail=str(e))


@app.get("/api/health")
def health():
    return {"ok": True}


@app.get("/api/warm")
def warm():
    """Load the service and the close sweep so the first real request is fast (called by the sign-in screens)."""
    s = svc()
    s.anomalies()
    return {"ok": True, "invoices": len(s.items)}


@app.post("/api/login")
def login(body: dict = Body(...)):
    if not TOKEN:
        return {"ok": True}
    if not hmac.compare_digest(str(body.get("passcode", "")), PASSWORD):
        raise HTTPException(401, "Incorrect passcode")
    resp = JSONResponse({"ok": True})
    resp.set_cookie("mc_demo", TOKEN, httponly=True, samesite="lax", secure=True, max_age=60 * 60 * 24 * 14)
    return resp


@app.get("/api/meta")
def meta():
    s = svc()
    s.sync_clock()
    return {"demo_date": s.s.demo_date, "now": clock.now_iso(), "clock_offset_hours": clock.offset_hours(), "mode": "live" if llm.live_enabled() else "replay", "model": llm.MODEL,
            "wildcard": WILDCARD, "personas": persona_list(s),
            "counts": {"history_invoices": len(s.s.history), "history_lines": len(s.s.lines),
                       "vendors": len(s.s.vendors), "people": len(s.s.people), "pos": len(s.s.pos),
                       "open_pos": len(s.s.open_pos)},
            "storyboard": s.by_key, "ofac": {"source": external.ofac.load().source, "entries": len(external.ofac.names)}}


def persona_list(s):
    ids = ["E34120", "E31188", "E33901", "E20417", "E10022", "E30542", "E20388", "E30911", "E30876", "E30233",
           "E30719", "E30655"]
    return [s.s.person_brief(i) for i in ids if i in s.s.people]


@app.get("/api/queue")
def queue():
    return svc().queue()


@app.get("/api/summary")
def summary():
    return svc().summary()


@app.get("/api/invoices/{intake_id}")
def invoice(intake_id: str):
    try:
        r = svc().result(intake_id)
        person = ((r.get("requester") or {}).get("person") or {}).get("id")
        r["requester_link_token"] = auth.sign(person) if person else None
        return r
    except KeyError:
        raise HTTPException(404, "Unknown invoice")


def _sse(events):
    def stream():
        for ev in events:
            yield f"data: {json.dumps(ev, default=str)}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/api/invoices/{intake_id}/run")
def run(intake_id: str, request: Request, actor: str | None = None):
    s = svc()
    actor = who(request, actor)
    s.authorize(actor, "run_agent", intake_id)
    if intake_id not in s.all_items():
        raise HTTPException(404, "Unknown invoice")
    return _sse(s.run_events(intake_id, actor=actor))


@app.get("/api/invoices/{intake_id}/runs")
def runs(intake_id: str):
    return svc().state.get(f"runs:{intake_id}") or []


@app.get("/api/mailbox/run")
def run_mailbox(request: Request, actor: str | None = None):
    actor = who(request, actor)
    svc().authorize(actor, "run_agent", "mailbox")
    return _sse(svc().run_mailbox(actor=actor))


@app.get("/api/work")
def work():
    return svc().work()


@app.post("/api/vendors/{vendor_id}/callback")
def callback(vendor_id: str, request: Request, body: dict = Body(...)):
    try:
        return svc().callback(vendor_id, body["outcome"], who(request, body.get("by")), body.get("note", ""))
    except ValueError as e:
        _bad(e)


@app.post("/api/invoices/{intake_id}/onboard")
def onboard(intake_id: str, request: Request, body: dict = Body(...)):
    try:
        return svc().onboard(intake_id, who(request, body.get("by")), body["tax_id"], body.get("category", "facilities"))
    except ValueError as e:
        _bad(e)


@app.post("/api/procurement/requests")
def po_request(request: Request, body: dict = Body(...)):
    try:
        return svc().request_po(body["vendor_id"], body["kind"], who(request, body.get("by")))
    except ValueError as e:
        _bad(e)


@app.post("/api/clock/advance")
def advance_clock(request: Request, body: dict = Body(...)):
    return svc().advance_clock(float(body.get("hours", 24)), who(request, body.get("by")))


@app.get("/api/model")
def model_info():
    return {"metrics": ds.metrics(), "card": ds.card(), "manifest": ds.manifest(),
            "calibration": ds._calibration(),
            "history": {"invoices": len(svc().s.history), "lines": len(svc().s.lines), "vendors": len(svc().s.vendors),
                        "pos": len(svc().s.pos)}}


def _case_call(fn, *args):
    try:
        return fn(*args)
    except KeyError:
        raise HTTPException(404, "Unknown case")
    except PermissionError as e:
        raise HTTPException(403, str(e))
    except ValueError as e:
        _bad(e)


@app.get("/api/cases")
def cases(source: str | None = None, status: str | None = None):
    out = svc().cases.all()
    return [c for c in out if (not source or c["source"] == source) and (not status or c["status"] == status)]


@app.get("/api/close")
def close_dashboard():
    return svc().cases.dashboard()


@app.get("/api/cases/batches/{batch}.csv")
def case_batch(batch: str):
    return PlainTextResponse(_case_call(svc().cases.batch_csv, batch), media_type="text/csv",
                             headers={"Content-Disposition": f"attachment; filename={batch}.csv"})


@app.post("/api/cases/bulk-prepare")
def cases_bulk(request: Request, body: dict = Body(...)):
    return _case_call(svc().cases.bulk_prepare, who(request, body.get("by")), float(body.get("min_confidence", 0.95)))


@app.post("/api/cases/export")
def cases_export(request: Request, body: dict = Body(...)):
    return _case_call(svc().cases.export, body["kind"], who(request, body.get("by")))


@app.get("/api/cases/{case_id}")
def case(case_id: str):
    c = _case_call(svc().cases.get, case_id)
    c["investigation"] = svc().state.get(f"caseinv:{case_id}")
    return c


@app.post("/api/cases/{case_id}/{action}")
def case_action(case_id: str, action: str, request: Request, body: dict = Body(...)):
    c = svc().cases
    by = who(request, body.get("by"))
    if action == "prepare":
        return _case_call(c.prepare, case_id, by, body.get("note", ""), body.get("account"))
    if action == "approve":
        return _case_call(c.approve, case_id, by, body.get("note", ""))
    if action == "send-back":
        return _case_call(c.send_back, case_id, by, body.get("reason", ""))
    if action == "dismiss":
        return _case_call(c.dismiss, case_id, by, body.get("reason"), body.get("note", ""))
    if action == "investigate":
        return _case_call(svc().investigate_case, case_id, by)
    raise HTTPException(404, "Unknown action")


@app.get("/api/operations")
def operations():
    return svc().operations()


@app.get("/api/agents")
def agents():
    return svc().agents()


@app.get("/api/invoices/{intake_id}/audit")
def audit(intake_id: str):
    return svc().audit(intake_id)


@app.post("/api/invoices/{intake_id}/receipt/request")
def receipt_request(intake_id: str, request: Request, body: dict = Body(default={})):
    try:
        return svc().request_receipt(intake_id, actor=who(request, body.get("actor")))
    except ValueError as e:
        _bad(e)


@app.post("/api/invoices/{intake_id}/receipt/confirm")
def receipt_confirm(intake_id: str, request: Request, body: dict = Body(...)):
    # A signed link (QR code / email) identifies the requester on a device with no session.
    linked = auth.verify(body.get("token")) if body.get("token") else None
    if body.get("token") and linked != body.get("by"):
        raise HTTPException(403, "This confirmation link is not valid for that person")
    actor = linked or who(request, body.get("by"))
    return svc().confirm_receipt(intake_id, actor, body.get("note", ""))


@app.get("/api/tasks")
def tasks(person: str | None = None):
    return svc().tasks(person)


@app.post("/api/invoices/{intake_id}/decision")
def decision(intake_id: str, request: Request, body: dict = Body(...)):
    try:
        return svc().submit(intake_id, body["action"], who(request, body.get("actor")), body.get("reason"),
                            body.get("override") or {})
    except ValueError as e:
        _bad(e)


@app.post("/api/invoices/{intake_id}/approve")
def approve(intake_id: str, request: Request, body: dict = Body(default={})):
    try:
        return svc().approve_step(intake_id, who(request, body.get("approver")))
    except ValueError as e:
        _bad(e)


@app.get("/api/anomalies")
def anomalies():
    return svc().anomalies()


@app.get("/api/insights/procurement")
def procurement():
    return svc().procurement()


@app.get("/api/vendors/{vendor_id}")
def vendor(vendor_id: str):
    s = svc().s
    v = s.vendors.get(vendor_id)
    if not v:
        raise HTTPException(404, "Unknown vendor")
    invs = s.history_by_vendor.get(vendor_id, [])
    bank = {k: val for k, val in v["bank"].items() if k != "iban"}
    return {**v, "bank": bank, "stats": s.vendor_stats(vendor_id),
            "recent": [{k: i[k] for k in ("invoice_id", "invoice_num", "invoice_date", "total_usd", "po_number")}
                       for i in invs[-12:]][::-1]}


@app.get("/api/pdf/{intake_id}")
def pdf(intake_id: str):
    item = svc().all_items().get(intake_id)
    if not item or not item.get("pdf"):
        raise HTTPException(404, "No PDF for this invoice")
    path = ROOT / "data" / item["pdf"]
    return FileResponse(path, media_type="application/pdf", headers={"Cache-Control": "public, max-age=3600"})


@app.get("/api/pdf/{intake_id}/preview")
def pdf_preview(intake_id: str):
    item = svc().all_items().get(intake_id)
    path = ROOT / "data" / item["pdf"].replace(".pdf", ".png") if item and item.get("pdf") else None
    if not path or not path.exists():
        raise HTTPException(404, "No preview for this invoice")
    return FileResponse(path, media_type="image/png", headers={"Cache-Control": "no-cache"})


def _csv_response(text, name):
    return PlainTextResponse(text, media_type="text/csv",
                             headers={"Content-Disposition": f'attachment; filename="{name}"'})


@app.get("/api/exports/ap-interface/{part}")
def export_ap(part: str):
    headers, lines = svc().export_ap()
    if part == "headers":
        return _csv_response(headers, "AP_INVOICES_INTERFACE.csv")
    return _csv_response(lines, "AP_INVOICE_LINES_INTERFACE.csv")


@app.get("/api/exports/amortisation/{intake_id}")
def export_amortisation(intake_id: str):
    try:
        return _csv_response(svc().export_amortisation(intake_id), f"GL_INTERFACE_amortisation_{intake_id}.csv")
    except ValueError as e:
        _bad(e)


@app.get("/api/exports/reclass")
def export_reclass():
    return _csv_response(svc().export_reclass(), "GL_INTERFACE_reclass_SEP26.csv")


@app.get("/api/exports/procurement")
def export_procurement():
    return _csv_response(svc().export_procurement(), "procurement_non_po_breaches.csv")


@app.post("/api/wildcard")
async def wildcard(request: Request, file: UploadFile = File(...)):
    svc().authorize(who(request, "E34120"), "upload")
    if not WILDCARD:
        raise HTTPException(403, "Live upload is switched off")
    data = await file.read()
    if len(data) > 8 * 1024 * 1024 or not data.startswith(b"%PDF"):
        raise HTTPException(400, "Upload a PDF under 8 MB")
    try:
        return {"intake_id": svc().add_wildcard(data, file.filename or "invoice.pdf")}
    except ValueError as e:
        _bad(e)


@app.post("/api/reset")
def reset(request: Request):
    svc().authorize(who(request, "E34120"), "reset")
    svc().reset()
    return {"ok": True}


# ---------- sign-in, people, audit, policies, evidence ----------
@app.get("/api/people")
def people():
    s = svc()
    ids = list(auth.FIXED_ROLES) + ["E31188", "E33901", "E20417", "E10022", "E20388", "E33000"]
    out = []
    for pid in dict.fromkeys(ids):
        p = s.s.person_brief(pid)
        if p:
            roles = auth.roles_for(s.s, pid)
            out.append({**p, "roles": roles, "role_labels": [auth.ROLE_LABEL[r] for r in roles]})
    return out


@app.get("/api/session")
def session(request: Request):
    pid = auth.verify(request.cookies.get("mc_user"))
    if not pid:
        return {"person": None}
    s = svc()
    roles = auth.roles_for(s.s, pid)
    return {"person": s.s.person_brief(pid), "roles": roles, "role_labels": [auth.ROLE_LABEL[r] for r in roles],
            "can": sorted(a for a in auth.PERMISSIONS if auth.allowed(s.s, pid, a))}


@app.post("/api/session")
def sign_in(request: Request, body: dict = Body(...)):
    s = svc()
    pid = body.get("person_id")
    if pid not in s.s.people:
        raise HTTPException(404, "Unknown person")
    previous = auth.verify(request.cookies.get("mc_user"))
    s.state.add_event("security", pid, "SIGNED_IN", {"switched_from": previous})
    resp = JSONResponse(session_payload(s, pid))
    resp.set_cookie("mc_user", auth.sign(pid), httponly=True, samesite="lax", secure=bool(TOKEN),
                    max_age=60 * 60 * 12)
    return resp


def session_payload(s, pid):
    roles = auth.roles_for(s.s, pid)
    return {"person": s.s.person_brief(pid), "roles": roles, "role_labels": [auth.ROLE_LABEL[r] for r in roles],
            "can": sorted(a for a in auth.PERMISSIONS if auth.allowed(s.s, pid, a))}


@app.get("/api/audit")
def audit_log(actor: str | None = None, kind: str | None = None, key: str | None = None, limit: int = 300):
    s = svc()
    events = s.state.events()
    out = []
    for e in reversed(events):
        if (actor and e["actor"] != actor) or (kind and e["kind"] != kind) or (key and e["invoice_key"] != key):
            continue
        e["actor_name"] = s.s.people[e["actor"]]["name"] if e["actor"] in s.s.people else \
            (brand.PRODUCT if e["actor"] == "AGENT" else e["actor"])
        out.append(e)
        if len(out) >= limit:
            break
    return {"events": out, "total": len(events), "kinds": sorted({e["kind"] for e in events})}


@app.get("/api/policies")
def policies():
    s = svc()
    s.sync_clock()
    return {**s.policies.editable(), "versions": s.policies.versions(),
            "proposed_bands": {m: v.get("proposed_bands") for m, v in ((ds.metrics() or {}).get("models") or {}).items()}}


@app.post("/api/policies")
def update_policies(request: Request, body: dict = Body(...)):
    try:
        return svc().update_policy(who(request, body.get("by")), body.get("changes") or {}, body.get("reason", ""))
    except ValueError as e:
        _bad(e)


@app.get("/api/invoices/{intake_id}/evidence", response_class=HTMLResponse)
def evidence(intake_id: str):
    from .evidence import render
    s = svc()
    try:
        r = s.result(intake_id)
    except KeyError:
        raise HTTPException(404, "Unknown invoice")
    return render(s, r, s.audit(intake_id))
