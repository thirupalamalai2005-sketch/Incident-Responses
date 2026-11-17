"""
app.py
Streamlit Web UI for AI-Powered Smart IT Service Desk Copilot.
Features:
- Authentication: Register / Login with PBKDF2 password hashing.
- Sidebar: Session controls, user info, ServiceNow connectivity status.
- Analysis Page: Issue input, Gemini analysis with rule-based fallback,
  result display (summary, category, priority badge, steps),
  and "Create ServiceNow Incident" button that displays the created INC number and link.
  Persists across Streamlit reruns via st.session_state.
- History Page: Past incidents in a structured table and expanders with a "Refresh status" action.
- Retry Pending Incidents: Dedicated view & button to retry incidents that failed or were saved offline.
"""

import os
from typing import Any, Dict
import pandas as pd
import streamlit as st

import ai_analyzer
import auth
import database
import servicenow

# ---------------------------------------------------------------------------
# Streamlit Page Config
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="AI IT Service Desk Copilot",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Priority Badges
PRIORITY_COLORS = {
    "Critical": "🔴 Critical",
    "High": "🟠 High",
    "Medium": "🟡 Medium",
    "Low": "🟢 Low",
}

# ---------------------------------------------------------------------------
# Session State Initialization
# ---------------------------------------------------------------------------
if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False
if "user_email" not in st.session_state:
    st.session_state["user_email"] = ""
if "user_id" not in st.session_state:
    st.session_state["user_id"] = None
if "current_analysis" not in st.session_state:
    st.session_state["current_analysis"] = None
if "last_issue_text" not in st.session_state:
    st.session_state["last_issue_text"] = ""
if "current_local_id" not in st.session_state:
    st.session_state["current_local_id"] = None
if "sn_status_cache" not in st.session_state:
    st.session_state["sn_status_cache"] = {}


# ---------------------------------------------------------------------------
# Authentication Page
# ---------------------------------------------------------------------------
def render_auth_page() -> None:
    st.title("🤖 AI-Powered Smart IT Service Desk Copilot")
    st.markdown("Intelligent IT incident classification, resolution guidance, and ServiceNow integration.")
    st.divider()

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        tab_login, tab_register = st.tabs(["🔐 Sign In", "📝 Create Account"])

        with tab_login:
            st.subheader("Login to your account")
            with st.form("login_form"):
                email = st.text_input("Corporate Email Address", placeholder="user@company.com")
                password = st.text_input("Password", type="password")
                submit_login = st.form_submit_button("Sign In", use_container_width=True, type="primary")

            if submit_login:
                if not email.strip() or not password:
                    st.warning("Please enter your email and password.")
                elif auth.login_user(email, password):
                    user_record = database.get_user_by_email(email)
                    st.session_state["logged_in"] = True
                    st.session_state["user_email"] = email.strip().lower()
                    st.session_state["user_id"] = user_record["id"] if user_record else None
                    st.success("Authentication successful.")
                    st.rerun()
                else:
                    st.error("Invalid email or password.")

        with tab_register:
            st.subheader("Register a new user")
            with st.form("register_form"):
                reg_email = st.text_input("Corporate Email Address", placeholder="user@company.com")
                reg_password = st.text_input("Password (min 8 chars)", type="password")
                reg_confirm = st.text_input("Confirm Password", type="password")
                submit_reg = st.form_submit_button("Register Account", use_container_width=True, type="primary")

            if submit_reg:
                if reg_password != reg_confirm:
                    st.error("Passwords do not match.")
                else:
                    success, message = auth.register_user(reg_email, reg_password)
                    if success:
                        st.success(f"{message} You may now sign in.")
                    else:
                        st.error(message)

    st.divider()
    st.caption("Secure Authentication: PBKDF2-HMAC-SHA256 with 310,000 iterations & random salt.")


