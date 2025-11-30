# Aegis Dashboard UX Design Document

## 1. Overview
The Aegis Dashboard is the central command center for users managing multiple projects with the Aegis swarm. It provides a comprehensive view of the system's health, active tasks, and agent activities, while offering control over agent execution and configuration.

## 2. Target Audience
- **Primary User:** A developer or project manager running Aegis on multiple projects simultaneously.
- **Key Needs:**
    - High-level observability of all projects.
    - Granular visibility into specific projects and agents.
    - Ability to intervene (start/stop agents, edit configs).
    - Debugging tools (logs, event history).

## 3. Core Features & Functionality

### 3.1. Multi-Project Overview (Home)
**Goal:** Provide an "at-a-glance" status of the entire swarm.

**UI Components:**
- **Global Status Bar:**
    - Total Active Agents
    - Total Projects Tracked
    - System Health (CPU/Memory usage of swarm - optional)
- **Project Cards (Grid View):**
    - Each card represents a tracked project.
    - **Visuals:** Project Name, Status Indicator (Running/Stopped/Error), Active Task Count, Last Activity Timestamp.
    - **Actions:** Quick "Start/Stop" toggle for the project's swarm.
- **Recent Global Activity Feed:** A consolidated list of the most recent events across all projects (e.g., "Agent X completed Task Y in Project Z").

### 3.2. Project Detail View
**Goal:** Deep dive into a specific project.

**UI Components:**
- **Header:** Project Name, Path, Status, Start/Stop Controls.
- **Task Board / Status:**
    - Visualization of tasks by section (e.g., Bar chart or Kanban-like summary).
    - List of currently active tasks with assigned agents and duration.
- **Event Timeline:**
    - A chronological feed of events specific to this project (Task transitions, Agent comments, Errors).
- **Configuration:**
    - Edit project-specific settings (e.g., Asana GIDs, local paths).

### 3.3. Agent Management & Active Tasks
**Goal:** Monitor and control individual agents.

**UI Components:**
- **Active Agents Table:**
    - Columns: Agent Name, Project, Task Name (with link to Asana), Status (Thinking/Acting/Waiting), Duration, Cost (est).
    - **Actions:** "Stop Agent" button (kill specific agent process).
- **Agent Registry:**
    - List of all available agent types (Triage, Worker, Reviewer, etc.).
    - View/Edit default configuration for each agent type (e.g., model selection, temperature).

### 3.4. Session Logs & Debugging
**Goal:** Investigate agent behavior and errors.

**UI Components:**
- **Session Explorer:**
    - Searchable list of sessions (by Task ID, Agent Name, Date).
    - Filter by "Error" or "Success".
- **Log Viewer:**
    - Streaming log view for active sessions.
    - Syntax highlighting for code blocks and JSON.
    - "Copy to Clipboard" for sharing/analysis.

### 3.5. Configuration & Settings
**Goal:** Manage system-wide and project-specific preferences.

**UI Components:**
- **Global Settings:**
    - Environment Variables editor (`.env`).
    - API Key management.
- **Prompt Editor:**
    - Interface to view and edit system prompts (`prompts/*.txt`).
    - Version history (if possible, or just simple save).

## 4. Technical Architecture & Implementation

### 4.1. Frontend
- **Framework:** Streamlit (existing).
- **Enhancements:**
    - Use `st.data_editor` for configuration editing.
    - Use `st.rerun` and `st.empty` for real-time updates (or polling).
    - Custom components for better visual hierarchy (Project Cards).

### 4.2. Backend / Data Layer
- **State Management:**
    - Continue using `.aegis/swarm_state.json` for persistence.
    - **New:** Need a more robust way to signal "Start/Stop" commands.
        - *Proposal:* Use a command queue file or a lightweight local server (FastAPI) if Streamlit's direct file manipulation is insufficient for process control.
        - *Simpler MVP:* Write "command files" (e.g., `.aegis/commands/stop_agent.cmd`) that the orchestrator watches for.
- **Event Logging:**
    - Structured logging (JSON lines) is essential for the "Event Timeline".
    - Ensure all agents emit standardized events: `AgentStarted`, `AgentFinished`, `TaskMoved`, `ErrorOccurred`.

### 4.3. Process Control
- **Starting/Stopping:**
    - The Dashboard needs to interact with the `SwarmDispatcher` or individual project orchestrators.
    - *Mechanism:* The dashboard can use `subprocess` to call `aegis start/stop` CLI commands, or write to a control file that the background daemon monitors.

## 5. User Journey Example

1.  **Monitoring:** User opens Dashboard, sees "Project Alpha" has 5 active agents and "Project Beta" is stopped.
2.  **Investigation:** User clicks "Project Alpha". Sees a spike in "Reviewer" agents. Checks "Event Timeline" and sees multiple "Code Review Requested" events.
3.  **Intervention:** User notices one agent is stuck (running for > 1 hour). Goes to "Active Tasks", finds the stuck agent, and clicks "Stop".
4.  **Configuration:** User decides to change the model for the "Reviewer" agent to a cheaper one. Goes to "Settings" -> "Agent Config", updates the model, and saves.
5.  **Restart:** User goes back to "Project Beta" card and clicks "Start" to resume work there.

## 6. Future Considerations
- **Historical Analytics:** Charts showing tasks completed over time, total cost per project.
- **Agent Sandbox:** A playground to test agent prompts against mock tasks.
- **Notifications:** System notifications for critical errors or completed milestones.
