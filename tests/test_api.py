import uuid

import psycopg

from conftest import TEST_DB


def make(client, **fields):
    app_id = str(uuid.uuid4())
    body = {"company": "Ashworth", "role": "AI & Data Analytics Intern", "stage": "applied",
            "appliedDate": "2026-10-01",
            "events": [{"date": "2026-10-01", "kind": "stage", "stage": "applied", "text": ""}]}
    body.update(fields)
    r = client.put(f"/api/applications/{app_id}", json=body)
    assert r.status_code == 200, r.text
    return app_id, r.json()


def test_health_and_ui(client):
    assert client.get("/api/health").json() == {"ok": True}
    r = client.get("/")
    assert r.status_code == 200 and "Job Tracker" in r.text


def test_create_and_list(client):
    app_id, saved = make(client, sector="Consulting", type="Internship", deadline="", followUp="2026-11-20",
                          nextStep="Technical interview")
    assert saved["id"] == app_id
    assert saved["appliedDate"] == "2026-10-01"
    assert saved["deadline"] == "" and saved["followUp"] == "2026-11-20"
    assert saved["nextStep"] == "Technical interview"
    assert saved["events"] == [{"date": "2026-10-01", "kind": "stage", "stage": "applied", "text": ""}]
    listed = client.get("/api/applications").json()
    assert [a["id"] for a in listed] == [app_id]


def test_update_replaces_fields_and_timeline(client):
    app_id, saved = make(client)
    saved["stage"] = "interview"
    saved["events"].append({"date": "2026-10-20", "kind": "stage", "stage": "interview", "text": ""})
    saved["events"].append({"date": "2026-10-20", "kind": "note", "text": "Phone screen"})
    r = client.put(f"/api/applications/{app_id}", json=saved)
    assert r.status_code == 200
    out = r.json()
    assert out["stage"] == "interview"
    assert [e["kind"] for e in out["events"]] == ["stage", "stage", "note"]
    assert out["createdAt"] <= out["updatedAt"]


def test_delete_cascades_events(client):
    app_id, _ = make(client)
    assert client.delete(f"/api/applications/{app_id}").status_code == 204
    assert client.get(f"/api/applications/{app_id}").status_code == 404
    with psycopg.connect(TEST_DB) as conn:
        n = conn.execute("SELECT count(*) FROM application_events").fetchone()[0]
    assert n == 0


def test_validation(client):
    bad_id = str(uuid.uuid4())
    assert client.put(f"/api/applications/{bad_id}", json={"company": "  "}).status_code == 422
    assert client.put(f"/api/applications/{bad_id}", json={"company": "X", "stage": "hired"}).status_code == 422
    r = client.put(f"/api/applications/{bad_id}",
                   json={"company": "X", "events": [{"date": "2026-01-01", "kind": "stage"}]})
    assert r.status_code == 422
    assert client.put("/api/applications/not-a-uuid", json={"company": "X"}).status_code == 422


def test_bulk_import_skips_duplicates(client):
    make(client)
    rows = [
        {"company": "Ashworth", "role": "ai & data analytics intern"},  # duplicate (case-insensitive)
        {"company": "Lockheed Martin", "role": "SWE Intern", "stage": "assessment",
         "appliedDate": "2026-10-12",
         "events": [{"date": "2026-10-12", "kind": "stage", "stage": "applied"},
                    {"date": "2026-11-01", "kind": "stage", "stage": "assessment"}]},
        {"company": "Senix Robotics", "role": "AI-Native Software Engineer"},
    ]
    r = client.post("/api/applications/bulk", json=rows)
    assert r.json() == {"created": 2, "skipped": 1}
    assert len(client.get("/api/applications").json()) == 3


def test_overview_view(client):
    make(client, company="A", stage="rejected", appliedDate="2026-10-01",
         events=[{"date": "2026-10-01", "kind": "stage", "stage": "applied"},
                 {"date": "2026-10-08", "kind": "stage", "stage": "rejected"}])
    make(client, company="B", stage="wishlist", appliedDate="", events=[])
    with psycopg.connect(TEST_DB) as conn:
        rows = {r[0]: tuple(r[1:]) for r in conn.execute(
            "SELECT company, sent, heard_back, interviewed, days_to_response FROM application_overview"
        ).fetchall()}
    assert rows["A"] == (True, True, False, 7)
    assert rows["B"] == (False, False, False, None)


def test_extract_disabled_without_key(client):
    assert client.get("/api/config").json()["extract"] is False
    r = client.post("/api/extract", json={"text": "x" * 60})
    assert r.status_code == 503
