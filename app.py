# app.py

from flask import Flask, jsonify, request, render_template, redirect, url_for, session, send_file, Response
import subprocess
import logging
import os
import psutil
import platform
import time
from datetime import datetime
from functools import wraps
from waitress import serve
import sqlite3
from collections import deque
import threading
import io
import json
import matplotlib.pyplot as plt
from config import load_config

from functools import lru_cache
from concurrent.futures import ThreadPoolExecutor
import asyncio
from datetime import datetime, timedelta

DB_POOL_SIZE = 5
db_semaphore = threading.Semaphore(DB_POOL_SIZE)

# Create necessary directories
REQUIRED_DIRS = ['static/css', 'templates', 'logs', 'data']
for directory in REQUIRED_DIRS:
    os.makedirs(directory, exist_ok=True)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/app.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

executor = ThreadPoolExecutor(max_workers=4)

try:
    config = load_config()
    API_KEY = config['API_KEY']
except Exception as e:
    logger.error(f"Configuration error: {e}")
    raise SystemExit(1)

app = Flask(__name__)
app.secret_key = config['SECRET_KEY']
METRICS_HISTORY = deque(maxlen=1440)  # Store 24 hours of data (1 sample per minute)

@lru_cache(maxsize=1)
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

def load_config():
    # Try to load python-dotenv if available
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        logger.warning("python-dotenv not installed. Using environment variables only.")

    config_file = 'config.json'
    default_config = {
        'CUSTOM_NAME': "Custom Name"  # This will be None by default
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

# Database initialization
def init_db():
    with sqlite3.connect('data/metrics.db') as conn:
        c = conn.cursor()
        
        # Create tables if they don't exist
        c.execute('''CREATE TABLE IF NOT EXISTS system_metrics
                    (timestamp TEXT, cpu_percent REAL, memory_percent REAL, 
                     disk_percent REAL, temperature REAL)''')
        
        c.execute('''CREATE TABLE IF NOT EXISTS events
                    (timestamp TEXT, event_type TEXT, description TEXT)''')
        
        # Create indexes for better query performance
        c.execute('''CREATE INDEX IF NOT EXISTS idx_metrics_timestamp 
                    ON system_metrics(timestamp)''')
                    
        c.execute('''CREATE INDEX IF NOT EXISTS idx_events_timestamp 
                    ON events(timestamp)''')
        
        conn.commit()

def get_cpu_temperature():
    try:
        if os.path.exists('/sys/class/thermal/thermal_zone0/temp'):
            with open('/sys/class/thermal/thermal_zone0/temp') as f:
                temp = float(f.read()) / 1000.0
            return round(temp, 1)
        return None
    except Exception as e:
        logger.error(f"Error reading CPU temperature: {str(e)}")
        return None

def log_event(event_type, description):
    try:
        with sqlite3.connect('data/metrics.db') as conn:
            c = conn.cursor()
            c.execute('INSERT INTO events VALUES (?, ?, ?)',
                     (datetime.now().isoformat(), event_type, description))
            conn.commit()
    except Exception as e:
        logger.error(f"Error logging event: {str(e)}")

_network_info_cache = None
_network_info_timestamp = None
def get_network_info():
    global _network_info_cache, _network_info_timestamp
    
    # Return cached value if less than 5 seconds old
    if (_network_info_cache and _network_info_timestamp and 
        datetime.now() - _network_info_timestamp < timedelta(seconds=5)):
        return _network_info_cache
    
    try:
        net_io = psutil.net_io_counters()
        _network_info_cache = {
            'bytes_sent': net_io.bytes_sent,
            'bytes_recv': net_io.bytes_recv,
            'packets_sent': net_io.packets_sent,
            'packets_recv': net_io.packets_recv
        }
        _network_info_timestamp = datetime.now()
        return _network_info_cache
    except Exception as e:
        logger.error(f"Error getting network info: {str(e)}")
        return None

@lru_cache(maxsize=100)
def get_system_info():
    """Cache system info as it rarely changes"""
    try:
        return {
            'platform': platform.platform(),
            'python_version': platform.python_version(),
            'processor': platform.processor(),
            'machine': platform.machine(),
            'hostname': platform.node()
        }
    except Exception as e:
        logger.error(f"Error getting system info: {str(e)}")
        return None
    
class MetricsCollector:
    def __init__(self):
        self.metrics_buffer = []
        self.buffer_lock = threading.Lock()
        self.last_metrics = None
        self.metrics_lock = threading.RLock()
        self.plot_lock = threading.Lock()
        self.db_conn = None
        self.last_save = datetime.now()
        
    def init_db_connection(self):
        if not self.db_conn:
            self.db_conn = sqlite3.connect('data/metrics.db', check_same_thread=False)
            
    def collect_metrics(self):
        self.init_db_connection()
        while True:
            try:
                current_time = datetime.now()
                
                metrics = {
                    'timestamp': current_time.isoformat(),
                    'cpu_percent': psutil.cpu_percent(interval=1),
                    'memory_percent': psutil.virtual_memory().percent,
                    'disk_percent': psutil.disk_usage('/').percent,
                    'temperature': get_cpu_temperature() or 0
                }
                
                # Update current metrics
                with self.metrics_lock:
                    self.last_metrics = metrics
                    METRICS_HISTORY.append(metrics)
                
                # Buffer for database
                with self.buffer_lock:
                    self.metrics_buffer.append(metrics)
                    
                    # Save to database every 5 minutes
                    if current_time - self.last_save > timedelta(minutes=5):
                        self._save_metrics_to_db()
                        self.last_save = current_time
                        
            except Exception as e:
                logger.error(f"Error collecting metrics: {str(e)}")
                
            time.sleep(30)  # Collect every 30 seconds
            
    def _save_metrics_to_db(self):
        if not self.metrics_buffer:
            return
            
        try:
            c = self.db_conn.cursor()
            with self.buffer_lock:
                c.executemany(
                    'INSERT INTO system_metrics VALUES (?, ?, ?, ?, ?)',
                    [(m['timestamp'], m['cpu_percent'],
                      m['memory_percent'], m['disk_percent'],
                      m['temperature']) for m in self.metrics_buffer]
                )
                self.metrics_buffer.clear()
            self.db_conn.commit()
        except Exception as e:
            logger.error(f"Error saving metrics to database: {str(e)}")
            # Attempt to reconnect
            self.db_conn = None
            self.init_db_connection()
            
    def _save_metrics_to_db(self):
        if not self.metrics_buffer:
            return
            
        with db_semaphore:
            try:
                with sqlite3.connect('data/metrics.db') as conn:
                    c = conn.cursor()
                    with self.buffer_lock:
                        c.executemany(
                            'INSERT INTO system_metrics VALUES (?, ?, ?, ?, ?)',
                            [(m['timestamp'], m['cpu_percent'],
                              m['memory_percent'], m['disk_percent'],
                              m['temperature']) for m in self.metrics_buffer]
                        )
                        self.metrics_buffer.clear()
                    conn.commit()
            except Exception as e:
                logger.error(f"Error saving metrics to database: {str(e)}")

def collect_metrics():
    metrics_buffer = []
    last_save = datetime.now()
    last_plot_update = datetime.now()
    
    while True:
        try:
            current_time = datetime.now()
            
            # Collect metrics
            metrics = {
                'timestamp': current_time.isoformat(),
                'cpu_percent': psutil.cpu_percent(interval=0.5),  # Reduced interval
                'memory_percent': psutil.virtual_memory().percent,
                'disk_percent': psutil.disk_usage('/').percent,
                'temperature': get_cpu_temperature() or 0
            }
            
            # Check alerts (reduced frequency)
            if len(metrics_buffer) % 6 == 0:  # Check every 30 seconds
                if metrics['cpu_percent'] > 90:
                    log_event('alert', f'High CPU usage: {metrics["cpu_percent"]}%')
                if metrics['memory_percent'] > 90:
                    log_event('alert', f'High memory usage: {metrics["memory_percent"]}%')
                if metrics['disk_percent'] > 90:
                    log_event('alert', f'High disk usage: {metrics["disk_percent"]}%')
                if metrics['temperature'] and metrics['temperature'] > 80:
                    log_event('alert', f'High CPU temperature: {metrics["temperature"]}°C')
            
            # Update in-memory history less frequently
            if current_time - last_plot_update > timedelta(seconds=10):
                METRICS_HISTORY.append(metrics)
                last_plot_update = current_time
            
            # Buffer for database
            metrics_buffer.append(metrics)
            
            # Save to database when buffer is full or time threshold reached
            if (len(metrics_buffer) >= 30 or 
                current_time - last_save > timedelta(minutes=5)):
                
                with sqlite3.connect('data/metrics.db') as conn:
                    c = conn.cursor()
                    c.executemany(
                        'INSERT INTO system_metrics VALUES (?, ?, ?, ?, ?)',
                        [(m['timestamp'], m['cpu_percent'],
                          m['memory_percent'], m['disk_percent'],
                          m['temperature']) for m in metrics_buffer]
                    )
                    conn.commit()
                
                metrics_buffer = []
                last_save = current_time
                
        except Exception as e:
            logger.error(f"Error collecting metrics: {str(e)}")
        
        time.sleep(5)  # Collect metrics every 5 seconds
        
# Initialize collector
metrics_collector = MetricsCollector()

def generate_metrics_plot():
    with metrics_collector.plot_lock:
        try:
            plt.switch_backend('Agg')  # Use non-interactive backend
            
            # Clear any existing plots
            plt.close('all')
            
            fig = plt.figure(figsize=(10, 6), dpi=80)
            
            metrics_list = list(METRICS_HISTORY)
            
            if not metrics_list:
                logger.warning("No metrics data available for plotting")
                plt.close(fig)
                return None
                
            # Convert timestamps and limit data points
            timestamps = [datetime.fromisoformat(m['timestamp']) 
                        for m in metrics_list[-60:]]
            cpu_data = [m['cpu_percent'] for m in metrics_list[-60:]]
            memory_data = [m['memory_percent'] for m in metrics_list[-60:]]
            
            plt.plot(timestamps, cpu_data, label='CPU %', linewidth=2)
            plt.plot(timestamps, memory_data, label='Memory %', linewidth=2)
            plt.title('System Resource Usage')
            plt.xlabel('Time')
            plt.ylabel('Percentage')
            plt.legend()
            plt.grid(True, alpha=0.3)
            plt.xticks(rotation=45)
            
            plt.tight_layout()
            
            buf = io.BytesIO()
            plt.savefig(buf, format='png', bbox_inches='tight')
            buf.seek(0)
            
            # Cleanup
            plt.close(fig)
            plt.close('all')
            
            return buf
        except Exception as e:
            logger.error(f"Error generating metrics plot: {str(e)}")
            plt.close('all')
            return None
    
def get_system_status():
    try:
        # Run commands in parallel using ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=4) as executor:
            uptime_future = executor.submit(lambda: execute_command(["uptime"]))
            cpu_future = executor.submit(lambda: psutil.cpu_percent(interval=0.5))
            memory_future = executor.submit(lambda: psutil.virtual_memory().percent)
            disk_future = executor.submit(lambda: psutil.disk_usage('/').percent)
            temp_future = executor.submit(get_cpu_temperature)

            success, uptime = uptime_future.result()
            if not success:
                uptime = "Not available"

            return {
                "status": "running",
                "uptime": uptime,
                "cpu_percent": cpu_future.result(),
                "memory": {
                    "percent": memory_future.result()
                },
                "disk": {
                    "percent": disk_future.result()
                },
                "temperature": temp_future.result(),
                "timestamp": datetime.now()
            }
    except Exception as e:
        logger.error(f"Error in get_system_status: {str(e)}")
        return {
            "status": "error",
            "uptime": "Not available",
            "cpu_percent": 0,
            "memory": {"percent": 0},
            "disk": {"percent": 0},
            "temperature": None,
            "timestamp": datetime.now()
        }

def get_running_services():
    """Get running services with better error handling and logging"""
    try:
        # First try using systemctl
        result = subprocess.run(
            ["systemctl", "list-units", "--type=service", "--state=running", 
             "--no-legend", "--plain", "--no-pager"],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        if result.returncode != 0:
            logger.error(f"systemctl command failed: {result.stderr}")
            # Fallback to service command
            result = subprocess.run(
                ["service", "--status-all"],
                capture_output=True,
                text=True,
                timeout=5
            )
        
        services = []
        
        # Parse systemctl output
        if "systemctl" in result.args[0]:
            for line in result.stdout.split('\n'):
                if '.service' in line and line.strip():
                    parts = line.split(None, 4)
                    if len(parts) >= 1:
                        service_name = parts[0].replace('.service', '')
                        description = parts[4] if len(parts) > 4 else "No description available"
                        services.append({
                            'name': service_name,
                            'description': description,
                            'status': 'running'
                        })
        # Parse service command output
        else:
            for line in result.stdout.split('\n'):
                if '[ + ]' in line:  # Running services
                    service_name = line.split('[ + ]')[1].strip()
                    services.append({
                        'name': service_name,
                        'description': 'Service status via service command',
                        'status': 'running'
                    })
        
        # Sort and limit results
        services.sort(key=lambda x: x['name'])
        return services[:20]  # Limit to first 20 services
        
    except subprocess.TimeoutExpired:
        logger.error("Timeout while fetching services")
        return []
    except Exception as e:
        logger.error(f"Error getting services: {str(e)}")
        return []
    
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('authenticated'):
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/')
def index():
    if session.get('authenticated'):
        try:
            status = get_system_status()
            services = get_running_services()  # Get services
            system_info = get_system_info()
            network_info = get_network_info()
            device_name = config.get('DEVICE_NAME', 'System Control Panel')
            
            # Debug logging
            logger.debug(f"Found {len(services)} services")
            
            # Check if services is empty
            if not services:
                logger.warning("No services retrieved")
            
            # Get recent events
            events = []
            try:
                with sqlite3.connect('data/metrics.db') as conn:
                    c = conn.cursor()
                    c.execute('SELECT * FROM events ORDER BY timestamp DESC LIMIT 10')
                    events = [{
                        'timestamp': datetime.fromisoformat(row[0]).strftime('%Y-%m-%d %H:%M:%S'),
                        'type': row[1],
                        'description': row[2]
                    } for row in c.fetchall()]
            except Exception as e:
                logger.error(f"Error fetching events: {str(e)}")
            
            return render_template('index.html',
                                 status=status,
                                 services=services,
                                 system_info=system_info,
                                 network_info=network_info,
                                 events=events,
                                 device_name=device_name)
        except Exception as e:
            logger.error(f"Error in index route: {str(e)}")
            return render_template('index.html', error="Error loading system information")
            
    return render_template('index.html')

@app.route('/metrics.png')
@login_required
def metrics_plot():
    buf = generate_metrics_plot()
    if buf:
        response = send_file(buf, mimetype='image/png')
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        return response
    return '', 404

@app.route('/api/metrics/history')
@login_required
def get_metrics_history():
    try:
        with sqlite3.connect('data/metrics.db') as conn:
            c = conn.cursor()
            c.execute('''SELECT * FROM system_metrics 
                        WHERE timestamp > datetime('now', '-1 day')
                        ORDER BY timestamp DESC''')
            metrics = [{'timestamp': row[0], 'cpu_percent': row[1],
                       'memory_percent': row[2], 'disk_percent': row[3],
                       'temperature': row[4]} for row in c.fetchall()]
        return jsonify(metrics)
    except Exception as e:
        logger.error(f"Error fetching metrics history: {str(e)}")
        return jsonify({'error': str(e)}), 500

def execute_command(command):
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=30
        )
        if result.returncode != 0:
            logger.error(f"Command failed: {result.stderr}")
            return False, result.stderr
        return True, result.stdout
    except Exception as e:
        logger.error(f"Error executing command: {str(e)}")
        return False, str(e)

@app.route('/service-logs/<service_name>')
@login_required
def get_service_logs(service_name):
    if not service_name.isalnum() and not all(c in '.-_' for c in service_name if not c.isalnum()):
        return jsonify({'error': 'Invalid service name'}), 400
        
    try:
        result = subprocess.run(
            ['journalctl', '-u', service_name, '-n', '100', '--no-pager'],
            capture_output=True,
            text=True
        )
        return jsonify({'logs': result.stdout.split('\n')})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    
def check_update_lock():
    """Check if there's an existing update process running"""
    try:
        # Check for dpkg lock
        dpkg_lock = subprocess.run(
            ["lsof", "/var/lib/dpkg/lock-frontend"],
            capture_output=True,
            text=True
        )
        
        # Check for apt-get processes
        apt_processes = subprocess.run(
            ["pgrep", "apt-get"],
            capture_output=True,
            text=True
        )
        
        if dpkg_lock.returncode == 0 or apt_processes.stdout.strip():
            return True, "Another update process is currently running"
        return False, None
    except Exception as e:
        logger.error(f"Error checking update lock: {str(e)}")
        return True, str(e)

def kill_stale_locks():
    """Attempt to clean up stale lock files"""
    try:
        # Check how long the lock has been held
        lock_file = "/var/lib/dpkg/lock-frontend"
        if os.path.exists(lock_file):
            lock_age = time.time() - os.path.getctime(lock_file)
            
            # If lock is older than 1 hour, attempt to clean up
            if lock_age > 3600:  # 1 hour in seconds
                subprocess.run(["sudo", "rm", "-f", "/var/lib/dpkg/lock-frontend"])
                subprocess.run(["sudo", "rm", "-f", "/var/lib/dpkg/lock"])
                subprocess.run(["sudo", "rm", "-f", "/var/cache/apt/archives/lock"])
                subprocess.run(["sudo", "dpkg", "--configure", "-a"])
                return True, "Stale locks cleaned"
                
        return False, "No stale locks found"
    except Exception as e:
        logger.error(f"Error cleaning locks: {str(e)}")
        return False, str(e)

@app.route('/system-update', methods=['POST'])
@login_required
def system_update():
    try:
        # Check for existing update process
        is_locked, lock_message = check_update_lock()
        if is_locked:
            # Check for stale locks
            cleaned, clean_message = kill_stale_locks()
            if not cleaned:
                return jsonify({
                    'error': 'Update in progress',
                    'details': lock_message
                }), 409  # Conflict status code
        
        # Run update process
        update_process = subprocess.Popen(
            ['sudo', 'apt-get', 'update'],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        
        update_output, update_error = update_process.communicate(timeout=300)  # 5 minute timeout
        
        if update_process.returncode == 0:
            # Run upgrade process
            upgrade_process = subprocess.Popen(
                ['sudo', 'apt-get', 'upgrade', '-y'],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            
            upgrade_output, upgrade_error = upgrade_process.communicate(timeout=600)  # 10 minute timeout
            
            if upgrade_process.returncode == 0:
                log_event('system_update', 'System update completed successfully')
                return jsonify({
                    'status': 'success',
                    'message': 'System updated successfully',
                    'details': {
                        'update_output': update_output.decode(),
                        'upgrade_output': upgrade_output.decode()
                    }
                })
            else:
                error_msg = upgrade_error.decode()
                log_event('error', f'System upgrade failed: {error_msg}')
                return jsonify({
                    'error': 'Upgrade failed',
                    'details': error_msg
                }), 500
        else:
            error_msg = update_error.decode()
            log_event('error', f'System update failed: {error_msg}')
            return jsonify({
                'error': 'Update failed',
                'details': error_msg
            }), 500
            
    except subprocess.TimeoutExpired:
        log_event('error', 'System update timed out')
        return jsonify({
            'error': 'Update timed out',
            'details': 'The operation took too long to complete'
        }), 504
        
    except Exception as e:
        log_event('error', f'System update error: {str(e)}')
        return jsonify({
            'error': str(e),
            'details': 'An unexpected error occurred'
        }), 500
    
@app.route('/metrics-stream')
@login_required
def metrics_stream():
    def generate():
        retry_count = 0
        max_retries = 3
        
        while retry_count < max_retries:
            try:
                # Get current metrics
                metrics = {
                    'cpu_percent': psutil.cpu_percent(interval=1),
                    'memory_percent': psutil.virtual_memory().percent,
                    'disk_percent': psutil.disk_usage('/').percent,
                    'temperature': get_cpu_temperature() or 0,
                    'timestamp': datetime.now().isoformat()
                }
                
                # Reset retry count on successful metric collection
                retry_count = 0
                
                # Format data for SSE
                data = f"data: {json.dumps(metrics)}\n\n"
                yield data
                
                # Add heartbeat every 30 seconds
                yield ": heartbeat\n\n"
                
                time.sleep(15)
                
            except GeneratorExit:
                logger.info("Client closed connection normally")
                break
            except Exception as e:
                retry_count += 1
                logger.error(f"Error in metrics stream (attempt {retry_count}): {str(e)}")
                if retry_count >= max_retries:
                    logger.error("Max retries reached, closing stream")
                    break
                time.sleep(1)  # Brief pause before retry
    
    response = Response(
        generate(),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no'
        }
    )
    
    # Set a reasonable timeout
    response.timeout = 300  # 5 minutes
    
    return response

@app.route('/login', methods=['POST'])
def login():
    provided_key = request.form.get('api_key')
    if provided_key == API_KEY:
        session['authenticated'] = True
        log_event('login', f'Successful login from {request.remote_addr}')
        return redirect(url_for('index'))
    
    log_event('error', f'Failed login attempt from {request.remote_addr}')
    return render_template('index.html', error="Invalid API key")

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

@app.route('/refresh-status')
@login_required
def refresh_status():
    status = get_system_status()
    services = get_running_services()
    system_info = get_system_info()  
    network_info = get_network_info()  

    # Add recent events
    events = []
    try:
        with sqlite3.connect('data/metrics.db') as conn:
            c = conn.cursor()
            c.execute('SELECT * FROM events ORDER BY timestamp DESC LIMIT 10')
            events = [{'timestamp': row[0], 'type': row[1], 'description': row[2]} 
                     for row in c.fetchall()]
    except Exception as e:
        logger.error(f"Error fetching events: {str(e)}")

    return render_template('index.html', 
                         status=status,
                         services=services,
                         system_info=system_info, 
                         network_info=network_info, 
                         events=events)  

@app.route('/reboot', methods=['GET'])
@login_required
def reboot():
    logger.info('Reboot requested')
    log_event('system_reboot', 'System reboot initiated')
    success, message = execute_command(["sudo", "reboot"])
    if success:
        return render_template('index.html', message="System is rebooting...")
    return render_template('index.html', error=message)

@app.route('/shutdown', methods=['GET'])
@login_required
def shutdown():
    logger.info('Shutdown requested')
    log_event('system_shutdown', 'System shutdown initiated')
    success, message = execute_command(["sudo", "shutdown", "now"])
    if success:
        return render_template('index.html', message="System is shutting down...")
    return render_template('index.html', error=message)

@app.route('/restart-service', methods=['POST'])
@login_required
def restart_service():
    service_name = request.form.get('service')
    if not service_name:
        return render_template('index.html', 
                             error="Service name not provided",
                             status=get_system_status(),
                             services=get_running_services(),
                             system_info=get_system_info(),
                             network_info=get_network_info(),
                             device_name=config.get('DEVICE_NAME', 'System Control Panel'),
                             events=get_recent_events())  
    
    if not service_name.isalnum() and not all(c in '.-_' for c in service_name if not c.isalnum()):
        return render_template('index.html', 
                             error="Invalid service name",
                             status=get_system_status(),
                             services=get_running_services(),
                             system_info=get_system_info(),
                             network_info=get_network_info(),
                             device_name=config.get('DEVICE_NAME', 'System Control Panel'),
                             events=get_recent_events())  
    
    logger.info(f'Service restart requested for: {service_name}')
    success, message = execute_command(["sudo", "systemctl", "restart", service_name])
    
    # Get all necessary data including events
    status = get_system_status()
    services = get_running_services()
    system_info = get_system_info()
    network_info = get_network_info()
    events = get_recent_events()  

    if success:
        log_event('service_restart', f'Service {service_name} restarted successfully')
        return render_template('index.html', 
                             status=status,
                             services=services,
                             system_info=system_info,
                             network_info=network_info,
                             device_name=config.get('DEVICE_NAME', 'System Control Panel'),
                             events=events,  # Added events
                             message=f"Service {service_name} restarted successfully")
    
    log_event('error', f'Failed to restart service {service_name}: {message}')
    return render_template('index.html', 
                         status=status,
                         services=services,
                         system_info=system_info,
                         network_info=network_info,
                         device_name=config.get('DEVICE_NAME', 'System Control Panel'),
                         events=events,  # Added events
                         error=f"Failed to restart {service_name}: {message}")

# Add this helper function if it doesn't exist
def get_recent_events():
    try:
        with sqlite3.connect('data/metrics.db') as conn:
            c = conn.cursor()
            c.execute('SELECT * FROM events ORDER BY timestamp DESC LIMIT 10')
            return [{
                'timestamp': datetime.fromisoformat(row[0]).strftime('%Y-%m-%d %H:%M:%S'),
                'type': row[1],
                'description': row[2]
            } for row in c.fetchall()]
    except Exception as e:
        logger.error(f"Error fetching events: {str(e)}")
        return []
    
if __name__ == '__main__':
    # Initialize database
    init_db()
    
    # Start only ONE metrics collection thread
    metrics_thread = threading.Thread(
        target=metrics_collector.collect_metrics,
        daemon=True
    )
    metrics_thread.start()
    
    # Run server with optimized settings
    serve(app, 
          host='0.0.0.0',
          port=5903,
          threads=4,
          connection_limit=100,
          channel_timeout=30,
          cleanup_interval=30,
          ident='System Control Panel')