"""Unit tests for response formatters."""


from aegis.agents.formatters import (
    MAX_COMMENT_LENGTH,
    SAFE_SPLIT_LENGTH,
    FormattedResponse,
    TaskStatus,
    format_code_snippet,
    format_error,
    format_response,
    format_task_list,
)


class TestFormatResponse:
    """Tests for format_response function."""

    def test_basic_formatting(self):
        """Test basic response formatting."""
        content = "This is a simple response."
        result = format_response(content, status=None, include_header=False)

        assert isinstance(result, FormattedResponse)
        assert len(result.parts) == 1
        assert result.total_length == len(content)
        assert not result.is_split
        assert result.primary == content

    def test_with_status_badge(self):
        """Test formatting with status badge."""
        content = "Task completed successfully."
        result = format_response(content, status=TaskStatus.COMPLETE, include_header=True)

        assert "✅ **Complete**" in result.primary
        assert content in result.primary
        assert not result.is_split

    def test_status_badge_not_included(self):
        """Test that status badge is not included when include_header=False."""
        content = "Task in progress."
        result = format_response(
            content, status=TaskStatus.IN_PROGRESS, include_header=False
        )

        assert "🔄 **In Progress**" not in result.primary
        assert result.primary == content

    def test_markdown_enhancement_code_blocks(self):
        """Test that code blocks are properly formatted."""
        content = """Here's some code:
def hello():
    print("Hello, world!")
    return True
"""
        result = format_response(content, enhance_markdown=True)

        assert "```python" in result.primary
        assert "def hello():" in result.primary

    def test_markdown_enhancement_shell_commands(self):
        """Test that shell commands are properly formatted."""
        content = """Run these commands:
$ ls -la
$ cd /tmp
$ echo "test"
"""
        result = format_response(content, enhance_markdown=True)

        assert "```bash" in result.primary
        assert "$ ls -la" in result.primary

    def test_markdown_enhancement_headers(self):
        """Test that headers get proper spacing."""
        content = "Some text\n# Header\nMore text"
        result = format_response(content, enhance_markdown=True)

        # Should have blank lines around header
        assert "\n\n# Header\n\n" in result.primary

    def test_markdown_enhancement_lists(self):
        """Test that lists get proper spacing."""
        content = "Introduction\n- Item 1\n- Item 2\nConclusion"
        result = format_response(content, enhance_markdown=True)

        # Should have blank line before list
        assert "Introduction\n\n- Item 1" in result.primary

    def test_no_markdown_enhancement(self):
        """Test that markdown enhancement can be disabled."""
        content = "def hello():\n    print('hi')"
        result = format_response(content, enhance_markdown=False)

        # Should not add code block formatting
        assert "```python" not in result.primary
        assert content in result.primary

    def test_existing_code_blocks_preserved(self):
        """Test that existing code blocks are not double-formatted."""
        content = "```python\nprint('hello')\n```"
        result = format_response(content, enhance_markdown=True)

        # Should not add another code block
        assert result.primary.count("```python") == 1

    def test_short_response_not_split(self):
        """Test that short responses are not split."""
        content = "x" * 1000
        result = format_response(content)

        assert len(result.parts) == 1
        assert not result.is_split
        assert result.continuation_parts == []

    def test_long_response_split(self):
        """Test that long responses are split into multiple parts."""
        # Create content longer than MAX_COMMENT_LENGTH
        content = "x" * (MAX_COMMENT_LENGTH + 1000)
        result = format_response(content)

        assert len(result.parts) > 1
        assert result.is_split
        assert len(result.continuation_parts) > 0

        # Check that each part is under the limit
        for part in result.parts:
            assert len(part) <= MAX_COMMENT_LENGTH

    def test_split_response_has_continuation_headers(self):
        """Test that split responses have continuation headers."""
        content = "x" * (MAX_COMMENT_LENGTH + 1000)
        result = format_response(content)

        # First part should not have continuation header
        assert "[Continued - Part" not in result.parts[0]

        # Subsequent parts should have continuation headers
        for i, part in enumerate(result.parts[1:], start=2):
            assert f"[Continued - Part {i}]" in part

    def test_split_at_paragraph_boundary(self):
        """Test that splitting prefers paragraph boundaries."""
        # Create content with clear paragraph break near split point
        paragraph1 = "x" * (SAFE_SPLIT_LENGTH - 100)
        paragraph2 = "y" * 1000
        content = f"{paragraph1}\n\n{paragraph2}"

        result = format_response(content)

        if result.is_split:
            # Should split at the paragraph boundary
            assert result.parts[0].rstrip().endswith("x")
            assert result.parts[1].startswith("**[Continued") or result.parts[1].startswith(
                "y"
            )

    def test_split_preserves_code_blocks(self):
        """Test that splitting doesn't break code blocks."""
        # Create content with code block near split point
        before = "x" * (SAFE_SPLIT_LENGTH - 200)
        code_block = "```python\ndef test():\n    pass\n```"
        after = "y" * 1000

        content = f"{before}\n\n{code_block}\n\n{after}"
        result = format_response(content)

        # Verify code blocks are intact in each part
        for part in result.parts:
            # Count opening and closing backticks
            opening = part.count("```")
            # Should have even number (each block has opening and closing)
            if "```" in part:
                assert opening % 2 == 0, f"Code block split in part: {part[:200]}"

    def test_total_length_calculation(self):
        """Test that total length is correctly calculated."""
        content = "x" * 10000
        result = format_response(content)

        calculated_total = sum(len(part) for part in result.parts)
        assert result.total_length == calculated_total


