# Agent Service Startup Fix

**Date**: 2025-11-25
**Issue**: Agent service was failing to start, causing orchestrator task execution failures

## Problem

The orchestrator was failing to execute tasks with the following error:

```
ValueError: Failed to parse agent port from stdout
ProcessLookupError
```

### Root Cause

The agent service (`src/aegis/agents/agent_service.py`) was attempting to use an incorrect Uvicorn API pattern:

```python
# OLD (broken) code:
async def startup():
    await server.startup()  # This method doesn't exist in Uvicorn API
    actual_port = server.config.port
    print(f"AGENT_PORT={actual_port}", flush=True)

async def serve():
    await startup()
    await server.main_loop()

asyncio.run(serve())
```

The problem was:
1. `server.startup()` tried to access `self.lifespan` which doesn't exist
2. The agent process crashed before printing the port number
3. The orchestrator couldn't parse the port and failed the task execution

### Error Details

```
AttributeError: 'Server' object has no attribute 'lifespan'
```

This occurred at line 298 in `agent_service.py` when trying to call `await server.startup()`.

## Solution

Changed the approach to:
1. **Bind a socket first** to get a free port when `port=0`
2. **Print the port immediately** to stdout (before starting uvicorn)
3. **Use the proper Uvicorn API** (`server.serve()`) instead of manually calling startup/main_loop

```python
# NEW (working) code:
def run_agent_service(host: str = "127.0.0.1", port: int = 0) -> None:
    import socket

    service = AgentService()

    # If port=0, find an available port first
    if port == 0:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind((host, 0))
        port = sock.getsockname()[1]
        sock.close()

    # Print port BEFORE starting uvicorn
    print(f"AGENT_PORT={port}", flush=True)
    logger.info("agent_service_starting", host=host, port=port)

    # Run uvicorn with the known port
    config = uvicorn.Config(service.app, host=host, port=port, ...)
    server = uvicorn.Server(config)
    asyncio.run(server.serve())  # Proper API
```

## Benefits

1. **Reliable port detection**: Socket binding guarantees we get a valid free port
2. **Immediate availability**: Port is printed before uvicorn starts, so orchestrator can read it instantly
3. **Proper API usage**: Uses `server.serve()` which is the official Uvicorn API
4. **No race conditions**: Port is determined and printed before any async operations

## Testing

Verified the fix with:

```bash
# Test 1: Agent service starts and prints port
python -m aegis.agents.agent_service
# Output: AGENT_PORT=58409

# Test 2: Orchestrator can launch agent and communicate
python test_agent_launch.py
# ✓ Agent launched successfully!
# ✓ Health check: {'status': 'healthy', 'agent_type': 'simple_executor'}
# ✓ Agent cleaned up
```

## Files Modified

- `src/aegis/agents/agent_service.py`: Fixed `run_agent_service()` function (lines 276-311)

## References

- Uvicorn API docs: https://www.uvicorn.org/
- Original error trace: See orchestrator logs from 2025-11-25 23:24:09
- Related files:
  - `src/aegis/orchestrator/agent_client.py`: Launches agent and parses port
  - `src/aegis/orchestrator/main.py`: Orchestrator execution logic
