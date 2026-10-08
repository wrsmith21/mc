"""Who may do what. Roles come from the directory; every action is checked on the server and refusals are audited.

The demo signs in as a named person (after the site passcode). Production would take the same roles from the
corporate identity provider (Entra ID groups or Cognito claims); the permission matrix does not change.
"""
import hashlib
import hmac
import os

ROLE_LABEL = {"ap_specialist": "AP specialist", "gl_accountant": "GL accountant", "controller": "Controller",
              "cash_preparer": "Cash application", "cash_lead": "Cash application lead",
              "procurement": "Procurement", "vendor_master": "Vendor master", "admin": "Finance systems admin",
              "approver": "Approver", "requester": "Requester", "fixed_assets": "Fixed Asset Accounting",
              "legal_ops": "Legal Operations"}

FIXED_ROLES = {
    "E34120": ["ap_specialist"],
    "E35123": ["gl_accountant"], "E35122": ["gl_accountant"],
    "E30233": ["controller", "approver"],
    "E35053": ["cash_preparer"],
    "E30719": ["cash_lead"],
    "E30911": ["procurement", "approver"],
    "E30655": ["vendor_master"],
    "E30876": ["fixed_assets", "approver"],
    "E30542": ["legal_ops", "approver"],
    "E35051": ["admin"],
}

# action -> roles allowed. Context-dependent rules (next approver, own task) are checked in the service.
PERMISSIONS = {
    "run_agent": {"ap_specialist", "admin"},
    "decide": {"ap_specialist"},
    "request_receipt": {"ap_specialist"},
    "upload": {"ap_specialist", "admin"},
    "callback": {"vendor_master"},
    "onboard": {"vendor_master"},
    "po_request": {"procurement", "ap_specialist"},
    "case_prepare_journals": {"gl_accountant"}, "case_prepare_ap_ledger": {"gl_accountant"},
    "case_prepare_cash": {"cash_preparer"},
    "case_approve_journals": {"controller"}, "case_approve_ap_ledger": {"controller"},
    "case_approve_cash": {"cash_lead"},
    "case_export_gl": {"controller"}, "case_export_cash": {"cash_lead"},
    "case_investigate": {"gl_accountant", "controller", "cash_preparer", "cash_lead", "ap_specialist", "admin"},
    "policy_edit": {"admin"},
    "clock": {"admin"},
    "reset": {"admin", "ap_specialist"},
}
SECRET = (os.environ.get("DEMO_PASSWORD") or "local-dev") + "::session"


def roles_for(store, person_id):
    p = store.people.get(person_id)
    if not p:
        return []
    roles = list(FIXED_ROLES.get(person_id, []))
    if p.get("approval_limit") is not None and "approver" not in roles:
        roles.append("approver")
    roles.append("requester")
    return roles


def allowed(store, person_id, action):
    return bool(PERMISSIONS.get(action, set()) & set(roles_for(store, person_id)))


def check(store, state, person_id, action, what=""):
    if allowed(store, person_id, action):
        return
    person = store.people.get(person_id, {}).get("name", person_id)
    need = ", ".join(sorted(ROLE_LABEL[r] for r in PERMISSIONS.get(action, set())))
    state.add_event("security", person_id, "ACCESS_DENIED", {"action": action, "what": what, "needs": need})
    raise PermissionError(f"{person} cannot {action.replace('_', ' ')}: needs {need}")


def deny(state, person_id, action, reason):
    state.add_event("security", person_id, "ACCESS_DENIED", {"action": action, "reason": reason})
    raise PermissionError(reason)


def sign(person_id):
    mac = hmac.new(SECRET.encode(), person_id.encode(), hashlib.sha256).hexdigest()[:24]
    return f"{person_id}.{mac}"


def verify(cookie):
    if not cookie or "." not in cookie:
        return None
    pid, mac = cookie.split(".", 1)
    return pid if hmac.compare_digest(sign(pid), cookie) else None