class TestFormatError:
    """Tests for format_error function."""

    def test_basic_error(self):
        """Test basic error formatting."""
        result = format_error("Something went wrong")

        assert "❌ **Error**" in result
        assert "Something went wrong" in result

    def test_error_with_type(self):
        """Test error formatting with error type."""
        result = format_error("Something went wrong", error_type="ValueError")

        assert "❌ **Error**" in result
        assert "ValueError" in result
        assert "Something went wrong" in result

    def test_error_with_context(self):
        """Test error formatting with context."""
        context = {"task_id": "123", "project": "test"}
        result = format_error("Something went wrong", context=context)

        assert "task_id" in result
        assert "123" in result
        assert "project" in result
        assert "test" in result

    def test_error_with_traceback(self):
        """Test error formatting with traceback."""
        traceback = "Traceback (most recent call last):\n  File test.py, line 1"
        result = format_error("Error", traceback=traceback)

        assert "```python" in result
        assert "Traceback" in result

    def test_complete_error(self):
        """Test error formatting with all fields."""
        result = format_error(
            error_message="Failed to connect",
            error_type="ConnectionError",
            traceback="Traceback...",
            context={"host": "localhost"},
        )

        assert "❌ **Error**" in result
        assert "ConnectionError" in result
        assert "Failed to connect" in result
        assert "localhost" in result
        assert "Traceback..." in result


class TestFormatCodeSnippet:
    """Tests for format_code_snippet function."""

    def test_basic_code_snippet(self):
        """Test basic code snippet formatting."""
        code = "print('hello')"
        result = format_code_snippet(code)

        assert "```python" in result
        assert code in result
        assert result.endswith("```")

    def test_code_snippet_with_language(self):
        """Test code snippet with custom language."""
        code = "console.log('hello');"
        result = format_code_snippet(code, language="javascript")

        assert "```javascript" in result
        assert code in result

    def test_code_snippet_with_title(self):
        """Test code snippet with title."""
        code = "print('hello')"
        result = format_code_snippet(code, title="Example Code")

        assert "**Example Code**" in result
        assert code in result

    def test_code_snippet_with_description(self):
        """Test code snippet with description."""
        code = "print('hello')"
        result = format_code_snippet(code, description="This prints hello")

        assert "This prints hello" in result
        assert code in result

    def test_code_snippet_complete(self):
        """Test code snippet with all fields."""
        result = format_code_snippet(
            code="print('hello')",
            language="python",
            title="Hello World",
            description="A simple example",
        )

        assert "**Hello World**" in result
        assert "A simple example" in result
        assert "```python" in result
        assert "print('hello')" in result


