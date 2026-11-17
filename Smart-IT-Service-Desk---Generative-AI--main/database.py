"""
database.py
SQLite storage and schema migrations for AI IT Service Desk Copilot.
Handles users and incidents tables with safe ALTER TABLE migrations.
All queries use parameterized SQL to prevent SQL injection.
"""

import json
import sqlite3
from typing import Any, Dict, List, Optional

DB_NAME = "incidents.db"


def get_connection() -> sqlite3.Connection:
    """Get SQLite connection configured for dict-like row access."""
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn


def initialize_database() -> None:
    """
    Initialize SQLite schema and run non-destructive migrations
    to ensure all required columns exist without losing existing data.
    """
    conn = get_connection()
    cursor = conn.cursor()

    # 1. Users table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            salt TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Check and migrate users columns if needed
    cursor.execute("PRAGMA table_info(users)")
    user_cols = {row["name"] for row in cursor.fetchall()}
    if "created_at" not in user_cols:
        cursor.execute("ALTER TABLE users ADD COLUMN created_at TIMESTAMP")
        cursor.execute("UPDATE users SET created_at = datetime('now') WHERE created_at IS NULL")

    # 2. Incidents table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS incidents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            issue_text TEXT,
            summary TEXT,
            category TEXT,
            priority TEXT,
            steps TEXT,
            source TEXT DEFAULT 'gemini',
            servicenow_number TEXT,
            servicenow_sys_id TEXT,
            servicenow_sync_status TEXT DEFAULT 'not_sent',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    """)

    # Check columns in existing incidents table for safe migration
    cursor.execute("PRAGMA table_info(incidents)")
    incident_cols = {row["name"] for row in cursor.fetchall()}

    needed_columns = {
        "user_id": "INTEGER",
        "issue_text": "TEXT",
        "summary": "TEXT",
        "category": "TEXT",
        "priority": "TEXT",
        "steps": "TEXT",
        "source": "TEXT DEFAULT 'gemini'",
        "servicenow_number": "TEXT",
        "servicenow_sys_id": "TEXT",
        "servicenow_sync_status": "TEXT DEFAULT 'not_sent'",
        "created_at": "TIMESTAMP",
        "owner_email": "TEXT DEFAULT ''",
    }

    for col_name, col_type in needed_columns.items():
        if col_name not in incident_cols:
            cursor.execute(f"ALTER TABLE incidents ADD COLUMN {col_name} {col_type}")

    # Set timestamps if NULL
    cursor.execute("UPDATE incidents SET created_at = datetime('now') WHERE created_at IS NULL")

    # Backfill missing new column values from legacy columns if present
    if "issue" in incident_cols:
        cursor.execute("UPDATE incidents SET issue_text = issue WHERE (issue_text IS NULL OR issue_text = '') AND issue IS NOT NULL")
    if "solutions" in incident_cols:
        cursor.execute("UPDATE incidents SET steps = solutions WHERE (steps IS NULL OR steps = '') AND solutions IS NOT NULL")

    conn.commit()
    conn.close()


# Run initialization immediately on module import
initialize_database()


# ---------------------------------------------------------------------------
# User Operations (Parameterized SQL)
# ---------------------------------------------------------------------------

def create_user(email: str, password_hash: str, salt: str) -> bool:
    """Insert a new user using parameterized SQL."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO users (email, password_hash, salt)
            VALUES (?, ?, ?)
            """,
            (email.strip().lower(), password_hash, salt),
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()


def get_user_by_email(email: str) -> Optional[Dict[str, Any]]:
    """Fetch user record by email."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT id, email, password_hash, salt, created_at
        FROM users
        WHERE email = ?
        """,
        (email.strip().lower(),),
    )
    row = cursor.fetchone()
    conn.close()
    if row:
        return dict(row)
    return None


# ---------------------------------------------------------------------------
# Incident Operations (Parameterized SQL)
# ---------------------------------------------------------------------------

def save_incident(
    user_id: Optional[int],
    owner_email: str,
    issue_text: str,
    summary: str,
    category: str,
    priority: str,
    steps: List[str],
    source: str = "gemini",
    servicenow_number: Optional[str] = None,
    servicenow_sys_id: Optional[str] = None,
    servicenow_sync_status: str = "not_sent",
) -> int:
    """Save an incident record using parameterized SQL."""
    conn = get_connection()
    cursor = conn.cursor()

    steps_json = json.dumps(steps) if isinstance(steps, list) else str(steps)

    cursor.execute(
        """
        INSERT INTO incidents (
            user_id, owner_email, issue_text, summary, category, priority,
            steps, source, servicenow_number, servicenow_sys_id,
            servicenow_sync_status, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
        """,
        (
            user_id,
            owner_email.strip().lower(),
            issue_text.strip(),
            summary.strip(),
            category.strip(),
            priority.strip(),
            steps_json,
            source.strip(),
            servicenow_number,
            servicenow_sys_id,
            servicenow_sync_status,
        ),
    )
    incident_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return incident_id


def update_servicenow_sync(
    incident_id: int,
    number: Optional[str],
    sys_id: Optional[str],
    sync_status: str,
) -> None:
    """Update ServiceNow sync status and incident numbers for an incident."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE incidents
        SET servicenow_number = ?,
            servicenow_sys_id = ?,
            servicenow_sync_status = ?
        WHERE id = ?
        """,
        (number, sys_id, sync_status, incident_id),
    )
    conn.commit()
    conn.close()


def get_user_incidents(owner_email: str) -> List[Dict[str, Any]]:
    """Retrieve all incidents submitted by a user ordered by ID desc."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT id, user_id, owner_email, issue_text, summary, category, priority,
               steps, source, servicenow_number, servicenow_sys_id,
               servicenow_sync_status, created_at
        FROM incidents
        WHERE owner_email = ?
        ORDER BY id DESC
        """,
        (owner_email.strip().lower(),),
    )
    rows = cursor.fetchall()
    conn.close()

    result = []
    for r in rows:
        item = dict(r)
        try:
            item["steps"] = json.loads(item["steps"]) if item["steps"] else []
        except Exception:
            item["steps"] = [item["steps"]] if item["steps"] else []
        result.append(item)
    return result


def get_pending_sync_incidents(owner_email: str) -> List[Dict[str, Any]]:
    """Retrieve incidents that failed sync or are marked pending_sync."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT id, user_id, owner_email, issue_text, summary, category, priority,
               steps, source, servicenow_number, servicenow_sys_id,
               servicenow_sync_status, created_at
        FROM incidents
        WHERE owner_email = ? AND servicenow_sync_status = 'pending_sync'
        ORDER BY id ASC
        """,
        (owner_email.strip().lower(),),
    )
    rows = cursor.fetchall()
    conn.close()
    result = []
    for r in rows:
        item = dict(r)
        try:
            item["steps"] = json.loads(item["steps"]) if item["steps"] else []
        except Exception:
            item["steps"] = [item["steps"]] if item["steps"] else []
        result.append(item)
    return result
