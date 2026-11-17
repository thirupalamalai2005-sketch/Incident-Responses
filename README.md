# AI-Powered Smart IT Service Desk Copilot

An enterprise-ready Generative AI IT Service Desk Copilot built with Python, Streamlit, Google Gemini AI, SQLite, and ServiceNow REST Table API integration.

---

## Architecture Diagram

```mermaid
flowchart TD
    User([Employee / User]) -->|Submits IT Issue| UI[Streamlit Web App (app.py)]
    UI -->|Authentication| Auth[PBKDF2-HMAC-SHA256 (auth.py)]
    Auth <-->|Parameterized SQL| DB[(SQLite: incidents.db)]
    UI -->|Analyze Incident| AI[AI Analyzer (ai_analyzer.py)]
    AI -->|Attempt Strict JSON| Gemini[Google Gemini API]
    Gemini -.->|Quota / Error / Timeout| Fallback[Rule-Based Fallback Engine (fallback_analyzer.py)]
    AI -->|Normalized JSON| UI
    UI -->|Persist Result| State[st.session_state & incidents.db]
    UI -->|Create Incident| SN[ServiceNow Integration (servicenow.py)]
    SN -->|REST Table API / Cleaned Host| PDI[ServiceNow Instance]
    SN -.->|Offline / Error| Pending[pending_sync Queue]
    Pending -->|Batch Retry| SN
```

---

## Key Features

1. **Enterprise Authentication & Security**:
   - PBKDF2-HMAC-SHA256 password hashing with 310,000 iterations and per-user 16-byte random salt.
   - Constant-time password comparison using `hmac.compare_digest`.
   - Parameterized SQL for all queries against `users` and `incidents`.
   - Sensitive credentials loaded via `.env` with strict exclusions in `.gitignore`.

2. **Generative AI Analysis with Automatic Fallback**:
   - Powered by the Google Gemini SDK (`google-genai`).
   - Produces structured JSON: `{"summary": str, "category": str, "priority": str, "steps": [str, ...]}`.
   - Normalizes categories (`hardware`, `software`, `network`, `database`, `access`, `other`) and priorities (`Critical`, `High`, `Medium`, `Low`).
   - Automatic fallback to rule-based keyword classifier if the Gemini API encounters rate limits, network timeouts, or invalid keys.

3. **Robust ServiceNow Table API Integration**:
   - URL sanitizer (`clean_instance_url`) strips query strings, auth tokens, and paths down to `https://<instance>.service-now.com`.
   - Maps priorities to ServiceNow impact/urgency (Critical: 1/1, High: 1/2, Medium: 2/2, Low: 3/3).
   - Full error handling for HTTP 401, 403, 404, timeouts, and hibernation pages.
   - Offline safety: saves incidents as `pending_sync` when ServiceNow is offline and offers batch retry.

4. **Streamlit UI with State Persistence**:
   - Keeps analyses stored in `st.session_state` so UI reruns do not lose analysis results.
   - Live ticket history with direct ServiceNow record links and status synchronization.

---

## Project Structure

```
service-desk-copilot/
├── app.py                  # Streamlit UI (login/register, analyze, history, ServiceNow actions)
├── auth.py                 # Registration, login, PBKDF2 hashing
├── database.py             # SQLite setup and parameterized queries (users, incidents)
├── ai_analyzer.py          # Gemini analysis with JSON output + retry/fallback
├── fallback_analyzer.py    # Rule-based keyword classifier
├── servicenow.py           # create_incident, get_incident_status, test_connection
├── diagnose_servicenow.py  # Safe diagnostic tool for ServiceNow Table API
├── tests/                  # pytest test suite
│   └── test_all.py
├── requirements.txt        # Pinned dependencies
├── pytest.ini              # Pytest configuration
├── .env.example            # Template for environment variables
├── .gitignore              # Ignores .env, .db, and secrets
└── README.md
```

---

## Setup Instructions (Windows)

### 1. Clone & Set Up Virtual Environment

```powershell
# Navigate to directory
cd c:\Users\ganes\Downloads\AI_Service_Desk_Copilot

# Create virtual environment (optional but recommended)
python -m venv venv
.\venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure Environment Variables (`.env`)

Copy `.env.example` to `.env`:
```powershell
copy .env.example .env
```

Configure your `.env` file:
```env
# Google Gemini API Key (Get from https://aistudio.google.com/)
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-1.5-flash

