# Aegis Tools

This document describes the tools available in Aegis that can be used by Claude Code or other automation systems.

## aegis do [project]

Execute the first incomplete task from an Asana project using Claude CLI.

### Usage

```bash
aegis do [project_name]
```

### Arguments

- `project_name` - Name of the Asana project (case-insensitive). Project must be in the Aegis portfolio.

### Examples

```bash
# Execute first task in Aegis project
aegis do Aegis

# Execute first task in Triptic project
aegis do Triptic
```

### Behavior

1. **Finds Project**: Searches Aegis portfolio for matching project
2. **Extracts Code Path**: Reads code location from project notes
3. **Fetches First Task**: Gets first incomplete task from project
4. **Executes Task**: Runs Claude CLI with task context in project directory
5. **Logs Output**: Writes execution log to `logs/{project}.log`
6. **Posts Comment**: Updates Asana task with execution results

### Output

- **Log File**: `logs/{project}.log` - Timestamped execution log with full output
- **Asana Comment**: Posted to task with summary and log file reference
- **Console**: Real-time status updates during execution

### Error Handling

The command is designed to be robust:

- **API Retry Logic**: Automatically retries Asana API calls (3 attempts with exponential backoff)
- **Graceful Degradation**: Continues even if Asana comment posting fails
- **Best-Effort Logging**: Always attempts to log errors even if main operation fails
- **No Exit on Error**: Reports errors but doesn't exit process (except for missing Claude CLI)

### Exit Codes

- `0` - Success (task executed, regardless of Claude CLI exit code)
- `1` - Fatal error (Claude CLI not found, project not found)

### Requirements

- Claude CLI must be installed and available in PATH
- Valid Asana API token in `.env`
- Project must exist in Aegis portfolio
- Project must have at least one incomplete task

### Flags Used with Claude CLI

The command automatically uses these flags:
- `--dangerously-skip-permissions` - Bypass permission prompts for automation
- `--output-format stream-json` - Structured JSON output
- `--verbose` - Include detailed execution information

### Integration with Claude Code

This command can be invoked by Claude Code using the Bash tool:

```python
# From within Claude Code
result = subprocess.run(["aegis", "do", "Aegis"])
```

The command is designed to be called programmatically and handles all errors gracefully.
