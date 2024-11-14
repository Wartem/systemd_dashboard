# config.py
import os
from pathlib import Path
import secrets
import logging
import os
import json
import platform
import subprocess

logger = logging.getLogger(__name__)

def get_device_name():
    # Try to get Raspberry Pi model
    try:
        with open('/proc/cpuinfo', 'r') as f:
            for line in f:
                if line.startswith('Model'):
                    return line.split(':')[1].strip()
    except:
        pass
    
    # Fallback to hostname if not a Pi
    try:
        return platform.node()
    except:
        return "System Control Panel"

def generate_secure_key():
    """Generate a cryptographically secure key"""
    return secrets.token_urlsafe(32)

def create_env_file():
    """Create a .env file with secure default values if it doesn't exist"""
    env_path = Path('.env')
    
    if not env_path.exists():
        with open(env_path, 'w') as f:
            f.write(f"SYSTEM_CONTROL_API_KEY={generate_secure_key()}\n")
            f.write(f"FLASK_SECRET_KEY={generate_secure_key()}\n")
        
        # Set restrictive permissions
        env_path.chmod(0o600)
        logger.info(".env file created with secure defaults")
        print("New .env file created with secure keys. Please save these keys securely.")
    
def load_config():
    # Try to load python-dotenv if available
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        logger.warning("python-dotenv not installed. Using environment variables only.")

    config_file = 'config.json'
    default_config = {
        'API_KEY': os.environ.get('SYSTEM_CONTROL_API_KEY'),
        'SECRET_KEY': os.environ.get('FLASK_SECRET_KEY'),
        'CUSTOM_NAME': "Custom Name"  
    }
    
    # Create config if it doesn't exist
    if not os.path.exists(config_file):
        with open(config_file, 'w') as f:
            json.dump(default_config, f, indent=4)
    
    # Load config
    try:
        with open(config_file, 'r') as f:
            config = json.load(f)
            
        # Update with any missing default values
        for key in default_config:
            if key not in config:
                config[key] = default_config[key]
        
        # If no custom name is set, try to detect device
        if not config.get('CUSTOM_NAME'):
            config['DEVICE_NAME'] = get_device_name()
        else:
            config['DEVICE_NAME'] = config['CUSTOM_NAME']
            
        return config
    except Exception as e:
        raise ValueError(f"Error loading config: {str(e)}")