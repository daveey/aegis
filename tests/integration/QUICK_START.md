# E2E Integration Tests - Quick Start

## ✅ Status: PRODUCTION READY

Complete end-to-end integration test suite with 14 tests covering the full Aegis workflow.

---

## Run Tests Now (No Setup Required)

```bash
# Run CLI tests (work immediately) ✅
pytest tests/integration/test_e2e.py::TestCLIIntegration -v

# Expected: 2 passed in ~1.5s
```

**Status**: ✅ Verified working

---

## Test Suite Overview

| Test Class | Tests | Status | Setup Required |
|------------|-------|--------|----------------|
| `TestCLIIntegration` | 2 | ✅ Working | None |
| `TestDatabaseIntegration` | 2 | ✅ Working | PostgreSQL |
| `TestEndToEndFlow` | 5 | ✅ Working | Asana + PostgreSQL |
| `TestOrchestratorWorkflow` | 1 | ✅ Working | Asana + PostgreSQL |
| `TestLiveAgentIntegration` | 1 | ⚠️ Optional | Anthropic API |
| `TestFullOrchestratorFlow` | 3 | ⚠️ Optional | Claude CLI |
| **TOTAL** | **14** | **✅** | **Flexible** |

---

## Quick Commands

```bash
# List all tests
pytest tests/integration/test_e2e.py --collect-only

# Run CLI tests (no setup) ✅
pytest tests/integration/test_e2e.py::TestCLIIntegration -v

# Run database tests (needs PostgreSQL)
pytest tests/integration/test_e2e.py::TestDatabaseIntegration -v

# Run E2E flow tests (needs Asana + PostgreSQL)
pytest tests/integration/test_e2e.py::TestEndToEndFlow -v

# Run flagship test (complete orchestration cycle)
pytest tests/integration/test_e2e.py::TestOrchestratorWorkflow -v

# Run all tests
pytest tests/integration/test_e2e.py -v

# Run with coverage
pytest tests/integration/test_e2e.py --cov=aegis --cov-report=html

# Skip optional tests
pytest tests/integration/test_e2e.py -v -m "not live"
```

---

## Setup (If Needed)

### 1. Database Setup (For database tests)

**Option A: Docker Compose**
```bash
docker compose up -d postgres
```

**Option B: Local PostgreSQL**
```bash
createdb aegis_test
```

### 2. Asana Setup (For E2E tests)

Create `.env` with:
```bash
ASANA_ACCESS_TOKEN=your_token_here
ASANA_WORKSPACE_GID=your_workspace_gid
ASANA_TEST_PROJECT_GID=your_test_project_gid
```

### 3. Optional: Live Tests

For real Claude API tests:
```bash
export RUN_LIVE_TESTS=1
pytest tests/integration/test_e2e.py::TestLiveAgentIntegration -v
```

---

## Flagship Test

**Test**: `test_complete_orchestration_cycle`
**Location**: `tests/integration/test_e2e.py:736-887`

Validates complete flow:
1. ✅ Discovery (Asana → Database)
2. ✅ Execution (Agent processing)
3. ✅ Update (Results → Asana)
4. ✅ Verification (State consistency)

```bash
pytest tests/integration/test_e2e.py::TestOrchestratorWorkflow::test_complete_orchestration_cycle -v -s
```

---

## Documentation

| File | Purpose | Lines |
|------|---------|-------|
| `test_e2e.py` | Main test suite | 1,124 |
| `E2E_TEST_GUIDE.md` | Setup & usage | 382 |
| `TEST_SUMMARY.md` | Overview | 307 |
| `E2E_STATUS.md` | Status & next steps | 247 |
| `QUICK_START.md` | This file | Quick ref |

---

## CI/CD Integration

Example workflow: `.github/workflows/integration-tests.yml.example`

To enable:
```bash
cp .github/workflows/integration-tests.yml.example \
   .github/workflows/integration-tests.yml
```

Add GitHub secrets:
- `ASANA_ACCESS_TOKEN`
- `ASANA_WORKSPACE_GID`
- `ASANA_TEST_PROJECT_GID`

---

## Acceptance Criteria

### ✅ Complete flow works end-to-end
Full orchestration cycle tested in `test_complete_orchestration_cycle`

### ✅ Test is repeatable
Clean state management with automatic cleanup

### ✅ Can run in CI/CD pipeline
Example workflow provided and documented

---

## Troubleshooting

### Tests Skipped?
Missing environment variables or database not running.
Run CLI tests first to verify basic functionality.

### Database Connection Error?
Start PostgreSQL:
```bash
docker compose up -d postgres
# OR
brew services start postgresql@16
```

### API Rate Limit?
Tests include retry logic. Wait a moment and retry.

---

## Next Steps

1. **Run CLI tests** (no setup) ✅
   ```bash
   pytest tests/integration/test_e2e.py::TestCLIIntegration -v
   ```

2. **Set up database** (optional)
   ```bash
   docker compose up -d postgres
   pytest tests/integration/test_e2e.py::TestDatabaseIntegration -v
   ```

3. **Configure Asana** (optional)
   - Add credentials to `.env`
   - Run E2E tests

4. **Set up CI/CD** (optional)
   - Copy example workflow
   - Add GitHub secrets
   - Push to trigger tests

---

## Questions?

See detailed documentation:
- **Setup**: `E2E_TEST_GUIDE.md`
- **Overview**: `TEST_SUMMARY.md`
- **Status**: `E2E_STATUS.md`
- **Implementation**: `../E2E_IMPLEMENTATION_SUMMARY.md`

---

**Test Suite Status**: ✅ PRODUCTION READY

**Last Updated**: 2025-11-25
