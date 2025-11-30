#!/usr/bin/env python3
"""Setup a new GitHub project with all required files.

Creates project structure, CI/CD workflows, and optionally uses Claude
to analyze design documents and generate initial scaffolding.
"""

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger()


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Setup a new GitHub project with all required files"
    )
    parser.add_argument(
        "--project-name",
        required=True,
        help="Name of the project",
    )
    parser.add_argument(
        "--github-url",
        help="GitHub repository URL (optional)",
    )
    parser.add_argument(
        "--github-repo",
        help="GitHub repository in format owner/repo (optional)",
    )
    parser.add_argument(
        "--design-doc",
        help="Path to design document (optional)",
    )
    parser.add_argument(
        "--project-dir",
        default=".",
        help="Project directory (default: current directory)",
    )
    parser.add_argument(
        "--skip-claude",
        action="store_true",
        help="Skip Claude analysis of design doc",
    )
    parser.add_argument(
        "--language",
        default="python",
        choices=["python", "typescript", "go", "rust"],
        help="Primary programming language (default: python)",
    )
    return parser.parse_args()


def create_directory_structure(project_dir: Path, language: str) -> None:
    """Create basic directory structure.

    Args:
        project_dir: Root project directory
        language: Programming language
    """
    logger.info("creating_directory_structure", project_dir=str(project_dir))

    if language == "python":
        dirs = [
            project_dir / "src",
            project_dir / "tests" / "unit",
            project_dir / "tests" / "integration",
            project_dir / "docs",
            project_dir / ".github" / "workflows",
        ]
    elif language == "typescript":
        dirs = [
            project_dir / "src",
            project_dir / "tests",
            project_dir / "docs",
            project_dir / ".github" / "workflows",
        ]
    elif language == "go":
        dirs = [
            project_dir / "cmd",
            project_dir / "pkg",
            project_dir / "internal",
            project_dir / "tests",
            project_dir / "docs",
            project_dir / ".github" / "workflows",
        ]
    elif language == "rust":
        dirs = [
            project_dir / "src",
            project_dir / "tests",
            project_dir / "docs",
            project_dir / ".github" / "workflows",
        ]
    else:
        dirs = [
            project_dir / "src",
            project_dir / "tests",
            project_dir / "docs",
            project_dir / ".github" / "workflows",
        ]

    for dir_path in dirs:
        dir_path.mkdir(parents=True, exist_ok=True)
        logger.debug("created_directory", path=str(dir_path))

    print(f"✓ Created directory structure for {language} project")


def create_gitignore(project_dir: Path, language: str) -> None:
    """Create .gitignore file.

    Args:
        project_dir: Root project directory
        language: Programming language
    """
    logger.info("creating_gitignore", language=language)

    gitignore_templates = {
        "python": """# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
build/
develop-eggs/
dist/
downloads/
eggs/
.eggs/
lib/
lib64/
parts/
sdist/
var/
wheels/
*.egg-info/
.installed.cfg
*.egg

# Virtual environments
venv/
env/
ENV/
.venv

# IDEs
.vscode/
.idea/
*.swp
*.swo
*~

# Testing
.pytest_cache/
.coverage
htmlcov/
.tox/

# Environment
.env
.env.local

# Logs
*.log
logs/

# OS
.DS_Store
Thumbs.db
""",
        "typescript": """# Node
node_modules/
npm-debug.log*
yarn-debug.log*
yarn-error.log*
lerna-debug.log*

# Build
dist/
build/
*.tsbuildinfo

# IDEs
.vscode/
.idea/
*.swp
*.swo
*~

# Testing
coverage/
.nyc_output/

# Environment
.env
.env.local

# Logs
*.log
logs/

# OS
.DS_Store
Thumbs.db
""",
        "go": """# Go
*.exe
*.exe~
*.dll
*.so
*.dylib
*.test
*.out
go.work

# Build
bin/
dist/

# IDEs
.vscode/
.idea/
*.swp
*.swo
*~

# Testing
coverage.txt
*.coverprofile

# Environment
.env
.env.local

# Logs
*.log
logs/

# OS
.DS_Store
Thumbs.db
""",
        "rust": """# Rust
/target
**/*.rs.bk
Cargo.lock

# IDEs
.vscode/
.idea/
*.swp
*.swo
*~

# Environment
.env
.env.local

# Logs
*.log
logs/

# OS
.DS_Store
Thumbs.db
""",
    }

    gitignore_path = project_dir / ".gitignore"
    gitignore_path.write_text(gitignore_templates.get(language, gitignore_templates["python"]))

    logger.info("created_gitignore", path=str(gitignore_path))
    print("✓ Created .gitignore")


