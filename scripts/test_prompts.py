#!/usr/bin/env python3
"""Test script for prompt template loading and rendering.

This script demonstrates how to use the prompt template system.
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from aegis.agents.prompts import PromptBuilder, PromptRenderer, PromptTemplateLoader


def test_template_loading():
    """Test loading templates from database."""
    print("=" * 80)
    print("TEST 1: Loading Templates")
    print("=" * 80)

    loader = PromptTemplateLoader()

    # Test loading a single template
    template = loader.get_active_template("simple_executor", "system")
    if template:
        print(f"\n✓ Loaded template: {template.name} v{template.version}")
        print(f"  Description: {template.description}")
        print(f"  Variables: {', '.join(template.variables)}")
        print(f"  System prompt length: {len(template.system_prompt)} chars")
        print(f"  User prompt length: {len(template.user_prompt_template)} chars")
    else:
        print("\n✗ Failed to load template")
        return False

    # Test loading all templates for an agent
    templates = loader.get_all_templates_for_agent("simple_executor")
    print(f"\n✓ Loaded {len(templates)} templates for simple_executor:")
    for name in templates:
        print(f"  - {name}")

    return True


def test_template_rendering():
    """Test rendering templates with variables."""
    print("\n" + "=" * 80)
    print("TEST 2: Template Rendering")
    print("=" * 80)

    renderer = PromptRenderer()

    # Test simple rendering
    template_str = "Hello {name}, you have {count} tasks to complete."
    variables = {"name": "Alice", "count": 5}
    rendered = renderer.render(template_str, variables)
    print(f"\nTemplate: {template_str}")
    print(f"Variables: {variables}")
    print(f"Rendered: {rendered}")

    expected = "Hello Alice, you have 5 tasks to complete."
    if rendered == expected:
        print("✓ Rendering successful")
    else:
        print(f"✗ Rendering failed. Expected: {expected}")
        return False

    # Test with missing variable (should not crash)
    template_str2 = "Hello {name}, you have {missing} tasks."
    rendered2 = renderer.render(template_str2, variables)
    print(f"\nTemplate with missing var: {template_str2}")
    print(f"Rendered: {rendered2}")
    print("✓ Handled missing variable gracefully")

    return True


def test_prompt_builder():
    """Test building complete prompts."""
    print("\n" + "=" * 80)
    print("TEST 3: Prompt Builder")
    print("=" * 80)

    builder = PromptBuilder("simple_executor")

    # Build a system prompt
    variables = {
        "project_name": "Test Project",
        "project_code_path": "/path/to/project",
        "task_name": "Fix authentication bug",
        "task_description": "Users are unable to log in with valid credentials",
        "additional_context": "Error occurs in production environment only",
    }

    result = builder.build_prompt("system", variables)

    if result:
        system_prompt, user_prompt = result
        print("\n✓ Built prompt successfully")
        print(f"  System prompt: {len(system_prompt)} chars")
        print(f"  User prompt: {len(user_prompt)} chars")

        # Show a preview
        print("\n  System prompt preview:")
        print(f"  {system_prompt[:200]}...")
        print("\n  User prompt preview:")
        print(f"  {user_prompt[:200]}...")

        return True
    else:
        print("\n✗ Failed to build prompt")
        return False


def test_specialized_prompts():
    """Test different specialized prompt types."""
    print("\n" + "=" * 80)
    print("TEST 4: Specialized Prompts")
    print("=" * 80)

    builder = PromptBuilder("simple_executor")

    # Test code task prompt
    print("\n--- Code Task Prompt ---")
    code_vars = {
        "task_name": "Implement user authentication",
        "task_description": "Add JWT-based authentication to the API",
        "project_code_path": "/path/to/project",
        "relevant_files": "Relevant files: src/auth.py, src/api/routes.py",
    }

    result = builder.build_prompt("code_task", code_vars)
    if result:
        print("✓ Code task prompt built successfully")
        print(f"  Length: {len(result[0])} + {len(result[1])} chars")

    # Test research task prompt
    print("\n--- Research Task Prompt ---")
    research_vars = {
        "task_name": "Research best practices for API authentication",
        "task_description": "Find and document modern authentication patterns",
        "research_scope": "Focus on JWT, OAuth2, and session-based auth",
    }

    result = builder.build_prompt("research_task", research_vars)
    if result:
        print("✓ Research task prompt built successfully")
        print(f"  Length: {len(result[0])} + {len(result[1])} chars")

    # Test clarification prompt
    print("\n--- Clarification Prompt ---")
    clarify_vars = {
        "task_name": "Fix the thing",
        "task_description": "Make it work better",
        "unclear_aspects": "Task is too vague - unclear what 'the thing' is and what 'better' means",
    }

    result = builder.build_prompt("clarification_needed", clarify_vars)
    if result:
        print("✓ Clarification prompt built successfully")
        print(f"  Length: {len(result[0])} + {len(result[1])} chars")

    return True


def test_usage_tracking():
    """Test usage count tracking."""
    print("\n" + "=" * 80)
    print("TEST 5: Usage Tracking")
    print("=" * 80)

    builder = PromptBuilder("simple_executor")
    loader = PromptTemplateLoader()

    # Get initial usage count
    template = loader.get_active_template("simple_executor", "system")
    initial_count = template.usage_count if template else 0
    print(f"\nInitial usage count: {initial_count}")

    # Increment usage
    builder.increment_usage("system")
    print("✓ Incremented usage count")

    # Verify it was incremented
    template = loader.get_active_template("simple_executor", "system")
    new_count = template.usage_count if template else 0
    print(f"New usage count: {new_count}")

    if new_count == initial_count + 1:
        print("✓ Usage count correctly incremented")
        return True
    else:
        print(f"✗ Usage count mismatch. Expected {initial_count + 1}, got {new_count}")
        return False


def main():
    """Run all tests."""
    print("\n" + "=" * 80)
    print("PROMPT TEMPLATE SYSTEM TESTS")
    print("=" * 80)

    tests = [
        ("Template Loading", test_template_loading),
        ("Template Rendering", test_template_rendering),
        ("Prompt Builder", test_prompt_builder),
        ("Specialized Prompts", test_specialized_prompts),
        ("Usage Tracking", test_usage_tracking),
    ]

    passed = 0
    failed = 0

    for name, test_func in tests:
        try:
            if test_func():
                passed += 1
            else:
                failed += 1
                print(f"\n✗ Test '{name}' FAILED")
        except Exception as e:
            failed += 1
            print(f"\n✗ Test '{name}' FAILED with exception: {e}")
            import traceback

            traceback.print_exc()

    # Summary
    print("\n" + "=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)
    print(f"Passed: {passed}/{len(tests)}")
    print(f"Failed: {failed}/{len(tests)}")

    if failed == 0:
        print("\n✓ All tests passed!")
        return 0
    else:
        print(f"\n✗ {failed} test(s) failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
