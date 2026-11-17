"""
servicenow.py
ServiceNow Table API integration for the AI-Powered Smart IT Service Desk Copilot.

Supports environment variables and .env configuration:
  - Instance URL: SERVICENOW_INSTANCE or SN_INSTANCE
  - Username:     SERVICENOW_USERNAME or SN_USER
  - Password:     SERVICENOW_PASSWORD or SN_PASSWORD
"""

import os
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlparse

import requests

try:
    from dotenv import load_dotenv
    # Always reload and override any stale shell environment variables
    load_dotenv(override=True)
except ImportError:
    pass

try:
    import streamlit as st
except ImportError:
    st = None

# ---------------------------------------------------------------------------
# Configuration & URL Normalization
# ---------------------------------------------------------------------------

_ALIASES = {
    "instance": ["SERVICENOW_INSTANCE", "SN_INSTANCE"],
    "user":     ["SERVICENOW_USERNAME", "SN_USER"],
    "password": ["SERVICENOW_PASSWORD", "SN_PASSWORD"],
}


def clean_instance_url(url: str) -> str:
    """
    Clean instance URL down to https://<host> without path, query params, or trailing slashes.
    Ensures scheme is https if omitted.
    """
    if not url:
        return ""
    url = url.strip()
    if not url.startswith("http://") and not url.startswith("https://"):
        url = "https://" + url

    parsed = urlparse(url)
    scheme = parsed.scheme if parsed.scheme else "https"
    netloc = parsed.netloc or parsed.path.split("/")[0]
    # Remove port if default or keep clean host
    return f"{scheme}://{netloc}".rstrip("/")


def get_config(name: str) -> str:
    """
    Fetch configuration value by alias name, stripping whitespace.
    Checks os.environ first, then st.secrets if available.
    """
    if name not in _ALIASES:
        raise KeyError(f"Unknown config key: {name}")

    for key in _ALIASES[name]:
        val = os.getenv(key)
        if val is not None and str(val).strip() != "":
            return str(val).strip()

        if st is not None:
            try:
                sec_val = st.secrets[key]
                if sec_val is not None and str(sec_val).strip() != "":
                    return str(sec_val).strip()
            except Exception:
                pass

    raise RuntimeError(f"Missing setting. Set one of: {', '.join(_ALIASES[name])}")


def _base_url() -> str:
    raw_url = get_config("instance")
    return clean_instance_url(raw_url)


def _auth() -> Tuple[str, str]:
    return (get_config("user"), get_config("password"))


HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json",
    "User-Agent": "AI-Service-Desk-Copilot/1.0",
}
TIMEOUT = 20  # seconds

# ---------------------------------------------------------------------------
# Mappings: Priority / Category / State
# ---------------------------------------------------------------------------

PRIORITY_MAP: Dict[str, Dict[str, str]] = {
    "critical": {"impact": "1", "urgency": "1"},
    "high":     {"impact": "1", "urgency": "2"},
    "medium":   {"impact": "2", "urgency": "2"},
    "low":      {"impact": "3", "urgency": "3"},
}

CATEGORY_MAP: Dict[str, str] = {
    "hardware": "hardware",
    "software": "software",
    "network":  "network",
    "database": "database",
    "inquiry":  "inquiry",
    "access":   "inquiry",
    "other":    "inquiry",
}

STATE_LABELS: Dict[str, str] = {
    "1": "New",
    "2": "In Progress",
    "3": "On Hold",
    "6": "Resolved",
    "7": "Closed",
    "8": "Canceled",
}


def _parse_error_response(resp: requests.Response) -> str:
    """Extract readable error message or detect hibernation HTML responses."""
    content_type = resp.headers.get("Content-Type", "")
    text = resp.text.strip() if resp.text else ""

    # Detect hibernation HTML page
    if "text/html" in content_type or "<html" in text.lower() or "hibernating" in text.lower():
        return (
            "ServiceNow instance is hibernating or returned a web redirect. "
            "Log in to developer.servicenow.com and click 'Wake Instance' or 'Refresh'."
        )

    try:
        data = resp.json()
        if "error" in data:
            err = data["error"]
            if isinstance(err, dict):
                msg = err.get("message", "")
                detail = err.get("detail", "")
                return f"{msg}: {detail}".strip(": ")
            return str(err)
    except Exception:
        pass

    hints = {
        401: "Authentication failed (HTTP 401). Verify username and password in .env. If password has special characters (# = $ /), wrap it in single quotes.",
        403: "Access forbidden (HTTP 403). The ServiceNow user needs the 'itil' or 'admin' role, or web service access permissions.",
        404: "Endpoint not found (HTTP 404). Check the ServiceNow instance URL.",
        500: "Internal server error on ServiceNow instance.",
    }
    return hints.get(resp.status_code, f"HTTP {resp.status_code}: {text[:150]}")


# ---------------------------------------------------------------------------
# Public Functions
# ---------------------------------------------------------------------------

