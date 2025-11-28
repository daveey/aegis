# End-to-End Integration Tests

This directory contains comprehensive end-to-end integration tests for the Aegis orchestration system. These tests validate the complete flow from Asana task creation through agent processing to response posting and execution logging.

## Test Coverage

### Core Test Classes

1. **TestEndToEndFlow** - Basic E2E workflow tests
   - `test_complete_flow_with_mock_agent` - Full flow with mocked agent execution
   - `test_error_handling_flow` - Error handling and recovery
   - `test_task_assignment_flow` - Task assignment and status updates
   - `test_concurrent_task_processing` - Concurrent task handling
   - `test_retry_mechanism` - Retry logic validation

2. **TestOrchestratorWorkflow** - Orchestrator component testing
   - `test_complete_orchestration_cycle` - Complete orchestration cycle validation
     - Phase 1: Task Discovery (Asana → Database sync)
     - Phase 2: Task Execution (Agent processing simulation)
     - Phase 3: Update Asana (Post results back)
     - Phase 4: State Verification (Validate consistency)

3. **TestDatabaseIntegration** - Database operations
   - `test_project_crud_operations` - Project CRUD operations
   - `test_task_execution_relationships` - Task/execution relationships and cascades

4. **TestCLIIntegration** - CLI command testing
   - `test_config_command` - Configuration display
   - `test_test_asana_command` - Asana connection validation

5. **TestLiveAgentIntegration** - Live API tests (optional)
   - `test_real_claude_execution` - Real Claude API execution

6. **TestFullOrchestratorFlow** - Full orchestrator tests (optional)
   - `test_orchestrator_task_discovery_and_execution` - Task discovery and execution
   - `test_orchestrator_handles_multiple_projects` - Multi-project handling
   - `test_execution_history_tracking` - Execution history tracking

## Prerequisites

### Required Environment Variables

Create a `.env.test` file or set these environment variables:

```bash
# Required for all tests
ASANA_ACCESS_TOKEN=your_asana_pat
ASANA_WORKSPACE_GID=your_workspace_gid
ASANA_TEST_PROJECT_GID=your_test_project_gid

# Optional - test database (defaults to postgresql://localhost/aegis_test)
TEST_DATABASE_URL=postgresql://localhost/aegis_test

# Optional - for live API tests
ANTHROPIC_API_KEY=your_anthropic_key
RUN_LIVE_TESTS=1

# Optional - for full orchestrator tests (requires Claude CLI)
RUN_ORCHESTRATOR_TESTS=1
```

### Test Infrastructure Setup

#### 1. Database Setup

**Option A: Docker Compose (Recommended)**
```bash
docker compose up -d postgres
```

**Option B: Local PostgreSQL**
```bash
# Install PostgreSQL
brew install postgresql@16

# Create test database
createdb aegis_test
```

#### 2. Asana Test Project

1. Create a dedicated test project in Asana
2. Get the project GID from the URL: `https://app.asana.com/0/{project_gid}/...`
3. Set `ASANA_TEST_PROJECT_GID` in your environment

**Important**: Use a dedicated test project - tests will create and delete tasks with `E2E_TEST_` prefix.

#### 3. Install Dependencies

```bash
# Install test dependencies
uv pip install -e ".[test]"

# Or with standard pip
pip install -e ".[test]"
```

## Running Tests

### Run All Integration Tests

```bash
# Run all integration tests
pytest tests/integration/test_e2e.py -v

# Run with coverage
pytest tests/integration/test_e2e.py --cov=aegis --cov-report=html
```

### Run Specific Test Classes

```bash
# Run only basic E2E flow tests
pytest tests/integration/test_e2e.py::TestEndToEndFlow -v

# Run only orchestrator workflow tests
pytest tests/integration/test_e2e.py::TestOrchestratorWorkflow -v

# Run only database tests
pytest tests/integration/test_e2e.py::TestDatabaseIntegration -v

# Run only CLI tests
pytest tests/integration/test_e2e.py::TestCLIIntegration -v
```

### Run Specific Tests

```bash
# Run single test
pytest tests/integration/test_e2e.py::TestEndToEndFlow::test_complete_flow_with_mock_agent -v

# Run complete orchestration cycle test
pytest tests/integration/test_e2e.py::TestOrchestratorWorkflow::test_complete_orchestration_cycle -v
```

### Run Optional Tests

```bash
# Run live API tests (incurs API costs)
RUN_LIVE_TESTS=1 pytest tests/integration/test_e2e.py::TestLiveAgentIntegration -v

# Run full orchestrator tests (requires Claude CLI)
RUN_ORCHESTRATOR_TESTS=1 pytest tests/integration/test_e2e.py::TestFullOrchestratorFlow -v
```

## CI/CD Integration

### GitHub Actions Example

