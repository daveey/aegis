import sys
from pathlib import Path

# Add src to path to ensure we use local modules
root_path = Path(__file__).parent.parent.parent.parent
sys.path.append(str(root_path / "src"))

import streamlit as st
import time
import pandas as pd
import json
import utils

st.set_page_config(
    page_title="Aegis Dashboard",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# --- Sidebar ---
st.sidebar.title("🛡️ Aegis Swarm")

# System Status
project_states = utils.get_all_project_states()

# Project Selector
project_names = ["Global"] + [p["name"] for p in project_states]
selected_project_name = st.sidebar.selectbox("Project", project_names)

# Filter states based on selection
if selected_project_name != "Global":
    filtered_states = [p for p in project_states if p["name"] == selected_project_name]
    current_project_state = filtered_states[0] if filtered_states else None
else:
    filtered_states = project_states
    current_project_state = None

st.sidebar.header("System Status")

if not project_states:
    st.sidebar.warning("No tracked projects found.")
else:
    for p in project_states:
        status_color = "green" if p["is_running"] else "red"
        status_text = "Running" if p["is_running"] else "Stopped"
        st.sidebar.markdown(f":{status_color}[●] **{p['name']}**: {status_text}")

# Navigation
if "nav_radio" not in st.session_state:
    st.session_state.nav_radio = "Overview"
page = st.sidebar.radio("Navigation", ["Overview", "Active Tasks", "Session Logs", "Memory", "Settings"], key="nav_radio")

# --- Main Content ---

if page == "Overview":
    if selected_project_name == "Global":
        st.title("Swarm Overview")

        # Global Metrics
        total_projects = len(project_states)
        total_active_agents = 0
        running_projects = 0

        for p in project_states:
            if p["is_running"]:
                running_projects += 1
            orch = p["state"].get("orchestrator", {})
            total_active_agents += len(orch.get("active_tasks_details", []))

        m1, m2, m3 = st.columns(3)
        m1.metric("Total Projects", total_projects)
        m2.metric("Running Projects", running_projects)
        m3.metric("Total Active Agents", total_active_agents)

        st.divider()

        # Project Cards
        st.subheader("Projects")
        if not project_states:
            st.info("No projects tracked.")
        else:
            cols = st.columns(3)
            for idx, p in enumerate(project_states):
                with cols[idx % 3]:
                    with st.container(border=True):
                        st.markdown(f"### {p['name']}")

                        is_running = p["is_running"]
                        status_color = "green" if is_running else "red"
                        status_text = "Running" if is_running else "Stopped"
                        st.markdown(f"**Status**: :{status_color}[{status_text}]")

                        orch = p["state"].get("orchestrator", {})
                        active_count = len(orch.get("active_tasks_details", []))
                        st.markdown(f"**Active Agents**: {active_count}")

                        last_activity = "Unknown" # Placeholder, could get from events
                        # st.caption(f"Last Activity: {last_activity}")

                        if st.button(f"Manage {p['name']}", key=f"btn_{p['gid']}"):
                            # In a real app we might redirect, but for now just a toast
                            st.toast(f"Switch to {p['name']} in sidebar to manage.")

                        # Syncer Log Link
                        syncer_info = utils.get_syncer_info(p["path"])
                        if syncer_info:
                            sid = syncer_info.get("session_id")
                            if sid:
                                if st.button(f"View Syncer Log", key=f"btn_log_{p['gid']}"):
                                    st.session_state.nav_radio = "Session Logs"
                                    st.session_state.target_session_id = sid
                                    st.rerun()

        st.divider()

        # Global Activity Feed
        st.subheader("Recent Activity (All Projects)")
        global_events = utils.get_global_activity_feed(limit=10)
        if global_events:
            for evt in global_events:
                timestamp = evt.get("timestamp", "")
                project = evt.get("project_name", "Unknown")
                evt_type = evt.get("type", "Event")
                st.text(f"[{timestamp}] [{project}] {evt_type}")
        else:
            st.info("No recent activity.")

    else:
        # Project Detail View
        if not current_project_state:
            st.error("Project state not found.")
        else:
            p = current_project_state
            st.title(f"{p['name']}")
            st.caption(f"Path: {p['path']}")

            # Top metrics row
            m1, m2, m3, m4 = st.columns(4)

            # Status
            is_running = p["is_running"]
            status_color = "green" if is_running else "red"
            status_text = "Running" if is_running else "Stopped"
            m1.markdown(f"**Status**: :{status_color}[{status_text}]")

            orch = p["state"].get("orchestrator", {})
            active_tasks = orch.get("active_tasks_details", [])

            # Active Agents Count
            m2.metric("Active Agents", len(active_tasks))

            # Errors Count
            errors = orch.get("recent_errors", [])
            m3.metric("Recent Errors", len(errors))

            # Events Count
            events = orch.get("recent_events", [])
            m4.metric("Recent Events", len(events))

            st.divider()

            # Detailed Views
            c1, c2 = st.columns([1, 1])

            with c1:
                st.markdown("#### Task Distribution")
                counts = orch.get("section_counts", {})
                if counts:
                    df_counts = pd.DataFrame([
                        {"Section": k, "Count": v} for k, v in counts.items()
                    ])
                    st.bar_chart(df_counts.set_index("Section"))
                else:
                    st.info("No tasks found.")

            with c2:
                st.markdown("#### Active Agents")
                if active_tasks:
                    df_active = pd.DataFrame(active_tasks)
                    # Handle case where keys might be missing or different
                    cols = [c for c in ["name", "agent", "section"] if c in df_active.columns]
                    if not cols and not df_active.empty:
                            cols = df_active.columns.tolist()

                    if cols:
                        st.dataframe(df_active[cols], use_container_width=True, hide_index=True)
                    else:
                        st.dataframe(df_active, use_container_width=True, hide_index=True)
                else:
                    st.info("No agents running.")

            # Errors and Events Expanders
            with st.expander("Recent Errors", expanded=bool(errors)):
                if errors:
                    for err in reversed(errors):
                        st.error(f"[{err['timestamp']}] {err['error']}")
                        if "details" in err and err["details"]:
                            st.code(json.dumps(err["details"], indent=2))
                else:
                    st.success("No recent errors.")

            with st.expander("Recent Events", expanded=True):
                if events:
                    for evt in reversed(events):
                        st.text(f"[{evt['timestamp']}] {evt['type']}")
                        if "details" in evt and evt["details"]:
                            st.caption(json.dumps(evt["details"]))
                else:
                    st.info("No recent events.")

elif page == "Active Tasks":
    st.title(f"Active Tasks - {selected_project_name}")

    active_tasks = utils.get_active_tasks()

    # Filter if not global
    if selected_project_name != "Global":
        active_tasks = [t for t in active_tasks if t.get("project_name") == selected_project_name]

    if not active_tasks:
        st.info("No active tasks.")
    else:
        for task in active_tasks:
            task_gid = task.get("gid", "Unknown")
            task_name = task.get("name", "Unknown Task")
            project_name = task.get("project_name", "Unknown Project")
            agent = task.get("agent", "Unknown Agent")

            with st.expander(f"[{project_name}] {task_name} ({agent})", expanded=True):
                st.write(f"**Task GID:** {task_gid}")
                st.write(f"**Project:** {project_name}")
                st.write(f"**Agent:** {agent}")
                st.write(f"**Section:** {task.get('section', 'Unknown')}")
                st.write(f"**Started At:** {task.get('started_at', 'Unknown')}")

                # Placeholder for task logs
                # st.info("Task details would appear here.")

elif page == "Session Logs":
    st.title(f"Session Log Viewer - {selected_project_name}")

    # Determine project path
    project_path = None
    if selected_project_name != "Global" and current_project_state:
         project_path = current_project_state["path"]

    # Allow user to input session ID or pick from list if we can list them

    # Check session state for target session ID (from Overview button)
    target_sid = st.session_state.get("target_session_id")
    if target_sid:
        # Clear it so it doesn't persist if user navigates away and back
        del st.session_state.target_session_id
        default_val = target_sid
    else:
        default_val = st.query_params.get("session_id", "")

    search_id = st.text_input("Enter Session ID", value=default_val)

    if search_id:
        st.subheader(f"Log for Session: {search_id}")
        log_content = utils.get_session_log(search_id, project_path=project_path)
        st.code(log_content, language="text")

elif page == "Memory":
    st.title(f"Swarm Memory - {selected_project_name}")

    # Determine project path
    project_path = None
    if selected_project_name != "Global" and current_project_state:
         project_path = current_project_state["path"]

    memory_content = utils.load_swarm_memory(project_path=project_path)
    st.markdown(memory_content)

elif page == "Settings":
    st.title("Settings")

    tab1, tab2 = st.tabs(["Configuration", "Prompts"])

    with tab1:
        st.header("Environment Variables (.env)")
        env_content = utils.read_env_file()

        with st.form("env_form"):
            new_env_content = st.text_area("Content", value=env_content, height=400)
            submitted = st.form_submit_button("Save .env")

            if submitted:
                if utils.write_env_file(new_env_content):
                    st.success("Successfully saved .env file!")
                else:
                    st.error("Failed to save .env file.")

    with tab2:
        st.header("System Prompts")

        prompt_files = utils.list_prompt_files()

        if not prompt_files:
            st.warning("No prompt files found in prompts/ directory.")
        else:
            selected_prompt = st.selectbox("Select Prompt File", prompt_files)

            if selected_prompt:
                prompt_content = utils.read_prompt_file(selected_prompt)

                with st.form("prompt_form"):
                    new_prompt_content = st.text_area("Content", value=prompt_content, height=600)
                    submitted = st.form_submit_button(f"Save {selected_prompt}")

                    if submitted:
                        if utils.write_prompt_file(selected_prompt, new_prompt_content):
                            st.success(f"Successfully saved {selected_prompt}!")
                        else:
                            st.error(f"Failed to save {selected_prompt}.")

# Footer
st.sidebar.markdown("---")
st.sidebar.caption(f"Aegis Dashboard v0.2.0")

# Auto-refresh
if st.sidebar.checkbox("Auto-refresh", value=True):
    time.sleep(5)
    st.rerun()
