"""CQ-032a slot-18 E2E: signup -> draft -> 4 tabs -> upload -> submit ->
poll as the assigned LO until priced -> Mailpit -> raw SSN column."""

import asyncio
import re
import time
import uuid
from pathlib import Path

import asyncpg
import httpx
import yaml

REPO = Path.cwd()
API = "http://localhost:8118/api/v1"
MAILPIT = "http://localhost:8025/api/v1"
ENV = dict(
    line.split("=", 1) for line in (REPO / ".env").read_text().splitlines() if "=" in line and not line.startswith("#")
)


def otp_for(email: str, after: float) -> str:
    for _ in range(40):
        msgs = httpx.get(f"{MAILPIT}/search", params={"query": f'to:"{email}"'}).json()["messages"]
        for m in msgs:
            detail = httpx.get(f"{MAILPIT}/message/{m['ID']}").json()
            match = re.search(r"\b(\d{6})\b", detail.get("Text") or detail.get("HTML") or "")
            if match and "code" in (m.get("Subject") or "").lower() or match:
                return match.group(1)
        time.sleep(0.5)
    raise RuntimeError(f"no OTP for {email}")


def mails_to(email: str) -> list[dict]:
    return httpx.get(f"{MAILPIT}/search", params={"query": f'to:"{email}"'}).json()["messages"]


