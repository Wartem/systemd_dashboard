# app.py

from flask import (
    Flask,
    jsonify,
    request,
    render_template,
    redirect,
    url_for,
    session,
    send_file,
    Response,
)
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
from datetime import datetime, timedelta
import hmac

DB_POOL_SIZE = 5
db_semaphore = threading.Semaphore(DB_POOL_SIZE)

PORT = 5900

# Create necessary directories
REQUIRED_DIRS = ["static/css", "templates", "logs", "data"]
for directory in REQUIRED_DIRS:
    os.makedirs(directory, exist_ok=True)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler("logs/app.log"), logging.StreamHandler()],
)

logger = logging.getLogger(__name__)

executor = ThreadPoolExecutor(max_workers=4)

try:
    config = load_config()
    API_KEY = config["API_KEY"]
except Exception as e:
    logger.error(f"Configuration error: {e}")
    raise SystemExit(1)

app = Flask(__name__)
app.secret_key = config["SECRET_KEY"]
METRICS_HISTORY = deque(maxlen=1440)  # Store 24 hours of data (1 sample per minute)


@lru_cache(maxsize=1)
def get_device_name():
    # Try to get Raspberry Pi model
    try:
        with open("/proc/cpuinfo", "r") as f:
            for line in f:
                if line.startswith("Model"):
                    return line.split(":")[1].strip()
    except:
        pass

    # Fallback to hostname if not a Pi
    try:
        return platform.node()
    except:
        return "SystemD Dashboard"


def load_config():
    # Try to load python-dotenv if available
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        logger.warning("python-dotenv not installed. Using environment variables only.")

    config_file = "config.json"
    default_config = {"CUSTOM_NAME": "Custom Name"}  # This will be None by default

    # Create config if it doesn't exist
    if not os.path.exists(config_file):
        with open(config_file, "w") as f:
            json.dump(default_config, f, indent=4)

    # Load config
    try:
        with open(config_file, "r") as f:
            config = json.load(f)

        # Update with any missing default values
        for key in default_config:
            if key not in config:
                config[key] = default_config[key]

        # If no custom name is set, try to detect device
        if not config.get("CUSTOM_NAME"):
            config["DEVICE_NAME"] = get_device_name()
        else:
            config["DEVICE_NAME"] = config["CUSTOM_NAME"]

        return config
    except Exception as e:
        raise ValueError(f"Error loading config: {str(e)}")


# Database initialization
def init_db():
    """Initialize the database schema if it doesn't exist"""
    with sqlite3.connect("data/metrics.db") as conn:
        c = conn.cursor()

        # Create metrics table if it doesn't exist
        c.execute(
            """CREATE TABLE IF NOT EXISTS system_metrics
                    (timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                     cpu_percent REAL,
                     memory_percent REAL, 
                     disk_percent REAL,
                     temperature REAL)"""
        )

        # Create index if it doesn't exist
        c.execute(
            """CREATE INDEX IF NOT EXISTS idx_metrics_timestamp 
                    ON system_metrics(timestamp)"""
        )

        # Create cleanup trigger if it doesn't exist
        c.execute(
            """CREATE TRIGGER IF NOT EXISTS cleanup_old_metrics
                    AFTER INSERT ON system_metrics
                    BEGIN
                        DELETE FROM system_metrics 
                        WHERE timestamp < datetime('now', '-24 hours');
                    END"""
        )

        # Create events table if it doesn't exist
        c.execute(
            """CREATE TABLE IF NOT EXISTS events
                    (timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                     event_type TEXT,
                     description TEXT)"""
        )

        # Create events index if it doesn't exist
        c.execute(
            """CREATE INDEX IF NOT EXISTS idx_events_timestamp 
                    ON events(timestamp)"""
        )

        conn.commit()

        # Verify tables exist
        c.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = c.fetchall()
        logger.info(f"Database initialized with tables: {[t[0] for t in tables]}")

        # Log table counts
        for table in ["system_metrics", "events"]:
            c.execute(f"SELECT COUNT(*) FROM {table}")
            count = c.fetchone()[0]
            logger.info(f"Table {table} contains {count} records")


def get_cpu_temperature():
    try:
        if os.path.exists("/sys/class/thermal/thermal_zone0/temp"):
            with open("/sys/class/thermal/thermal_zone0/temp") as f:
                temp = float(f.read()) / 1000.0
            return round(temp, 1)
        return None
    except Exception as e:
        logger.error(f"Error reading CPU temperature: {str(e)}")
        return None


