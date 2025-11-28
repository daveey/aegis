"""Example usage of the Aegis response formatters.

This file demonstrates how to use the formatters module to create
well-formatted Asana comments from agent responses.
"""

from aegis.agents.formatters import (
    TaskStatus,
    format_code_snippet,
    format_error,
    format_response,
    format_task_list,
)


def example_basic_response():
    """Example: Basic response formatting."""
    print("=" * 60)
    print("EXAMPLE 1: Basic Response")
    print("=" * 60)

    content = """I've analyzed your code and found a few issues:

1. Missing error handling in the API client
2. Inefficient database queries in the user service
3. Outdated dependencies in package.json

I recommend addressing these in priority order."""

    result = format_response(content, status=TaskStatus.COMPLETE)

    print(result.primary)
    print(f"\nLength: {result.total_length} chars")
    print(f"Split: {result.is_split}")


def example_code_snippet():
    """Example: Formatting code snippets."""
    print("\n" + "=" * 60)
    print("EXAMPLE 2: Code Snippet")
    print("=" * 60)

    code = """def calculate_total(items):
    total = sum(item.price * item.quantity for item in items)
    tax = total * 0.08
    return total + tax"""

    result = format_code_snippet(
        code=code,
        language="python",
        title="Refactored Function",
        description="Here's the improved version with better naming:",
    )

    print(result)


def example_error_formatting():
    """Example: Formatting error messages."""
    print("\n" + "=" * 60)
    print("EXAMPLE 3: Error Formatting")
    print("=" * 60)

    result = format_error(
        error_message="Failed to connect to database",
        error_type="ConnectionError",
        context={
            "host": "localhost",
            "port": "5432",
            "database": "aegis",
        },
        traceback="Traceback (most recent call last):\n  File db.py, line 42, in connect\n    connection = psycopg2.connect(...)\nConnectionError: could not connect to server",
    )

    print(result)


def example_task_list():
    """Example: Formatting task lists."""
    print("\n" + "=" * 60)
    print("EXAMPLE 4: Task List")
    print("=" * 60)

    items = [
        ("Set up database schema", True),
        ("Implement user authentication", True),
        ("Add API endpoints", False),
        ("Write unit tests", False),
        ("Deploy to staging", False),
    ]

    result = format_task_list(items, title="Implementation Progress")

    print(result)


def example_long_response():
    """Example: Long response with automatic splitting."""
    print("\n" + "=" * 60)
    print("EXAMPLE 5: Long Response (Split)")
    print("=" * 60)

    # Create a long response that will be split
    sections = []
    for i in range(100):
        sections.append(f"""
## Section {i + 1}

This is section {i + 1} of a very long response. It contains detailed
analysis and recommendations for improving your codebase.

Key points:
- Point 1 for section {i + 1}
- Point 2 for section {i + 1}
- Point 3 for section {i + 1}

```python
def function_{i}():
    # Implementation for section {i + 1}
    return "result_{i}"
```
""")

    content = "\n".join(sections)
    result = format_response(content, status=TaskStatus.IN_PROGRESS)

    print(f"Total length: {result.total_length:,} chars")
    print(f"Split into {len(result.parts)} parts")
    print(f"Part lengths: {[len(p) for p in result.parts]}")
    print("\n--- First 500 chars of Part 1 ---")
    print(result.primary[:500])
    print("\n--- First 500 chars of Part 2 ---")
    if result.continuation_parts:
        print(result.continuation_parts[0][:500])


def example_auto_code_detection():
    """Example: Automatic code block detection."""
    print("\n" + "=" * 60)
    print("EXAMPLE 6: Auto Code Detection")
    print("=" * 60)

    content = """I've created the following function:

def process_order(order_id):
    order = db.get_order(order_id)
    if order.status == 'pending':
        order.process()
        return True
    return False

And here's how to use it from the command line:

$ python process_orders.py --order-id 12345
$ python process_orders.py --batch --date 2025-11-25
"""

    result = format_response(content, enhance_markdown=True)

    print(result.primary)


def example_integration_with_asana():
    """Example: Complete workflow for posting to Asana."""
    print("\n" + "=" * 60)
    print("EXAMPLE 7: Integration with Asana Client")
    print("=" * 60)

    # Simulate agent output
    agent_output = """I've completed the task successfully!

## Changes Made

1. Added input validation to the API endpoint
2. Improved error messages for better debugging
3. Updated unit tests

## Code Changes

def validate_input(data):
    if not data:
        raise ValueError("Input cannot be empty")
    if not isinstance(data, dict):
        raise TypeError("Input must be a dictionary")
    return True

## Testing

All tests pass:
$ pytest tests/ -v
======================== 15 passed in 2.3s ========================

## Next Steps

- ☐ Deploy to staging
- ☐ Run integration tests
- ☐ Update documentation
"""

    # Format the response
    result = format_response(agent_output, status=TaskStatus.COMPLETE)

    print("--- Formatted Response ---")
    print(result.primary)

    print("\n--- Ready to post to Asana ---")
    print(f"Parts: {len(result.parts)}")
    print(f"Total length: {result.total_length} chars")

    # In real usage:
    # async with asana_client:
    #     # Post primary comment
    #     await asana_client.add_comment(task_gid, result.primary)
    #
    #     # Post continuation parts if needed
    #     for part in result.continuation_parts:
    #         await asana_client.add_comment(task_gid, part)


if __name__ == "__main__":
    example_basic_response()
    example_code_snippet()
    example_error_formatting()
    example_task_list()
    example_long_response()
    example_auto_code_detection()
    example_integration_with_asana()

    print("\n" + "=" * 60)
    print("Examples complete!")
    print("=" * 60)