def main() -> None:
    email = f"e2e.apply.{uuid.uuid4().hex[:8]}@example.com"
    password = "Sup3r-secret-pass!"
    b = httpx.Client(base_url=API, timeout=30)
    t0 = time.time()
    ch = b.post("/auth/borrower/signup", json={"full_name": "Tina Tampa", "email": email, "password": password})
    print("signup", ch.status_code)
    code = otp_for(email, t0)
    v = b.post("/auth/borrower/otp/verify", json={"challenge_id": ch.json()["challenge_id"], "code": code})
    print("otp verify", v.status_code)

    draft = b.post("/portal/applications").json()
    draft_id = draft["id"]
    print("draft", draft_id, "email prefilled:", draft["email"] == email, "current_tab:", draft["current_tab"])
    tabs = {
        "you": {
            "first_name": "Tina", "last_name": "Tampa", "cell_phone": "813-555-0142", "dob": "1988-04-12",
            "ssn": "123-45-6789", "marital_status": "unmarried", "dependents_count": 0,
            "current_address": {"street": "22 River Rd", "city": "Lakeland", "state": "FL", "zip": "33801"},
            "housing_status": "rent", "residence_years": 3, "residence_months": 2, "has_co_borrower": False,
        },
        "property": {
            "occupancy": "str", "has_property": False, "buy_box_states": ["FL"], "buy_box_metros": ["Tampa"],
            "target_price": "400000", "down_payment_pct": "0.25",
        },
        "income": {"monthly_debts": "450", "liquid_assets": "180000"},
        "consent": {"soft_pull_authorized": True, "contact_consent": True, "terms_accepted": True,
                    "typed_name": "tina tampa"},
    }
    print("metros:", b.get("/portal/applications/metros").json()["states"][:3])
    for tab, data in tabs.items():
        r = b.patch(f"/portal/applications/{draft_id}/draft", json={"tab": tab, "data": data}).json()
        print("patch", tab, "valid:", r["tab_valid"], r["field_errors"])
        if tab == "you":
            you = r["draft"]["data"]["you"]
            print("  you ssn fields in response:", {k: v for k, v in you.items() if "ssn" in k},
                  "| digits echoed:", "123456789" in str(r) or "123-45-6789" in str(r))
    resave = {k: v for k, v in tabs["you"].items() if k != "ssn"}
    r = b.patch(f"/portal/applications/{draft_id}/draft", json={"tab": "you", "data": resave}).json()
    print("resave you without ssn -> valid:", r["tab_valid"], "ssn_set:", r["draft"]["data"]["you"]["ssn_set"])

    # Upload guard: an oversized Content-Length with no session is refused
    # before auth or parsing (raw socket so the client never sends 50 MB).
    import socket

    with socket.create_connection(("localhost", 8118)) as sock:
        sock.sendall(
            f"POST /api/v1/portal/applications/{uuid.uuid4()}/documents HTTP/1.1\r\nHost: localhost\r\n"
            "Content-Type: multipart/form-data; boundary=zzz\r\nContent-Length: 52428800\r\n\r\n".encode()
            + b"--zzz\r\n"
        )
        print("unauthenticated 50 MB Content-Length ->", sock.recv(200).split(b"\r\n")[0].decode())

    pdf = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"
    up = b.post(f"/portal/applications/{draft_id}/documents", files={"file": ("paystub.pdf", pdf, "application/pdf")},
                data={"doc_type": "pay_stub"})
    print("upload pdf", up.status_code)
    big = b.post(f"/portal/applications/{draft_id}/documents",
                 files={"file": ("big.pdf", b"%PDF" + b"0" * (11 * 1024 * 1024), "application/pdf")},
                 data={"doc_type": "pay_stub"})
    print("upload 11MB", big.status_code, big.json()["error"]["message"])
    exe = b.post(f"/portal/applications/{draft_id}/documents", files={"file": ("setup.exe", b"MZ\x90", "application/octet-stream")},
                 data={"doc_type": "w2"})
    print("upload exe", exe.status_code, exe.json()["error"]["message"])

    sub = b.post(f"/portal/applications/{draft_id}/submit", headers={"user-agent": "E2E/cq032"})
    print("submit", sub.status_code, sub.json())
    app_id = sub.json()["application_id"]
    lo_name = sub.json()["assigned_lo_name"]
    users = yaml.safe_load((REPO / "seed/users.yaml").read_text())
    users = users["users"] if isinstance(users, dict) else users
    lo_email = next(u["email"] for u in users if u.get("full_name") == lo_name)
    print("assigned LO", lo_name, lo_email)

    s = httpx.Client(base_url=API, timeout=30)
    t1 = time.time()
    ch = s.post("/auth/staff/login", json={"email": lo_email, "password": ENV["SEED_STAFF_PASSWORD"]})
    time.sleep(1)
    msgs = [m for m in mails_to(lo_email) if "code" in (m.get("Subject") or "").lower() or "sign" in (m.get("Subject") or "").lower()]
    detail = httpx.get(f"{MAILPIT}/message/{msgs[0]['ID']}").json()
    code = re.search(r"\b(\d{6})\b", detail.get("Text") or "").group(1)
    print("staff otp", s.post("/auth/staff/otp/verify", json={"challenge_id": ch.json()["challenge_id"], "code": code}).status_code)

    summary = {}
    for _ in range(90):
        summary = s.get(f"/applications/{app_id}/summary").json()
        if summary.get("status") in ("priced", "needs_attention"):
            break
        time.sleep(1)
    print("summary status:", summary.get("status"), "stage:", summary.get("last_pipeline_stage"))
    print("summary keys:", sorted(summary.keys()))
    print("summary excerpt:", {k: summary[k] for k in summary if "quote" in k or "numbers" in k or "source" in k})

    new_app_mails = [m for m in mails_to(lo_email) if m["Subject"].startswith("New application from")]
    print("LO 'New application' emails:", [(m["Subject"]) for m in new_app_mails])

    async def db_checks() -> None:
        url = ENV["DATABASE_URL"].replace("postgresql+asyncpg", "postgresql")
        conn = await asyncpg.connect(url)
        rows = await conn.fetch("SELECT role::text, ssn_encrypted FROM application_parties WHERE application_id=$1", uuid.UUID(app_id))
        for r in rows:
            raw = bytes(r["ssn_encrypted"])
            print("raw ssn column", r["role"], raw[:24], "... contains digits:", b"123456789" in raw)
        quotes = await conn.fetchval(
            "SELECT count(*) FROM quotes q JOIN scenarios s ON s.id=q.scenario_id WHERE s.application_id=$1", uuid.UUID(app_id))
        print("quotes:", quotes)
        docs = await conn.fetch("SELECT doc_type, object_key FROM documents WHERE application_id=$1", uuid.UUID(app_id))
        print("documents:", [dict(d) for d in docs])
        consent = await conn.fetchrow("SELECT type::text, status::text, text_hash, ip, user_agent, at FROM consents WHERE application_id=$1", uuid.UUID(app_id))
        print("consent:", dict(consent))
        ev = await conn.fetch("SELECT type FROM activity_events WHERE application_id=$1 ORDER BY at, created_at", uuid.UUID(app_id))
        print("events:", [e["type"] for e in ev])
        src = await conn.fetchval("SELECT source::text FROM applications WHERE id=$1", uuid.UUID(app_id))
        print("source:", src)
        draft_raw = await conn.fetchval("SELECT data::text FROM application_drafts WHERE id=$1", uuid.UUID(draft_id))
        print("draft data after submit: has 123456789:", "123456789" in draft_raw,
              "| has ssn_encrypted:", "ssn_encrypted" in draft_raw, "| has ssn_last4:", "ssn_last4" in draft_raw)
        await conn.close()

    asyncio.run(db_checks())


main()
