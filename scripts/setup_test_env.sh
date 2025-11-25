#!/bin/bash
# Setup script for Aegis integration test environment

set -e  # Exit on error

echo "=========================================="
echo "Aegis Integration Test Environment Setup"
echo "=========================================="
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Check for required commands
check_command() {
    if ! command -v $1 &> /dev/null; then
        echo -e "${RED}Error: $1 is not installed${NC}"
        return 1
    else
        echo -e "${GREEN}✓${NC} $1 is installed"
        return 0
    fi
}

echo "Checking prerequisites..."
check_command docker || exit 1
check_command python3 || exit 1
check_command psql || echo -e "${YELLOW}⚠ psql not installed (optional)${NC}"

echo ""
echo "=========================================="
echo "Step 1: Setting up Test Database"
echo "=========================================="

# Check if postgres container exists
if docker ps -a | grep -q "aegis-test-postgres"; then
    echo -e "${YELLOW}Test PostgreSQL container already exists${NC}"
    echo "Do you want to:"
    echo "  1) Use existing container"
    echo "  2) Remove and recreate"
    read -p "Choice (1/2): " choice

    if [ "$choice" = "2" ]; then
        echo "Stopping and removing existing container..."
        docker stop aegis-test-postgres 2>/dev/null || true
        docker rm aegis-test-postgres 2>/dev/null || true

        echo "Creating new test PostgreSQL container..."
        docker run --name aegis-test-postgres \
            -e POSTGRES_PASSWORD=postgres \
            -e POSTGRES_DB=aegis_test \
            -p 5433:5432 \
            -d postgres:16

        echo -e "${GREEN}✓${NC} New test database container created"
    else
        # Start if not running
        if ! docker ps | grep -q "aegis-test-postgres"; then
            echo "Starting existing container..."
            docker start aegis-test-postgres
        fi
        echo -e "${GREEN}✓${NC} Using existing test database"
    fi
else
    echo "Creating test PostgreSQL container..."
    docker run --name aegis-test-postgres \
        -e POSTGRES_PASSWORD=postgres \
        -e POSTGRES_DB=aegis_test \
        -p 5433:5432 \
        -d postgres:16

    echo -e "${GREEN}✓${NC} Test database container created"
fi

# Wait for postgres to be ready
echo "Waiting for PostgreSQL to be ready..."
for i in {1..30}; do
    if docker exec aegis-test-postgres pg_isready -U postgres &>/dev/null; then
        echo -e "${GREEN}✓${NC} PostgreSQL is ready"
        break
    fi
    sleep 1
    if [ $i -eq 30 ]; then
        echo -e "${RED}Error: PostgreSQL failed to start${NC}"
        exit 1
    fi
done

echo ""
echo "=========================================="
echo "Step 2: Setting up Redis (optional)"
echo "=========================================="

read -p "Set up Redis for testing? (y/n): " setup_redis

if [ "$setup_redis" = "y" ]; then
    if docker ps -a | grep -q "aegis-test-redis"; then
        echo -e "${YELLOW}Test Redis container already exists${NC}"
        if ! docker ps | grep -q "aegis-test-redis"; then
            docker start aegis-test-redis
        fi
    else
        echo "Creating test Redis container..."
        docker run --name aegis-test-redis \
            -p 6380:6379 \
            -d redis:7
    fi
    echo -e "${GREEN}✓${NC} Redis ready"
fi

echo ""
echo "=========================================="
echo "Step 3: Installing Python Dependencies"
echo "=========================================="

if [ -f "pyproject.toml" ]; then
    echo "Installing test dependencies..."
    pip install -e ".[test]" || {
        echo -e "${RED}Error: Failed to install dependencies${NC}"
        exit 1
    }
    echo -e "${GREEN}✓${NC} Dependencies installed"
else
    echo -e "${RED}Error: pyproject.toml not found. Are you in the project root?${NC}"
    exit 1
fi

echo ""
echo "=========================================="
echo "Step 4: Environment Configuration"
echo "=========================================="

if [ -f ".env.test" ]; then
    echo -e "${YELLOW}.env.test already exists${NC}"
    echo "Please review and update the following values:"
    echo ""
    echo "  ASANA_ACCESS_TOKEN=<your token>"
    echo "  ASANA_WORKSPACE_GID=<your workspace>"
    echo "  ASANA_TEST_PROJECT_GID=<your test project>"
    echo ""
else
    echo -e "${YELLOW}Creating .env.test from template...${NC}"
    if [ -f ".env.test.example" ]; then
        cp .env.test.example .env.test
    fi
    echo -e "${YELLOW}Please edit .env.test with your Asana credentials${NC}"
fi

echo ""
echo "=========================================="
echo "Step 5: Database Schema Setup"
echo "=========================================="

echo "Testing database connection..."
if docker exec aegis-test-postgres psql -U postgres -d aegis_test -c "SELECT 1" &>/dev/null; then
    echo -e "${GREEN}✓${NC} Database connection successful"
    echo ""
    echo "Note: Database tables will be created automatically when tests run"
else
    echo -e "${RED}Error: Cannot connect to test database${NC}"
    exit 1
fi

echo ""
echo "=========================================="
echo "Setup Complete!"
echo "=========================================="
echo ""
echo -e "${GREEN}✓${NC} Test database running on localhost:5433"
if [ "$setup_redis" = "y" ]; then
    echo -e "${GREEN}✓${NC} Redis running on localhost:6380"
fi
echo ""
echo "Next steps:"
echo ""
echo "  1. Edit .env.test with your Asana credentials:"
echo -e "     ${BLUE}vim .env.test${NC}"
echo ""
echo "  2. Create a test project in Asana and add the GID to .env.test"
echo ""
echo "  3. Run the tests:"
echo -e "     ${BLUE}export \$(cat .env.test | xargs)${NC}"
echo -e "     ${BLUE}pytest tests/integration/test_e2e.py -v${NC}"
echo ""
echo "  4. (Optional) Clean up test tasks when done:"
echo -e "     ${BLUE}python scripts/cleanup_test_tasks.py --dry-run${NC}"
echo ""
echo "To stop test services:"
echo -e "  ${BLUE}docker stop aegis-test-postgres${NC}"
if [ "$setup_redis" = "y" ]; then
    echo -e "  ${BLUE}docker stop aegis-test-redis${NC}"
fi
echo ""
echo "To remove test services:"
echo -e "  ${BLUE}docker rm aegis-test-postgres${NC}"
if [ "$setup_redis" = "y" ]; then
    echo -e "  ${BLUE}docker rm aegis-test-redis${NC}"
fi
echo ""
