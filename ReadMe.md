# SystemD Dashboard

A web-based interface for monitoring and managing Linux systems and systemd services. This dashboard provides system metrics, basic service management, and system control capabilities through an intuitive UI.

<div align="center">
  <details>
    <summary>Click to view screenshots</summary>
    <br>
    <details>
      <summary>Screenshot 1</summary>
      <img src="https://github.com/user-attachments/assets/871a3a4f-f85b-4af5-af18-2f9c0c1fe070" width="600">
    </details>
    <details>
      <summary>Screenshot 2</summary>
      <img src="https://github.com/user-attachments/assets/2cfa200f-4f24-46c5-9768-061d045eb4e1" width="600">
    </details>
    <details>
      <summary>Screenshot 3</summary>
      <img src="https://github.com/user-attachments/assets/a006ce58-9de2-446b-8692-d977f06ed50a" width="600">
    </details>
  </details>
</div>

## Features

- **Real-time System Monitoring**
  - CPU usage and temperature
  - Memory utilization
  - Disk usage
  - Network statistics
  - Historical metrics visualization

- **Service Management**
  - View running services
  - Start/stop/restart services
  - Real-time service status
  - Service logs viewer
  - Search and filter services

- **System Control**
  - System updates
  - Reboot/shutdown controls
  - Secure authentication
  - Event logging
  - Mobile-responsive interface

### Security Features
- Secure API key authentication
- CSRF protection
- Rate limiting
- Secure session handling
- Environment variable configuration

> ⚠️ **Security Notice**: This dashboard is designed for local network use or development environments. While it includes basic security features like API key authentication and session management, it should not be exposed to the public internet without additional security measures (VPN, reverse proxy with SSL, etc.).

### Technical Highlights
- Built with Flask
- Real-time updates via Server-Sent Events (SSE)
- SQLite metrics database
- Matplotlib for metrics visualization
- Responsive UI with modern CSS

## Technical Details

### Architecture
```
systemd_dashboard/
├── app.py              # Main Flask application
├── config.py           # Configuration management
├── static/            
│   └── css/           
│       └── style.css   # Styling
├── templates/
│   └── index.html      # Dashboard template
├── data/               # SQLite database
├── logs/               # Application logs
└── service_install.sh     # Service installation
└── setup_credentials.py   # Credential setup
```

### Dependencies
- Python 3.8+
- Flask
- SQLite3
- Matplotlib
- psutil
- python-dotenv
- waitress (WSGI server)

### System Requirements
- Linux system with systemd
- Python 3.8 or higher
- 256MB RAM minimum
- 100MB disk space
- Sudo privileges for service installation

### Performance
- Lightweight: < 50MB RAM usage
- Real-time updates: 5-second intervals
- Metrics retention: 24 hours
- Database pooling: 5 concurrent connections
- Rate limiting: 100 requests/minute

## Installation & Setup

### Prerequisites
```bash
# Install system dependencies
sudo apt-get update
sudo apt-get install python3-venv python3-dev
```

### Quick Install
```bash
git clone https://github.com/wartem/systemd_dashboard.git
cd systemd_dashboard
bash full_install_with_setup.sh
```

### Manual Installation

1. Create virtual environment:
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2. Generate credentials:
```bash
python setup_credentials.py
```
Make sure to save the generated credentials for later use.

3. Optional - Install systemd service:
```bash
bash service_install.sh
```
The script ensures secure deployment and easy management of the Flask app as a system service.

### Optional Configuration

1. Environment Variables (`.env`):
```plaintext
SYSTEM_CONTROL_API_KEY=your_generated_key
FLASK_SECRET_KEY=your_secret_key
```

2. Custom Settings (`config.json`):
```json
{
    "CUSTOM_NAME": "",
}
```

### Service Management
```bash
# Start service
sudo systemctl start systemd_dashboard

# Check status
sudo systemctl status systemd_dashboard

# View logs
sudo journalctl -u systemd_dashboard -f
```

### Default Access
- URL: http://localhost:5900
- Authentication: Use API key generated during setup

## Usage Guide

### Dashboard Overview
- **System Metrics**: Real-time display of CPU, memory, disk usage and temperature
- **Network Stats**: Current network throughput and total data transferred
- **Resource Graph**: 24-hour historical view of system metrics
- **Service List**: Running services with status and controls
- **Event Log**: System events and service changes

