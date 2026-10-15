"""The firm database that both services read: orgs, bids, projects, people
and document snippets. SQLite on a shared volume, seeded on first use.

Each org has its own props table (org_<n>_props), the way the reference
backend lays out tenant data. The MCP server reads every one of them on
each request, which is the per-org query loop the traces show.
"""

import json
import os
import sqlite3
from contextlib import contextmanager

DB_PATH = os.environ.get("DEMO_DB_PATH", "/data/firm.db")
ORG_COUNT = 60
DEMO_ORG_ID = 54
DEMO_BID_ID = "wrw50evpgs8z9l"

GUIDELINES = """## Firm-Wide Content Guidelines
- Lead with the client's outcome, not with our history.
- Name the project manager and two comparable projects in every pursuit.
- Do not promise schedule dates that the RFP does not give."""

PROJECTS = [
    ("414945489583W", "Riverside Wastewater Treatment Upgrade", "City of Riverside", 2023, 48_000_000,
     "Expansion of a 12 MGD plant with new clarifiers and a biosolids building."),
    ("913385709268W", "North County Transit Center", "North County Transit District", 2022, 31_500_000,
     "Bus transfer hub with a parking structure and solar canopies."),
    ("578692717522W", "Harbor Bridge Seismic Retrofit", "Port Authority", 2021, 22_000_000,
     "Seismic retrofit of a 1960s steel truss bridge under live traffic."),
    ("043904274067W", "Mesa Unified K-8 Campus", "Mesa Unified School District", 2024, 64_000_000,
     "New K-8 campus for 1,100 students, design-build, LEED Gold."),
    ("394718595955W", "Valley Medical Center Central Plant", "Valley Health", 2023, 18_750_000,
     "Chiller and boiler replacement in an operating hospital."),
]

EMPLOYEES = [
    ("Dana Whitfield", "Principal in Charge", 24),
    ("Marcus Lee", "Senior Project Manager", 17),
    ("Priya Raman", "Water Resources Lead", 12),
    ("Tomás Ortega", "Structural Engineer", 9),
    ("Grace Kim", "Proposal Manager", 7),
]

DOCUMENTS = [
    ("1790941918186566039", "414945489583W", "Riverside final report",
     "Delivered the clarifier expansion three weeks early with no permit violations during construction."),
    ("-7873854199872705048", "913385709268W", "Transit center lessons learned",
     "Phasing around live bus operations kept the hub open throughout construction."),
    ("63969276736009642", "578692717522W", "Bridge retrofit closeout",
     "Night-only closures and a temporary bypass let traffic run during the retrofit."),
    ("-8857541797583122584", "043904274067W", "K-8 campus award letter",
     "The district cited our community engagement plan and the LEED Gold commitment."),
    ("2233263107820336767", "394718595955W", "Central plant risk memo",
     "Shutdown windows of four hours limited the chiller swaps to two per weekend."),
]


def connect() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def session():
    """A connection whose statements are traced, when run through q().

    The sqlite3 instrumentation traces cursor.execute only. Connection.execute
    makes its own, untraced cursor, and `with sqlite3.connect() as conn`
    gives back the raw, untraced connection. So callers do not use either."""
    conn = connect()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def q(conn, sql: str, params=()):
    """Run one statement on a new cursor, so it gets a span."""
    cur = conn.cursor()
    cur.execute(sql, params)
    return cur


def ensure_seeded() -> None:
    """Create and fill the database once. Both services call this at
    startup, so every statement is idempotent. It uses Connection.execute
    on purpose: seeding is not part of the demo's traces."""
    with connect() as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS orgs (org_id INTEGER PRIMARY KEY, name TEXT)")
        for n in range(1, ORG_COUNT + 1):
            name = "Acme Engineering" if n == DEMO_ORG_ID else f"Firm {n}"
            conn.execute("INSERT OR IGNORE INTO orgs VALUES (?, ?)", (n, name))
            conn.execute(f"CREATE TABLE IF NOT EXISTS org_{n}_props (key TEXT PRIMARY KEY, value TEXT)")
            conn.execute(f"INSERT OR IGNORE INTO org_{n}_props VALUES ('region', 'us-west')")
        conn.execute(
            """CREATE TABLE IF NOT EXISTS bids (
                bid_id TEXT PRIMARY KEY, org_id INTEGER, title TEXT, client TEXT,
                due_date TEXT, team TEXT)"""
        )
        conn.execute(
            "INSERT OR IGNORE INTO bids VALUES (?, ?, ?, ?, ?, ?)",
            (DEMO_BID_ID, DEMO_ORG_ID, "Sample RFP", "Unknown client", "",
             json.dumps(["Marcus Lee", "Grace Kim"])),
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS projects (
                project_id TEXT PRIMARY KEY, org_id INTEGER, name TEXT, client TEXT,
                year INTEGER, value_usd INTEGER, summary TEXT)"""
        )
        conn.executemany(
            "INSERT OR IGNORE INTO projects VALUES (?, ?, ?, ?, ?, ?, ?)",
            [(p[0], DEMO_ORG_ID, *p[1:]) for p in PROJECTS],
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS employees (
                org_id INTEGER, name TEXT, role TEXT, years INTEGER,
                PRIMARY KEY (org_id, name))"""
        )
        conn.executemany(
            "INSERT OR IGNORE INTO employees VALUES (?, ?, ?, ?)",
            [(DEMO_ORG_ID, *e) for e in EMPLOYEES],
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS documents (
                snippet_id TEXT PRIMARY KEY, org_id INTEGER, project_id TEXT,
                title TEXT, text TEXT)"""
        )
        conn.executemany(
            "INSERT OR IGNORE INTO documents VALUES (?, ?, ?, ?, ?)",
            [(d[0], DEMO_ORG_ID, *d[1:]) for d in DOCUMENTS],
        )
        # Progress of each managed-agent session, written by the app's poller.
        conn.execute(
            """CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY, org_id INTEGER, agent_id TEXT,
                status TEXT, events INTEGER, updated_at TEXT)"""
        )
