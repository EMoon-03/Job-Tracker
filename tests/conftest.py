import os

import psycopg
import pytest

TEST_DB = os.getenv("TEST_DATABASE_URL", "postgresql:///jobtracker_test")
os.environ["DATABASE_URL"] = TEST_DB
os.environ.pop("ANTHROPIC_API_KEY", None)


@pytest.fixture(scope="session", autouse=True)
def fresh_schema():
    with psycopg.connect(TEST_DB, autocommit=True) as conn:
        conn.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
    yield


@pytest.fixture()
def client(fresh_schema):
    from fastapi.testclient import TestClient

    from jobtracker.main import create_app

    with TestClient(create_app()) as c:
        with psycopg.connect(TEST_DB, autocommit=True) as conn:
            conn.execute("TRUNCATE applications CASCADE")
        yield c
