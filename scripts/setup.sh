#!/bin/bash
# PMON-AI-OPS Setup Script
# Initializes development environment

set -e

echo "╔══════════════════════════════════════════════════════════════╗"
echo "║           PMON-AI-OPS Environment Setup                      ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check Python version
echo "Checking Python version..."
python_version=$(python3 --version 2>&1 | awk '{print $2}')
required_version="3.11"

if [ "$(printf '%s\n' "$required_version" "$python_version" | sort -V | head -n1)" = "$required_version" ]; then 
    echo -e "${GREEN}✓ Python $python_version detected${NC}"
else
    echo -e "${RED}✗ Python 3.11+ required, found $python_version${NC}"
    exit 1
fi

# Check Node.js version
echo "Checking Node.js version..."
if command -v node &> /dev/null; then
    node_version=$(node --version | cut -d'v' -f2)
    echo -e "${GREEN}✓ Node.js $node_version detected${NC}"
else
    echo -e "${RED}✗ Node.js not found. Please install Node.js 20+${NC}"
    exit 1
fi

# Check if .env exists
echo ""
echo "Checking environment configuration..."
if [ ! -f ".env" ]; then
    echo -e "${YELLOW}! .env file not found${NC}"
    echo "Creating from .env.example..."
    cp .env.example .env
    echo -e "${YELLOW}! Please edit .env and set your DEEPSEEK_API_KEY${NC}"
else
    echo -e "${GREEN}✓ .env file exists${NC}"
fi

# Create necessary directories
echo ""
echo "Creating directories..."
mkdir -p logs data/tftp data/db backend/tftp_receive

# Install backend dependencies
echo ""
echo "Installing backend dependencies..."
cd backend
pip install -e ".[dev]"
cd ..

# Install frontend dependencies
echo ""
echo "Installing frontend dependencies..."
cd frontend
npm install
cd ..

echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║                    Setup Complete!                           ║"
echo "╠══════════════════════════════════════════════════════════════╣"
echo "║                                                              ║"
echo "║  Next steps:                                                 ║"
echo "║  1. Edit .env and set DEEPSEEK_API_KEY                       ║"
echo "║  2. Run 'make dev' to start development environment          ║"
echo "║  3. Visit http://localhost:5173                              ║"
echo "║                                                              ║"
echo "║  Commands:                                                   ║"
echo "║  - make help    Show all available commands                  ║"
echo "║  - make dev     Start development server                     ║"
echo "║  - make test    Run tests                                    ║"
echo "║  - make lint    Check code quality                           ║"
echo "║                                                              ║"
echo "╚══════════════════════════════════════════════════════════════╝"