def log_event(event_type, description):
    try:
        with sqlite3.connect("data/metrics.db") as conn:
            c = conn.cursor()
            c.execute(
                "INSERT INTO events VALUES (?, ?, ?)",
                (datetime.now().isoformat(), event_type, description),
            )
            conn.commit()
    except Exception as e:
        logger.error(f"Error logging event: {str(e)}")


_network_info_cache = None
_network_info_timestamp = None


class MetricsCollector:
    def __init__(self):
        self.metrics_buffer = []
        self.buffer_lock = threading.Lock()
        self.metrics_lock = threading.RLock()
        self.plot_lock = threading.Lock()
        self.running = False
        self.db_path = "data/metrics.db"

    def start(self):
        """Start the metrics collection"""
        self.running = True
        threading.Thread(target=self.collect_metrics, daemon=True).start()
        logger.info("Metrics collection started")

    def stop(self):
        """Stop the metrics collection"""
        self.running = False
        logger.info("Metrics collection stopped")

    def collect_metrics(self):
        while self.running:
            try:
                # Collect current metrics
                metrics = {
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "cpu_percent": psutil.cpu_percent(interval=1),
                    "memory_percent": psutil.virtual_memory().percent,
                    "disk_percent": psutil.disk_usage("/").percent,
                    "temperature": get_cpu_temperature() or 0,
                }

                # Save to database immediately
                with sqlite3.connect(self.db_path) as conn:
                    c = conn.cursor()
                    c.execute(
                        "INSERT INTO system_metrics (timestamp, cpu_percent, memory_percent, disk_percent, temperature) VALUES (?, ?, ?, ?, ?)",
                        (
                            metrics["timestamp"],
                            metrics["cpu_percent"],
                            metrics["memory_percent"],
                            metrics["disk_percent"],
                            metrics["temperature"],
                        ),
                    )
                    conn.commit()

                logger.debug(
                    f"Metrics saved: CPU {metrics['cpu_percent']}%, Memory {metrics['memory_percent']}%"
                )

            except Exception as e:
                logger.error(f"Error collecting metrics: {str(e)}")

            time.sleep(30)  # Collect every 30 seconds


def generate_metrics_plot():
    """Generate the metrics plot from database data"""
    try:
        plt.switch_backend("Agg")
        plt.close("all")

        fig = plt.figure(figsize=(10, 6), dpi=80)

        # Fetch last 24 hours of data
        with sqlite3.connect("data/metrics.db") as conn:
            df = pd.read_sql_query(
                """
                SELECT timestamp, cpu_percent, memory_percent 
                FROM system_metrics 
                WHERE timestamp > datetime('now', '-24 hours')
                ORDER BY timestamp ASC
            """,
                conn,
                parse_dates=["timestamp"],
            )

        if df.empty:
            logger.warning("No metrics data available for plotting")
            plt.close(fig)
            return None

        # Plot the data
        plt.plot(
            df["timestamp"],
            df["cpu_percent"],
            label="CPU %",
            linewidth=2,
            color="#3498db",
        )
        plt.plot(
            df["timestamp"],
            df["memory_percent"],
            label="Memory %",
            linewidth=2,
            color="#e74c3c",
        )

        # Customize the plot
        plt.title("System Resource Usage", pad=20)
        plt.xlabel("Time")
        plt.ylabel("Percentage")
        plt.legend(loc="upper right")
        plt.grid(True, alpha=0.3)
        plt.ylim(0, 100)

        # Format x-axis
        plt.gcf().autofmt_xdate()

        # Add padding
        plt.tight_layout()

        # Save to buffer
        buf = io.BytesIO()
        plt.savefig(buf, format="png", bbox_inches="tight", dpi=80)
        buf.seek(0)

        plt.close(fig)
        return buf

    except Exception as e:
        logger.error(f"Error generating metrics plot: {str(e)}")
        plt.close("all")
        return None