# ---------------------------------------------------------------------------
# Sidebar Navigation & Status
# ---------------------------------------------------------------------------
def render_sidebar() -> str:
    st.sidebar.title("🤖 IT Service Desk")
    st.sidebar.markdown(f"**Logged in as:** `{st.session_state['user_email']}`")

    # ServiceNow Connection Indicator
    st.sidebar.markdown("---")
    st.sidebar.subheader("ServiceNow Connection")

    if st.sidebar.button("Test ServiceNow Connection", use_container_width=True):
        with st.sidebar:
            with st.spinner("Connecting to ServiceNow Table API..."):
                ok, msg = servicenow.test_connection()
                if ok:
                    st.session_state["sn_connection_state"] = ("online", msg)
                else:
                    st.session_state["sn_connection_state"] = ("offline", msg)

    conn_state = st.session_state.get("sn_connection_state", None)
    if conn_state:
        status_type, msg = conn_state
        if status_type == "online":
            st.sidebar.success("🟢 Connected")
            st.sidebar.caption(msg)
        else:
            st.sidebar.error("🔴 Offline / Error")
            st.sidebar.caption(msg[:150])
    else:
        st.sidebar.info("⚪ Not tested yet")

    st.sidebar.markdown("---")
    nav_choice = st.sidebar.radio(
        "Navigation",
        ["🔍 Incident Analysis", "📋 Incident History", "🔄 Pending Syncs"],
    )

    st.sidebar.markdown("---")
    if st.sidebar.button("Sign Out", use_container_width=True):
        st.session_state.clear()
        st.rerun()

    return nav_choice


# ---------------------------------------------------------------------------
# Page: Incident Analysis
# ---------------------------------------------------------------------------
def render_analysis_page() -> None:
    st.subheader("🔍 IT Incident Triage & Analysis")
    st.markdown("Enter an employee's technical issue. The Copilot analyzes symptoms, assigns category and priority, and generates resolution steps.")

    with st.form("incident_submission_form"):
        issue_text = st.text_area(
            "Describe the IT issue:",
            placeholder="e.g. My laptop screen turned blue with error CRITICAL_PROCESS_DIED and keeps rebooting.",
            height=130,
            value=st.session_state.get("last_issue_text", ""),
        )
        submitted = st.form_submit_button("⚡ Analyze Incident", type="primary")

    if submitted:
        if not issue_text.strip():
            st.warning("Please provide a description of the IT issue.")
        else:
            with st.spinner("Analyzing incident with Generative AI..."):
                analysis_result, source = ai_analyzer.analyze_incident(issue_text)

                # Persist in session state
                st.session_state["current_analysis"] = analysis_result
                st.session_state["analysis_source"] = source
                st.session_state["last_issue_text"] = issue_text

                # Save locally immediately
                inc_id = database.save_incident(
                    user_id=st.session_state.get("user_id"),
                    owner_email=st.session_state["user_email"],
                    issue_text=issue_text,
                    summary=analysis_result["summary"],
                    category=analysis_result["category"],
                    priority=analysis_result["priority"],
                    steps=analysis_result["steps"],
                    source=source,
                    servicenow_sync_status="not_sent",
                )
                st.session_state["current_local_id"] = inc_id

    # Render Current Analysis (persisted across Streamlit reruns)
    if st.session_state.get("current_analysis"):
        analysis = st.session_state["current_analysis"]
        source = st.session_state.get("analysis_source", "gemini")
        local_id = st.session_state.get("current_local_id")

        st.divider()

        # Small notice if fallback analyzer was invoked
        if source == "fallback":
            st.info("ℹ️ Notice: Gemini AI was unavailable or returned an error; analyzed using the rule-based fallback engine.")
        else:
            st.success("✨ Analyzed using Google Gemini AI.")

        # Header metrics
        m1, m2, m3 = st.columns(3)
        with m1:
            st.metric("Local Incident ID", f"#{local_id}")
        with m2:
            st.metric("Category", analysis["category"].capitalize())
        with m3:
            badge = PRIORITY_COLORS.get(analysis["priority"], analysis["priority"])
            st.metric("Assigned Priority", badge)

        st.markdown(f"### **Summary:** {analysis['summary']}")

        st.markdown("#### **Recommended Troubleshooting Steps:**")
        for i, step in enumerate(analysis["steps"], 1):
            st.markdown(f"**{i}.** {step}")

        st.divider()

        # ServiceNow Incident Creation Action
        st.subheader("ServiceNow Integration")
        create_sn = st.button("🚀 Create ServiceNow Incident", type="primary", use_container_width=True)

        if create_sn:
            with st.spinner("Submitting incident to ServiceNow Table API..."):
                work_notes = "\n".join([f"{i}. {s}" for i, s in enumerate(analysis["steps"], 1)])
                sn_resp = servicenow.create_incident(
                    short_description=analysis["summary"],
                    description=st.session_state.get("last_issue_text", ""),
                    priority=analysis["priority"],
                    category=analysis["category"],
                    work_notes=f"AI Troubleshooting Steps:\n{work_notes}",
                )

                if sn_resp.get("success"):
                    sn_num = sn_resp.get("number")
                    sys_id = sn_resp.get("sys_id")
                    link = sn_resp.get("link")

                    # Save in SQLite
                    database.update_servicenow_sync(local_id, sn_num, sys_id, "synced")
                    st.success(f"🎉 ServiceNow incident created successfully: **{sn_num}**")
                    if link:
                        st.markdown(f"[🔗 View Record in ServiceNow ({sn_num})]({link})")
                else:
                    err_msg = sn_resp.get("error", "Unknown error")
                    # Mark local incident as pending_sync for later retry
                    database.update_servicenow_sync(local_id, None, None, "pending_sync")
                    st.error(f"Failed to reach ServiceNow: {err_msg}")
                    st.warning("⚠️ Incident saved locally with status `pending_sync`. You can click 'Retry pending incidents' in the Pending Syncs tab once connectivity is restored.")


