"""The sanctions list never blocks a request: a stale bundled copy answers at once and refreshes behind it."""
import json
import threading
import time

from backend.integrations import external

SDN = '1,"ACME TRADING LLC",-0-,SDGT\n2,"NORTHWIND HOLDINGS",-0-,IRAN\n'


def bundle(tmp_path, monkeypatch, fetched_at):
    cache, writable = tmp_path / "cache", tmp_path / "tmp"
    cache.mkdir()
    (cache / "sdn.csv").write_text(SDN)
    (cache / "sdn.json").write_text(json.dumps({"fetched_at": fetched_at}))
    monkeypatch.setattr(external, "CACHE", cache)
    monkeypatch.setattr(external, "WRITABLE", writable)
    monkeypatch.setattr(external, "OFFLINE", False)


def test_stale_list_answers_from_the_bundle_and_refreshes_in_the_background(tmp_path, monkeypatch):
    bundle(tmp_path, monkeypatch, "2026-01-01T00:00:00+00:00")
    released = threading.Event()

    def slow_download(self):
        released.wait(5)
        return SDN + '3,"GLOBEX EXPORTS",-0-,SDGT\n'

    monkeypatch.setattr(external.OfacList, "_download", slow_download)
    ofac = external.OfacList()
    started = time.perf_counter()
    result = ofac.screen("Acme Trading")
    assert time.perf_counter() - started < 1
    assert result["status"] == "potential_match" and result["source"] == "cached"
    assert result["as_of"] == "2026-01-01T00:00:00+00:00"

    released.set()
    for _ in range(50):
        if ofac.source == "live":
            break
        time.sleep(0.05)
    assert ofac.source == "live" and len(ofac.names) == 3
    assert (tmp_path / "tmp" / "sdn.csv").exists()


def test_fresh_list_is_not_downloaded(tmp_path, monkeypatch):
    bundle(tmp_path, monkeypatch, external._now())
    monkeypatch.setattr(external.OfacList, "_download", lambda self: (_ for _ in ()).throw(AssertionError("downloaded")))
    ofac = external.OfacList().load()
    time.sleep(0.1)
    assert ofac.source == "cached" and len(ofac.names) == 2
