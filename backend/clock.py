"""The demo clock: every action is stamped on the scenario date (15 Oct 2026) at the current time of day.

Seed data is dated around the workshop, so stamping new actions with the real date would put decisions before the
invoices they decide. An admin can move the clock forward to show SLA reminders and escalations; the offset is held
in state so every instance agrees.
"""
import os
from datetime import date, datetime, time, timedelta

DEMO_DATE = date.fromisoformat(os.environ.get("DEMO_DATE", "2026-10-15"))
EARLIEST = time(9, 5)  # the morning mailbox closes at 09:00; nothing can happen before it arrives

_offset = timedelta(0)


def set_offset_hours(hours: float):
    global _offset
    _offset = timedelta(hours=hours or 0)


def offset_hours() -> float:
    return _offset.total_seconds() / 3600


def now() -> datetime:
    local = datetime.now().time().replace(microsecond=0)
    return datetime.combine(DEMO_DATE, max(local, EARLIEST)) + _offset


def now_iso() -> str:
    return now().isoformat(timespec="seconds")


def today() -> str:
    return now().date().isoformat()