def collect_metrics():
    metrics_buffer = []
    last_save = datetime.now()
    last_plot_update = datetime.now()

    while True:
        try:
            current_time = datetime.now()

            # Collect metrics
            metrics = {
                "timestamp": current_time.isoformat(),
                "cpu_percent": psutil.cpu_percent(interval=0.5),  # Reduced interval
                "memory_percent": psutil.virtual_memory().percent,
                "disk_percent": psutil.disk_usage("/").percent,
                "temperature": get_cpu_temperature() or 0,
            }

            # Check alerts (reduced frequency)
            if len(metrics_buffer) % 6 == 0:  # Check every 30 seconds
                if metrics["cpu_percent"] > 90:
                    log_event("alert", f'High CPU usage: {metrics["cpu_percent"]}%')
                if metrics["memory_percent"] > 90:
                    log_event(
                        "alert", f'High memory usage: {metrics["memory_percent"]}%'
                    )
                if metrics["disk_percent"] > 90:
                    log_event("alert", f'High disk usage: {metrics["disk_percent"]}%')
                if metrics["temperature"] and metrics["temperature"] > 80:
                    log_event(
                        "alert", f'High CPU temperature: {metrics["temperature"]}°C'
                    )

            # Update in-memory history less frequently
            if current_time - last_plot_update > timedelta(seconds=10):
                METRICS_HISTORY.append(metrics)
                last_plot_update = current_time

            # Buffer for database
            metrics_buffer.append(metrics)

            # Save to database when buffer is full or time threshold reached
            if len(metrics_buffer) >= 30 or current_time - last_save > timedelta(
                minutes=5
            ):

                with sqlite3.connect("data/metrics.db") as conn:
                    c = conn.cursor()
                    c.executemany(
                        "INSERT INTO system_metrics VALUES (?, ?, ?, ?, ?)",
                        [
                            (
                                m["timestamp"],
                                m["cpu_percent"],
                                m["memory_percent"],
                                m["disk_percent"],
                                m["temperature"],
                            )
                            for m in metrics_buffer
                        ],
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
            plt.switch_backend("Agg")  # Use non-interactive backend

            # Clear any existing plots
            plt.close("all")

            fig = plt.figure(figsize=(10, 6), dpi=80)

            # Get metrics from the database for the last 24 hours
            metrics_list = []
            try:
                with sqlite3.connect("data/metrics.db") as conn:
                    c = conn.cursor()
                    c.execute(
                        """
                        SELECT timestamp, cpu_percent, memory_percent 
                        FROM system_metrics 
                        WHERE timestamp > datetime('now', '-24 hours')
                        ORDER BY timestamp ASC
                    """
                    )
                    metrics_list = c.fetchall()
            except Exception as e:
                logger.error(f"Error fetching metrics from database: {str(e)}")
                return None

            if not metrics_list:
                logger.warning("No metrics data available for plotting")
                plt.close(fig)
                return None

            # Convert timestamps and prepare data
            timestamps = []
            cpu_data = []
            memory_data = []

            for metric in metrics_list:
                try:
                    # Parse timestamp and convert to local timezone
                    ts = datetime.fromisoformat(metric[0].replace("Z", "+00:00"))
                    timestamps.append(ts)
                    cpu_data.append(float(metric[1]))
                    memory_data.append(float(metric[2]))
                except (ValueError, TypeError) as e:
                    logger.error(f"Error parsing metric data: {str(e)}")
                    continue

            if not timestamps:
                logger.warning("No valid timestamps found in metrics")
                plt.close(fig)
                return None

            # Create the plot
            plt.plot(timestamps, cpu_data, label="CPU %", linewidth=2, color="#3498db")
            plt.plot(
                timestamps, memory_data, label="Memory %", linewidth=2, color="#e74c3c"
            )

            # Customize the plot
            plt.title("System Resource Usage", pad=20)
            plt.xlabel("Time")
            plt.ylabel("Percentage")
            plt.legend(loc="upper right")
            plt.grid(True, alpha=0.3)

            # Format x-axis
            plt.gcf().autofmt_xdate()  # Angle and align the tick labels so they look better

            # Use AutoDateFormatter for smart date formatting
            from matplotlib.dates import AutoDateFormatter, AutoDateLocator

            locator = AutoDateLocator()
            formatter = AutoDateFormatter(locator)
            plt.gca().xaxis.set_major_locator(locator)
            plt.gca().xaxis.set_major_formatter(formatter)

            # Set y-axis range from 0 to 100
            plt.ylim(0, 100)

            # Add padding to prevent label cutoff
            plt.tight_layout()

            # Save to buffer
            buf = io.BytesIO()
            plt.savefig(buf, format="png", bbox_inches="tight", dpi=80)
            buf.seek(0)

            # Cleanup
            plt.close(fig)
            plt.close("all")

            return buf
        except Exception as e:
            logger.error(f"Error generating metrics plot: {str(e)}")
            plt.close("all")
            return None


def get_system_status():
    try:
        # Run commands in parallel using ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=4) as executor:
            uptime_future = executor.submit(lambda: execute_command(["uptime"]))
            cpu_future = executor.submit(lambda: psutil.cpu_percent(interval=0.5))
            memory_future = executor.submit(lambda: psutil.virtual_memory().percent)
            disk_future = executor.submit(lambda: psutil.disk_usage("/").percent)
            temp_future = executor.submit(get_cpu_temperature)

            success, uptime = uptime_future.result()
            if not success:
                uptime = "Not available"

            return {
                "status": "running",
                "uptime": uptime,
                "cpu_percent": cpu_future.result(),
                "memory": {"percent": memory_future.result()},
                "disk": {"percent": disk_future.result()},
                "temperature": temp_future.result(),
                "timestamp": datetime.now(),
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
            "timestamp": datetime.now(),
        }


def get_error_template_data(error_message):
    """Get safe template data for error pages"""
    try:
        return {
            "status": {
                "status": "error",
                "uptime": "Not available",
                "cpu_percent": 0,
                "memory": {"percent": 0},
                "disk": {"percent": 0},
                "temperature": None,
                "timestamp": datetime.now(),
            },
            "system_info": {
                "hostname": platform.node(),
                "platform": platform.platform(),
                "python_version": platform.python_version(),
            },
            "network_info": {
                "bytes_sent": 0,
                "bytes_recv": 0,
                "packets_sent": 0,
                "packets_recv": 0,
            },
            "device_name": config.get("DEVICE_NAME", "SystemD Dashboard"),
            "events": [],
            "services": [],
            "error": error_message,
        }
    except Exception as e:
        logger.error(f"Error getting error template data: {str(e)}", exc_info=True)
        return {
            "status": {"status": "error"},
            "system_info": {"hostname": "Unknown"},
            "network_info": {"bytes_sent": 0, "bytes_recv": 0},
            "device_name": "SystemD Dashboard",
            "error": error_message,
        }


def get_running_services():
    """Get running services with better error handling and logging"""
    try:
        # First try using systemctl
        result = subprocess.run(
            [
                "systemctl",
                "list-units",
                "--type=service",
                "--state=running",
                "--no-legend",
                "--plain",
                "--no-pager",
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )

        if result.returncode != 0:
            logger.error(f"systemctl command failed: {result.stderr}")
            # Fallback to service command
            result = subprocess.run(
                ["service", "--status-all"], capture_output=True, text=True, timeout=5
            )

        services = []

        # Parse systemctl output
        if "systemctl" in result.args[0]:
            for line in result.stdout.split("\n"):
                if ".service" in line and line.strip():
                    parts = line.split(None, 4)
                    if len(parts) >= 1:
                        service_name = parts[0].replace(".service", "")
                        description = (
                            parts[4] if len(parts) > 4 else "No description available"
                        )
                        services.append(
                            {
                                "name": service_name,
                                "description": description,
                                "status": "running",
                            }
                        )
        # Parse service command output
        else:
            for line in result.stdout.split("\n"):
                if "[ + ]" in line:  # Running services
                    service_name = line.split("[ + ]")[1].strip()
                    services.append(
                        {
                            "name": service_name,
                            "description": "Service status via service command",
                            "status": "running",
                        }
                    )

        # Sort and limit results
        services.sort(key=lambda x: x["name"])
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
        if not session.get("authenticated"):
            return redirect(url_for("index"))
        return f(*args, **kwargs)

    return decorated_function


@app.route("/")
def index():
    if session.get("authenticated"):
        try:
            status = get_system_status()
            services = get_running_services()  # Get services
            system_info = get_system_info()
            network_info = get_safe_network_info()
            device_name = config.get("DEVICE_NAME", "SystemD Dashboard")

            # Debug logging
            logger.debug(f"Found {len(services)} services")

            # Check if services is empty
            if not services:
                logger.warning("No services retrieved")

            # Get recent events
            events = []
            try:
                with sqlite3.connect("data/metrics.db") as conn:
                    c = conn.cursor()
                    c.execute("SELECT * FROM events ORDER BY timestamp DESC LIMIT 10")
                    events = [
                        {
                            "timestamp": datetime.fromisoformat(row[0]).strftime(
                                "%Y-%m-%d %H:%M:%S"
                            ),
                            "type": row[1],
                            "description": row[2],
                        }
                        for row in c.fetchall()
                    ]
            except Exception as e:
                logger.error(f"Error fetching events: {str(e)}")

            return render_template(
                "index.html",
                status=status,
                services=services,
                system_info=system_info,
                network_info=network_info,
                events=events,
                device_name=device_name,
            )
        except Exception as e:
            logger.error(f"Error in index route: {str(e)}")
            return render_template(
                "index.html", error="Error loading system information"
            )

    return render_template("index.html")


@app.route("/metrics.png")
@login_required
def metrics_plot():
    buf = generate_metrics_plot()
    if buf:
        response = send_file(buf, mimetype="image/png")
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        return response
    return "", 404


@app.route("/api/metrics/history")
@login_required
def get_metrics_history():
    try:
        with sqlite3.connect("data/metrics.db") as conn:
            c = conn.cursor()
            c.execute(
                """SELECT * FROM system_metrics 
                        WHERE timestamp > datetime('now', '-1 day')
                        ORDER BY timestamp DESC"""
            )
            metrics = [
                {
                    "timestamp": row[0],
                    "cpu_percent": row[1],
                    "memory_percent": row[2],
                    "disk_percent": row[3],
                    "temperature": row[4],
                }
                for row in c.fetchall()
            ]
        return jsonify(metrics)
    except Exception as e:
        logger.error(f"Error fetching metrics history: {str(e)}")
        return jsonify({"error": str(e)}), 500


def execute_command(command, shell=False):
    """Execute a system command with detailed error handling and logging"""
    logger.info(f"Attempting to execute command: {command}")

    try:
        # Check current user and permissions
        current_user = subprocess.check_output(["whoami"]).decode().strip()
        logger.info(f"Current user: {current_user}")

        # Check sudo capabilities
        sudo_test = subprocess.run(
            ["sudo", "-n", "true"], capture_output=True, text=True
        )

        if sudo_test.returncode != 0:
            logger.error(f"Sudo test failed: {sudo_test.stderr}")
            return False, "No sudo privileges. Please configure sudoers file."

        # Check if command exists
        if command[0] == "sudo":
            cmd_to_check = command[1]
        else:
            cmd_to_check = command[0]

        which_cmd = subprocess.run(
            ["which", cmd_to_check], capture_output=True, text=True
        )

        if which_cmd.returncode != 0:
            logger.error(f"Command not found: {cmd_to_check}")
            return False, f"Command not found: {cmd_to_check}"

        # Execute the command
        logger.info(f"Executing command with full path: {which_cmd.stdout.strip()}")
        result = subprocess.run(command, capture_output=True, text=True, timeout=30)

        # Log the complete output
        logger.info(f"Command exit code: {result.returncode}")
        logger.info(f"Command stdout: {result.stdout}")
        logger.info(f"Command stderr: {result.stderr}")

        if result.returncode != 0:
            return False, f"Command failed: {result.stderr}"
        return True, result.stdout

    except subprocess.TimeoutExpired:
        logger.error("Command execution timed out")
        return False, "Command timed out after 30 seconds"
    except Exception as e:
        logger.error(f"Unexpected error executing command: {str(e)}", exc_info=True)
        return False, f"Error: {str(e)}"


@app.route("/service-logs/<service_name>")
@login_required
def get_service_logs(service_name):
    if not service_name.isalnum() and not all(
        c in ".-_" for c in service_name if not c.isalnum()
    ):
        return jsonify({"error": "Invalid service name"}), 400

    try:
        result = subprocess.run(
            ["journalctl", "-u", service_name, "-n", "100", "--no-pager"],
            capture_output=True,
            text=True,
        )
        return jsonify({"logs": result.stdout.split("\n")})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


def check_update_lock():
    """Check if there's an existing update process running"""
    try:
        # Check for dpkg lock
        dpkg_lock = subprocess.run(
            ["lsof", "/var/lib/dpkg/lock-frontend"], capture_output=True, text=True
        )

        # Check for apt-get processes
        apt_processes = subprocess.run(
            ["pgrep", "apt-get"], capture_output=True, text=True
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

@app.route("/system-update", methods=["POST"])
@login_required
def system_update():
    logger.info("Starting system update process")
    try:
        # Initial mount fixes
        remount_commands = [
            "sudo mount -o remount,rw,errors=remount-ro /",
            "sudo mount -o remount,rw /boot",
            "sudo mount -o remount,rw /boot/firmware"
        ]
        
        for cmd in remount_commands:
            subprocess.run(cmd.split(), check=False, capture_output=True)
            
        # Test write access to critical paths
        test_paths = ['/etc/default', '/']
        for path in test_paths:
            try:
                test_file = os.path.join(path, 'write_test')
                with open(test_file, 'w') as f:
                    f.write('test')
                os.remove(test_file)
            except Exception as e:
                logger.error(f"Write test failed for {path}: {e}")
                return jsonify({"error": f"System partition {path} is read-only. Please reboot and try again."}), 500

        env = os.environ.copy()
        env.update({
            'DEBIAN_FRONTEND': 'noninteractive',
            'DEBCONF_NONINTERACTIVE_SEEN': 'true',
            'APT_LISTCHANGES_FRONTEND': 'none'
        })

        # First clear any previous failed updates
        cleanup_commands = [
            "sudo rm -f /var/lib/dpkg/lock*",
            "sudo rm -f /var/cache/apt/archives/lock",
            "sudo rm -f /var/cache/apt/archives/rpi-eeprom_26.4-1_all.deb",
            "sudo dpkg --configure -a",
            "sudo apt-get -f install"
        ]
        
        for cmd in cleanup_commands:
            subprocess.run(cmd.split(), check=False, capture_output=True)

        # Update sequence
        update_commands = [
            "sudo apt-get clean",
            "sudo apt-get update",
            "sudo DEBIAN_FRONTEND=noninteractive apt-get -o Dpkg::Options::='--force-confdef' -o Dpkg::Options::='--force-confold' -y upgrade",
            "sudo apt-get -y autoremove",
            "sudo apt-get clean"
        ]

        outputs = []
        for cmd in update_commands:
            process = subprocess.run(
                cmd,
                shell=True,
                env=env,
                capture_output=True,
                text=True
            )
            
            outputs.append({
                'command': cmd,
                'output': process.stdout,
                'error': process.stderr,
                'code': process.returncode
            })
            
            if process.returncode != 0:
                error_details = '\n'.join([
                    f"Command: {o['command']}\nOutput: {o['output']}\nError: {o['error']}\nCode: {o['code']}\n"
                    for o in outputs
                ])
                
                logger.error(f"Update process failed:\n{error_details}")
                return jsonify({
                    "error": "Update process failed",
                    "details": error_details
                }), 500

        return jsonify({
            "status": "success",
            "message": "System update completed successfully",
            "details": outputs
        })

    except Exception as e:
        error_msg = f"System update error: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return jsonify({
            "error": error_msg,
            "details": str(e)
        }), 500
       
@app.route("/metrics-stream")
@login_required
def metrics_stream():
    def generate():
        retry_count = 0
        max_retries = 3

        while retry_count < max_retries:
            try:
                # Get current metrics
                metrics = {
                    "cpu_percent": psutil.cpu_percent(interval=1),
                    "memory_percent": psutil.virtual_memory().percent,
                    "disk_percent": psutil.disk_usage("/").percent,
                    "temperature": get_cpu_temperature() or 0,
                    "timestamp": datetime.now().isoformat(),
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
                logger.error(
                    f"Error in metrics stream (attempt {retry_count}): {str(e)}"
                )
                if retry_count >= max_retries:
                    logger.error("Max retries reached, closing stream")
                    break
                time.sleep(1)  # Brief pause before retry

    response = Response(
        generate(),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )

    # Set a reasonable timeout
    response.timeout = 300  # 5 minutes

    return response


@app.route("/debug/metrics")
@login_required
def debug_metrics():
    try:
        with sqlite3.connect("data/metrics.db") as conn:
            # Get count of metrics
            c = conn.cursor()
            c.execute("SELECT COUNT(*) FROM system_metrics")
            total_count = c.fetchone()[0]

            # Get latest metrics
            c.execute(
                """
                SELECT timestamp, cpu_percent, memory_percent 
                FROM system_metrics 
                ORDER BY timestamp DESC 
                LIMIT 5
            """
            )
            latest_metrics = c.fetchall()

            # Get time range
            c.execute(
                """
                SELECT 
                    MIN(timestamp) as earliest,
                    MAX(timestamp) as latest,
                    (julianday(MAX(timestamp)) - julianday(MIN(timestamp))) * 24 as hours
                FROM system_metrics
            """
            )
            time_range = c.fetchone()

            return jsonify(
                {
                    "total_metrics": total_count,
                    "latest_metrics": latest_metrics,
                    "time_range": {
                        "earliest": time_range[0],
                        "latest": time_range[1],
                        "hours": time_range[2],
                    },
                }
            )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/login", methods=["POST"])
def login():
    provided_key = request.form.get("api_key")
    if provided_key and hmac.compare_digest(provided_key, API_KEY):
        session["authenticated"] = True
        log_event("login", f"Successful login from {request.remote_addr}")
        return redirect(url_for("index"))

    log_event("error", f"Failed login attempt from {request.remote_addr}")
    return render_template("index.html", error="Invalid API key")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))


