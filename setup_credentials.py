#!/usr/bin/env python3

# setup_credentials.py

"""
Setup script to generate secure credentials for the SystemD Dashboard.
This script creates a .env file with secure random keys.
"""
import secrets
import os
from pathlib import Path

def generate_credentials():
    """Generate secure credentials and save them to .env file"""
    # Generate secure keys
    api_key = secrets.token_urlsafe(32)
    secret_key = secrets.token_urlsafe(32)
    
    # Create .env file
    env_path = Path('.env')
    
    # Check if .env already exists
    if env_path.exists():
        response = input(".env file already exists. Overwrite? (y/N): ")
        if response.lower() != 'y':
            print("Setup cancelled.")
            return
    
    # Write new credentials
    with open(env_path, 'w') as f:
        f.write(f"SYSTEM_CONTROL_API_KEY={api_key}\n")
        f.write(f"FLASK_SECRET_KEY={secret_key}\n")
    
    # Set restrictive permissions
    env_path.chmod(0o600)
    
    print("\nCredentials generated successfully!")
    print("\nYour credentials (save these securely):")
    print(f"API Key: {api_key}")
    print(f"Secret Key: {secret_key}")
    print("\nThese credentials have been saved to .env")
    print("Keep this file secure and never commit it to version control.")

if __name__ == "__main__":
    generate_credentials()