def create_github_actions_ci(project_dir: Path, language: str) -> None:
    """Create GitHub Actions CI workflow.

    Args:
        project_dir: Root project directory
        language: Programming language
    """
    logger.info("creating_github_actions_ci", language=language)

    ci_templates = {
        "python": """name: CI

on:
  push:
    branches: [ main, master ]
  pull_request:
    branches: [ main, master ]

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.11", "3.12"]

    steps:
    - uses: actions/checkout@v4

    - name: Set up Python ${{ matrix.python-version }}
      uses: actions/setup-python@v5
      with:
        python-version: ${{ matrix.python-version }}

    - name: Install uv
      run: |
        curl -LsSf https://astral.sh/uv/install.sh | sh
        echo "$HOME/.cargo/bin" >> $GITHUB_PATH

    - name: Install dependencies
      run: |
        uv venv
        source .venv/bin/activate
        uv pip install -e ".[dev]"

    - name: Run tests
      run: |
        source .venv/bin/activate
        pytest tests/ -v --cov=src --cov-report=xml

    - name: Upload coverage
      uses: codecov/codecov-action@v4
      with:
        file: ./coverage.xml
        fail_ci_if_error: false
""",
        "typescript": """name: CI

on:
  push:
    branches: [ main, master ]
  pull_request:
    branches: [ main, master ]

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        node-version: [18.x, 20.x]

    steps:
    - uses: actions/checkout@v4

    - name: Use Node.js ${{ matrix.node-version }}
      uses: actions/setup-node@v4
      with:
        node-version: ${{ matrix.node-version }}

    - name: Install dependencies
      run: npm ci

    - name: Run linter
      run: npm run lint

    - name: Run tests
      run: npm test

    - name: Build
      run: npm run build
""",
        "go": """name: CI

on:
  push:
    branches: [ main, master ]
  pull_request:
    branches: [ main, master ]

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        go-version: ['1.21', '1.22']

    steps:
    - uses: actions/checkout@v4

    - name: Set up Go ${{ matrix.go-version }}
      uses: actions/setup-go@v5
      with:
        go-version: ${{ matrix.go-version }}

    - name: Install dependencies
      run: go mod download

    - name: Run tests
      run: go test -v -race -coverprofile=coverage.txt -covermode=atomic ./...

    - name: Upload coverage
      uses: codecov/codecov-action@v4
      with:
        file: ./coverage.txt
        fail_ci_if_error: false
""",
        "rust": """name: CI

on:
  push:
    branches: [ main, master ]
  pull_request:
    branches: [ main, master ]

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        rust: [stable, beta]

    steps:
    - uses: actions/checkout@v4

    - name: Install Rust ${{ matrix.rust }}
      uses: actions-rs/toolchain@v1
      with:
        toolchain: ${{ matrix.rust }}
        override: true

    - name: Run tests
      run: cargo test --verbose

    - name: Run clippy
      run: cargo clippy -- -D warnings

    - name: Check formatting
      run: cargo fmt -- --check
""",
    }

    ci_path = project_dir / ".github" / "workflows" / "ci.yml"
    ci_path.write_text(ci_templates.get(language, ci_templates["python"]))

    logger.info("created_github_actions_ci", path=str(ci_path))
    print("✓ Created GitHub Actions CI workflow")


