"""Public-data checks: OFAC SDN screening, EU VIES VAT validation, ECB FX, bank-detail checksums.

Every call has a short timeout and falls back to the last cached answer, so the demo survives venue Wi-Fi.
The result always says whether it was live or cached, and when.
"""
import csv
import io
import json
import os
import re
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
from rapidfuzz import fuzz, process

CACHE = Path(os.environ.get("CACHE_DIR", Path(__file__).resolve().parents[2] / "data" / "cache"))
WRITABLE = Path(os.environ.get("RUNTIME_CACHE_DIR", "/tmp/mc-demo-cache"))
TIMEOUT = float(os.environ.get("EXTERNAL_TIMEOUT", "3.5"))
OFFLINE = os.environ.get("DEMO_OFFLINE") == "1"

SDN_URL = "https://www.treasury.gov/ofac/downloads/sdn.csv"
VIES_URL = "https://ec.europa.eu/taxation_customs/vies/rest-api/check-vat-number"
FX_URL = "https://api.frankfurter.dev/v1/latest"


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _read_json(name):
    for base in (WRITABLE, CACHE):
        p = base / name
        if p.exists():
            return json.loads(p.read_text())
    return {}


def _write_json(name, data):
    for base in (WRITABLE, CACHE):
        try:
            base.mkdir(parents=True, exist_ok=True)
            (base / name).write_text(json.dumps(data, indent=1))
            return
        except OSError:
            continue


# ---------------- OFAC ----------------
_SUFFIXES = re.compile(r"\b(llc|llp|inc|ltd|limited|co|corp|corporation|company|group|srl|sa|plc|gmbh|&)\b\.?")


def _norm(name):
    return re.sub(r"\s+", " ", _SUFFIXES.sub(" ", name.lower().replace(",", " "))).strip()


class OfacList:
    """Screens against the bundled SDN list at once; a copy older than a day is refreshed from Treasury in the
    background, so no request ever waits on the 5.7 MB download."""
    REFRESH_AFTER = 86400

    def __init__(self):
        self._list, self.source, self.as_of = None, None, None
        self._refreshing = False

    @property
    def names(self):
        return self._list[0] if self._list else []

    @staticmethod
    def _parse(text):
        names, rows = [], []
        for row in csv.reader(io.StringIO(text)):
            if len(row) > 3 and row[1] and row[1] != "-0-":
                rows.append({"uid": row[0], "name": row[1], "type": row[2], "program": row[3]})
                names.append(_norm(row[1]))
        return names, rows

    @staticmethod
    def _fetched_at(base):
        # bundle file dates are not preserved on deploy, so the fetch time is recorded next to the list
        meta = base / "sdn.json"
        if meta.exists():
            return json.loads(meta.read_text())["fetched_at"]
        return datetime.fromtimestamp((base / "sdn.csv").stat().st_mtime, timezone.utc).isoformat(timespec="seconds")

    def _download(self):
        r = httpx.get(SDN_URL, timeout=TIMEOUT * 3, follow_redirects=True)
        r.raise_for_status()
        return r.text

    def _refresh(self):
        try:
            text = self._download()
            self._list, self.source, self.as_of = self._parse(text), "live", _now()
            WRITABLE.mkdir(parents=True, exist_ok=True)
            (WRITABLE / "sdn.csv").write_text(text)
            (WRITABLE / "sdn.json").write_text(json.dumps({"fetched_at": self.as_of}))
        except (httpx.HTTPError, OSError):
            pass
        finally:
            self._refreshing = False

    def load(self):
        if self._list:
            return self
        base = next((b for b in (WRITABLE, CACHE) if (b / "sdn.csv").exists()), None)
        if base:
            self.as_of, self.source = self._fetched_at(base), "cached"
            self._list = self._parse((base / "sdn.csv").read_text(errors="ignore"))
            age = time.time() - datetime.fromisoformat(self.as_of).timestamp()
            if not OFFLINE and age > self.REFRESH_AFTER and not self._refreshing:
                self._refreshing = True
                threading.Thread(target=self._refresh, daemon=True).start()
        elif not OFFLINE:
            self._refreshing = True
            self._refresh()
        if not self._list:
            self.source = "unavailable"
        return self

    def screen(self, name, threshold=92):
        self.load()
        if not self._list:
            return {"status": "unavailable", "source": self.source, "matches": []}
        names, rows = self._list
        hits = process.extract(_norm(name), names, scorer=fuzz.token_sort_ratio, limit=3,
                               score_cutoff=threshold)
        return {"status": "potential_match" if hits else "clear", "source": self.source, "as_of": self.as_of,
                "list_size": len(names), "screened_name": name,
                "matches": [{**rows[i], "score": round(s, 1)} for _n, s, i in hits]}


ofac = OfacList()


# ---------------- VIES ----------------
def vies_check(vat_number: str, live: bool = False):
    """live=False answers from cache when it can (bulk runs); live=True always asks VIES first."""
    vat = vat_number.replace(" ", "").replace(".", "").upper()
    country, number = vat[:2], vat[2:]
    cache = _read_json("vies.json")
    if not live and vat in cache:
        return cache[vat]
    if not OFFLINE:
        try:
            t = time.time()
            r = httpx.post(VIES_URL, json={"countryCode": country, "vatNumber": number}, timeout=TIMEOUT)
            r.raise_for_status()
            body = r.json()
            result = {"vat_number": vat, "valid": bool(body.get("valid")), "name": body.get("name"),
                      "request_date": body.get("requestDate"), "source": "live", "checked_at": _now(),
                      "latency_ms": round((time.time() - t) * 1000)}
            cache[vat] = {**result, "source": "cached"}
            _write_json("vies.json", cache)
            return result
        except (httpx.HTTPError, ValueError):
            pass
    if vat in cache:
        return cache[vat]
    return {"vat_number": vat, "valid": None, "source": "unavailable", "checked_at": _now()}


def be_vat_checksum_ok(vat: str) -> bool:
    digits = re.sub(r"\D", "", vat)
    if len(digits) != 10:
        return False
    return 97 - int(digits[:8]) % 97 == int(digits[8:])


# ---------------- FX ----------------
def fx_rate(base: str, quote: str = "USD"):
    if base == quote:
        return {"rate": 1.0, "source": "identity"}
    cache = _read_json("fx.json")
    key = f"{base}{quote}"
    if not OFFLINE:
        try:
            r = httpx.get(FX_URL, params={"base": base, "symbols": quote}, timeout=TIMEOUT)
            r.raise_for_status()
            body = r.json()
            result = {"rate": body["rates"][quote], "date": body["date"], "provider": "ECB via Frankfurter",
                      "source": "live", "checked_at": _now()}
            cache[key] = {**result, "source": "cached"}
            _write_json("fx.json", cache)
            return result
        except (httpx.HTTPError, KeyError, ValueError):
            pass
    return cache.get(key) or {"rate": None, "source": "unavailable"}


# ---------------- Bank details ----------------
def aba_valid(routing: str) -> bool:
    if not routing or not routing.isdigit() or len(routing) != 9:
        return False
    d = [int(c) for c in routing]
    return (3 * (d[0] + d[3] + d[6]) + 7 * (d[1] + d[4] + d[7]) + (d[2] + d[5] + d[8])) % 10 == 0


def iban_valid(iban: str) -> bool:
    s = iban.replace(" ", "").upper()
    if len(s) < 15:
        return False
    moved = s[4:] + s[:4]
    numeric = "".join(str(int(ch, 36)) for ch in moved)
    return int(numeric) % 97 == 1
