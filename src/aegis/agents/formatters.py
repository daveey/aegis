"""Response formatters for Aegis agent outputs.

This module provides functions to format agent responses for posting to Asana,
including markdown enhancement, code block formatting, and intelligent splitting
of long responses.
"""

import re
from dataclasses import dataclass
from enum import Enum

import structlog

logger = structlog.get_logger()


class TaskStatus(str, Enum):
    """Task execution status indicators."""

    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    COMPLETE = "complete"
    ERROR = "error"


# Asana comment length limit (leaving buffer for formatting)
MAX_COMMENT_LENGTH = 65000
SAFE_SPLIT_LENGTH = 60000

# Status badge templates
STATUS_BADGES = {
    TaskStatus.IN_PROGRESS: "🔄 **In Progress**",
    TaskStatus.BLOCKED: "🚫 **Blocked**",
    TaskStatus.COMPLETE: "✅ **Complete**",
    TaskStatus.ERROR: "❌ **Error**",
}


@dataclass
class FormattedResponse:
    """A formatted response ready for posting to Asana."""

    parts: list[str]
    total_length: int
    is_split: bool
    status: TaskStatus | None = None

    @property
    def primary(self) -> str:
        """Get the first (or only) part of the response."""
        return self.parts[0] if self.parts else ""

    @property
    def continuation_parts(self) -> list[str]:
        """Get any continuation parts (2nd onward)."""
        return self.parts[1:] if len(self.parts) > 1 else []


def format_response(
    content: str,
    status: TaskStatus | None = None,
    include_header: bool = True,
    enhance_markdown: bool = True,
) -> FormattedResponse:
    """Format agent response for Asana comment.

    Args:
        content: Raw response content from agent
        status: Optional status indicator to include
        include_header: Whether to include status badge header
        enhance_markdown: Whether to enhance markdown formatting

    Returns:
        FormattedResponse with formatted content, potentially split into parts
    """
    logger.debug(
        "formatting_response",
        content_length=len(content),
        status=status,
        include_header=include_header,
    )

    # Enhance markdown if requested
    if enhance_markdown:
        content = _enhance_markdown(content)

    # Add status header if provided
    formatted_content = content
    if status and include_header:
        badge = STATUS_BADGES[status]
        formatted_content = f"{badge}\n\n{content}"

    # Check if splitting is needed
    if len(formatted_content) <= MAX_COMMENT_LENGTH:
        logger.debug("response_fits_single_comment", length=len(formatted_content))
        return FormattedResponse(
            parts=[formatted_content],
            total_length=len(formatted_content),
            is_split=False,
            status=status,
        )

    # Split into multiple parts
    parts = _split_response(formatted_content, status)
    total_length = sum(len(p) for p in parts)

    logger.info(
        "response_split_into_parts",
        num_parts=len(parts),
        total_length=total_length,
        part_lengths=[len(p) for p in parts],
    )

    return FormattedResponse(
        parts=parts,
        total_length=total_length,
        is_split=True,
        status=status,
    )


def _enhance_markdown(content: str) -> str:
    """Enhance markdown formatting in content.

    Args:
        content: Raw content to enhance

    Returns:
        Content with enhanced markdown
    """
    # Detect and format code blocks if not already formatted
    content = _format_code_blocks(content)

    # Ensure proper spacing around headers
    content = _format_headers(content)

    # Format lists
    content = _format_lists(content)

    return content


def _format_code_blocks(content: str) -> str:
    """Format code blocks with proper syntax highlighting.

    Detects code blocks and ensures they have proper markdown formatting
    with language specifiers where possible.
    """
    # Pattern for existing code blocks
    existing_blocks = re.compile(r"```[\w]*\n.*?```", re.DOTALL)
    if existing_blocks.search(content):
        # Already has code blocks, just ensure they're properly formatted
        return content

    # Detect potential code blocks (indented blocks, or lines with common code patterns)
    # Look for Python-like code patterns
    python_pattern = re.compile(
        r"(?:^|\n)((?:(?:def|class|import|from|if|for|while|try|except|return|async|await)\s+.*\n(?:\s{4,}.*\n)*)+)",
        re.MULTILINE,
    )

    def replace_python(match: re.Match) -> str:
        code = match.group(1).rstrip()
        return f"\n```python\n{code}\n```\n"

    content = python_pattern.sub(replace_python, content)

    # Look for shell command patterns
    shell_pattern = re.compile(
        r"(?:^|\n)((?:\$\s+.*\n(?:\s{2,}.*\n)*)+)", re.MULTILINE
    )

    def replace_shell(match: re.Match) -> str:
        code = match.group(1).rstrip()
        return f"\n```bash\n{code}\n```\n"

    content = shell_pattern.sub(replace_shell, content)

    # Look for JSON patterns
    json_pattern = re.compile(r"(\{[\s\S]*?\}|\[[\s\S]*?\])", re.MULTILINE)

    def replace_json(match: re.Match) -> str:
        code = match.group(1)
        # Only treat as JSON if it has typical JSON structure
        if re.search(r'["\s]*:\s*["\d\[\{]', code):
            return f"```json\n{code}\n```"
        return code

    # Be conservative with JSON detection to avoid false positives
    if re.search(r'\{\s*"[\w_]+"\s*:', content):
        content = json_pattern.sub(replace_json, content)

    return content