@app.route("/refresh-status")
@login_required
def refresh_status():
    status = get_system_status()
    services = get_running_services()
    system_info = get_system_info()
    network_info = get_safe_network_info()

    # Add recent events
    events = []
    try:
        with sqlite3.connect("data/metrics.db") as conn:
            c = conn.cursor()
            c.execute("SELECT * FROM events ORDER BY timestamp DESC LIMIT 10")
            events = [
                {"timestamp": row[0], "type": row[1], "description": row[2]}
                for row in c.fetchall()
            ]
    except Exception as e:
        logger.error(f"Error fetching events: {str(e)}")

    return render_template(
        "index.html",
        status=status,
        services=services,
        system_info=system_info,
        network_info=network_info,
        events=events,
    )


# Global cache for network info
_network_info_cache = None
_network_info_timestamp = None


def get_safe_network_info():
    """Get network info with safe default values"""
    try:
        net_io = psutil.net_io_counters()
        return {
            "bytes_sent": net_io.bytes_sent or 0,
            "bytes_recv": net_io.bytes_recv or 0,
            "packets_sent": net_io.packets_sent or 0,
            "packets_recv": net_io.packets_recv or 0,
        }
    except Exception as e:
        logger.error(f"Error getting network info: {str(e)}", exc_info=True)
        return {"bytes_sent": 0, "bytes_recv": 0, "packets_sent": 0, "packets_recv": 0}


