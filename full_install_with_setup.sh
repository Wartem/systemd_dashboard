#!/bin/bash

# full_install_with_setup.sh

# Exit on any error
set -e

echo "=== System Control Panel Installation ==="

echo "For manual installation, run these commands in order:"
echo "1. python3 -m venv .venv                   # Creates Python virtual environment"
echo "2. source .venv/bin/activate               # Activates virtual environment"
echo "3. pip install -r requirements.txt         # Installs required Python packages"
echo "4. bash service_install.sh                 # Creates and starts systemd service for automatic startup"
echo "5. python setup_credentials.py             # Generates secure login credentials"
echo ""
echo "Note: service_install.sh will create a systemd service that runs on startup"
echo "      setup_credentials.py will generate admin username and password - save these!"

read -p "Do you want to continue? (yes/no): " continue_install
if [ "$continue_install" != "yes" ]; then
    echo "Installation cancelled."
    exit 0
fi

# Ask user for installation type
echo -e "\nChoose installation type:"
echo "1: Full installation (virtual environment, requirements, service, credentials)"
echo "2: Only setup service and create credentials"
read -p "Enter choice (1 or 2): " choice

echo "Checking prerequisites..."

# Check Python version
if ! command -v python3 &> /dev/null; then
    echo "Python 3 is not installed. Please install Python 3.8 or higher."
    exit 1
fi

PYTHON_VERSION=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
if (( $(echo "$PYTHON_VERSION < 3.8" | bc -l) )); then
    echo "Python 3.8 or higher is required. Found version: $PYTHON_VERSION"
    exit 1
fi

# Check if running as root
if [ "$EUID" = 0 ]; then
    echo "Please run this script as a regular user, not as root/sudo"
    exit 1
fi

# Get the installation directory
INSTALL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CURRENT_USER=$(whoami)

echo "Installing in: $INSTALL_DIR"

# Ask user for installation type
echo "Choose installation type:"
echo "1: Full installation (virtual environment, requirements, service, credentials)"
echo "2: Only setup service and create credentials"
read -p "Enter choice (1 or 2): " choice

case $choice in
    1)
        # Create virtual environment
        if [ ! -d ".venv" ]; then
            echo "Creating virtual environment..."
            python3 -m venv .venv
        fi

        # Activate virtual environment
        source .venv/bin/activate

        # Install required packages
        echo "Installing required packages..."
        if [ -f "requirements.txt" ]; then
            pip install -r requirements.txt
        else
            echo "Error: requirements.txt not found!"
            exit 1
        fi

        # Create systemd service
        echo "Setting up systemd service..."
        bash service_install.sh

        # Generate credentials
        echo "Generating secure credentials... Make sure to save them! You will need them to login."
        python setup_credentials.py
        ;;
    2)
        # Create systemd service
        echo "Setting up systemd service..."
        bash service_install.sh

        # Generate credentials only
        echo "Generating secure credentials... Make sure to save them! You will need them to login."
        python setup_credentials.py
        ;;
    *)
        echo "Invalid choice. Please enter 1 or 2."
        exit 1
        ;;
esac