def create_incident(
    short_description: str,
    description: str,
    priority: str = "Medium",
    category: str = "inquiry",
    work_notes: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Create an incident in ServiceNow via the Table API.
    Truncates short_description to 160 characters. Does not set caller_id.
    """
    try:
        base = _base_url()
        url = f"{base}/api/now/table/incident"

        cat_key = str(category).lower().strip()
        prio_key = str(priority).lower().strip()

        payload: Dict[str, Any] = {
            "short_description": str(short_description).strip()[:160],
            "description": str(description).strip(),
            "category": CATEGORY_MAP.get(cat_key, "inquiry"),
            **PRIORITY_MAP.get(prio_key, PRIORITY_MAP["medium"]),
        }
        if work_notes:
            payload["work_notes"] = str(work_notes).strip()

        resp = requests.post(
            url,
            auth=_auth(),
            headers=HEADERS,
            json=payload,
            timeout=TIMEOUT,
        )

        if resp.status_code not in (200, 201):
            err_msg = _parse_error_response(resp)
            return {"success": False, "error": f"Failed to create incident: {err_msg}"}

        # Check JSON parse
        try:
            data = resp.json()
            result = data["result"]
            sys_id = result.get("sys_id", "")
            number = result.get("number", "")
            return {
                "success": True,
                "number": number,
                "sys_id": sys_id,
                "link": f"{base}/nav_to.do?uri=incident.do?sys_id={sys_id}",
            }
        except Exception:
            return {
                "success": False,
                "error": "ServiceNow returned non-JSON response. Instance may be hibernating.",
            }

    except requests.exceptions.Timeout:
        return {
            "success": False,
            "error": "Request timed out (20s). The ServiceNow instance may be hibernating. Wake it from developer.servicenow.com.",
        }
    except requests.exceptions.ConnectionError:
        return {
            "success": False,
            "error": "Could not connect to ServiceNow. Check internet connection and instance URL.",
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_incident_status(number: str) -> Dict[str, Any]:
    """
    Look up an incident by number (e.g. 'INC0010001') and return state, priority, and update time.
    """
    try:
        base = _base_url()
        url = f"{base}/api/now/table/incident"
        clean_num = str(number).strip()
        params = {
            "sysparm_query": f"number={clean_num}",
            "sysparm_fields": "number,state,priority,short_description,assigned_to,sys_updated_on,sys_id",
            "sysparm_limit": 1,
        }

        resp = requests.get(
            url,
            auth=_auth(),
            headers=HEADERS,
            params=params,
            timeout=TIMEOUT,
        )

        if resp.status_code != 200:
            err_msg = _parse_error_response(resp)
            return {"success": False, "error": f"Error fetching incident {clean_num}: {err_msg}"}

        try:
            data = resp.json()
            results = data.get("result", [])
        except Exception:
            return {
                "success": False,
                "error": "ServiceNow returned non-JSON response. Instance may be hibernating.",
            }

        if not results:
            return {"success": False, "error": f"Incident {clean_num} not found in ServiceNow."}

        rec = results[0]
        raw_state = str(rec.get("state", ""))
        state_str = STATE_LABELS.get(raw_state, f"State ({raw_state})")

        assigned_to_val = rec.get("assigned_to", "")
        if isinstance(assigned_to_val, dict):
            assigned_to_val = assigned_to_val.get("display_value", "") or assigned_to_val.get("value", "")

        return {
            "success": True,
            "number": rec.get("number", clean_num),
            "sys_id": rec.get("sys_id", ""),
            "state": state_str,
            "raw_state": raw_state,
            "priority": rec.get("priority", "N/A"),
            "short_description": rec.get("short_description", ""),
            "assigned_to": assigned_to_val,
            "updated": rec.get("sys_updated_on", ""),
            "link": f"{base}/nav_to.do?uri=incident.do?sys_id={rec.get('sys_id', '')}",
        }

    except requests.exceptions.Timeout:
        return {
            "success": False,
            "error": "Request timed out (20s). The ServiceNow instance may be hibernating.",
        }
    except requests.exceptions.ConnectionError:
        return {
            "success": False,
            "error": "Could not connect to ServiceNow. Check internet connection and instance URL.",
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def test_connection() -> Tuple[bool, str]:
    """
    Test connectivity and credentials against the Table API.
    Returns (True, message) on success or (False, detailed_explanation) on failure.
    """
    try:
        base = _base_url()
        if not base:
            return False, "ServiceNow instance URL is missing or empty."

        url = f"{base}/api/now/table/incident"
        resp = requests.get(
            url,
            auth=_auth(),
            headers=HEADERS,
            params={"sysparm_limit": 1},
            timeout=TIMEOUT,
        )

        content_type = resp.headers.get("Content-Type", "")
        if "text/html" in content_type or "<html" in resp.text.lower():
            return (
                False,
                "Instance is hibernating or redirected to HTML login. Please log in to developer.servicenow.com and wake/refresh your instance.",
            )

        if resp.status_code == 200:
            return True, f"Successfully connected to ServiceNow ({base})."

        err_msg = _parse_error_response(resp)
        return False, err_msg

    except requests.exceptions.Timeout:
        return False, "Connection timed out (20s). Instance may be hibernating."
    except requests.exceptions.ConnectionError:
        return False, "Connection error. Unable to reach the ServiceNow host."
    except RuntimeError as e:
        return False, f"Configuration error: {str(e)}"
    except Exception as e:
        return False, f"Unexpected error: {str(e)}"


# ---------------------------------------------------------------------------
# Self-test execution: python servicenow.py
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("Testing ServiceNow connection...")
    ok, msg = test_connection()
    print(f"Connection result: {msg}")
    if ok:
        print("Creating a test incident...")
        result = create_incident(
            short_description="Test incident from AI Service Desk Copilot self-test",
            description="Created by running python servicenow.py directly to verify Table API integration.",
            priority="Low",
            category="software",
            work_notes="Automated self-test verification."
        )
        print(f"Create incident result: {result}")