### Service Management
```bash
# View service logs
Click "Logs" button next to service name

# Restart service
Click "Restart" button next to service name

# Search services
Use search bar above service list
```

### System Actions
- **Update System**: Runs apt-get update/upgrade
- **Reboot**: Safely restarts system
- **Shutdown**: Powers down system
- **Service Control**: Start/stop/restart individual services

### Alert Monitoring
- High CPU usage (>90%)
- High memory usage (>90%)
- High disk usage (>90%)
- High temperature (>80°C)

### Metrics History
- 24-hour retention
- 5-second update interval
- Exportable graphs
- Configurable thresholds

### Mobile Access
- Responsive design
- Touch-friendly controls
- Optimized data usage
- Persistent sessions

## Development & Contributing

### Local Development Setup
```bash
# Clone repository
git clone https://github.com/wartem/systemd_dashboard.git
cd systemd_dashboard

# Create development environment
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Run in development mode
python app.py
```

### Testing
```bash
# Run tests
python -m pytest tests/

# Check code style
flake8 .
```

### Code Style
- Follow PEP 8 guidelines
- Use type hints
- Maximum line length: 100 characters
- Document all functions and classes
- Clear variable naming

### Pull Request Guidelines
1. Fork the repository
2. Create feature branch from `main`
3. Follow code style guidelines
4. Add tests for new features
5. Update documentation
6. Submit PR with description

### Development Features
- Debug logging enabled in development
- Auto-reload on code changes
- SQLite for local development
- Mock system data available

## Security

### Authentication
- API key-based authentication
- Secure session management
- CSRF protection
- Rate limiting
- Automatic session timeout

### System Security
```bash
# Secure file permissions
chmod 600 .env
chmod 600 config.json

# Service hardening
ProtectSystem=full
NoNewPrivileges=true
PrivateTmp=true
```

## Use Cases & Target Devices

### Ideal Use Cases
- **Home Lab Monitoring**: Keep track of your personal servers and development machines
- **Raspberry Pi Projects**: Monitor your Pi-based projects, home automation systems, or media servers
- **Local Development**: Track system resources during development and testing
- **Small Network Monitoring**: Monitor a handful of devices in a local network environment
- **Educational Purposes**: Learn about system monitoring, service management, and Linux administration

### Recommended Devices
1. **Raspberry Pi**
   - Perfect for Pi 3B+ and newer
   - Works great as a monitoring solution for Pi-based projects
   - Lightweight enough to run alongside other services
   - Helps monitor temperature (especially useful for Pi installations)

2. **Home Servers**
   - Small NAS systems
   - Media servers
   - Home automation hubs
   - Development servers

3. **Development Machines**
   - Linux workstations
   - Test environments
   - Virtual machines
   - Containers (with proper permissions)

### Not Recommended For
- Production servers exposed to the internet
- Critical infrastructure systems
- Large-scale deployments
- High-security environments

### Resource Requirements
- Minimal CPU usage (~1-2% on Raspberry Pi 4)
- Memory footprint: ~50MB
- Storage: ~100MB including logs
- Network: Minimal (SSE-based updates)

### Example Setups
```plaintext
1. Raspberry Pi Home Server
   - Running on Pi 4 with 4GB RAM
   - Monitoring temperature and resource usage
   - Managing services like Plex, Pi-hole, Home Assistant

2. Development Environment
   - Running on Ubuntu/Debian desktop
   - Monitoring resource usage during development
   - Managing Docker and development services

3. Home Lab
   - Running on a small NAS or mini PC
   - Monitoring network traffic and storage
   - Managing backup and media services
```

### Best Practices
- Store credentials in `.env`
- Never commit `.env` or `config.json`
- Regular security updates
- Monitor system logs
- Use HTTPS in production

### Hardening Options
```ini
# systemd service restrictions
MemoryLimit=256M
CPUQuota=50%
PrivateTmp=true
NoNewPrivileges=true
```

### Access Control
- Single admin user
- IP-based access control (optional)
- Audit logging
- Failed login monitoring

### Credits
- Built with [Flask](https://flask.palletsprojects.com/)
- UI components from [shadcn/ui](https://ui.shadcn.com/)
- Icons by [Lucide](https://lucide.dev/)
- Charts by [Chart.js](https://www.chartjs.org/)
