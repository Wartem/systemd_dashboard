![Python](https://img.shields.io/badge/python-v3.7+-blue.svg)
![Flask](https://img.shields.io/badge/flask-v2.0+-lightgrey.svg)
![Platform](https://img.shields.io/badge/platform-linux-lightgrey)
![HTML](https://img.shields.io/badge/HTML5-E34F26?style=for-the-badge&logo=html5&logoColor=white)
![CSS](https://img.shields.io/badge/CSS3-1572B6?style=for-the-badge&logo=css3&logoColor=white)
![JavaScript](https://img.shields.io/badge/JavaScript-F7DF1E?style=for-the-badge&logo=javascript&logoColor=black)
![SystemD](https://img.shields.io/badge/SystemD-Compatible-blue)
![Monitoring](https://img.shields.io/badge/Monitoring-Real--time-green)
![Database](https://img.shields.io/badge/Database-SQLite-blue)
![Raspberry Pi](https://img.shields.io/badge/Raspberry%20Pi-Compatible-C51A4A)
![Authentication](https://img.shields.io/badge/Authentication-API%20Key-yellow)
![UI](https://img.shields.io/badge/UI-Responsive-blue)
![Charts](https://img.shields.io/badge/Charts-matplotlib-orange)
![Services](https://img.shields.io/badge/Services-Management-green)
![Theme](https://img.shields.io/badge/Theme-Dark-lightgrey)

# SystemD Dashboard | Monitoring and managing Linux systems

<div align="center">
  <img src="https://github.com/user-attachments/assets/1a51e3b7-6584-4ba6-861d-1585f54b779e" alt="SystemD Dashboard">
</div>
<br>
<br>

A lightweight web-based dashboard for monitoring and managing Linux systems running SystemD. This dashboard provides real-time system metrics, service management, and system control capabilities through an intuitive UI. Designed to run as a service on local Linux systems like Raspberry Pi, home servers, or development machines, providing easy access to system monitoring and controls through your web browser.

<br>
<div align="center">
  
![image](https://github.com/user-attachments/assets/432c681f-34a7-4c56-b29a-b07c2aa4e4bb)

![image](https://github.com/user-attachments/assets/819a0525-adf7-48c1-b9a2-3140d5c54270)

</div>

<br>

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
  - Reboot/shutdown controls
  - ~~System updates~~
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

### Sudo without password
You need to configure sudo to allow these specific commands without a password. Here's how to set it up:

1. First, create a file for the sudo configuration:
```bash
sudo visudo -f /etc/sudoers.d/systemd-dashboard
```

2. Add these lines (replace `your_username` with the actual username running the Flask app):
```
your_username ALL=(ALL) NOPASSWD: /usr/sbin/reboot
your_username ALL=(ALL) NOPASSWD: /usr/sbin/shutdown
your_username ALL=(ALL) NOPASSWD: /usr/bin/systemctl poweroff
your_username ALL=(ALL) NOPASSWD: /usr/bin/systemctl reboot
```

3. Save and exit (in visudo, usually Ctrl+X, then Y, then Enter)

4. Set proper permissions:
```bash
sudo chmod 440 /etc/sudoers.d/systemd-dashboard
```

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

### Log Locations
- Application logs: `logs/app.log`
- Metrics database: `data/metrics.db`
- SystemD service log: `journalctl -u systemd_dashboard`

### System Actions
- **Reboot**: Safely restarts system
- **Shutdown**: Powers down system
- ~~**Update System**: Runs apt-get update/upgrade~~
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

## Limitations
- Single-user authentication only
- 24-hour metrics retention
- Local network usage only
- Linux/SystemD systems only
- Requires sudo privileges for system controls

## Troubleshooting

### Common Issues
1. **Permission Denied for Shutdown/Reboot**
   - Configure sudo permissions as described in installation

2. **Metrics Graph Not Updating**
   - Check if metrics collection service is running
   - Verify database permissions
   - Check application logs

3. **Service Status Errors**
   - Verify systemd permissions
   - Check service naming

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