# ---------------------------------------------------------------------------
# Page: Incident History (with Refresh Status)
# ---------------------------------------------------------------------------
def render_history_page() -> None:
    st.subheader("📋 Incident History")
    st.markdown("Past incidents recorded locally and synchronized with ServiceNow.")

    incidents = database.get_user_incidents(st.session_state["user_email"])
    if not incidents:
        st.info("No past incidents found. Submit an IT issue on the Analysis page to get started.")
        return

    # Action bar: Refresh status for all ServiceNow incidents
    col_summary, col_action = st.columns([3, 1])
    with col_summary:
        st.caption(f"Showing {len(incidents)} total incidents for {st.session_state['user_email']}")
    with col_action:
        if st.button("🔄 Refresh status", use_container_width=True):
            refreshed_count = 0
            for inc in incidents:
                sn_num = inc.get("servicenow_number")
                if sn_num and sn_num != "Not Synced":
                    st_resp = servicenow.get_incident_status(sn_num)
                    if st_resp.get("success"):
                        st.session_state["sn_status_cache"][sn_num] = st_resp.get("state")
                        refreshed_count += 1
            if refreshed_count > 0:
                st.success(f"Updated status for {refreshed_count} ServiceNow incident(s)!")
            st.rerun()

    # Overview Table
    table_data = []
    for inc in incidents:
        sn_num = inc.get("servicenow_number") or "Not Synced"
        cached_state = st.session_state["sn_status_cache"].get(sn_num)
        table_data.append({
            "Local ID": f"#{inc['id']}",
            "Summary": inc["summary"],
            "Category": inc["category"].capitalize(),
            "Priority": inc["priority"],
            "Source": inc["source"],
            "ServiceNow INC": sn_num,
            "Sync Status": inc.get("servicenow_sync_status", "not_sent"),
            "Live State": cached_state or "-",
            "Created At": inc.get("created_at", "N/A"),
        })

    df = pd.DataFrame(table_data)
    st.dataframe(df, use_container_width=True, hide_index=True)

    st.markdown("---")
    st.subheader("Detailed Incident Records")

    for inc in incidents:
        sn_num = inc.get("servicenow_number") or "Not Synced"
        sync_status = inc.get("servicenow_sync_status", "not_sent")
        prio_badge = PRIORITY_COLORS.get(inc["priority"], inc["priority"])
        live_state = st.session_state["sn_status_cache"].get(sn_num)
        status_suffix = f" | ServiceNow: {sn_num} ({live_state or sync_status})" if sn_num != "Not Synced" else " | Local Only"

        with st.expander(f"Incident #{inc['id']} - {inc['category'].capitalize()} - {prio_badge}{status_suffix}"):
            c1, c2, c3, c4 = st.columns(4)
            c1.markdown(f"**Source Engine:** `{inc['source']}`")
            c2.markdown(f"**Created:** `{inc.get('created_at', 'N/A')}`")
            c3.markdown(f"**Sync Status:** `{sync_status}`")
            c4.markdown(f"**SN Incident:** `{sn_num}`")

            st.markdown(f"**Issue Description:**\n{inc['issue_text']}")
            st.markdown(f"**Summary:**\n{inc['summary']}")

            st.markdown("**Troubleshooting Steps:**")
            for idx, step in enumerate(inc.get("steps", []), 1):
                st.markdown(f"{idx}. {step}")

            # Individual Refresh Status action
            if sn_num and sn_num != "Not Synced":
                if st.button(f"🔍 Refresh status for {sn_num}", key=f"btn_refresh_{inc['id']}"):
                    with st.spinner(f"Querying ServiceNow for {sn_num}..."):
                        stat_resp = servicenow.get_incident_status(sn_num)
                        if stat_resp.get("success"):
                            st.session_state["sn_status_cache"][sn_num] = stat_resp.get("state")
                            st.success(f"State: **{stat_resp.get('state')}** | Priority: {stat_resp.get('priority')} | Last Updated: {stat_resp.get('updated')}")
                            if stat_resp.get("link"):
                                st.markdown(f"[🔗 Open in ServiceNow]({stat_resp.get('link')})")
                        else:
                            st.error(stat_resp.get("error"))


