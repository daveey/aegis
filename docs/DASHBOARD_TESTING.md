# Testing the Aegis Dashboard with Antigravity (LLM)

This guide provides instructions for Antigravity (the LLM) to test and verify the Aegis Dashboard.

## Prerequisites

- The Aegis environment must be set up (dependencies installed).
- You must have the `browser_subagent` tool available.

## Step-by-Step Testing Procedure

### 1. Start the Dashboard

First, start the dashboard in the background using the CLI. Use a specific port to avoid conflicts.

```bash
aegis dashboard start --port 8501
```

**Note:** If the dashboard is already running, you may need to stop it first with `aegis dashboard stop` or use the existing instance if you know the port.

### 2. Verify Dashboard Accessibility

Use the `browser_subagent` to navigate to the dashboard URL.

**Task for Browser Subagent:**
"Navigate to http://localhost:8501 and verify that the page loads. Check for the title 'Aegis Dashboard' and the sidebar."

### 3. Verify System Status

Instruct the browser subagent to check the "System Status" section in the sidebar.

**Task for Browser Subagent:**
"Check the sidebar for the 'System Status' section. Verify if it says 'Orchestrator Running' or shows the last poll time."

### 4. Verify Active Tasks

Navigate to the "Active Tasks" page using the sidebar radio button.

**Task for Browser Subagent:**
"Click on 'Active Tasks' in the sidebar navigation. Verify that the 'Active Tasks' title is displayed in the main area. Check if there are any active tasks listed or if it says 'No active tasks'."

### 5. Verify Settings (Optional)

Navigate to the "Settings" page.

**Task for Browser Subagent:**
"Click on 'Settings' in the sidebar. Verify that the tabs 'Configuration' and 'Prompts' are visible."

### 6. Stop the Dashboard

After testing is complete, stop the dashboard to clean up resources.

```bash
aegis dashboard stop
```

## Troubleshooting

- **Connection Refused:** Ensure the dashboard started successfully and is running on the expected port (default 8501). Check `logs/aegis.log` or `.aegis/dashboard.log` for errors.
- **Streamlit not found:** Run `uv sync` to ensure all dependencies are installed.