def create_project_config(project_dir: Path, project_name: str, language: str) -> None:
    """Create project configuration file.

    Args:
        project_dir: Root project directory
        project_name: Name of the project
        language: Programming language
    """
    logger.info("creating_project_config", language=language)

    if language == "python":
        config_path = project_dir / "pyproject.toml"
        config_content = f"""[project]
name = "{project_name}"
version = "0.1.0"
description = "A new project"
readme = "README.md"
requires-python = ">=3.11"
dependencies = []

[project.optional-dependencies]
dev = [
    "pytest>=7.0.0",
    "pytest-asyncio>=0.21.0",
    "pytest-cov>=4.0.0",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
"""
        config_path.write_text(config_content)
        print("✓ Created pyproject.toml")

    elif language == "typescript":
        config_path = project_dir / "package.json"
        config_content = json.dumps(
            {
                "name": project_name,
                "version": "0.1.0",
                "description": "A new project",
                "main": "dist/index.js",
                "types": "dist/index.d.ts",
                "scripts": {
                    "build": "tsc",
                    "test": "jest",
                    "lint": "eslint src/**/*.ts",
                },
                "devDependencies": {
                    "@types/node": "^20.0.0",
                    "typescript": "^5.0.0",
                    "jest": "^29.0.0",
                    "@types/jest": "^29.0.0",
                    "ts-jest": "^29.0.0",
                    "eslint": "^8.0.0",
                },
            },
            indent=2,
        )
        config_path.write_text(config_content + "\n")
        print("✓ Created package.json")

    elif language == "go":
        subprocess.run(
            ["go", "mod", "init", f"github.com/username/{project_name}"],
            cwd=project_dir,
            check=True,
        )
        print("✓ Created go.mod")

    elif language == "rust":
        subprocess.run(
            ["cargo", "init", "--name", project_name],
            cwd=project_dir,
            check=True,
        )
        print("✓ Created Cargo.toml")


def analyze_design_doc_with_claude(
    design_doc_path: Path, project_name: str, language: str
) -> dict[str, Any]:
    """Use Claude to analyze design document and suggest project structure.

    Args:
        design_doc_path: Path to design document
        project_name: Name of the project
        language: Programming language

    Returns:
        Dict with analysis results including:
        - description: Project description
        - architecture: Architecture overview
        - modules: Suggested modules/packages
        - dependencies: Required dependencies
    """
    logger.info("analyzing_design_doc_with_claude", design_doc_path=str(design_doc_path))

    # Create a prompt for Claude
    prompt = f"""Analyze this design document for a {language} project named "{project_name}".

Provide a structured analysis in JSON format with:
1. description: A brief 1-2 sentence project description
2. architecture: High-level architecture overview
3. modules: List of suggested modules/packages to create
4. dependencies: List of required third-party dependencies
5. readme_content: Complete README.md content in markdown

Design Document:
{design_doc_path.read_text()}

Respond with ONLY valid JSON, no additional text."""

    try:
        # Run Claude Code in headless mode
        result = subprocess.run(
            [
                "claude",
                "-p",
                "--dangerously-skip-permissions",
            ],
            input=prompt,
            capture_output=True,
            text=True,
            check=True,
        )

        # Parse JSON response
        output = result.stdout.strip()
        # Find JSON in output (may have surrounding text)
        json_start = output.find("{")
        json_end = output.rfind("}") + 1
        if json_start >= 0 and json_end > json_start:
            json_str = output[json_start:json_end]
            analysis = json.loads(json_str)
            logger.info("claude_analysis_complete")
            return analysis
        else:
            logger.warning("no_json_in_claude_response")
            return _default_analysis(project_name, language)

    except (subprocess.CalledProcessError, json.JSONDecodeError) as e:
        logger.error("claude_analysis_failed", error=str(e))
        print(f"⚠ Claude analysis failed, using default structure: {e}")
        return _default_analysis(project_name, language)


