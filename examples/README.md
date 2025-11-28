# Aegis Examples

This directory contains example scripts demonstrating various features of the Aegis orchestration system.

## Available Examples

### `prioritization_example.py`

Demonstrates the intelligent task prioritization system.

**Features shown:**
- Multi-factor task scoring
- Due date urgency handling
- Dependency management (parent/child tasks)
- User-assigned priorities
- Project importance
- Anti-starvation mechanism
- Custom weight configurations

**Run it:**
```bash
python examples/prioritization_example.py
```

**Output:**
- Prioritized task list with score breakdowns
- Comparison of different weight configurations
- Recommended next task to work on

## Adding New Examples

When adding new examples:

1. Create a new `.py` file in this directory
2. Add a shebang: `#!/usr/bin/env python3`
3. Include a module docstring explaining what the example demonstrates
4. Make it executable: `chmod +x examples/your_example.py`
5. Update this README with a description

## Running Examples

From the project root:

```bash
# Run a specific example
python examples/prioritization_example.py

# Or make it executable and run directly
chmod +x examples/prioritization_example.py
./examples/prioritization_example.py
```

## Dependencies

All examples use the Aegis package. Ensure you have:

1. Installed the project: `pip install -e .`
2. Or have the project root in your PYTHONPATH

Some examples may require additional configuration (e.g., `.env` file with API keys).
