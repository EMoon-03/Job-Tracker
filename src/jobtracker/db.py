"""Connection pool, migrations, and the queries the API uses."""

from __future__ import annotations

import datetime as dt
from importlib import resources
from uuid import UUID, uuid4

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from .models import ApplicationIn

MIGRATION_LOCK_ID = 74_220_901  # arbitrary advisory-lock key for this app

# UI field name -> column name
COLUMNS: dict[str, str] = {
    "company": "company",
    "role": "role",
    "stage": "stage",
    "type": "job_type",
    "sector": "sector",
    "location": "location",
    "mode": "work_mode",
    "salary": "salary",
    "appliedDate": "applied_on",
    "deadline": "deadline",
    "followUp": "follow_up_on",
    "nextStep": "next_step",
    "source": "source",
    "referral": "referral",
    "contact": "contact",
    "url": "url",
    "resume": "resume",
    "notes": "notes",
}


def make_pool(database_url: str) -> ConnectionPool:
    # check_connection replaces connections a hosted database dropped while idle
    # (Neon, for example, suspends after a few minutes without queries).
    pool = ConnectionPool(database_url, min_size=1, max_size=5, open=False,
                          kwargs={"row_factory": dict_row}, check=ConnectionPool.check_connection)
    pool.open(wait=True, timeout=10)
    return pool


# ---------------------------------------------------------------- migrations

def migrate(conn: psycopg.Connection) -> list[str]:
    """Apply any migrations in jobtracker/migrations that haven't run yet."""
    applied_now: list[str] = []
    with conn.transaction():
        conn.execute("SELECT pg_advisory_xact_lock(%s)", (MIGRATION_LOCK_ID,))
        conn.execute(
            """CREATE TABLE IF NOT EXISTS schema_migrations (
                   version    text PRIMARY KEY,
                   applied_at timestamptz NOT NULL DEFAULT now())"""
        )
        done = {r["version"] for r in conn.execute("SELECT version FROM schema_migrations")}
        files = sorted(
            (f for f in (resources.files("jobtracker") / "migrations").iterdir() if f.name.endswith(".sql")),
            key=lambda f: f.name,
        )
        for f in files:
            version = f.name.removesuffix(".sql")
            if version in done:
                continue
            conn.execute(f.read_text(encoding="utf-8"))
            conn.execute("INSERT INTO schema_migrations (version) VALUES (%s)", (version,))
            applied_now.append(version)
    return applied_now


# ---------------------------------------------------------------- reads

LIST_SQL = """
SELECT a.*,
       COALESCE(
           json_agg(json_build_object('date', e.occurred_on, 'kind', e.kind,
                                      'stage', e.stage, 'text', e.body)
                    ORDER BY e.occurred_on, e.position)
           FILTER (WHERE e.id IS NOT NULL),
           '[]'::json) AS events
FROM applications a
LEFT JOIN application_events e ON e.application_id = a.id
{where}
GROUP BY a.id
ORDER BY a.updated_at DESC
"""


def _iso(d: dt.date | None) -> str:
    return d.isoformat() if d else ""


def _ms(t: dt.datetime) -> int:
    return int(t.timestamp() * 1000)


def row_to_app(row: dict) -> dict:
    app = {"id": str(row["id"])}
    for field, col in COLUMNS.items():
        v = row[col]
        app[field] = _iso(v) if isinstance(v, dt.date) else (v or "")
    app["events"] = [
        {"date": e["date"], "kind": e["kind"], "stage": e["stage"] or "", "text": e["text"] or ""}
        for e in row["events"]
    ]
    app["createdAt"] = _ms(row["created_at"])
    app["updatedAt"] = _ms(row["updated_at"])
    return app


def list_applications(conn: psycopg.Connection) -> list[dict]:
    rows = conn.execute(LIST_SQL.format(where="")).fetchall()
    return [row_to_app(r) for r in rows]


def get_application(conn: psycopg.Connection, app_id: UUID) -> dict | None:
    row = conn.execute(LIST_SQL.format(where="WHERE a.id = %s"), (app_id,)).fetchone()
    return row_to_app(row) if row else None


# ---------------------------------------------------------------- writes

def _values(data: ApplicationIn) -> dict:
    return {col: getattr(data, field) for field, col in COLUMNS.items()}


def upsert_application(conn: psycopg.Connection, app_id: UUID, data: ApplicationIn) -> None:
    """Insert or fully replace one application and its timeline. Call inside a transaction."""
    vals = _values(data)
    cols = list(vals)
    created = (dt.datetime.fromtimestamp(data.createdAt / 1000, tz=dt.timezone.utc)
               if data.createdAt else None)
    conn.execute(
        f"""INSERT INTO applications (id, {", ".join(cols)}, created_at)
            VALUES (%(id)s, {", ".join(f"%({c})s" for c in cols)}, COALESCE(%(created_at)s, now()))
            ON CONFLICT (id) DO UPDATE SET {", ".join(f"{c} = EXCLUDED.{c}" for c in cols)}""",
        {"id": app_id, "created_at": created, **vals},
    )
    conn.execute("DELETE FROM application_events WHERE application_id = %s", (app_id,))
    if data.events:
        with conn.cursor() as cur:
            cur.executemany(
                """INSERT INTO application_events (application_id, occurred_on, kind, stage, body, position)
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                [(app_id, e.date, e.kind, e.stage, e.text, i) for i, e in enumerate(data.events)],
            )


def save_application(conn: psycopg.Connection, app_id: UUID, data: ApplicationIn) -> dict:
    with conn.transaction():
        upsert_application(conn, app_id, data)
    return get_application(conn, app_id)  # type: ignore[return-value]


def delete_application(conn: psycopg.Connection, app_id: UUID) -> bool:
    cur = conn.execute("DELETE FROM applications WHERE id = %s", (app_id,))
    return cur.rowcount > 0


def bulk_import(conn: psycopg.Connection, items: list) -> dict:
    """Import many applications in one transaction, skipping company+role pairs already tracked."""
    created = skipped = 0
    with conn.transaction():
        existing = {
            (r["company"].lower(), r["role"].lower())
            for r in conn.execute("SELECT company, role FROM applications")
        }
        for item in items:
            key = (item.company.lower(), item.role.lower())
            if key in existing:
                skipped += 1
                continue
            upsert_application(conn, item.id or uuid4(), item)
            existing.add(key)
            created += 1
    return {"created": created, "skipped": skipped}