def _format_headers(content: str) -> str:
    """Ensure proper spacing around markdown headers."""
    # Add blank line before headers (except at start)
    content = re.sub(r"([^\n])\n(#{1,6}\s)", r"\1\n\n\2", content)

    # Add blank line after headers
    content = re.sub(r"(#{1,6}\s[^\n]+)\n([^#\n])", r"\1\n\n\2", content)

    return content


def _format_lists(content: str) -> str:
    """Ensure proper spacing around lists."""
    # Add blank line before lists (if not already present)
    content = re.sub(r"([^\n])\n([*\-+]\s)", r"\1\n\n\2", content)
    content = re.sub(r"([^\n])\n(\d+\.\s)", r"\1\n\n\2", content)

    # Add blank line after lists
    content = re.sub(r"([*\-+]\s[^\n]+)\n([^*\-+\d\s\n])", r"\1\n\n\2", content)
    content = re.sub(r"(\d+\.\s[^\n]+)\n([^\d\s\n])", r"\1\n\n\2", content)

    return content


def _split_response(content: str, status: TaskStatus | None = None) -> list[str]:
    """Split long response into multiple parts.

    Attempts to split at natural boundaries (paragraphs, code blocks)
    to maintain readability.

    Args:
        content: Content to split
        status: Optional status for continuation headers

    Returns:
        List of content parts, each under MAX_COMMENT_LENGTH
    """
    if len(content) <= MAX_COMMENT_LENGTH:
        return [content]

    parts: list[str] = []
    remaining = content

    part_num = 1
    while remaining:
        # Determine split point
        if len(remaining) <= SAFE_SPLIT_LENGTH:
            # Last part
            part_content = remaining
            remaining = ""
        else:
            # Find a good split point
            split_point = _find_split_point(remaining, SAFE_SPLIT_LENGTH)
            part_content = remaining[:split_point].rstrip()
            remaining = remaining[split_point:].lstrip()

        # Add continuation header for parts after the first
        if part_num > 1:
            header = f"**[Continued - Part {part_num}]**\n\n"
            part_content = header + part_content

        parts.append(part_content)
        part_num += 1

        logger.debug(
            "response_part_created",
            part_num=part_num - 1,
            length=len(part_content),
            remaining_length=len(remaining),
        )

    return parts


def _find_split_point(content: str, max_length: int) -> int:
    """Find a good point to split content.

    Prefers to split at:
    1. End of code blocks
    2. Paragraph breaks (double newline)
    3. Single newlines
    4. Last space before max_length

    Args:
        content: Content to find split point in
        max_length: Maximum length for this part

    Returns:
        Index to split at
    """
    # Don't split in the middle of a code block
    code_block_end = content[:max_length].rfind("```\n")
    if code_block_end > max_length * 0.7:  # If we find one in the last 30%
        # Check if there's a matching start
        before = content[: code_block_end + 4]
        if before.count("```") % 2 == 0:  # Even number means we're at a block end
            return code_block_end + 4

    # Try to split at paragraph break
    paragraph_break = content[:max_length].rfind("\n\n")
    if paragraph_break > max_length * 0.5:  # If we find one in the last 50%
        return paragraph_break + 2

    # Try to split at single newline
    newline = content[:max_length].rfind("\n")
    if newline > max_length * 0.7:  # If we find one in the last 30%
        return newline + 1

    # Try to split at last space
    space = content[:max_length].rfind(" ")
    if space > max_length * 0.8:  # If we find one in the last 20%
        return space + 1

    # Last resort: split at max_length
    return max_length


def format_error(
    error_message: str,
    error_type: str | None = None,
    traceback: str | None = None,
    context: dict | None = None,
) -> str:
    """Format error information for Asana comment.

    Args:
        error_message: Main error message
        error_type: Type of error (e.g., "ApiException")
        traceback: Optional traceback string
        context: Optional context dictionary

    Returns:
        Formatted error message
    """
    parts = [STATUS_BADGES[TaskStatus.ERROR]]

    if error_type:
        parts.append(f"\n**Error Type**: `{error_type}`")

    parts.append(f"\n**Message**: {error_message}")

    if context:
        parts.append("\n**Context**:")
        for key, value in context.items():
            parts.append(f"- **{key}**: `{value}`")

    if traceback:
        parts.append("\n**Traceback**:")
        parts.append(f"```python\n{traceback}\n```")

    return "\n".join(parts)


def format_code_snippet(
    code: str,
    language: str = "python",
    title: str | None = None,
    description: str | None = None,
) -> str:
    """Format a code snippet for Asana comment.

    Args:
        code: Code to format
        language: Programming language for syntax highlighting
        title: Optional title for the snippet
        description: Optional description

    Returns:
        Formatted code snippet
    """
    parts = []

    if title:
        parts.append(f"**{title}**\n")

    if description:
        parts.append(f"{description}\n")

    parts.append(f"```{language}\n{code}\n```")

    return "\n".join(parts)


def format_task_list(
    items: list[str | tuple[str, bool]],
    title: str | None = None,
) -> str:
    """Format a task list (checklist) for Asana comment.

    Args:
        items: List of tasks (strings or (text, completed) tuples)
        title: Optional title for the task list

    Returns:
        Formatted task list
    """
    parts = []

    if title:
        parts.append(f"**{title}**\n")

    for item in items:
        if isinstance(item, tuple):
            text, completed = item
            checkbox = "☑" if completed else "☐"
            parts.append(f"{checkbox} {text}")
        else:
            parts.append(f"☐ {item}")

    return "\n".join(parts)