def get_template_data(message=None, error=None):
    """Get all required template data with safe defaults"""
    start_time = time.time()
    logger.info("Gathering template data...")

    try:
        data = {
            "status": get_system_status(),
            "system_info": get_system_info(),
            "network_info": get_safe_network_info(),
            "device_name": config.get("DEVICE_NAME", "SystemD Dashboard"),
            "events": get_recent_events(),
            "services": get_running_services(),
        }

        if message:
            data["message"] = message
            logger.info(f"Template message: {message}")
        if error:
            data["error"] = error
            logger.error(f"Template error: {error}")

        logger.info(f"Template data gathered in {time.time() - start_time:.2f} seconds")
        return data

    except Exception as e:
        logger.error(f"Error gathering template data: {str(e)}", exc_info=True)
        # Return minimal safe data
        return {
            "status": {"status": "error"},
            "system_info": {"hostname": "unknown"},
            "network_info": get_safe_network_info(),
            "device_name": "SystemD Dashboard",
            "events": [],
            "services": [],
            "error": f"System error: {str(e)}",
        }


@app.route("/shutdown", methods=["GET"])
@login_required
def shutdown():
    logger.info("Shutdown requested")

    try:
        # Try different shutdown methods
        methods = [
            ["sudo", "systemctl", "poweroff"],
            ["sudo", "shutdown", "-h", "now"],
            ["sudo", "poweroff"],
        ]

        for method in methods:
            logger.info(f"Trying shutdown method: {method}")
            success, message = execute_command(method)
            if success:
                log_event(
                    "system_shutdown", f"System shutdown initiated using {method[0]}"
                )
                template_data = get_template_data()
                template_data["message"] = "System is shutting down..."
                return render_template("index.html", **template_data)
            else:
                logger.error(f"Method {method} failed: {message}")

        # If we get here, all methods failed
        error_msg = "All shutdown methods failed. Check system logs and permissions."
        logger.error(error_msg)
        template_data = get_template_data()
        template_data["error"] = error_msg
        return render_template("index.html", **template_data)

    except Exception as e:
        error_msg = f"Shutdown error: {str(e)}"
        logger.error(error_msg, exc_info=True)
        template_data = get_template_data()
        template_data["error"] = error_msg
        return render_template("index.html", **template_data)


