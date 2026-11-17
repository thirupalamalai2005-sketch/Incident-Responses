"""
tests/test_all.py
Unit tests for AI IT Service Desk Copilot.
Tests:
- Password hashing, salt randomness, and constant-time verification.
- Fallback keyword rule classification and coverage.
- Gemini JSON parsing, markdown code-fence stripping, and normalization (mocked network).
- ServiceNow URL cleaning, priority mapping, and category mapping.
"""

import json
from unittest.mock import MagicMock, patch
import pytest

import auth
import fallback_analyzer
import ai_analyzer
import servicenow


# ============================================================================
# 1. Authentication & PBKDF2 Password Hashing Tests
# ============================================================================

def test_hash_password_generates_unique_salt():
    """Verify that hashing the same password twice yields different salts and hashes."""
    pwd = "SecurePassword123!"
    hash1, salt1 = auth.hash_password(pwd)
    hash2, salt2 = auth.hash_password(pwd)

    assert salt1 != salt2
    assert hash1 != hash2
    assert len(salt1) == 32  # 16 bytes in hex = 32 hex chars
    assert len(hash1) == 64  # SHA-256 hex digest = 64 hex chars


def test_verify_password_correct_and_incorrect():
    """Verify password check works with correct credentials and rejects incorrect ones."""
    pwd = "CorrectHorseBatteryStaple!"
    pwd_hash, salt = auth.hash_password(pwd)

    # Correct password
    assert auth.verify_password(pwd, pwd_hash, salt) is True

    # Incorrect passwords
    assert auth.verify_password("WrongPassword!", pwd_hash, salt) is False
    assert auth.verify_password(pwd.lower(), pwd_hash, salt) is False
    assert auth.verify_password("", pwd_hash, salt) is False


def test_email_validation():
    """Verify email format regex checks."""
    assert auth.validate_email("user@example.com") is True
    assert auth.validate_email("john.doe@company.org") is True
    assert auth.validate_email("invalid-email") is False
    assert auth.validate_email("user@") is False
    assert auth.validate_email("@domain.com") is False
    assert auth.validate_email("") is False


# ============================================================================
# 2. Fallback Rule-Based Analyzer Tests
# ============================================================================

def test_fallback_security_phishing():
    """Phishing/malware should map to access category with Critical priority."""
    issue = "I received a suspicious phishing email claiming my account was hacked."
    res = fallback_analyzer.analyze_with_rules(issue)

    assert res["category"] == "access"
    assert res["priority"] == "Critical"
    assert len(res["steps"]) >= 3
    assert any("disconnect" in s.lower() for s in res["steps"])


def test_fallback_bsod_crash():
    """Blue screen / crash should map to hardware category with High priority."""
    issue = "My laptop had a blue screen crash with BSOD error."
    res = fallback_analyzer.analyze_with_rules(issue)

    assert res["category"] == "hardware"
    assert res["priority"] == "High"
    assert len(res["steps"]) >= 3


def test_fallback_network_vpn():
    """VPN / wifi should map to network category."""
    issue = "Cannot connect to company VPN or Wi-Fi network."
    res = fallback_analyzer.analyze_with_rules(issue)

    assert res["category"] == "network"
    assert res["priority"] in ["High", "Medium"]
    assert len(res["steps"]) >= 3


def test_fallback_database():
    """Database query timeout or SQL errors should map to database category."""
    issue = "Application throwing database query timeout error."
    res = fallback_analyzer.analyze_with_rules(issue)

    assert res["category"] == "database"
    assert res["priority"] == "High"


def test_fallback_printer():
    """Printer issues should map to hardware category with Low priority."""
    issue = "The office printer has a paper jam and is offline."
    res = fallback_analyzer.analyze_with_rules(issue)

    assert res["category"] == "hardware"
    assert res["priority"] == "Low"


# ============================================================================
# 3. AI Analyzer & JSON Parsing Tests (Mocked, No Real Network)
# ============================================================================

def test_clean_markdown_json_strip_fences():
    """Verify markdown code fences ```json ... ``` are cleanly removed."""
    raw = "```json\n{\"summary\": \"Test summary\", \"category\": \"network\"}\n```"
    cleaned = ai_analyzer.clean_markdown_json(raw)
    parsed = json.loads(cleaned)
    assert parsed["summary"] == "Test summary"
    assert parsed["category"] == "network"


def test_ai_analyzer_normalizes_category_and_priority():
    """Ensure casing and non-standard synonyms are normalized."""
    assert ai_analyzer.normalize_category("WIFI") == "network"
    assert ai_analyzer.normalize_category("Laptop") == "hardware"
    assert ai_analyzer.normalize_category("unknown_thing") == "other"

    assert ai_analyzer.normalize_priority("critical") == "Critical"
    assert ai_analyzer.normalize_priority("P1") == "Critical"
    assert ai_analyzer.normalize_priority("p3") == "Medium"


