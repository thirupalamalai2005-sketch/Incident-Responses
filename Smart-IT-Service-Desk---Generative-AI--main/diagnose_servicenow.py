"""
diagnose_servicenow.py
Safe diagnostic tool for ServiceNow Table API connectivity.
Inspects environment settings without printing full credentials.
"""

import os
from pathlib import Path
from urllib.parse import urlparse
import requests

try:
    from dotenv import load_dotenv
    env_path = Path(".env")
    env_found = env_path.exists()
    load_dotenv(override=True)
except ImportError:
    env_found = False

from servicenow import clean_instance_url, TIMEOUT, HEADERS

def mask_password(pwd: str) -> str:
    """Mask password, returning length, first char, and last char only."""
    if not pwd:
        return "[EMPTY]"
    length = len(pwd)
    if length == 1:
        return f"[Length: 1, char: '{pwd}']"
    first_char = pwd[0]
    last_char = pwd[-1]
    return f"[Length: {length}, starts with: '{first_char}', ends with: '{last_char}']"

def run_diagnostics():
    print("=" * 65)
    print("ServiceNow Integration Diagnostic Tool")
    print("=" * 65)

    # 1. Check .env file
    print(f"\n[1] .env File Status:")
    if Path(".env").exists():
        print("  ✓ .env file found in current directory.")
    else:
        print("  ✗ .env file NOT found in current directory!")

    # 2. Check variable presence (both canonical and alias)
    raw_instance = os.getenv("SERVICENOW_INSTANCE") or os.getenv("SN_INSTANCE") or ""
    raw_user = os.getenv("SERVICENOW_USERNAME") or os.getenv("SN_USER") or ""
    raw_password = os.getenv("SERVICENOW_PASSWORD") or os.getenv("SN_PASSWORD") or ""

    clean_url = clean_instance_url(raw_instance)
    user = raw_user.strip()
    password = raw_password.strip()

    print(f"\n[2] Configuration Values Detected:")
    print(f"  • Raw Instance config : {'[SET]' if raw_instance else '[NOT SET]'}")
    print(f"  • Cleaned Instance URL: {clean_url if clean_url else '[EMPTY]'}")
    print(f"  • Username            : {user if user else '[EMPTY]'}")
    print(f"  • Password info       : {mask_password(password)}")

    if not clean_url or not user or not password:
        print("\n[!] Error: Missing required credentials in .env. Please define instance, user, and password.")
        return

    # 3. Connection Test
    test_endpoint = f"{clean_url}/api/now/table/incident?sysparm_limit=1"
    print(f"\n[3] Testing HTTP GET against Table API:")
    print(f"  Endpoint: {test_endpoint}")

    try:
        resp = requests.get(
            test_endpoint,
            auth=(user, password),
            headers=HEADERS,
            timeout=TIMEOUT,
        )
        status = resp.status_code
        content_type = resp.headers.get("Content-Type", "")
        print(f"  HTTP Status Code: {status}")
        print(f"  Content-Type    : {content_type}")

        print("\n[4] Diagnostic Assessment:")
        if "text/html" in content_type or "<html" in resp.text.lower():
            print("  ⚠️ HTML Response Detected (Instance Hibernating):")
            print("     Your ServiceNow Developer Instance appears to be hibernating or redirected to a browser page.")
            print("     Action: Go to https://developer.servicenow.com, log in, open your profile drop-down,")
            print("     and click 'Wake Instance' or 'Refresh'. Wait ~3 minutes before trying again.")
        elif status == 200:
            print("  ✓ SUCCESS (200 OK):")
            print("     Authentication successful and Table API is reachable!")
        elif status == 401:
            print("  ✗ AUTHENTICATION FAILED (401 Unauthorized):")
            print("     The instance rejected the credentials.")
            print("     Common fixes to check in .env:")
            print("     1. Special characters: If your password contains characters like #, =, $, or /,")
            print("        wrap the entire password in single quotes: SERVICENOW_PASSWORD='...'")
            print("     2. Developer Instance password vs ServiceNow ID password:")
            print("        The admin password for your instance is often DIFFERENT from your developer.servicenow.com login password.")
            print("        In developer.servicenow.com, click your profile icon -> 'Manage instance pwd' -> 'Reset instance password'.")
            print("     3. Stale shell variables: Ensure python-dotenv is loaded with override=True.")
            print("     4. Whitespace: Ensure no accidental leading/trailing spaces.")
        elif status == 403:
            print("  ✗ FORBIDDEN (403 Forbidden):")
            print("     User is authenticated, but lacks permissions to query the incident table.")
            print("     Action: In ServiceNow, assign the 'itil' or 'admin' role to this user.")
        elif status == 404:
            print("  ✗ NOT FOUND (404 Not Found):")
            print("     The Table API endpoint could not be found.")
            print("     Action: Check the instance URL. It should look like: https://devXXXXX.service-now.com")
        else:
            print(f"  ⚠️ Unexpected HTTP Status {status}:")
            print(f"     Response body excerpt: {resp.text[:300]}")

    except requests.exceptions.Timeout:
        print("\n[4] Diagnostic Assessment:")
        print("  ✗ REQUEST TIMED OUT:")
        print("     The request took more than 20 seconds. Developer instances often timeout when hibernating.")
        print("     Action: Log into developer.servicenow.com and wake the instance.")
    except requests.exceptions.ConnectionError as ce:
        print("\n[4] Diagnostic Assessment:")
        print("  ✗ CONNECTION ERROR:")
        print(f"     Could not resolve or connect to {clean_url}.")
        print(f"     Details: {ce}")
    except Exception as e:
        print("\n[4] Diagnostic Assessment:")
        print(f"  ✗ UNEXPECTED EXCEPTION: {e}")

    print("=" * 65)

if __name__ == "__main__":
    run_diagnostics()
