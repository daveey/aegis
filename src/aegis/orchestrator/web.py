"""Web interface for Aegis orchestrator.

Provides a real-time dashboard showing:
- Orchestrator status
- Active agents and their tasks
- Task logs
- System statistics
"""

import asyncio
import os
from datetime import datetime
from pathlib import Path
from typing import Any

import structlog
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse

logger = structlog.get_logger(__name__)


class OrchestratorWebServer:
    """Web server for orchestrator dashboard."""

    def __init__(self, orchestrator: Any, host: str = "127.0.0.1", port: int = 8000):
        """Initialize web server.

        Args:
            orchestrator: Orchestrator instance to monitor
            host: Host to bind to
            port: Port to bind to
        """
        self.orchestrator = orchestrator
        self.host = host
        self.port = port
        self.app = FastAPI(title="Aegis Orchestrator Dashboard")
        self.active_websockets: list[WebSocket] = []

        # Setup routes
        self._setup_routes()

    def _setup_routes(self):
        """Setup FastAPI routes."""

        @self.app.get("/", response_class=HTMLResponse)
        async def dashboard():
            """Serve the main dashboard."""
            return self._get_dashboard_html()

        @self.app.get("/api/status")
        async def get_status():
            """Get current orchestrator status."""
            return self._get_status_data()

        @self.app.get("/api/agents")
        async def get_agents():
            """Get list of active agents."""
            return self._get_agents_data()

        @self.app.get("/api/queued")
        async def get_queued_tasks():
            """Get list of queued tasks."""
            return await self._get_queued_tasks_data()

        @self.app.post("/api/execute/{task_gid}")
        async def execute_task(task_gid: str):
            """Manually trigger execution of a task."""
            return await self._execute_task(task_gid)

        @self.app.get("/api/logs/{task_gid}")
        async def get_task_log(task_gid: str):
            """Get log content for a specific task."""
            return self._get_task_log(task_gid)

        @self.app.websocket("/ws")
        async def websocket_endpoint(websocket: WebSocket):
            """WebSocket endpoint for real-time updates."""
            await websocket.accept()
            self.active_websockets.append(websocket)
            try:
                while True:
                    # Keep connection alive and send updates
                    await asyncio.sleep(1)
                    await websocket.send_json(self._get_status_data())
            except WebSocketDisconnect:
                self.active_websockets.remove(websocket)

    def _get_status_data(self) -> dict:
        """Get current status data."""
        display = self.orchestrator.display if self.orchestrator.display else None

        return {
            "timestamp": datetime.now().isoformat(),
            "orchestrator": {
                "status": self.orchestrator.shutdown_handler.shutdown_requested if self.orchestrator.shutdown_handler else False,
                "pid": os.getpid(),
                "project_name": self.orchestrator.project_name,
                "project_gid": self.orchestrator.project_gid,
                "auto_dispatch": self.orchestrator.auto_dispatch,
            },
            "stats": display.stats if display else {
                "total_dispatched": 0,
                "completed": 0,
                "failed": 0,
                "launched": 0,
            },
            "settings": {
                "poll_interval": self.orchestrator.settings.poll_interval_seconds,
                "max_concurrent": self.orchestrator.settings.max_concurrent_tasks,
                "execution_mode": self.orchestrator.settings.execution_mode,
            },
        }

    def _get_agents_data(self) -> dict:
        """Get active agents data."""
        display = self.orchestrator.display if self.orchestrator.display else None
        active_tasks = display.active_tasks if display else {}

        agents = []
        for task_gid, task_info in active_tasks.items():
            # Calculate duration
            started_at = task_info.get("started_at")
            duration_seconds = (datetime.now() - started_at).total_seconds() if started_at else 0

            agents.append({
                "task_gid": task_gid,
                "task_name": task_info.get("name", "Unknown"),
                "status": task_info.get("status", "unknown"),
                "log_file": task_info.get("log_file"),
                "started_at": started_at.isoformat() if started_at else None,
                "duration_seconds": int(duration_seconds),
            })

        return {"agents": agents}

    def _get_task_log(self, task_gid: str) -> dict:
        """Get log content for a specific task."""
        display = self.orchestrator.display if self.orchestrator.display else None
        active_tasks = display.active_tasks if display else {}

        if task_gid not in active_tasks:
            return {"error": "Task not found"}

        log_file = active_tasks[task_gid].get("log_file")
        if not log_file or not Path(log_file).exists():
            return {"error": "Log file not found"}

        try:
            # Read last 1000 lines of log
            with open(log_file) as f:
                lines = f.readlines()
                content = "".join(lines[-1000:])
            return {"log": content}
        except Exception as e:
            return {"error": f"Failed to read log: {str(e)}"}

    async def _get_queued_tasks_data(self) -> dict:
        """Get queued tasks data."""
        try:
            queued_tasks_with_scores = await self.orchestrator.get_queued_tasks()

            tasks = []
            for task, score in queued_tasks_with_scores:
                tasks.append({
                    "task_gid": task.gid,
                    "task_name": task.name,
                    "priority_score": round(score.total_score, 2),
                    "due_date": task.due_on.isoformat() if task.due_on else None,
                    "created_at": task.created_at.isoformat() if task.created_at else None,
                    "notes": task.notes[:200] + "..." if task.notes and len(task.notes) > 200 else task.notes,
                })

            return {"tasks": tasks}
        except Exception as e:
            logger.error("failed_to_get_queued_tasks", error=str(e), exc_info=True)
            return {"tasks": [], "error": str(e)}

    async def _execute_task(self, task_gid: str) -> dict:
        """Execute a specific task."""
        try:
            result = await self.orchestrator.manual_execute_task(task_gid)
            return result
        except Exception as e:
            logger.error("failed_to_execute_task", task_gid=task_gid, error=str(e), exc_info=True)
            return {
                "success": False,
                "message": f"Failed to execute task: {str(e)}",
                "error": str(e)
            }

    def _get_dashboard_html(self) -> str:
        """Generate dashboard HTML."""
        return """
<!DOCTYPE html>
<html>
<head>
    <title>Aegis Orchestrator Dashboard</title>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            background: #0d1117;
            color: #c9d1d9;
            padding: 20px;
        }

        .container {
            max-width: 1400px;
            margin: 0 auto;
        }

        header {
            margin-bottom: 30px;
            padding-bottom: 20px;
            border-bottom: 1px solid #30363d;
        }

        h1 {
            font-size: 32px;
            color: #58a6ff;
            margin-bottom: 10px;
        }

        .status-badge {
            display: inline-block;
            padding: 4px 12px;
            border-radius: 12px;
            font-size: 12px;
            font-weight: 600;
            text-transform: uppercase;
        }

        .status-running {
            background: #1f6feb;
            color: #ffffff;
        }

        .status-stopped {
            background: #da3633;
            color: #ffffff;
        }

        .grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }

        .card {
            background: #161b22;
            border: 1px solid #30363d;
            border-radius: 6px;
            padding: 20px;
        }

        .card-title {
            font-size: 14px;
            color: #8b949e;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            margin-bottom: 10px;
        }

        .card-value {
            font-size: 36px;
            font-weight: 700;
            color: #58a6ff;
        }

        .card-label {
            font-size: 14px;
            color: #8b949e;
            margin-top: 5px;
        }

        .agents-section {
            margin-top: 30px;
        }

        .section-title {
            font-size: 20px;
            font-weight: 600;
            margin-bottom: 15px;
            color: #c9d1d9;
        }

        .agent-card {
            background: #161b22;
            border: 1px solid #30363d;
            border-radius: 6px;
            padding: 20px;
            margin-bottom: 15px;
        }

        .agent-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 15px;
        }

        .agent-name {
            font-size: 16px;
            font-weight: 600;
            color: #c9d1d9;
        }

        .agent-status {
            display: inline-block;
            padding: 4px 10px;
            border-radius: 12px;
            font-size: 11px;
            font-weight: 600;
            text-transform: uppercase;
        }

        .status-dispatched {
            background: #ffc107;
            color: #000;
        }

        .status-in_progress {
            background: #58a6ff;
            color: #ffffff;
        }

        .status-running {
            background: #2ea043;
            color: #ffffff;
        }

        .agent-details {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 15px;
            margin-bottom: 15px;
            font-size: 13px;
        }

        .agent-detail {
            color: #8b949e;
        }

        .agent-detail strong {
            color: #c9d1d9;
        }

        .log-preview {
            background: #0d1117;
            border: 1px solid #30363d;
            border-radius: 4px;
            padding: 15px;
            font-family: "SF Mono", Monaco, Consolas, monospace;
            font-size: 12px;
            line-height: 1.6;
            max-height: 200px;
            overflow-y: auto;
            white-space: pre-wrap;
            word-wrap: break-word;
            cursor: pointer;
            transition: border-color 0.2s;
        }

        .log-preview:hover {
            border-color: #58a6ff;
        }

        .log-preview-hint {
            text-align: center;
            color: #8b949e;
            font-size: 11px;
            margin-top: 8px;
        }

        /* Modal styles */
        .modal {
            display: none;
            position: fixed;
            z-index: 1000;
            left: 0;
            top: 0;
            width: 100%;
            height: 100%;
            background-color: rgba(0, 0, 0, 0.8);
        }

        .modal.active {
            display: flex;
            align-items: center;
            justify-content: center;
        }

        .modal-content {
            background: #161b22;
            border: 1px solid #30363d;
            border-radius: 6px;
            width: 90%;
            max-width: 1200px;
            max-height: 90%;
            display: flex;
            flex-direction: column;
        }

        .modal-header {
            padding: 20px;
            border-bottom: 1px solid #30363d;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }

        .modal-title {
            font-size: 18px;
            font-weight: 600;
            color: #c9d1d9;
        }

        .modal-close {
            background: transparent;
            border: none;
            color: #8b949e;
            font-size: 24px;
            cursor: pointer;
            padding: 0;
            width: 32px;
            height: 32px;
            display: flex;
            align-items: center;
            justify-content: center;
            border-radius: 4px;
        }

        .modal-close:hover {
            background: #30363d;
            color: #c9d1d9;
        }

        .modal-body {
            padding: 20px;
            overflow-y: auto;
            flex: 1;
        }

        .modal-log {
            background: #0d1117;
            border: 1px solid #30363d;
            border-radius: 4px;
            padding: 15px;
            font-family: "SF Mono", Monaco, Consolas, monospace;
            font-size: 12px;
            line-height: 1.6;
            white-space: pre-wrap;
            word-wrap: break-word;
            color: #c9d1d9;
        }

        .empty-state {
            text-align: center;
            padding: 60px 20px;
            color: #8b949e;
        }

        .empty-state-icon {
            font-size: 48px;
            margin-bottom: 15px;
        }

        .refresh-indicator {
            position: fixed;
            top: 20px;
            right: 20px;
            padding: 8px 16px;
            background: #1f6feb;
            color: #ffffff;
            border-radius: 6px;
            font-size: 12px;
            opacity: 0;
            transition: opacity 0.3s;
        }

        .refresh-indicator.active {
            opacity: 1;
        }

        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.5; }
        }

        .pulse {
            animation: pulse 2s infinite;
        }

        .run-button {
            background: #2ea043;
            color: #ffffff;
            border: none;
            padding: 8px 16px;
            border-radius: 6px;
            font-size: 14px;
            font-weight: 600;
            cursor: pointer;
            transition: background 0.2s;
        }

        .run-button:hover {
            background: #2c974b;
        }

        .run-button:disabled {
            background: #30363d;
            color: #8b949e;
            cursor: not-allowed;
        }

        .task-card {
            background: #161b22;
            border: 1px solid #30363d;
            border-radius: 6px;
            padding: 20px;
            margin-bottom: 15px;
        }

        .task-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 15px;
        }

        .task-name {
            font-size: 16px;
            font-weight: 600;
            color: #c9d1d9;
            flex: 1;
        }

        .task-details {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 15px;
            margin-bottom: 15px;
            font-size: 13px;
        }

        .task-detail {
            color: #8b949e;
        }

        .task-detail strong {
            color: #c9d1d9;
        }

        .task-notes {
            background: #0d1117;
            border: 1px solid #30363d;
            border-radius: 4px;
            padding: 10px;
            font-size: 12px;
            color: #8b949e;
            margin-bottom: 15px;
            max-height: 100px;
            overflow-y: auto;
        }

        .priority-badge {
            display: inline-block;
            padding: 4px 10px;
            border-radius: 12px;
            font-size: 11px;
            font-weight: 600;
            margin-left: 10px;
        }

        .priority-high {
            background: #da3633;
            color: #ffffff;
        }

        .priority-medium {
            background: #ffc107;
            color: #000;
        }

        .priority-low {
            background: #1f6feb;
            color: #ffffff;
        }
    </style>
</head>
<body>
    <div class="refresh-indicator" id="refreshIndicator">Updated</div>

    <div class="container">
        <header>
            <h1>🛡️ Aegis Orchestrator</h1>
            <div id="headerInfo"></div>
        </header>

        <div class="grid" id="statsGrid"></div>

        <div class="agents-section">
            <h2 class="section-title">Queued Tasks</h2>
            <div id="queuedTasksList"></div>
        </div>

        <div class="agents-section">
            <h2 class="section-title">Active Agents</h2>
            <div id="agentsList"></div>
        </div>
    </div>

    <!-- Log Modal -->
    <div class="modal" id="logModal">
        <div class="modal-content">
            <div class="modal-header">
                <div class="modal-title" id="modalTitle">Full Log</div>
                <button class="modal-close" onclick="closeLogModal()">&times;</button>
            </div>
            <div class="modal-body">
                <div class="modal-log" id="modalLog">Loading...</div>
            </div>
        </div>
    </div>

    <script>
        let ws;
        let reconnectTimeout;

        function connectWebSocket() {
            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            ws = new WebSocket(`${protocol}//${window.location.host}/ws`);

            ws.onopen = () => {
                console.log('WebSocket connected');
                clearTimeout(reconnectTimeout);
                fetchStatus();
                fetchAgents();
            };

            ws.onmessage = (event) => {
                const data = JSON.parse(event.data);
                updateDashboard(data);
                showRefreshIndicator();
            };

            ws.onclose = () => {
                console.log('WebSocket disconnected, reconnecting...');
                reconnectTimeout = setTimeout(connectWebSocket, 3000);
            };

            ws.onerror = (error) => {
                console.error('WebSocket error:', error);
            };
        }

        async function fetchStatus() {
            try {
                const response = await fetch('/api/status');
                const data = await response.json();
                updateDashboard(data);
            } catch (error) {
                console.error('Failed to fetch status:', error);
            }
        }

        async function fetchAgents() {
            try {
                const response = await fetch('/api/agents');
                const data = await response.json();
                updateAgents(data);
            } catch (error) {
                console.error('Failed to fetch agents:', error);
            }
        }

        async function fetchQueuedTasks() {
            try {
                const response = await fetch('/api/queued');
                const data = await response.json();
                updateQueuedTasks(data);
            } catch (error) {
                console.error('Failed to fetch queued tasks:', error);
            }
        }

        async function executeTask(taskGid) {
            try {
                const button = document.getElementById(`run-btn-${taskGid}`);
                if (button) {
                    button.disabled = true;
                    button.textContent = 'Starting...';
                }

                const response = await fetch(`/api/execute/${taskGid}`, {
                    method: 'POST'
                });
                const data = await response.json();

                if (data.success) {
                    showRefreshIndicator();
                    // Refresh both queued tasks and agents
                    await fetchQueuedTasks();
                    await fetchAgents();
                } else {
                    alert(`Failed to execute task: ${data.message}`);
                    if (button) {
                        button.disabled = false;
                        button.textContent = 'Run';
                    }
                }
            } catch (error) {
                console.error('Failed to execute task:', error);
                alert(`Error executing task: ${error.message}`);
            }
        }

        function updateDashboard(data) {
            // Update header
            const headerInfo = document.getElementById('headerInfo');
            const status = data.orchestrator.status ? 'stopped' : 'running';
            headerInfo.innerHTML = `
                <span class="status-badge status-${status}">${status}</span>
                <span style="margin-left: 15px; color: #8b949e;">
                    Project: <strong style="color: #c9d1d9;">${data.orchestrator.project_name}</strong>
                    (PID: ${data.orchestrator.pid})
                </span>
            `;

            // Update stats
            const statsGrid = document.getElementById('statsGrid');
            statsGrid.innerHTML = `
                <div class="card">
                    <div class="card-title">Dispatched</div>
                    <div class="card-value">${data.stats.total_dispatched}</div>
                    <div class="card-label">Total tasks</div>
                </div>
                <div class="card">
                    <div class="card-title">Completed</div>
                    <div class="card-value" style="color: #2ea043;">${data.stats.completed}</div>
                    <div class="card-label">Successfully finished</div>
                </div>
                <div class="card">
                    <div class="card-title">Failed</div>
                    <div class="card-value" style="color: #da3633;">${data.stats.failed}</div>
                    <div class="card-label">Errors encountered</div>
                </div>
                <div class="card">
                    <div class="card-title">Poll Interval</div>
                    <div class="card-value" style="font-size: 28px;">${data.settings.poll_interval}s</div>
                    <div class="card-label">Max concurrent: ${data.settings.max_concurrent}</div>
                </div>
            `;
        }

        function updateQueuedTasks(data) {
            const queuedTasksList = document.getElementById('queuedTasksList');

            if (!data.tasks || data.tasks.length === 0) {
                queuedTasksList.innerHTML = `
                    <div class="empty-state">
                        <div class="empty-state-icon">📋</div>
                        <div>No queued tasks</div>
                    </div>
                `;
                return;
            }

            queuedTasksList.innerHTML = data.tasks.map(task => {
                const priorityClass = task.priority_score > 50 ? 'priority-high' :
                                     task.priority_score > 20 ? 'priority-medium' :
                                     'priority-low';
                const priorityLabel = task.priority_score > 50 ? 'High' :
                                     task.priority_score > 20 ? 'Medium' :
                                     'Low';

                return `
                    <div class="task-card">
                        <div class="task-header">
                            <div class="task-name">
                                ${escapeHtml(task.task_name)}
                                <span class="priority-badge ${priorityClass}">
                                    Priority: ${priorityLabel} (${task.priority_score})
                                </span>
                            </div>
                            <button class="run-button" id="run-btn-${task.task_gid}" onclick="executeTask('${task.task_gid}')">
                                Run
                            </button>
                        </div>
                        <div class="task-details">
                            <div class="task-detail">
                                <strong>Task GID:</strong> ${task.task_gid.substring(0, 12)}...
                            </div>
                            <div class="task-detail">
                                <strong>Due Date:</strong> ${task.due_date ? new Date(task.due_date).toLocaleDateString() : 'None'}
                            </div>
                            <div class="task-detail">
                                <strong>Created:</strong> ${task.created_at ? new Date(task.created_at).toLocaleDateString() : 'Unknown'}
                            </div>
                        </div>
                        ${task.notes ? `
                            <div class="task-notes">
                                ${escapeHtml(task.notes)}
                            </div>
                        ` : ''}
                    </div>
                `;
            }).join('');
        }

        function updateAgents(data) {
            const agentsList = document.getElementById('agentsList');

            if (!data.agents || data.agents.length === 0) {
                agentsList.innerHTML = `
                    <div class="empty-state">
                        <div class="empty-state-icon">💤</div>
                        <div>No active agents</div>
                    </div>
                `;
                return;
            }

            agentsList.innerHTML = data.agents.map(agent => {
                const duration = formatDuration(agent.duration_seconds);
                return `
                    <div class="agent-card">
                        <div class="agent-header">
                            <div class="agent-name">${escapeHtml(agent.task_name)}</div>
                            <span class="agent-status status-${agent.status}">${agent.status}</span>
                        </div>
                        <div class="agent-details">
                            <div class="agent-detail">
                                <strong>Task GID:</strong> ${agent.task_gid.substring(0, 12)}...
                            </div>
                            <div class="agent-detail">
                                <strong>Duration:</strong> ${duration}
                            </div>
                            <div class="agent-detail">
                                <strong>Started:</strong> ${new Date(agent.started_at).toLocaleTimeString()}
                            </div>
                        </div>
                        ${agent.log_file ? `
                            <div class="log-preview" id="log-${agent.task_gid}" onclick="showFullLog('${agent.task_gid}', '${escapeHtml(agent.task_name)}')">
                                <span class="pulse">Loading log...</span>
                            </div>
                            <div class="log-preview-hint">Click to view full log</div>
                        ` : ''}
                    </div>
                `;
            }).join('');

            // Fetch logs for each agent
            data.agents.forEach(agent => {
                if (agent.log_file) {
                    fetchTaskLog(agent.task_gid);
                }
            });
        }

        async function fetchTaskLog(taskGid) {
            try {
                const response = await fetch(`/api/logs/${taskGid}`);
                const data = await response.json();
                const logElement = document.getElementById(`log-${taskGid}`);
                if (logElement) {
                    if (data.error) {
                        logElement.textContent = `Error: ${data.error}`;
                    } else {
                        // Show last 20 lines
                        const lines = data.log.split('\\n').slice(-20).join('\\n');
                        logElement.textContent = lines || '(No output yet)';
                    }
                }
            } catch (error) {
                console.error('Failed to fetch log:', error);
            }
        }

        function formatDuration(seconds) {
            if (seconds < 60) return `${seconds}s`;
            const minutes = Math.floor(seconds / 60);
            const secs = seconds % 60;
            if (minutes < 60) return `${minutes}m ${secs}s`;
            const hours = Math.floor(minutes / 60);
            const mins = minutes % 60;
            return `${hours}h ${mins}m`;
        }

        function escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }

        function showRefreshIndicator() {
            const indicator = document.getElementById('refreshIndicator');
            indicator.classList.add('active');
            setTimeout(() => {
                indicator.classList.remove('active');
            }, 1000);
        }

        // Modal functions
        async function showFullLog(taskGid, taskName) {
            const modal = document.getElementById('logModal');
            const modalTitle = document.getElementById('modalTitle');
            const modalLog = document.getElementById('modalLog');

            // Set title
            modalTitle.textContent = `Log: ${taskName}`;

            // Show modal
            modal.classList.add('active');

            // Load full log
            modalLog.textContent = 'Loading full log...';
            try {
                const response = await fetch(`/api/logs/${taskGid}`);
                const data = await response.json();
                if (data.error) {
                    modalLog.textContent = `Error: ${data.error}`;
                } else {
                    modalLog.textContent = data.log || '(No output yet)';
                }
            } catch (error) {
                modalLog.textContent = `Failed to load log: ${error.message}`;
            }
        }

        function closeLogModal() {
            const modal = document.getElementById('logModal');
            modal.classList.remove('active');
        }

        // Close modal on escape key
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') {
                closeLogModal();
            }
        });

        // Close modal when clicking outside
        document.getElementById('logModal').addEventListener('click', (e) => {
            if (e.target.id === 'logModal') {
                closeLogModal();
            }
        });

        // Initialize
        connectWebSocket();
        fetchQueuedTasks(); // Initial fetch
        setInterval(fetchAgents, 2000); // Update agents every 2 seconds
        setInterval(fetchQueuedTasks, 3000); // Update queued tasks every 3 seconds
    </script>
</body>
</html>
        """

    async def start(self):
        """Start the web server."""
        import uvicorn

        config = uvicorn.Config(
            self.app,
            host=self.host,
            port=self.port,
            log_level="warning",  # Reduce noise
            access_log=False,
        )
        server = uvicorn.Server(config)

        logger.info("web_server_starting", host=self.host, port=self.port, url=f"http://{self.host}:{self.port}")
        await server.serve()

    def get_url(self) -> str:
        """Get the URL for the web interface."""
        return f"http://{self.host}:{self.port}"