@patch("ai_analyzer.genai.Client")
def test_ai_analyzer_success_mock(mock_client_class):
    """Test successful Gemini JSON parsing and normalization without network call."""
    mock_response = MagicMock()
    mock_response.text = json.dumps({
        "summary": "Wi-Fi adapter disconnected",
        "category": "network",
        "priority": "Medium",
        "steps": ["Restart Wi-Fi adapter", "Check IP config"]
    })

    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = mock_response
    mock_client_class.return_value = mock_client

    with patch.dict("os.environ", {"GEMINI_API_KEY": "fake_key_123"}):
        result, source = ai_analyzer.analyze_incident("My Wi-Fi is broken")

    assert source == "gemini"
    assert result["category"] == "network"
    assert result["priority"] == "Medium"
    assert len(result["steps"]) == 2


@patch("ai_analyzer.genai.Client")
def test_ai_analyzer_fallback_on_gemini_error(mock_client_class):
    """Test that any Gemini exception automatically falls back to rule-based engine."""
    mock_client = MagicMock()
    mock_client.models.generate_content.side_effect = RuntimeError("Quota exceeded 429")
    mock_client_class.return_value = mock_client

    with patch.dict("os.environ", {"GEMINI_API_KEY": "fake_key_123"}):
        result, source = ai_analyzer.analyze_incident("VPN connection dropped suddenly")

    assert source == "fallback"
    assert result["category"] == "network"
    assert "summary" in result
    assert isinstance(result["steps"], list)


# ============================================================================
# 4. ServiceNow Integration Tests (Mocked, No Real Network)
# ============================================================================

def test_clean_instance_url():
    """Verify URL cleaning handles login URLs, query params, paths, and trailing slashes."""
    assert servicenow.clean_instance_url("https://dev12345.service-now.com/login.do?user=admin") == "https://dev12345.service-now.com"
    assert servicenow.clean_instance_url("dev12345.service-now.com/") == "https://dev12345.service-now.com"
    assert servicenow.clean_instance_url("http://dev99999.service-now.com/sub/path/") == "http://dev99999.service-now.com"


def test_priority_and_category_mapping():
    """Verify priority impact/urgency and category mapping dicts."""
    assert servicenow.PRIORITY_MAP["critical"] == {"impact": "1", "urgency": "1"}
    assert servicenow.PRIORITY_MAP["high"] == {"impact": "1", "urgency": "2"}
    assert servicenow.PRIORITY_MAP["medium"] == {"impact": "2", "urgency": "2"}
    assert servicenow.PRIORITY_MAP["low"] == {"impact": "3", "urgency": "3"}

    assert servicenow.CATEGORY_MAP["hardware"] == "hardware"
    assert servicenow.CATEGORY_MAP["software"] == "software"
    assert servicenow.CATEGORY_MAP["network"] == "network"
    assert servicenow.CATEGORY_MAP["database"] == "database"
    assert servicenow.CATEGORY_MAP["access"] == "inquiry"
    assert servicenow.CATEGORY_MAP["other"] == "inquiry"


@patch("servicenow.requests.post")
def test_create_incident_success(mock_post):
    """Test successful incident creation returning number, sys_id and link."""
    mock_resp = MagicMock()
    mock_resp.status_code = 201
    mock_resp.json.return_value = {
        "result": {
            "number": "INC0010042",
            "sys_id": "abc123sysid456",
        }
    }
    mock_post.return_value = mock_resp

    with patch("servicenow._base_url", return_value="https://dev12345.service-now.com"), \
         patch("servicenow._auth", return_value=("admin", "pwd")):
        res = servicenow.create_incident(
            short_description="Printer issue",
            description="Paper jam in floor 2 printer",
            priority="Low",
            category="hardware"
        )

    assert res["success"] is True
    assert res["number"] == "INC0010042"
    assert res["sys_id"] == "abc123sysid456"
    assert "https://dev12345.service-now.com" in res["link"]


@patch("servicenow.requests.post")
def test_create_incident_401_error(mock_post):
    """Test readable error handling on HTTP 401."""
    mock_resp = MagicMock()
    mock_resp.status_code = 401
    mock_resp.headers = {"Content-Type": "application/json"}
    mock_resp.json.return_value = {"error": {"message": "User not authenticated"}}
    mock_resp.text = json.dumps(mock_resp.json.return_value)
    mock_post.return_value = mock_resp

    with patch("servicenow._base_url", return_value="https://dev12345.service-now.com"), \
         patch("servicenow._auth", return_value=("admin", "pwd")):
        res = servicenow.create_incident(
            short_description="Test issue",
            description="Description",
        )

    assert res["success"] is False
    assert "401" in res["error"] or "authenticated" in res["error"]