@app.route("/reboot", methods=["GET"])
@login_required
def reboot():
    logger.info("Reboot requested")

    try:
        # First check if we can use sudo
        logger.info("Checking sudo privileges...")
        sudo_test = subprocess.run(
            ["sudo", "-n", "true"], capture_output=True, text=True
        )

        if sudo_test.returncode != 0:
            error_msg = "Insufficient privileges. Please configure sudo without password for reboot command."
            logger.error(f"Sudo check failed: {sudo_test.stderr}")
            return render_template("index.html", **get_template_data(error=error_msg))

        # Try reboot methods
        methods = [
            ["sudo", "systemctl", "reboot"],
            ["sudo", "reboot"],
            ["sudo", "shutdown", "-r", "now"],
        ]

        for method in methods:
            logger.info(f"Attempting reboot with: {' '.join(method)}")
            try:
                result = subprocess.run(
                    method, capture_output=True, text=True, timeout=30
                )
                if result.returncode == 0:
                    success_msg = f"System reboot initiated using {method[0]}"
                    logger.info(success_msg)
                    log_event("system_reboot", success_msg)
                    return render_template(
                        "index.html",
                        **get_template_data(message="System is rebooting..."),
                    )
                logger.error(
                    f"Method {method} failed with return code {result.returncode}"
                )
                logger.error(f"Command output: {result.stdout}")
                logger.error(f"Command error: {result.stderr}")
            except subprocess.TimeoutExpired:
                logger.error(f"Command timeout after 30 seconds: {' '.join(method)}")
            except Exception as e:
                logger.error(f"Error executing {method}: {str(e)}", exc_info=True)
            continue

        # If we get here, all methods failed
        error_msg = "All reboot methods failed. Check system logs and permissions."
        logger.error(error_msg)
        return render_template("index.html", **get_template_data(error=error_msg))

    except Exception as e:
        error_msg = f"Reboot error: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return render_template("index.html", **get_template_data(error=error_msg))


