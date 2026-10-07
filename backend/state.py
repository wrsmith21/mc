"""Mutable demo state: audit events and key/value records (decisions, receipt tasks, learned overrides).

Postgres when DATABASE_URL is set (Vercel + Neon), otherwise a local SQLite file.
"""
import json
import os
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

DATABASE_URL = os.environ.get("DATABASE_URL")
_default_db = Path("/tmp/mc-demo-state.db") if os.environ.get("VERCEL") else \
    Path(__file__).resolve().parent.parent / "data" / "state.db"
SQLITE_PATH = Path(os.environ.get("STATE_DB", _default_db))

_lock = threading.Lock()


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class SqliteState:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY AUTOINCREMENT, invoice_key TEXT, ts TEXT,
                actor TEXT, kind TEXT, payload TEXT);
            CREATE INDEX IF NOT EXISTS events_key ON events(invoice_key);
            CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT);
        """)

    def add_event(self, key, actor, kind, payload, ts=None):
        with _lock:
            self.conn.execute("INSERT INTO events (invoice_key, ts, actor, kind, payload) VALUES (?,?,?,?,?)",
                              (key, ts or now_iso(), actor, kind, json.dumps(payload)))
            self.conn.commit()

    def events(self, key=None):
        q = "SELECT id, invoice_key, ts, actor, kind, payload FROM events"
        rows = self.conn.execute(q + (" WHERE invoice_key=? ORDER BY id" if key else " ORDER BY id"),
                                 (key,) if key else ()).fetchall()
        return [{"id": r[0], "invoice_key": r[1], "ts": r[2], "actor": r[3], "kind": r[4],
                 "payload": json.loads(r[5])} for r in rows]

    def get(self, key, default=None):
        row = self.conn.execute("SELECT value FROM kv WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def put(self, key, value):
        with _lock:
            self.conn.execute("INSERT INTO kv (key, value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                              (key, json.dumps(value)))
            self.conn.commit()

    def prefix(self, prefix):
        rows = self.conn.execute("SELECT key, value FROM kv WHERE key LIKE ?", (prefix + "%",)).fetchall()
        return {k: json.loads(v) for k, v in rows}

    def reset(self):
        with _lock:
            self.conn.executescript("DELETE FROM events; DELETE FROM kv;")
            self.conn.commit()

    def bulk(self, events, kv):
        with _lock:
            self.conn.executemany("INSERT INTO events (invoice_key, ts, actor, kind, payload) VALUES (?,?,?,?,?)",
                                  events)
            self.conn.executemany("INSERT INTO kv (key, value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET "
                                  "value=excluded.value", [(k, json.dumps(v)) for k, v in kv.items()])
            self.conn.commit()


class PostgresState:
    def __init__(self, url):
        import psycopg
        self.psycopg = psycopg
        self.url = url
        with self._conn() as c:
            c.execute("""
                CREATE TABLE IF NOT EXISTS events (id BIGSERIAL PRIMARY KEY, invoice_key TEXT, ts TEXT, actor TEXT,
                    kind TEXT, payload JSONB);
                CREATE INDEX IF NOT EXISTS events_key ON events(invoice_key);
                CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value JSONB);
            """)

    def _conn(self):
        return self.psycopg.connect(self.url, autocommit=True)

    def add_event(self, key, actor, kind, payload, ts=None):
        with self._conn() as c:
            c.execute("INSERT INTO events (invoice_key, ts, actor, kind, payload) VALUES (%s,%s,%s,%s,%s)",
                      (key, ts or now_iso(), actor, kind, json.dumps(payload)))

    def events(self, key=None):
        with self._conn() as c:
            if key:
                rows = c.execute("SELECT id, invoice_key, ts, actor, kind, payload FROM events WHERE invoice_key=%s "
                                 "ORDER BY id", (key,)).fetchall()
            else:
                rows = c.execute("SELECT id, invoice_key, ts, actor, kind, payload FROM events ORDER BY id").fetchall()
        return [{"id": r[0], "invoice_key": r[1], "ts": r[2], "actor": r[3], "kind": r[4], "payload": r[5]}
                for r in rows]

    def get(self, key, default=None):
        with self._conn() as c:
            row = c.execute("SELECT value FROM kv WHERE key=%s", (key,)).fetchone()
        return row[0] if row else default

    def put(self, key, value):
        with self._conn() as c:
            c.execute("INSERT INTO kv (key, value) VALUES (%s,%s) ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value",
                      (key, json.dumps(value)))

    def prefix(self, prefix):
        with self._conn() as c:
            rows = c.execute("SELECT key, value FROM kv WHERE key LIKE %s", (prefix + "%",)).fetchall()
        return {k: v for k, v in rows}

    def reset(self):
        with self._conn() as c:
            c.execute("TRUNCATE events; TRUNCATE kv;")

    def bulk(self, events, kv):
        with self._conn() as c, c.cursor() as cur:
            cur.executemany("INSERT INTO events (invoice_key, ts, actor, kind, payload) VALUES (%s,%s,%s,%s,%s)",
                            events)
            cur.executemany("INSERT INTO kv (key, value) VALUES (%s,%s) ON CONFLICT (key) DO UPDATE SET "
                            "value=EXCLUDED.value", [(k, json.dumps(v)) for k, v in kv.items()])


class BufferedState:
    """Collects writes in memory and flushes them in one transaction (used when seeding the demo)."""

    def __init__(self, inner):
        self.inner, self.kv, self.ev = inner, {}, []

    def add_event(self, key, actor, kind, payload, ts=None):
        self.ev.append((key, ts or now_iso(), actor, kind, json.dumps(payload)))

    def events(self, key=None):
        return [{"invoice_key": e[0], "ts": e[1], "actor": e[2], "kind": e[3], "payload": json.loads(e[4])}
                for e in self.ev if key is None or e[0] == key]

    def get(self, key, default=None):
        return self.kv.get(key, default)

    def put(self, key, value):
        self.kv[key] = value

    def prefix(self, prefix):
        return {k: v for k, v in self.kv.items() if k.startswith(prefix)}

    def flush(self):
        self.inner.bulk(self.ev, self.kv)


_state = None


def get_state():
    global _state
    if _state is None:
        _state = PostgresState(DATABASE_URL) if DATABASE_URL else SqliteState(SQLITE_PATH)
    return _state
