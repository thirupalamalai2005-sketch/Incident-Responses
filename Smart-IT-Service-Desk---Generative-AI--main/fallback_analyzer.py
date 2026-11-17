"""
fallback_analyzer.py
Rule-based keyword fallback analyzer for IT incidents.
Runs automatically when the Gemini API is unreachable, quota is exceeded,
or the model returns invalid format.

Covers:
- VPN / Network / Wi-Fi
- Password reset / locked account / login permissions
- Email / Outlook
- Printer issues
- Slow laptop / performance
- Blue screen / crash / kernel panic
- Software install / permissions
- Database errors / SQL / timeout
- Security / phishing / malware (High or Critical priority)
"""

from typing import Any, Dict, List

# Allowed categories and priorities
ALLOWED_CATEGORIES = ["hardware", "software", "network", "database", "access", "other"]
ALLOWED_PRIORITIES = ["Critical", "High", "Medium", "Low"]


def analyze_with_rules(issue_text: str) -> Dict[str, Any]:
    """
    Classify an issue using keyword rules and return troubleshooting steps.
    Matches the schema:
    {
        "summary": str,
        "category": str,
        "priority": str,
        "steps": [str, ...]
    }
    """
    text = (issue_text or "").lower()

    # Default baseline
    category = "other"
    priority = "Medium"
    summary = (issue_text.strip()[:150] if issue_text else "General IT Support Incident")
    steps: List[str] = [
        "Record exact error messages and any recent system changes.",
        "Restart the affected application or device.",
        "Check organizational service health dashboards for active outages.",
        "If the issue persists, escalate to the central IT Service Desk.",
    ]

    # 1. Security / Phishing / Malware (Critical or High)
    if any(k in text for k in ["phish", "malware", "ransomware", "virus", "hacked", "compromised", "suspicious email", "breach"]):
        category = "access"
        priority = "Critical"
        summary = "Urgent: Potential security threat or compromised credentials"
        steps = [
            "Immediately disconnect your machine from Wi-Fi and unplug the Ethernet network cable.",
            "Do NOT click any suspicious links, download attachments, or forward the email.",
            "If credentials were submitted on a suspicious page, immediately alert the IT Security Operations Center (SOC).",
            "Change your corporate passwords from a secondary, known-clean device.",
            "Await immediate triage instructions from the InfoSec team.",
        ]

    # 2. Blue screen / Crash / Kernel Panic (High)
    elif any(k in text for k in ["bsod", "blue screen", "system crash", "kernel panic", "freezing completely", "auto reboot"]):
        category = "hardware"
        priority = "High"
        summary = "Operating system crash / Blue Screen of Death (BSOD)"
        steps = [
            "Note any stop code displayed on the screen (e.g. CRITICAL_PROCESS_DIED, MEMORY_MANAGEMENT).",
            "Perform a hard reset by pressing and holding the power button for 15-20 seconds.",
            "Disconnect external docks, USB hubs, or third-party monitors to isolate faulty peripherals.",
            "Boot into Safe Mode and run Windows Memory Diagnostic (`mdsched.exe`).",
            "If system fails to boot, contact IT Desktop Support for memory or SSD replacement.",
        ]

    # 3. Database errors / SQL / Timeout
    elif any(k in text for k in ["database", "sql", "postgres", "mysql", "oracle", "query timeout", "db connection"]):
        category = "database"
        priority = "High"
        summary = "Database connectivity or query timeout error"
        steps = [
            "Verify network access and firewall connectivity to the database host and port (e.g., using `telnet` or `Test-NetConnection`).",
            "Check database service status and pool connection utilization on the database server.",
            "Examine application logs for specific SQL exception codes, deadlocks, or exhausted connection pools.",
            "Verify that your database service user credentials and certificates have not expired.",
            "Contact the Database Administration (DBA) team if database locks or high CPU usage are observed.",
        ]

    # 4. VPN / Wi-Fi / Network
    elif any(k in text for k in ["vpn", "wifi", "wi-fi", "internet", "network", "dns", "gateway", "disconnected", "no internet"]):
        category = "network"
        priority = "High" if "vpn" in text else "Medium"
        summary = "Network or VPN connection failure"
        steps = [
            "Toggle airplane mode on/off or restart your network adapter.",
            "Verify your physical Wi-Fi connection and test DNS resolution (e.g., run `ipconfig /flushdns` in terminal).",
            "If using corporate VPN (e.g. Cisco AnyConnect, GlobalProtect), confirm your internet is stable before initiating the VPN tunnel.",
            "Restart the VPN client application and verify that your VPN certificate or Multi-Factor Authentication (MFA) has not expired.",
            "Restart your home/office router if all devices are affected.",
        ]

    # 5. Password Reset / Locked Account / Access
    elif any(k in text for k in ["password", "locked", "forgot password", "reset password", "login failed", "access denied", "permission", "mfa", "2fa", "okta"]):
        category = "access"
        priority = "Medium"
        summary = "Account lockout or password reset request"
        steps = [
            "Verify Caps Lock is turned off and ensure you are using the correct corporate email username.",
            "Navigate to the self-service password reset portal (SSPR) to unlock your account via MFA.",
            "Wait 15 minutes for any temporary account lockouts to clear automatically.",
            "Clear cached browser credentials or try in a private/incognito browsing session.",
            "Contact IT Identity & Access Management (IAM) if self-service reset is unavailable.",
        ]

    # 6. Email / Outlook
    elif any(k in text for k in ["outlook", "email", "mailbox", "exchange", "send email", "receive email", "inbox"]):
        category = "software"
        priority = "Medium"
        summary = "Email client or Outlook synchronization issue"
        steps = [
            "Log in to Outlook Web App (OWA) in your browser to confirm whether the Exchange mailbox is operational.",
            "Restart Microsoft Outlook and check the bottom status bar for 'Connected to Microsoft Exchange'.",
            "If Outlook is frozen or indexing slowly, start it in Safe Mode by running `outlook.exe /safe`.",
            "Verify that your mailbox storage quota has not been exceeded.",
            "Check corporate IT announcements for Microsoft 365 Exchange tenant alerts.",
        ]

    # 7. Printer Issues
    elif any(k in text for k in ["printer", "print", "paper jam", "spooler", "toner"]):
        category = "hardware"
        priority = "Low"
        summary = "Printer offline or print spooler error"
        steps = [
            "Check that the printer is powered on, has paper/toner, and displays no error or paper-jam lights.",
            "Verify your computer is on the same local network subnet or VPN required for the network printer.",
            "Open Services (`services.msc`) and restart the 'Print Spooler' service.",
            "Remove and re-add the network printer queue in Windows Settings > Printers & Scanners.",
            "Print a test page to verify communication.",
        ]

    # 8. Slow Laptop / High CPU / Memory
    elif any(k in text for k in ["slow", "lagging", "high cpu", "memory", "hanging", "sluggish", "performance"]):
        category = "hardware"
        priority = "Low"
        summary = "System performance degradation and high resource usage"
        steps = [
            "Open Task Manager (`Ctrl + Shift + Esc`) to identify processes with high CPU, Memory, or Disk usage.",
            "Close memory-intensive browser tabs or unnecessary background applications.",
            "Check available hard drive space and ensure at least 15% free disk space is available.",
            "Perform a clean system restart to release system memory leaks and apply pending updates.",
            "Run hardware diagnostics if fans are constantly running at maximum speed.",
        ]

    # 9. Software Install / Permissions
    elif any(k in text for k in ["install", "installation", "update", "admin rights", "uac", "license"]):
        category = "software"
        priority = "Medium"
        summary = "Software installation or application license issue"
        steps = [
            "Check whether the requested software is approved and available in the Company Portal / Software Center.",
            "Verify if administrator elevation is required for the installation.",
            "Confirm that your operating system meets the minimum system and architecture requirements (64-bit).",
            "Submit an IT catalog request if a dedicated enterprise license key is required.",
        ]

    return {
        "summary": summary,
        "category": category,
        "priority": priority,
        "steps": steps,
    }