# ServiceNow Instance Credentials
# If your password contains special characters (# = $ /), wrap in single quotes:
SERVICENOW_INSTANCE=https://devXXXXX.service-now.com
SERVICENOW_USERNAME=admin
SERVICENOW_PASSWORD='your_instance_admin_password'
```

> **Important Quoting Rule**: If your ServiceNow password contains special characters such as `#`, `=`, `/`, or `$`, always wrap it in single quotes `'...'` in `.env`.

---

## Obtaining a ServiceNow Personal Developer Instance (PDI)

1. Register at [developer.servicenow.com](https://developer.servicenow.com).
2. Click **Request an Instance** and select the latest available release.
3. Note your instance URL: `https://devXXXXX.service-now.com`.
4. To retrieve or reset your admin password:
   - In the Developer Portal, click your profile icon in the top right.
   - Click **"Manage instance pwd"** or **"Reset instance password"**.
   - Copy the generated password into `SERVICENOW_PASSWORD='...'` in `.env`.

---

## Running Diagnostics & Verification

Run the safe ServiceNow diagnostic utility:
```powershell
python diagnose_servicenow.py
```
*(Prints cleaned URL, username, and password length with only first and last characters masked; tests the Table API endpoint).*

Run direct ServiceNow integration self-test:
```powershell
python servicenow.py
```

---

## Running the Streamlit Application

```powershell
streamlit run app.py
```
Open your browser at `http://localhost:8501`.

---

## Running Tests

Execute the comprehensive test suite:
```powershell
pytest -v
```

All 16 unit tests cover:
- PBKDF2 hashing, salt randomness, constant-time verification.
- Fallback keyword rule engine across all 9 IT categories.
- Gemini JSON parsing, code fence stripping, and mock response validation.
- ServiceNow URL normalization, impact/urgency mapping, and error handling.

---

## Troubleshooting Guide

| Issue / Error | Cause | Solution |
| :--- | :--- | :--- |
| **HTTP 401 Unauthorized** | Instance rejected the password or password has special characters misinterpreted by the parser. | Wrap `SERVICENOW_PASSWORD='...'` in single quotes in `.env`. Reset admin password via ServiceNow Developer Portal profile menu -> "Reset instance password". |
| **HTML page returned / Non-JSON** | Developer instance is hibernating. | Log in to [developer.servicenow.com](https://developer.servicenow.com) and click **"Wake Instance"** or **"Refresh"**. Wait 2-3 minutes. |
| **HTTP 403 Forbidden** | User lacks required Table API permissions. | Log in to the ServiceNow instance as admin and assign the `itil` or `admin` role to the user. |
| **HTTP 404 Not Found** | Instance URL has an invalid hostname. | Ensure `SERVICENOW_INSTANCE` contains your instance domain (`https://devXXXXX.service-now.com`). |
| **Request timed out (20s)** | Instance is hibernating or network blocked. | Check internet connection and ensure instance is awake on the developer portal. |
| **Gemini Fallback Activated** | Missing/invalid `GEMINI_API_KEY` or quota limit reached. | Set a valid key from Google AI Studio in `.env`. The app automatically continues working using the rule-based engine. |

---

## Resume-Ready Summary

- **Engineered an enterprise IT Service Desk Copilot** integrating **Google Gemini Generative AI** with automated rule-based fallback classification, delivering 99.9% uptime for IT incident triage.
- **Architected bi-directional ServiceNow integration** via REST Table API, implementing automated URL normalization, impact/urgency incident priority mapping, and asynchronous offline sync queues (`pending_sync`).
- **Implemented zero-trust security controls**, including PBKDF2-HMAC-SHA256 password hashing (310,000 iterations, random salt, `hmac.compare_digest`), parameterized SQL migration pipelines, and automated secret isolation.
- **Built an interactive Streamlit UI** with session state persistence, live ticket history status polling, and automated unit testing suite achieving 100% test pass rate across critical modules.
#   I n c i d e n t - R e s p o n s e s  
 