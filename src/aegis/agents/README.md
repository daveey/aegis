# Aegis Agents Module

This module contains components for Aegis agent implementations, including prompt template management and response formatting utilities.

## Formatters (`formatters.py`)

The formatters module provides functions to format agent responses for posting to Asana comments.

### Key Features

1. **Markdown Enhancement**: Automatically detects and formats code blocks, headers, and lists
2. **Syntax Highlighting**: Adds language specifiers to code blocks (Python, Bash, JSON)
3. **Response Splitting**: Intelligently splits long responses (>65k chars) at natural boundaries
4. **Status Badges**: Visual indicators for task status (✅ Complete, 🔄 In Progress, ❌ Error, 🚫 Blocked)
5. **Error Formatting**: Structured error messages with type, context, and traceback
6. **Code Snippets**: Formatted code blocks with optional titles and descriptions
7. **Task Lists**: Checklist formatting with completion indicators (☑/☐)

### Usage

#### Basic Response Formatting

```python
from aegis.agents.formatters import format_response, TaskStatus

content = "I've completed the analysis and found 3 issues."
result = format_response(content, status=TaskStatus.COMPLETE)

# Post to Asana
await asana_client.add_comment(task_gid, result.primary)
```

#### Long Response with Auto-Splitting

```python
# Long responses are automatically split at natural boundaries
long_content = "..." # 100k+ characters
result = format_response(long_content, status=TaskStatus.IN_PROGRESS)

# Post primary comment
await asana_client.add_comment(task_gid, result.primary)

# Post continuation parts
for part in result.continuation_parts:
    await asana_client.add_comment(task_gid, part)
```

#### Error Formatting

```python
from aegis.agents.formatters import format_error

error_msg = format_error(
    error_message="Failed to connect to database",
    error_type="ConnectionError",
    context={"host": "localhost", "port": 5432},
    traceback=traceback_string
)

await asana_client.add_comment(task_gid, error_msg)
```

#### Code Snippet Formatting

```python
from aegis.agents.formatters import format_code_snippet

code = format_code_snippet(
    code="def hello(): return 'world'",
    language="python",
    title="New Function",
    description="Added helper function for greeting"
)

await asana_client.add_comment(task_gid, code)
```

#### Task List Formatting

```python
from aegis.agents.formatters import format_task_list

checklist = format_task_list(
    items=[
        ("Setup database", True),
        ("Write tests", True),
        ("Deploy", False),
    ],
    title="Progress"
)

await asana_client.add_comment(task_gid, checklist)
```

### API Reference

#### `format_response(content, status=None, include_header=True, enhance_markdown=True)`

Main formatting function for agent responses.

**Parameters:**
- `content` (str): Raw response content from agent
- `status` (TaskStatus | None): Optional status badge (COMPLETE, IN_PROGRESS, BLOCKED, ERROR)
- `include_header` (bool): Whether to include status badge header (default: True)
- `enhance_markdown` (bool): Whether to enhance markdown formatting (default: True)

**Returns:**
- `FormattedResponse`: Object with formatted content, potentially split into multiple parts

**Example:**
```python
result = format_response("Task done!", status=TaskStatus.COMPLETE)
print(result.primary)  # First (or only) part
print(result.continuation_parts)  # Additional parts if split
print(result.is_split)  # Whether response was split
print(result.total_length)  # Total length across all parts
```

#### `format_error(error_message, error_type=None, traceback=None, context=None)`

Format error information for Asana comment.

**Parameters:**
- `error_message` (str): Main error message
- `error_type` (str | None): Type of error (e.g., "ValueError")
- `traceback` (str | None): Optional traceback string
- `context` (dict | None): Optional context dictionary

**Returns:**
- `str`: Formatted error message with status badge

#### `format_code_snippet(code, language="python", title=None, description=None)`

Format a code snippet for Asana comment.

**Parameters:**
- `code` (str): Code to format
- `language` (str): Programming language for syntax highlighting (default: "python")
- `title` (str | None): Optional title for the snippet
- `description` (str | None): Optional description

**Returns:**
- `str`: Formatted code snippet

#### `format_task_list(items, title=None)`

Format a task list (checklist) for Asana comment.

**Parameters:**
- `items` (list): List of tasks (strings or (text, completed) tuples)
- `title` (str | None): Optional title for the task list

**Returns:**
- `str`: Formatted task list

### Response Splitting

