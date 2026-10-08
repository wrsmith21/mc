"""HTTP API for the Non-PO Invoice Agent demo."""
import hashlib
import hmac
import json
import os

from fastapi import Body, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, StreamingResponse

from . import clock, llm
from .integrations import external
from .service import DemoService
from .store import ROOT

PASSWORD = os.environ.get("DEMO_PASSWORD")
TOKEN = hashlib.sha256(f"mc-nonpo::{PASSWORD}".encode()).hexdigest() if PASSWORD else None
WILDCARD = os.environ.get("ENABLE_WILDCARD", "1") == "1"

app = FastAPI(title="Non-PO Invoice Agent", version="1.0")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5174", "http://127.0.0.1:5174"],
                   allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
_svc = None


def svc() -> DemoService:
    global _svc
    if _svc is None:
        _svc = DemoService()
    return _svc


@app.middleware("http")
async def passcode(request: Request, call_next):
    path = request.url.path
    if TOKEN and path.startswith("/api/") and path not in ("/api/health", "/api/login"):
        supplied = request.cookies.get("mc_demo") or request.headers.get("x-demo-token") or ""
        if not hmac.compare_digest(supplied, TOKEN):
            return JSONResponse({"detail": "passcode required"}, status_code=401)
    return await call_next(request)


def _bad(e: Exception):
    raise HTTPException(status_code=409, detail=str(e))


@app.get("/api/health")
def health():
    return {"ok": True}


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
        return svc().result(intake_id)
    except KeyError:
        raise HTTPException(404, "Unknown invoice")


def _sse(events):
    def stream():
        for ev in events:
            yield f"data: {json.dumps(ev, default=str)}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/api/invoices/{intake_id}/run")
def run(intake_id: str, actor: str = "E34120"):
    s = svc()
    if intake_id not in s.all_items():
        raise HTTPException(404, "Unknown invoice")
    return _sse(s.run_events(intake_id, actor=actor))


@app.get("/api/invoices/{intake_id}/runs")
def runs(intake_id: str):
    return svc().state.get(f"runs:{intake_id}") or []


@app.get("/api/mailbox/run")
def run_mailbox(actor: str = "E34120"):
    return _sse(svc().run_mailbox(actor=actor))


@app.get("/api/work")
def work():
    return svc().work()


@app.post("/api/vendors/{vendor_id}/callback")
def callback(vendor_id: str, body: dict = Body(...)):
    try:
        return svc().callback(vendor_id, body["outcome"], body["by"], body.get("note", ""))
    except ValueError as e:
        _bad(e)


@app.post("/api/invoices/{intake_id}/onboard")
def onboard(intake_id: str, body: dict = Body(...)):
    try:
        return svc().onboard(intake_id, body["by"], body["tax_id"], body.get("category", "facilities"))
    except ValueError as e:
        _bad(e)


@app.post("/api/procurement/requests")
def po_request(body: dict = Body(...)):
    try:
        return svc().request_po(body["vendor_id"], body["kind"], body["by"])
    except ValueError as e:
        _bad(e)


@app.post("/api/clock/advance")
def advance_clock(body: dict = Body(...)):
    return svc().advance_clock(float(body.get("hours", 24)), body.get("by", "E34120"))


@app.get("/api/model")
def model_info():
    from . import model as ds
    return {"metrics": ds.metrics(), "card": ds.card(), "manifest": ds.manifest(),
            "calibration": ds._calibration(),
            "history": {"invoices": len(svc().s.history), "lines": len(svc().s.lines), "vendors": len(svc().s.vendors),
                        "pos": len(svc().s.pos)}}


@app.get("/api/agents")
def agents():
    return svc().agents()


@app.get("/api/invoices/{intake_id}/audit")
def audit(intake_id: str):
    return svc().audit(intake_id)


@app.post("/api/invoices/{intake_id}/receipt/request")
def receipt_request(intake_id: str, body: dict = Body(default={})):
    try:
        return svc().request_receipt(intake_id, actor=body.get("actor", "AGENT"))
    except ValueError as e:
        _bad(e)


@app.post("/api/invoices/{intake_id}/receipt/confirm")
def receipt_confirm(intake_id: str, body: dict = Body(...)):
    return svc().confirm_receipt(intake_id, body["by"], body.get("note", ""))


@app.get("/api/tasks")
def tasks(person: str | None = None):
    return svc().tasks(person)


@app.post("/api/invoices/{intake_id}/decision")
def decision(intake_id: str, body: dict = Body(...)):
    try:
        return svc().submit(intake_id, body["action"], body.get("actor", "E34120"), body.get("reason"),
                            body.get("override") or {})
    except ValueError as e:
        _bad(e)


@app.post("/api/invoices/{intake_id}/approve")
def approve(intake_id: str, body: dict = Body(...)):
    try:
        return svc().approve_step(intake_id, body["approver"])
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
async def wildcard(file: UploadFile = File(...)):
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
def reset():
    svc().reset()
    return {"ok": True}