```yaml
name: Integration Tests

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]

jobs:
  integration-tests:
    runs-on: ubuntu-latest

    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_PASSWORD: postgres
          POSTGRES_DB: aegis_test
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
        ports:
          - 5432:5432

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          pip install -e ".[test]"

      - name: Run integration tests
        env:
          ASANA_ACCESS_TOKEN: ${{ secrets.ASANA_ACCESS_TOKEN }}
          ASANA_WORKSPACE_GID: ${{ secrets.ASANA_WORKSPACE_GID }}
          ASANA_TEST_PROJECT_GID: ${{ secrets.ASANA_TEST_PROJECT_GID }}
          TEST_DATABASE_URL: postgresql://postgres:postgres@localhost:5432/aegis_test
        run: |
          pytest tests/integration/test_e2e.py -v --cov=aegis

      - name: Upload coverage
        uses: codecov/codecov-action@v3
        if: success()
```

### GitLab CI Example

```yaml
integration-tests:
  stage: test
  image: python:3.11

  services:
    - postgres:16

  variables:
    POSTGRES_DB: aegis_test
    POSTGRES_USER: postgres
    POSTGRES_PASSWORD: postgres
    TEST_DATABASE_URL: postgresql://postgres:postgres@postgres:5432/aegis_test

  before_script:
    - pip install -e ".[test]"

  script:
    - pytest tests/integration/test_e2e.py -v --cov=aegis --cov-report=xml

  coverage: '/(?i)total.*? (100(?:\.0+)?\%|[1-9]?\d(?:\.\d+)?\%)$/'

  artifacts:
    reports:
      coverage_report:
        coverage_format: cobertura
        path: coverage.xml
```

## Test Isolation and Cleanup

### Automatic Cleanup

Tests automatically clean up after themselves:

1. **Database**: Each test gets a fresh session; all tables are dropped after test session
2. **Asana Tasks**: Tasks with `E2E_TEST_` prefix are automatically marked complete and archived
3. **Test Fixtures**: Fixtures handle cleanup in their teardown phase

### Manual Cleanup

If tests are interrupted, you may need to manually clean up:

```bash
# Clean up Asana test tasks
# 1. Go to your test project in Asana
# 2. Filter for tasks starting with "E2E_TEST_"
# 3. Bulk select and delete/archive them

# Clean up test database
dropdb aegis_test
createdb aegis_test
```

## Troubleshooting

### Common Issues

#### 1. Missing Environment Variables
```
Error: Missing required test environment variables: ASANA_ACCESS_TOKEN
```
**Solution**: Set required environment variables in `.env` or export them

#### 2. Database Connection Error
```
Error: could not connect to server: Connection refused
```
**Solution**: Start PostgreSQL service or Docker container

#### 3. Test Project Not Found
```
Error: Project 'test_project_gid' not found in portfolio
```
**Solution**: Verify `ASANA_TEST_PROJECT_GID` is correct and accessible

#### 4. Rate Limiting
```
Error: 429 Too Many Requests
```
**Solution**: Tests include retry logic, but you may need to wait or reduce concurrency

### Debug Mode

Run tests with verbose output and logs:

```bash
# Verbose pytest output
pytest tests/integration/test_e2e.py -vv -s

# Show log output
pytest tests/integration/test_e2e.py --log-cli-level=DEBUG

# Keep test database for inspection
pytest tests/integration/test_e2e.py --keepdb
```

## Best Practices

### Writing New E2E Tests

1. **Use Fixtures**: Leverage existing fixtures for setup/teardown
2. **Prefix Test Tasks**: Always prefix test task names with `E2E_TEST_`
3. **Isolate Tests**: Each test should be independent and not rely on others
4. **Mock When Possible**: Use mocks for expensive operations (API calls, etc.)
5. **Clean Up**: Ensure cleanup happens even if test fails (use fixtures)

### Example Test Structure

```python
@pytest.mark.asyncio
async def test_new_feature(
    asana_client: AsanaClient,
    test_project: AsanaProject,
    test_task: AsanaTask,
    db_session: Session,
):
    """Test description.

    What this test validates:
    1. Step 1
    2. Step 2
    3. Step 3
    """
    # Arrange
    # Set up test data

    # Act
    # Execute the feature

    # Assert
    # Verify results

    # Cleanup handled by fixtures
```

## Performance Considerations

- **Basic Tests**: ~30 seconds (mocked, no real API calls)
- **Full Integration**: ~2-5 minutes (real Asana API, database operations)
- **Live API Tests**: ~5-10 minutes (includes Claude API calls)
- **Orchestrator Tests**: ~10-30 minutes (requires Claude CLI execution)

## Maintenance

### Updating Tests

When adding new features, update E2E tests to cover:

1. Happy path (success case)
2. Error handling (failure cases)
3. Edge cases (boundary conditions)
4. Integration points (cross-component interactions)

### Test Data Management

- Test tasks are automatically cleaned up
- Test database is recreated for each test session
- Consider adding seed data fixtures for complex scenarios

## Questions?

For questions about the tests:
1. Check existing test implementations for examples
2. Review the [Project Overview](../../design/PROJECT_OVERVIEW.md)
3. Check the [Task List](../../design/TASK_LIST.md) for planned features

## Future Enhancements

Planned improvements to the test suite:

- [ ] Performance benchmarking tests
- [ ] Load testing for concurrent task processing
- [ ] End-to-end tests with multiple agent types
- [ ] Integration with real vector database
- [ ] Snapshot testing for Asana comments
- [ ] Test data factories for easier test creation