# ---------------------------------------------------------------------------
# Page: Pending Syncs (with Retry Pending Incidents)
# ---------------------------------------------------------------------------
def render_pending_page() -> None:
    st.subheader("🔄 Pending ServiceNow Synchronizations")
    st.markdown("Incidents saved locally while ServiceNow was unreachable, timed out, or returned errors.")

    pending_list = database.get_pending_sync_incidents(st.session_state["user_email"])

    if not pending_list:
        st.success("✨ All incidents are synchronized! No pending items in queue.")
        return

    st.warning(f"You have **{len(pending_list)} incident(s)** pending synchronization.")

    # "Retry pending incidents" button
    if st.button("🚀 Retry pending incidents", type="primary", use_container_width=True):
        success_count = 0
        with st.spinner("Retrying pending incident submissions to ServiceNow..."):
            for inc in pending_list:
                steps_text = "\n".join([f"{i}. {s}" for i, s in enumerate(inc.get("steps", []), 1)])
                resp = servicenow.create_incident(
                    short_description=inc["summary"],
                    description=inc["issue_text"],
                    priority=inc["priority"],
                    category=inc["category"],
                    work_notes=f"Synced via Retry Pending Incidents queue:\n{steps_text}",
                )
                if resp.get("success"):
                    database.update_servicenow_sync(
                        inc["id"],
                        resp.get("number"),
                        resp.get("sys_id"),
                        "synced"
                    )
                    success_count += 1
                else:
                    st.error(f"Failed to sync Incident #{inc['id']}: {resp.get('error')}")

        if success_count > 0:
            st.success(f"Successfully synced {success_count} pending incident(s) to ServiceNow!")
            st.rerun()

    st.markdown("---")
    st.subheader("Pending Incidents Queue")
    for inc in pending_list:
        with st.container(border=True):
            st.markdown(f"**Local Incident #{inc['id']}** | Category: `{inc['category']}` | Priority: `{inc['priority']}`")
            st.markdown(f"**Summary:** {inc['summary']}")
            st.caption(f"Created: {inc.get('created_at', 'N/A')} | Status: {inc.get('servicenow_sync_status')}")


# ---------------------------------------------------------------------------
# Application Entry Point
# ---------------------------------------------------------------------------
def main() -> None:
    if not st.session_state["logged_in"]:
        render_auth_page()
    else:
        page = render_sidebar()
        if page == "🔍 Incident Analysis":
            render_analysis_page()
        elif page == "📋 Incident History":
            render_history_page()
        elif page == "🔄 Pending Syncs":
            render_pending_page()


if __name__ == "__main__":
    main()