class TestFormatTaskList:
    """Tests for format_task_list function."""

    def test_basic_task_list(self):
        """Test basic task list formatting."""
        items = ["Task 1", "Task 2", "Task 3"]
        result = format_task_list(items)

        assert "☐ Task 1" in result
        assert "☐ Task 2" in result
        assert "☐ Task 3" in result

    def test_task_list_with_completion(self):
        """Test task list with completed items."""
        items = [
            ("Task 1", True),
            ("Task 2", False),
            ("Task 3", True),
        ]
        result = format_task_list(items)

        assert "☑ Task 1" in result
        assert "☐ Task 2" in result
        assert "☑ Task 3" in result

    def test_task_list_with_title(self):
        """Test task list with title."""
        items = ["Task 1", "Task 2"]
        result = format_task_list(items, title="My Tasks")

        assert "**My Tasks**" in result
        assert "☐ Task 1" in result

    def test_task_list_mixed_format(self):
        """Test task list with mixed string and tuple items."""
        items = [
            "Task 1",
            ("Task 2", True),
            "Task 3",
        ]
        result = format_task_list(items)

        assert "☐ Task 1" in result
        assert "☑ Task 2" in result
        assert "☐ Task 3" in result


class TestFormattedResponse:
    """Tests for FormattedResponse dataclass."""

    def test_primary_property(self):
        """Test primary property returns first part."""
        response = FormattedResponse(
            parts=["Part 1", "Part 2"],
            total_length=12,
            is_split=True,
        )

        assert response.primary == "Part 1"

    def test_primary_property_empty(self):
        """Test primary property with empty parts."""
        response = FormattedResponse(
            parts=[],
            total_length=0,
            is_split=False,
        )

        assert response.primary == ""

    def test_continuation_parts_property(self):
        """Test continuation_parts property."""
        response = FormattedResponse(
            parts=["Part 1", "Part 2", "Part 3"],
            total_length=18,
            is_split=True,
        )

        assert response.continuation_parts == ["Part 2", "Part 3"]

    def test_continuation_parts_single_part(self):
        """Test continuation_parts with single part."""
        response = FormattedResponse(
            parts=["Part 1"],
            total_length=6,
            is_split=False,
        )

        assert response.continuation_parts == []


class TestTaskStatus:
    """Tests for TaskStatus enum."""

    def test_status_values(self):
        """Test that all expected status values exist."""
        assert TaskStatus.IN_PROGRESS == "in_progress"
        assert TaskStatus.BLOCKED == "blocked"
        assert TaskStatus.COMPLETE == "complete"
        assert TaskStatus.ERROR == "error"

    def test_status_badges_exist(self):
        """Test that all status values have corresponding badges."""
        from aegis.agents.formatters import STATUS_BADGES

        for status in TaskStatus:
            assert status in STATUS_BADGES
            assert isinstance(STATUS_BADGES[status], str)
            assert len(STATUS_BADGES[status]) > 0


class TestEdgeCases:
    """Tests for edge cases and error conditions."""

    def test_empty_content(self):
        """Test formatting empty content."""
        result = format_response("")

        assert len(result.parts) == 1
        assert result.primary == ""
        assert not result.is_split

    def test_whitespace_only_content(self):
        """Test formatting whitespace-only content."""
        result = format_response("   \n\n   ")

        assert len(result.parts) == 1
        assert result.primary.strip() == "" or "   \n\n   " in result.primary

    def test_special_characters(self):
        """Test formatting with special characters."""
        content = "Test with special chars: < > & \" ' \n\t"
        result = format_response(content)

        assert content in result.primary

    def test_unicode_content(self):
        """Test formatting with unicode content."""
        content = "Unicode test: 你好 🎉 café"
        result = format_response(content)

        assert content in result.primary

    def test_very_long_single_line(self):
        """Test formatting very long single line."""
        content = "x" * (MAX_COMMENT_LENGTH + 1000)
        result = format_response(content)

        assert result.is_split
        # Should split even without natural boundaries
        for part in result.parts:
            assert len(part) <= MAX_COMMENT_LENGTH

    def test_multiple_code_blocks(self):
        """Test formatting with multiple code blocks."""
        content = """
```python
def func1():
    pass
```

Some text

```python
def func2():
    pass
```
"""
        result = format_response(content)

        assert result.primary.count("```python") == 2

    def test_nested_markdown(self):
        """Test formatting with nested markdown structures."""
        content = """
# Header

- List item with **bold** and `code`
- Another item

```python
def test():
    # Comment
    return True
```
"""
        result = format_response(content)

        assert "# Header" in result.primary
        assert "**bold**" in result.primary
        assert "`code`" in result.primary
        assert "```python" in result.primary
