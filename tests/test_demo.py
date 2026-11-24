import base64
import dataclasses

import psycopg
import pytest
from fastapi.testclient import TestClient

from jobtracker import demo
from jobtracker.config import get_settings
from jobtracker.main import DEMO_MAX_APPLICATIONS, create_app

from conftest import TEST_DB


def _client(**overrides):
    return TestClient(create_app(dataclasses.replace(get_settings(), **overrides)))


def test_demo_mode_seeds_sample_data_and_fakes_gmail(fresh_schema):
    with _client(demo_mode=True, repo_url="https://github.com/x/y") as c:
        apps = c.get("/api/applications").json()
        assert len(apps) == len(demo.SAMPLES)
        assert {a["stage"] for a in apps} >= {"wishlist", "applied", "assessment", "interview", "offer", "rejected"}
        cfg = c.get("/api/config").json()
        assert cfg["demo"] is True and cfg["repoUrl"] == "https://github.com/x/y" and cfg["extract"] is False

        st = c.get("/api/gmail/status").json()
        assert st["configured"] and st["pending"] == len(demo.SUGGESTIONS)
        assert c.post("/api/gmail/sync", json={}).json()["demo"] is True
        sid = c.get("/api/gmail/suggestions").json()[0]["id"]
        assert c.post(f"/api/gmail/suggestions/{sid}/accept").status_code == 200

        assert c.post("/api/extract", json={"text": "x" * 50}).status_code == 403
        assert c.get("/docs").status_code == 404

        # Edits work until the next reset, which restores the sample data.
        a = apps[0]
        assert c.delete(f"/api/applications/{a['id']}").status_code == 204
        with psycopg.connect(TEST_DB) as conn:
            conn.row_factory = psycopg.rows.dict_row
            demo.reset(conn)
        assert len(c.get("/api/applications").json()) == len(demo.SAMPLES)


def test_demo_mode_caps_size(fresh_schema):
    with _client(demo_mode=True) as c:
        big = [{"company": f"Co {i}", "role": "Engineer"} for i in range(DEMO_MAX_APPLICATIONS)]
        assert c.post("/api/applications/bulk", json=big).status_code == 403
        r = c.put("/api/applications/00000000-0000-0000-0000-000000000001",
                  json={"company": "X", "notes": "y" * 150_000})
        assert r.status_code == 413


def test_demo_dates_are_relative_to_today():
    import datetime as dt
    day = dt.date(2027, 3, 1)
    _, data = demo._app(demo.SAMPLES[5], day)  # Larkspur, applied 12 days ago
    assert data.appliedDate == day - dt.timedelta(days=12)
    assert data.followUp == day + dt.timedelta(days=1)


@pytest.mark.parametrize("auth,code", [
    (None, 401),
    ("Basic " + base64.b64encode(b"someone:wrong").decode(), 401),
    ("Basic " + base64.b64encode(b"anyone:s3cret pass").decode(), 200),
    ("Bearer s3cret pass", 401),
])
def test_password(fresh_schema, auth, code):
    with _client(password="s3cret pass") as c:
        assert c.get("/api/health").status_code == 200  # health checks stay open
        headers = {"Authorization": auth} if auth else {}
        r = c.get("/api/applications", headers=headers)
        assert r.status_code == code
        if code == 401:
            assert "Basic" in r.headers["www-authenticate"]