def _default_analysis(project_name: str, language: str) -> dict[str, Any]:
    """Return default analysis structure.

    Args:
        project_name: Name of the project
        language: Programming language

    Returns:
        Default analysis dict
    """
    return {
        "description": f"A new {language} project",
        "architecture": "Standard project structure",
        "modules": ["core", "utils"],
        "dependencies": [],
        "readme_content": f"""# {project_name}

A new {language} project.

## Installation

Install dependencies:

```bash
# Instructions here
```

## Usage

```bash
# Usage examples here
```

## Development

Run tests:

```bash
# Test commands here
```

## License

MIT
""",
    }


def create_readme(
    project_dir: Path,
    project_name: str,
    github_url: str | None,
    analysis: dict[str, Any] | None,
) -> None:
    """Create README.md file.

    Args:
        project_dir: Root project directory
        project_name: Name of the project
        github_url: GitHub repository URL (optional)
        analysis: Claude analysis results (optional)
    """
    logger.info("creating_readme")

    if analysis and "readme_content" in analysis:
        readme_content = analysis["readme_content"]
    else:
        readme_content = f"""# {project_name}

{analysis["description"] if analysis else "A new project"}

## Installation

Install dependencies:

```bash
# Instructions here
```

## Usage

```bash
# Usage examples here
```

## Development

Run tests:

```bash
# Test commands here
```

## License

MIT
"""

    readme_path = project_dir / "README.md"
    readme_path.write_text(readme_content)

    logger.info("created_readme", path=str(readme_path))
    print("✓ Created README.md")


def create_design_doc(project_dir: Path, design_doc_path: Path | None) -> None:
    """Create design.md file from provided design doc.

    Args:
        project_dir: Root project directory
        design_doc_path: Path to source design document (optional)
    """
    if not design_doc_path:
        logger.debug("no_design_doc_provided")
        return

    logger.info("creating_design_doc", source=str(design_doc_path))

    design_path = project_dir / "design.md"
    design_path.write_text(design_doc_path.read_text())

    logger.info("created_design_doc", path=str(design_path))
    print("✓ Created design.md")


def create_initial_code(
    project_dir: Path, project_name: str, language: str, analysis: dict[str, Any] | None
) -> None:
    """Create initial code scaffolding.

    Args:
        project_dir: Root project directory
        project_name: Name of the project
        language: Programming language
        analysis: Claude analysis results (optional)
    """
    logger.info("creating_initial_code", language=language)

    if language == "python":
        # Create __init__.py files
        src_dir = project_dir / "src" / project_name.replace("-", "_")
        src_dir.mkdir(parents=True, exist_ok=True)

        init_file = src_dir / "__init__.py"
        init_file.write_text(f'"""Root package for {project_name}."""\n\n__version__ = "0.1.0"\n')

        # Create main.py
        main_file = src_dir / "main.py"
        main_file.write_text("""\"\"\"Main entry point.\"\"\"


def main() -> None:
    \"\"\"Main function.\"\"\"
    print("Hello from {project_name}!")


if __name__ == "__main__":
    main()
""".format(project_name=project_name))

        # Create test file
        test_file = project_dir / "tests" / "test_main.py"
        test_file.write_text(f"""\"\"\"Tests for main module.\"\"\"

from {project_name.replace("-", "_")}.main import main


def test_main():
    \"\"\"Test main function.\"\"\"
    # Add your tests here
    pass
""")

        print(f"✓ Created initial Python code in src/{project_name.replace('-', '_')}/")

    elif language == "typescript":
        # Create index.ts
        index_file = project_dir / "src" / "index.ts"
        index_file.write_text(f"""/**
 * Main entry point for {project_name}
 */

export function main(): void {{
  console.log("Hello from {project_name}!");
}}

main();
""")

        # Create tsconfig.json
        tsconfig_file = project_dir / "tsconfig.json"
        tsconfig_file.write_text(json.dumps(
            {
                "compilerOptions": {
                    "target": "ES2022",
                    "module": "commonjs",
                    "outDir": "./dist",
                    "rootDir": "./src",
                    "strict": True,
                    "esModuleInterop": True,
                    "skipLibCheck": True,
                    "forceConsistentCasingInFileNames": True,
                    "declaration": True,
                },
                "include": ["src/**/*"],
                "exclude": ["node_modules", "dist"],
            },
            indent=2,
        ))

        print("✓ Created initial TypeScript code in src/")

    elif language == "go":
        # Create main.go
        main_file = project_dir / "cmd" / project_name / "main.go"
        main_file.parent.mkdir(parents=True, exist_ok=True)
        main_file.write_text(f"""package main

import "fmt"

func main() {{
    fmt.Println("Hello from {project_name}!")
}}
""")

        print(f"✓ Created initial Go code in cmd/{project_name}/")

    elif language == "rust":
        # Cargo init already creates src/main.rs
        print("✓ Initial Rust code created by cargo init")