The formatter automatically splits long responses (>65,000 characters) to fit within Asana's comment length limit. It attempts to split at natural boundaries:

1. End of code blocks (preferred)
2. Paragraph breaks (double newline)
3. Single newlines
4. Last space before limit

Each continuation part includes a header: `**[Continued - Part N]**`

### Markdown Enhancement

When `enhance_markdown=True`, the formatter automatically:

- Detects Python code and wraps it in ` ```python ` blocks
- Detects shell commands (lines starting with `$`) and wraps them in ` ```bash ` blocks
- Detects JSON and wraps it in ` ```json ` blocks
- Adds proper spacing around headers
- Adds proper spacing around lists
- Preserves existing code blocks (doesn't double-format)

### Status Badges

Available status indicators:

- `TaskStatus.COMPLETE`: ✅ **Complete**
- `TaskStatus.IN_PROGRESS`: 🔄 **In Progress**
- `TaskStatus.BLOCKED`: 🚫 **Blocked**
- `TaskStatus.ERROR`: ❌ **Error**

### Examples

See `examples/formatter_usage.py` for comprehensive usage examples.

### Testing

The formatters module has 42 unit tests with 92% code coverage.

Run tests:
```bash
pytest tests/unit/test_formatters.py -v
```

Run with coverage:
```bash
pytest tests/unit/test_formatters.py --cov=src/aegis/agents/formatters --cov-report=term-missing
```

## Prompt Templates (`prompts.py`)

The prompt template system provides a flexible way to manage and version prompts for different agent types and task scenarios.

### Components

- **`PromptRenderer`**: Renders templates with variable substitution
- **`PromptTemplateLoader`**: Loads templates from the database
- **`PromptBuilder`**: High-level interface for building complete prompts

### Database Schema

Prompt templates are stored in the `prompt_templates` table with:

- `name`: Template identifier (e.g., "system", "code_task")
- `agent_type`: Agent type (e.g., "simple_executor")
- `version`: Version number for template evolution
- `system_prompt`: System-level instructions
- `user_prompt_template`: User message template with variables
- `active`: Whether the template is currently active
- `variables`: List of required template variables
- `usage_count`: Number of times used

### Available Templates

Six templates are available for the `simple_executor` agent:

1. **system**: Base system prompt defining agent role
2. **task_classifier**: Analyzes tasks to determine type and complexity
3. **code_task**: Specialized for software development
4. **research_task**: Specialized for research and information gathering
5. **clarification_needed**: For asking clarifying questions
6. **bug_fix**: Specialized for debugging

### Usage Examples

#### Building a Prompt

```python
from aegis.agents.prompts import PromptBuilder

builder = PromptBuilder("simple_executor")

variables = {
    "project_name": "My Project",
    "project_code_path": "/path/to/project",
    "task_name": "Implement authentication",
    "task_description": "Add JWT-based auth to the API",
    "additional_context": "Use existing user model"
}

result = builder.build_prompt("system", variables)
if result:
    system_prompt, user_prompt = result
    # Use with your LLM
```

#### Loading Templates

```python
from aegis.agents.prompts import PromptTemplateLoader

loader = PromptTemplateLoader()

# Load specific template
template = loader.get_active_template("simple_executor", "code_task")

# Load all templates for an agent
templates = loader.get_all_templates_for_agent("simple_executor")
```

#### Manual Rendering

```python
from aegis.agents.prompts import PromptRenderer

renderer = PromptRenderer()
rendered = renderer.render(
    "Hello {name}, you have {count} tasks.",
    {"name": "Alice", "count": 5}
)
```

### Management Scripts

#### Populate Templates

Load initial templates into the database:

```bash
python scripts/populate_prompt_templates.py
```

#### List Templates

View all templates in the database:

```bash
python scripts/populate_prompt_templates.py list
```

#### Test System

Verify functionality:

```bash
python scripts/test_prompts.py
```

### Template Variables

Templates support `{variable}` substitution. Standard variables:

- `current_date`: Today's date (YYYY-MM-DD)
- `current_datetime`: Current date and time

Each template may require additional variables. Check `template.variables`.

### Best Practices

1. **Version Templates**: Create new versions when updating, mark old ones inactive
2. **Use Specialized Templates**: Choose specific templates (code_task, research_task) over generic ones
3. **Test Changes**: Use test script to verify templates
4. **Track Performance**: Monitor `usage_count` and `success_rate`
5. **Document Variables**: List required variables in template metadata