@lru_cache(maxsize=100)
def get_system_info():
    """Get system information with caching and error handling"""
    try:
        return {
            "platform": platform.platform(),
            "python_version": platform.python_version(),
            "processor": platform.processor(),
            "machine": platform.machine(),
            "hostname": platform.node(),
        }
    except Exception as e:
        logger.error(f"Error getting system info: {str(e)}", exc_info=True)
        return {
            "platform": "Unknown",
            "python_version": "Unknown",
            "processor": "Unknown",
            "machine": "Unknown",
            "hostname": "Unknown",
        }


@app.route("/restart-service", methods=["POST"])
@login_required
def restart_service():
    service_name = request.form.get("service")
    if not service_name:
        return render_template(
            "index.html",
            error="Service name not provided",
            status=get_system_status(),
            services=get_running_services(),
            system_info=get_system_info(),
            network_info=get_safe_network_info(),
            device_name=config.get("DEVICE_NAME", "SystemD Dashboard"),
            events=get_recent_events(),
        )

    if not service_name.isalnum() and not all(
        c in ".-_" for c in service_name if not c.isalnum()
    ):
        return render_template(
            "index.html",
            error="Invalid service name",
            status=get_system_status(),
            services=get_running_services(),
            system_info=get_system_info(),
            network_info=get_safe_network_info(),
            device_name=config.get("DEVICE_NAME", "SystemD Dashboard"),
            events=get_recent_events(),
        )

    logger.info(f"Service restart requested for: {service_name}")
    success, message = execute_command(["sudo", "systemctl", "restart", service_name])

    # Get all necessary data including events
    status = get_system_status()
    services = get_running_services()
    system_info = get_system_info()
    network_info = get_safe_network_info()
    events = get_recent_events()

    if success:
        log_event("service_restart", f"Service {service_name} restarted successfully")
        return render_template(
            "index.html",
            status=status,
            services=services,
            system_info=system_info,
            network_info=network_info,
            device_name=config.get("DEVICE_NAME", "SystemD Dashboard"),
            events=events,  # Added events
            message=f"Service {service_name} restarted successfully",
        )

    log_event("error", f"Failed to restart service {service_name}: {message}")
    return render_template(
        "index.html",
        status=status,
        services=services,
        system_info=system_info,
        network_info=network_info,
        device_name=config.get("DEVICE_NAME", "SystemD Dashboard"),
        events=events,  # Added events
        error=f"Failed to restart {service_name}: {message}",
    )


# Add this helper function if it doesn't exist
def get_recent_events():
    try:
        with sqlite3.connect("data/metrics.db") as conn:
            c = conn.cursor()
            c.execute("SELECT * FROM events ORDER BY timestamp DESC LIMIT 10")
            return [
                {
                    "timestamp": datetime.fromisoformat(row[0]).strftime(
                        "%Y-%m-%d %H:%M:%S"
                    ),
                    "type": row[1],
                    "description": row[2],
                }
                for row in c.fetchall()
            ]
    except Exception as e:
        logger.error(f"Error fetching events: {str(e)}")
        return []


if __name__ == "__main__":
    # Initialize database
    init_db()

    metrics_collector = MetricsCollector()
    metrics_collector.start()

    # Run server with optimized settings
    try:
        serve(
            app,
            host="0.0.0.0",
            port=PORT,
            threads=8,
            connection_limit=100,
            channel_timeout=60,
            cleanup_interval=60,
            ident="SystemD Dashboard",
        )
    finally:
        metrics_collector.stop()