def git_commit_all(project_dir: Path, message: str) -> None:
    """Commit all files to git.

    Args:
        project_dir: Root project directory
        message: Commit message
    """
    logger.info("git_commit_all", message=message)

    try:
        # Check if git repo exists
        subprocess.run(
            ["git", "rev-parse", "--git-dir"],
            cwd=project_dir,
            check=True,
            capture_output=True,
        )
    except subprocess.CalledProcessError:
        # Initialize git repo
        subprocess.run(["git", "init"], cwd=project_dir, check=True)
        print("✓ Initialized git repository")

    # Add all files
    subprocess.run(["git", "add", "."], cwd=project_dir, check=True)

    # Commit
    subprocess.run(
        ["git", "commit", "-m", message],
        cwd=project_dir,
        check=True,
    )

    logger.info("git_committed")
    print(f"✓ Committed: {message}")


def main() -> None:
    """Main entry point."""
    args = parse_args()

    project_dir = Path(args.project_dir).resolve()
    project_name = args.project_name
    language = args.language

    print(f"\n🚀 Setting up {project_name} ({language} project)\n")

    # Create directory structure
    create_directory_structure(project_dir, language)

    # Create .gitignore
    create_gitignore(project_dir, language)

    # Create GitHub Actions CI
    create_github_actions_ci(project_dir, language)

    # Create project config
    create_project_config(project_dir, project_name, language)

    # Analyze design doc with Claude (if provided and not skipped)
    analysis = None
    if args.design_doc and not args.skip_claude:
        design_doc_path = Path(args.design_doc)
        if design_doc_path.exists():
            print("\n🤖 Analyzing design document with Claude...")
            analysis = analyze_design_doc_with_claude(design_doc_path, project_name, language)
            print("✓ Design document analysis complete")
        else:
            print(f"⚠ Design document not found: {design_doc_path}")

    # Create README
    create_readme(project_dir, project_name, args.github_url, analysis)

    # Create design.md (if provided)
    if args.design_doc:
        design_doc_path = Path(args.design_doc)
        if design_doc_path.exists():
            create_design_doc(project_dir, design_doc_path)

    # Create initial code
    create_initial_code(project_dir, project_name, language, analysis)

    # Git commit
    try:
        git_commit_all(
            project_dir,
            f"Initial project setup: {project_name}\n\n"
            f"- Added project structure\n"
            f"- Added GitHub Actions CI\n"
            f"- Added README and documentation\n"
            f"{'- Analyzed design document with Claude' + chr(10) if analysis else ''}"
            f"\n🤖 Generated with Aegis",
        )
    except subprocess.CalledProcessError as e:
        logger.warning("git_commit_failed", error=str(e))
        print("⚠ Git commit failed (this is okay if remote push is pending)")

    print(f"\n✅ Project setup complete!\n")
    print(f"Next steps:")
    print(f"  cd {project_dir}")
    if language == "python":
        print(f"  uv venv && source .venv/bin/activate")
        print(f"  uv pip install -e '.[dev]'")
    elif language == "typescript":
        print(f"  npm install")
    elif language == "go":
        print(f"  go mod tidy")
    elif language == "rust":
        print(f"  cargo build")

    if args.github_url:
        print(f"\n  Git remote: {args.github_url}")
        print(f"  git push origin main")


if __name__ == "__main__":
    main()
