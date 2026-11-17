"""Tests sur une vraie base PostgreSQL (les garde-fous sont dans la base, on ne les simule pas)."""
import os
import uuid

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://proteine:proteine@localhost:5432/proteine_test")
os.environ.setdefault("ADMIN_PHONES", "+2250700000000")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.db import engine  # noqa: E402
from app.main import app  # noqa: E402

SQL_DIR = os.path.join(os.path.dirname(__file__), "..", "sql")


@pytest.fixture(scope="session", autouse=True)
def schema():
    raw = engine.raw_connection()
    try:
        cur = raw.cursor()
        cur.execute("DROP SCHEMA IF EXISTS public CASCADE; CREATE SCHEMA public;")
        for name in ("0001_schema.sql", "0002_reference.sql"):
            with open(os.path.join(SQL_DIR, name), encoding="utf-8") as f:
                cur.execute(f.read())
        raw.commit()
    finally:
        raw.close()


@pytest.fixture(autouse=True)
def clean():
    # TRUNCATE ne déclenche pas les gardes de suppression ligne à ligne : réservé aux tests.
    with engine.begin() as conn:
        conn.execute(text("""TRUNCATE users, user_versions, waste_offers, waste_offer_versions, waste_lots,
                             flour_batches, flour_batch_sources, orders, payments, recalls, notifications,
                             disputes, price_reports, herds, rations, otp_codes, status_events, change_log,
                             cdc_cursors RESTART IDENTITY CASCADE"""))
        conn.execute(text("UPDATE impact_totals SET value = 0"))
    yield


@pytest.fixture
def client():
    return TestClient(app)


ABIDJAN = (5.3600, -4.0083)


class Actor:
    def __init__(self, client, token, data):
        self.client, self.token, self.data = client, token, data
        self.headers = {"Authorization": f"Bearer {token}"}
        self.id = data["id"]

    def get(self, path, **kw):
        return self.client.get("/api/v1" + path, headers={**self.headers, **kw.pop("headers", {})}, **kw)

    def post(self, path, json=None, **kw):
        return self.client.post("/api/v1" + path, json=json or {}, headers={**self.headers, **kw.pop("headers", {})},
                                **kw)

    def patch(self, path, json=None):
        return self.client.patch("/api/v1" + path, json=json or {}, headers=self.headers)


def _login(client, phone):
    code = client.post("/api/v1/auth/otp/request", json={"phone": phone}).json()["dev_code"]
    return client.post("/api/v1/auth/otp/verify", json={"phone": phone, "code": code}).json()


def make_actor(client, role, name=None, lat=ABIDJAN[0], lng=ABIDJAN[1], phone=None, validate=True, is_woman=False):
    phone = phone or "+22501" + str(uuid.uuid4().int)[:8]
    res = _login(client, phone)
    if res.get("needs_signup"):
        res = client.post("/api/v1/auth/signup", json={
            "signup_token": res["signup_token"], "name": name or role.title(), "role": role,
            "lat": lat, "lng": lng, "commune": "Yopougon", "is_woman": is_woman}).json()
    token = res["token"]
    me = client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"}).json()
    actor = Actor(client, token, me)
    if validate and me["status"] == "pending":
        adm = admin(client)
        assert adm.post(f"/admin/users/{me['id']}/validate").status_code == 200
    return actor


def admin(client):
    res = _login(client, "+2250700000000")
    if res.get("needs_signup"):
        res = client.post("/api/v1/auth/signup", json={"signup_token": res["signup_token"], "name": "Admin",
                                                       "role": "producer"}).json()
    token = res["token"]
    me = client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"}).json()
    return Actor(client, token, me)
