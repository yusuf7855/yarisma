#!/usr/bin/env python3
"""
SpectraLoop Backend - OPTIMIZED v3.4 - REAL-TIME Temperature Updates
Ultra-fast temperature monitoring with sub-second updates
"""

from flask import Flask, jsonify, request
from flask_cors import CORS
import serial
import serial.tools.list_ports
import time
import threading
import logging
import os
from datetime import datetime
import signal
import sys
import queue
import json
import re

app = Flask(__name__)
CORS(app, resources={
    r"/api/*": {
        "origins": "*",
        "methods": ["GET", "POST", "OPTIONS"],
        "allow_headers": ["Content-Type"]
    }
})

# Enhanced logging configuration
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('spectraloop.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Thread-safe global state
motor_states = {i: False for i in range(1, 7)}
individual_motor_speeds = {i: 0 for i in range(1, 7)}
group_speeds = {'levitation': 0, 'thrust': 0}

# Temperature and safety system state - OPTIMIZED
temperature_data = {
    'current_temp': 25.0,
    'temp_alarm': False,
    'buzzer_active': False,
    'last_temp_update': datetime.now(),
    'temp_history': [],
    'max_temp_reached': 25.0,
    'alarm_start_time': None,
    'alarm_count': 0,
    'update_frequency': 0.0  # NEW: Updates per second
}

system_state = {
    'armed': False,
    'brake_active': False,
    'relay_brake_active': False,
    'connected': False,
    'last_response': None,
    'errors': 0,
    'commands': 0,
    'uptime': datetime.now(),
    'temperature_emergency': False
}

# Thread synchronization
state_lock = threading.Lock()
shutdown_event = threading.Event()

# Temperature safety constants - OPTIMIZED
TEMP_ALARM_THRESHOLD = 55.0
TEMP_SAFE_THRESHOLD = 50.0
TEMP_WARNING_THRESHOLD = 45.0
MAX_TEMP_HISTORY = 200  # Increased for better tracking

# OPTIMIZED CONSTANTS
CONTINUOUS_READ_INTERVAL = 0.05  # 50ms - Much faster reading
TEMP_UPDATE_THRESHOLD = 0.1     # Update if temp changes by 0.1°C
STATUS_BROADCAST_INTERVAL = 0.5  # 500ms status updates

class OptimizedArduinoController:
    def __init__(self, port=None, baudrate=115200):
        self.port = port or self.find_arduino_port()
        self.baudrate = baudrate
        self.connection = None
        self.is_connected = False
        self.last_command_time = 0
        self.reconnect_attempts = 0
        self.max_attempts = 5
        
        # Command processing - OPTIMIZED
        self.command_queue = queue.Queue(maxsize=200)  # Increased size
        self.response_timeout = 2.0  # Reduced timeout
        
        # Connection management
        self.connection_lock = threading.Lock()
        
        # Background threads
        self.processor_thread = None
        self.monitor_thread = None
        
        # Temperature monitoring - ULTRA-FAST
        self.continuous_reader_thread = None
        self.temp_stats_thread = None
        
        # OPTIMIZED: Arduino stream parsing
        self.stream_buffer = ""
        self.temp_pattern = re.compile(r'\[TEMP:([\d.]+)\]')
        self.heartbeat_pattern = re.compile(r'HEARTBEAT:(\d+),(\d),(\d),(\d),([\d.]+),(\d),(\d)')
        self.temp_alarm_pattern = re.compile(r'TEMP_ALARM:([\d.]+)')
        self.temp_safe_pattern = re.compile(r'TEMP_SAFE:([\d.]+)')
        
        # Performance tracking
        self.temp_updates_count = 0
        self.last_stats_time = time.time()
        
        # Initialize connection safely
        try:
            if self.port:
                self.connect()
                self._start_command_processor()
                self._start_connection_monitor()
                self._start_continuous_reader()
                self._start_temp_stats_monitor()  # NEW: Performance monitoring
            else:
                logger.error("No Arduino port found")
                system_state['connected'] = False
        except KeyboardInterrupt:
            logger.info("Initialization interrupted by user")
            self.disconnect()
            raise
        except Exception as e:
            logger.error(f"Initialization error: {e}")
            self.disconnect()
    
    def find_arduino_port(self):
        """Find available Arduino port - Cross-platform compatible"""
        try:
            ports = serial.tools.list_ports.comports()
            
            # Look for Arduino-specific ports
            for port in ports:
                description = port.description.lower()
                if any(keyword in description for keyword in ['arduino', 'usb serial', 'ch340', 'cp210', 'ftdi']):
                    try:
                        # Test the port
                        test_conn = serial.Serial(port.device, self.baudrate, timeout=1)
                        test_conn.close()
                        logger.info(f"Found Arduino port: {port.device} - {port.description}")
                        return port.device
                    except Exception as e:
                        logger.debug(f"Port {port.device} test failed: {e}")
                        continue
            
            # Fallback to common port names
            common_ports = [
                # Windows
                'COM3', 'COM4', 'COM5', 'COM6', 'COM7', 'COM8', 'COM9', 'COM10',
                # Linux/Mac
                '/dev/ttyUSB0', '/dev/ttyUSB1', '/dev/ttyACM0', '/dev/ttyACM1',
                '/dev/cu.usbmodem*', '/dev/cu.usbserial*'
            ]
            
            for port in common_ports:
                try:
                    if '*' in port:
                        continue
                    if os.path.exists(port) or port.startswith('COM'):
                        test_conn = serial.Serial(port, self.baudrate, timeout=1)
                        test_conn.close()
                        logger.info(f"Found valid port: {port}")
                        return port
                except Exception:
                    continue
            
            logger.warning("No Arduino port found automatically")
            return None
            
        except Exception as e:
            logger.error(f"Port scanning error: {e}")
            return None
    
    def connect(self):
        """Connect to Arduino with enhanced reliability"""
        if self.reconnect_attempts >= self.max_attempts:
            logger.error(f"Max reconnection attempts ({self.max_attempts}) reached")
            return False
        
        if not self.port:
            logger.error("No port specified for connection")
            return False
        
        try:
            with self.connection_lock:
                # Close existing connection if any
                if self.connection:
                    try:
                        self.connection.close()
                    except:
                        pass
                    self.connection = None
                
                # Create connection - OPTIMIZED
                self.connection = serial.Serial(
                    port=self.port,
                    baudrate=self.baudrate,
                    timeout=1,  # Reduced timeout
                    write_timeout=1,  # Reduced timeout
                    parity=serial.PARITY_NONE,
                    stopbits=serial.STOPBITS_ONE,
                    bytesize=serial.EIGHTBITS,
                    rtscts=False,
                    dsrdtr=False
                )
                
                logger.info(f"Serial connection opened: {self.port} @ {self.baudrate}")
                
                # Wait for Arduino to initialize - REDUCED
                time.sleep(2)  # Reduced from 3 to 2 seconds
                self.connection.flushInput()
                self.connection.flushOutput()
                
                # Test connection
                if self._test_connection():
                    self.is_connected = True
                    self.reconnect_attempts = 0
                    system_state['connected'] = True
                    logger.info("Arduino connection successful - ULTRA-FAST temperature monitoring active")
                    return True
                else:
                    raise Exception("Connection test failed")
        
        except Exception as e:
            self.reconnect_attempts += 1
            logger.error(f"Connection error (attempt {self.reconnect_attempts}/{self.max_attempts}): {e}")
            system_state['connected'] = False
            self.is_connected = False
            if self.connection:
                try:
                    self.connection.close()
                except:
                    pass
                self.connection = None
            return False
    
    def _test_connection(self):
        """Test Arduino connection - OPTIMIZED"""
        try:
            if not self.connection:
                return False
            
            # Send PING command
            self.connection.write(b"PING\n")
            self.connection.flush()
            
            start_time = time.time()
            response = ""
            
            while time.time() - start_time < 2.0:  # Reduced timeout
                if self.connection.in_waiting > 0:
                    try:
                        data = self.connection.read(self.connection.in_waiting)
                        response += data.decode('utf-8', errors='ignore')
                        
                        if any(keyword in response.upper() for keyword in ["PONG", "ACK", "SPECTRALOOP", "READY"]):
                            logger.info(f"Arduino responded: {response.strip()}")
                            return True
                    except Exception as e:
                        logger.debug(f"Read error during test: {e}")
                        break
                time.sleep(0.05)  # Reduced sleep
            
            logger.warning(f"Arduino test failed. Response: '{response.strip()}'")
            return False
            
        except Exception as e:
            logger.error(f"Connection test error: {e}")
            return False
    
    def _start_continuous_reader(self):
        """OPTIMIZED: Ultra-fast continuous Arduino reading"""
        if self.continuous_reader_thread and self.continuous_reader_thread.is_alive():
            return
        
        self.continuous_reader_thread = threading.Thread(target=self._continuous_reader, daemon=True, name="UltraFastReader")
        self.continuous_reader_thread.start()
        logger.info("ULTRA-FAST continuous Arduino reader started (50ms intervals)")
    
    def _start_temp_stats_monitor(self):
        """NEW: Temperature update frequency monitor"""
        if self.temp_stats_thread and self.temp_stats_thread.is_alive():
            return
        
        self.temp_stats_thread = threading.Thread(target=self._temp_stats_monitor, daemon=True, name="TempStatsMonitor")
        self.temp_stats_thread.start()
        logger.info("Temperature statistics monitor started")
    
    def _temp_stats_monitor(self):
        """NEW: Monitor temperature update frequency"""
        while not shutdown_event.is_set():
            try:
                time.sleep(1.0)  # Check every second
                
                current_time = time.time()
                elapsed = current_time - self.last_stats_time
                
                if elapsed >= 1.0:
                    updates_per_second = self.temp_updates_count / elapsed
                    
                    with state_lock:
                        temperature_data['update_frequency'] = round(updates_per_second, 2)
                    
                    if updates_per_second > 0:
                        logger.debug(f"Temperature updates: {updates_per_second:.2f} Hz")
                    else:
                        logger.warning("No temperature updates received!")
                    
                    # Reset counters
                    self.temp_updates_count = 0
                    self.last_stats_time = current_time
                
            except Exception as e:
                logger.error(f"Temperature stats monitor error: {e}")
                time.sleep(5)
    
    def _continuous_reader(self):
        """OPTIMIZED: Ultra-fast Arduino stream reader"""
        logger.info("Ultra-fast continuous reader thread started")
        buffer = ""
        last_temp = None
        
        while not shutdown_event.is_set():
            try:
                if not self.is_connected or not self.connection:
                    time.sleep(0.5)
                    continue
                
                # Ultra-fast reading - every 50ms
                if self.connection.in_waiting > 0:
                    try:
                        # Read all available data at once
                        data = self.connection.read(self.connection.in_waiting)
                        new_data = data.decode('utf-8', errors='ignore')
                        buffer += new_data
                        
                        # Process complete lines immediately
                        while '\n' in buffer:
                            line, buffer = buffer.split('\n', 1)
                            line = line.strip()
                            
                            if line:
                                # Fast temperature extraction
                                temp_value = self._extract_temperature_fast(line)
                                if temp_value is not None:
                                    # Only update if temperature changed significantly
                                    if last_temp is None or abs(temp_value - last_temp) >= TEMP_UPDATE_THRESHOLD:
                                        self._update_temperature_fast(temp_value)
                                        last_temp = temp_value
                                        self.temp_updates_count += 1
                                    else:
                                        # Still count minor updates for frequency calculation
                                        self.temp_updates_count += 1
                                
                                # Process other messages
                                self._parse_system_messages(line)
                    
                    except Exception as e:
                        logger.debug(f"Fast read error: {e}")
                
                # Ultra-fast polling
                time.sleep(CONTINUOUS_READ_INTERVAL)
                
            except Exception as e:
                logger.error(f"Continuous reader error: {e}")
                time.sleep(1)
        
        logger.info("Ultra-fast continuous reader thread stopped")
    
    def _extract_temperature_fast(self, line):
        """OPTIMIZED: Fast temperature extraction"""
        try:
            # Priority order - most common patterns first
            
            # 1. [TEMP:xx.xx] format (most common from ACK messages)
            temp_match = self.temp_pattern.search(line)
            if temp_match:
                return float(temp_match.group(1))
            
            # 2. HEARTBEAT format
            heartbeat_match = self.heartbeat_pattern.search(line)
            if heartbeat_match:
                return float(heartbeat_match.group(5))  # Temperature is 5th element
            
            # 3. TEMP_ALARM format
            alarm_match = self.temp_alarm_pattern.search(line)
            if alarm_match:
                return float(alarm_match.group(1))
            
            # 4. TEMP_SAFE format
            safe_match = self.temp_safe_pattern.search(line)
            if safe_match:
                return float(safe_match.group(1))
            
            return None
            
        except (ValueError, IndexError):
            return None
    
    def _update_temperature_fast(self, temp_value):
        """OPTIMIZED: Ultra-fast temperature update"""
        try:
            current_time = datetime.now()
            
            with state_lock:
                old_temp = temperature_data['current_temp']
                temperature_data['current_temp'] = temp_value
                temperature_data['last_temp_update'] = current_time
                
                # Update max temperature
                if temp_value > temperature_data['max_temp_reached']:
                    temperature_data['max_temp_reached'] = temp_value
                
                # Add to history - but limit frequency to avoid memory issues
                if len(temperature_data['temp_history']) == 0 or \
                   (current_time - datetime.fromisoformat(temperature_data['temp_history'][-1]['timestamp'])).total_seconds() >= 0.5:
                    temperature_data['temp_history'].append({
                        'timestamp': current_time.isoformat(),
                        'temperature': temp_value
                    })
                    
                    # Keep only recent history
                    if len(temperature_data['temp_history']) > MAX_TEMP_HISTORY:
                        temperature_data['temp_history'] = temperature_data['temp_history'][-MAX_TEMP_HISTORY:]
                
                # Log significant changes
                if abs(temp_value - old_temp) > 0.5:
                    logger.info(f"Temperature: {old_temp:.1f}°C → {temp_value:.1f}°C")
                
        except Exception as e:
            logger.error(f"Fast temperature update error: {e}")
    
    def _parse_system_messages(self, line):
        """OPTIMIZED: Fast system message parsing"""
        try:
            line_upper = line.upper()
            
            # Temperature alarms
            if "TEMP_ALARM:" in line:
                with state_lock:
                    if not temperature_data['temp_alarm']:
                        temperature_data['temp_alarm'] = True
                        temperature_data['buzzer_active'] = True
                        temperature_data['alarm_start_time'] = datetime.now()
                        temperature_data['alarm_count'] += 1
                        system_state['temperature_emergency'] = True
                        logger.warning(f"🚨 TEMPERATURE ALARM! Line: {line}")
            
            elif "TEMP_SAFE:" in line:
                with state_lock:
                    if temperature_data['temp_alarm']:
                        temperature_data['temp_alarm'] = False
                        temperature_data['buzzer_active'] = False
                        system_state['temperature_emergency'] = False
                        logger.info(f"✅ Temperature returned to safe level. Line: {line}")
            
            # Emergency stop
            elif "EMERGENCY_STOP" in line_upper:
                logger.warning(f"🛑 Emergency stop detected: {line}")
            
            # System state from HEARTBEAT
            elif "HEARTBEAT:" in line:
                heartbeat_match = self.heartbeat_pattern.search(line)
                if heartbeat_match:
                    _, armed, brake_active, relay_brake_active, _, temp_alarm, _ = heartbeat_match.groups()
                    
                    with state_lock:
                        system_state['armed'] = bool(int(armed))
                        system_state['brake_active'] = bool(int(brake_active))
                        system_state['relay_brake_active'] = bool(int(relay_brake_active))
                        
                        # Update temperature alarm from heartbeat
                        temp_alarm_active = bool(int(temp_alarm))
                        if temp_alarm_active != temperature_data['temp_alarm']:
                            temperature_data['temp_alarm'] = temp_alarm_active
                            if temp_alarm_active:
                                temperature_data['alarm_start_time'] = datetime.now()
                                temperature_data['alarm_count'] += 1
                                system_state['temperature_emergency'] = True
                
        except Exception as e:
            logger.debug(f"System message parsing error: {e}")
    
    def _start_command_processor(self):
        """Start background command processor thread"""
        if self.processor_thread and self.processor_thread.is_alive():
            return
        
        self.processor_thread = threading.Thread(target=self._command_processor, daemon=True, name="CommandProcessor")
        self.processor_thread.start()
        logger.info("Command processor started")
    
    def _start_connection_monitor(self):
        """Start background connection monitor thread"""
        if self.monitor_thread and self.monitor_thread.is_alive():
            return
        
        self.monitor_thread = threading.Thread(target=self._connection_monitor, daemon=True, name="ConnectionMonitor")
        self.monitor_thread.start()
        logger.info("Connection monitor started")
    
    def _command_processor(self):
        """Background command processor with error handling"""
        logger.info("Command processor thread started")
        while not shutdown_event.is_set():
            try:
                if not self.command_queue.empty():
                    try:
                        command_data = self.command_queue.get(timeout=1)
                        self._execute_command(command_data)
                        self.command_queue.task_done()
                    except queue.Empty:
                        continue
                else:
                    time.sleep(0.05)  # Reduced sleep for faster processing
                    
            except Exception as e:
                logger.error(f"Command processor error: {e}")
                time.sleep(0.5)
        
        logger.info("Command processor thread stopped")
    
    def _connection_monitor(self):
        """Background connection monitor - OPTIMIZED"""
        logger.info("Connection monitor thread started")
        while not shutdown_event.is_set():
            try:
                if self.is_connected:
                    # Send periodic heartbeat - less frequent
                    if time.time() - self.last_command_time > 60:  # Increased to 60 seconds
                        success, _ = self.send_command_sync("PING", timeout=1.0)
                        if not success:
                            logger.warning("Heartbeat failed - connection may be lost")
                            self.is_connected = False
                            system_state['connected'] = False
                else:
                    # Try to reconnect
                    logger.info("Attempting automatic reconnection...")
                    if self.connect():
                        logger.info("Automatic reconnection successful")
                        # Restart continuous reader if needed
                        if not self.continuous_reader_thread or not self.continuous_reader_thread.is_alive():
                            self._start_continuous_reader()
                        if not self.temp_stats_thread or not self.temp_stats_thread.is_alive():
                            self._start_temp_stats_monitor()
                    else:
                        time.sleep(5)  # Reduced retry interval
                
                time.sleep(10)  # Reduced monitoring interval
                
            except Exception as e:
                logger.error(f"Connection monitor error: {e}")
                time.sleep(5)
        
        logger.info("Connection monitor thread stopped")
    
    def send_command_sync(self, command, timeout=3.0):
        """Send command synchronously with timeout - OPTIMIZED"""
        if not self.is_connected or not self.connection or shutdown_event.is_set():
            return False, "Not connected"
        
        try:
            with self.connection_lock:
                # Minimal rate limiting
                current_time = time.time()
                time_since_last = current_time - self.last_command_time
                if time_since_last < 0.02:  # Reduced from 0.05 to 0.02
                    time.sleep(0.02 - time_since_last)
                
                # Send command
                command_bytes = f"{command}\n".encode('utf-8')
                self.connection.write(command_bytes)
                self.connection.flush()
                self.last_command_time = time.time()
                
                # Read response with timeout
                start_time = time.time()
                response = ""
                
                while time.time() - start_time < timeout:
                    if shutdown_event.is_set():
                        return False, "Shutdown requested"
                    
                    if self.connection.in_waiting > 0:
                        try:
                            data = self.connection.read(self.connection.in_waiting)
                            response += data.decode('utf-8', errors='ignore')
                            
                            # Check for command completion
                            if any(keyword in response for keyword in ["MOTOR_STARTED", "MOTOR_STOPPED", "LEV_GROUP_STARTED", 
                                                                       "THR_GROUP_STARTED", "ARMED", "RELAY_BRAKE:", 
                                                                       "PONG", "ACK:", "BRAKE_", "DISARMED", "EMERGENCY_STOP"]):
                                break
                            
                            if '\n' in response or len(response) > 150:
                                break
                        except Exception as e:
                            logger.debug(f"Read error: {e}")
                            break
                    
                    time.sleep(0.01)  # Reduced polling interval
                
                # Update statistics
                with state_lock:
                    system_state['commands'] += 1
                    system_state['last_response'] = datetime.now()
                
                response = response.strip()
                if response:
                    logger.debug(f"Command '{command}' response: '{response}'")
                    return True, response
                else:
                    logger.warning(f"Command '{command}' got empty response")
                    return False, "Empty response"
                
        except Exception as e:
            logger.error(f"Sync command error for '{command}': {e}")
            with state_lock:
                system_state['errors'] += 1
            return False, str(e)
    
    def _execute_command(self, command_data):
        """Execute command from queue with retry logic"""
        if not self.is_connected or shutdown_event.is_set():
            return
        
        command = command_data['command']
        attempts = command_data.get('attempts', 0)
        max_attempts = 2
        
        try:
            success, response = self.send_command_sync(command, timeout=1.5)  # Reduced timeout
            
            if success:
                logger.debug(f"Command executed: {command}")
            else:
                if attempts < max_attempts:
                    command_data['attempts'] = attempts + 1
                    try:
                        self.command_queue.put(command_data, timeout=0.05)
                        logger.debug(f"Retrying command: {command}")
                    except queue.Full:
                        logger.warning(f"Queue full, dropping command: {command}")
                else:
                    logger.error(f"Command failed: {command}")
                
        except Exception as e:
            logger.error(f"Command execution error: {e}")
    
    def reconnect(self):
        """Manual reconnect with full reset"""
        logger.info("Manual reconnection requested")
        
        old_connected = self.is_connected
        self.is_connected = False
        
        try:
            self.disconnect(keep_threads=True)
            time.sleep(1)  # Reduced delay
            
            self.reconnect_attempts = 0
            
            new_port = self.find_arduino_port()
            if new_port:
                self.port = new_port
                logger.info(f"Using port for reconnection: {self.port}")
            
            success = self.connect()
            
            if success:
                # Restart all monitoring threads
                self._start_continuous_reader()
                self._start_temp_stats_monitor()
                logger.info("Manual reconnection successful")
                return True
            else:
                logger.error("Manual reconnection failed")
                return False
                
        except Exception as e:
            logger.error(f"Manual reconnection error: {e}")
            return False
    
    def disconnect(self, keep_threads=False):
        """Safely disconnect from Arduino"""
        logger.info("Disconnecting Arduino...")
        
        self.is_connected = False
        system_state['connected'] = False
        
        if self.connection:
            try:
                acquired = self.connection_lock.acquire(timeout=2.0)  # Reduced timeout
                try:
                    if acquired:
                        self.connection.close()
                        logger.info("Serial connection closed")
                    else:
                        self.connection.close()
                        logger.warning("Serial connection force closed")
                except Exception as e:
                    logger.debug(f"Serial close error: {e}")
                finally:
                    if acquired:
                        self.connection_lock.release()
                        
            except Exception as e:
                logger.debug(f"Disconnect error: {e}")
            finally:
                self.connection = None
        
        if not keep_threads:
            logger.info("Stopping background threads...")
            shutdown_event.set()
            
            threads = [
                (self.processor_thread, "CommandProcessor"),
                (self.monitor_thread, "ConnectionMonitor"),
                (self.continuous_reader_thread, "ContinuousReader"),
                (self.temp_stats_thread, "TempStatsMonitor")
            ]
            
            for thread, name in threads:
                if thread and thread.is_alive():
                    thread.join(timeout=1.0)  # Reduced timeout
        
        logger.info("Arduino disconnected successfully")

# Initialize optimized Arduino controller
logger.info("Initializing OPTIMIZED Arduino controller...")
try:
    arduino_controller = OptimizedArduinoController()
except Exception as e:
    logger.error(f"Failed to initialize Arduino controller: {e}")
    arduino_controller = None

# API Routes - OPTIMIZED

@app.route('/api/status', methods=['GET'])
def get_status():
    """Get comprehensive system status - OPTIMIZED"""
    try:
        with state_lock:
            uptime_seconds = (datetime.now() - system_state['uptime']).total_seconds()
            
            return jsonify({
                'connected': arduino_controller.is_connected if arduino_controller else False,
                'armed': system_state['armed'],
                'motors': motor_states.copy(),
                'individual_speeds': individual_motor_speeds.copy(),
                'group_speeds': group_speeds.copy(),
                'brake_active': system_state['brake_active'],
                'relay_brake_active': system_state['relay_brake_active'],
                'temperature': {
                    'current': temperature_data['current_temp'],
                    'alarm': temperature_data['temp_alarm'],
                    'buzzer_active': temperature_data['buzzer_active'],
                    'max_reached': temperature_data['max_temp_reached'],
                    'last_update': temperature_data['last_temp_update'].isoformat(),
                    'alarm_threshold': TEMP_ALARM_THRESHOLD,
                    'safe_threshold': TEMP_SAFE_THRESHOLD,
                    'warning_threshold': TEMP_WARNING_THRESHOLD,
                    'emergency_active': system_state['temperature_emergency'],
                    'alarm_count': temperature_data['alarm_count'],
                    'history_count': len(temperature_data['temp_history']),
                    'update_frequency': temperature_data['update_frequency']  # NEW
                },
                'stats': {
                    'commands': system_state['commands'],
                    'errors': system_state['errors'],
                    'uptime_seconds': int(uptime_seconds),
                    'last_response': system_state['last_response'].isoformat() if system_state['last_response'] else None,
                    'reconnect_attempts': arduino_controller.reconnect_attempts if arduino_controller else 0
                },
                'timestamp': datetime.now().isoformat(),
                'version': '3.4-ULTRA-FAST-OPTIMIZED'
            })
    except Exception as e:
        logger.error(f"Status endpoint error: {e}")
        return jsonify({'error': str(e), 'connected': False}), 500

@app.route('/api/temperature', methods=['GET'])
def get_temperature_data():
    """Get detailed temperature data - ULTRA-FAST"""
    try:
        with state_lock:
            current_time = datetime.now()
            last_update_age = (current_time - temperature_data['last_temp_update']).total_seconds()
            
            alarm_duration = None
            if temperature_data['temp_alarm'] and temperature_data['alarm_start_time']:
                alarm_duration = (current_time - temperature_data['alarm_start_time']).total_seconds()
            
            return jsonify({
                'current_temperature': temperature_data['current_temp'],
                'temperature_alarm': temperature_data['temp_alarm'],
                'buzzer_active': temperature_data['buzzer_active'],
                'max_temperature_reached': temperature_data['max_temp_reached'],
                'last_update': temperature_data['last_temp_update'].isoformat(),
                'thresholds': {
                    'alarm': TEMP_ALARM_THRESHOLD,
                    'safe': TEMP_SAFE_THRESHOLD,
                    'warning': TEMP_WARNING_THRESHOLD
                },
                'alarm_info': {
                    'count': temperature_data['alarm_count'],
                    'start_time': temperature_data['alarm_start_time'].isoformat() if temperature_data['alarm_start_time'] else None,
                    'duration_seconds': alarm_duration
                },
                'safety_status': {
                    'emergency_active': system_state['temperature_emergency'],
                    'can_arm_system': not temperature_data['temp_alarm'] and temperature_data['current_temp'] < TEMP_ALARM_THRESHOLD - 5,
                    'safe_to_operate': temperature_data['current_temp'] < TEMP_WARNING_THRESHOLD
                },
                'history': temperature_data['temp_history'][-30:],  # Son 30 okuma
                'timestamp': current_time.isoformat(),
                'performance': {
                    'update_frequency_hz': temperature_data['update_frequency'],
                    'last_update_ago_seconds': last_update_age,
                    'status': 'real-time' if last_update_age < 2.0 else 'delayed',
                    'continuous_reader_alive': arduino_controller.continuous_reader_thread.is_alive() if arduino_controller and arduino_controller.continuous_reader_thread else False,
                    'temp_stats_alive': arduino_controller.temp_stats_thread.is_alive() if arduino_controller and arduino_controller.temp_stats_thread else False,
                    'optimization_level': 'ultra-fast'
                }
            })
    except Exception as e:
        logger.error(f"Temperature endpoint error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/temperature/realtime', methods=['GET'])
def get_realtime_temperature():
    """NEW: Ultra-fast temperature endpoint for real-time updates"""
    try:
        with state_lock:
            current_time = datetime.now()
            last_update_age = (current_time - temperature_data['last_temp_update']).total_seconds()
            
            return jsonify({
                'temperature': temperature_data['current_temp'],
                'alarm': temperature_data['temp_alarm'],
                'buzzer': temperature_data['buzzer_active'],
                'last_update': temperature_data['last_temp_update'].isoformat(),
                'age_seconds': last_update_age,
                'frequency_hz': temperature_data['update_frequency'],
                'timestamp': current_time.isoformat(),
                'status': 'real-time' if last_update_age < 1.0 else 'delayed'
            })
    except Exception as e:
        logger.error(f"Realtime temperature error: {e}")
        return jsonify({'error': str(e)}), 500

# Simplified motor control for testing
@app.route('/api/system/arm', methods=['POST'])
def arm_system():
    """Arm system - OPTIMIZED"""
    if not arduino_controller or not arduino_controller.is_connected:
        return jsonify({'status': 'error', 'message': 'Arduino not connected'}), 503
    
    if temperature_data['temp_alarm']:
        return jsonify({
            'status': 'error',
            'message': 'Cannot arm - temperature alarm active',
            'current_temp': temperature_data['current_temp']
        }), 400
    
    try:
        success, response = arduino_controller.send_command_sync("ARM", timeout=3.0)
        
        if success and "ARMED" in response.upper():
            with state_lock:
                system_state['armed'] = True
            logger.info(f"System ARMED - Temp: {temperature_data['current_temp']}°C")
            return jsonify({
                'status': 'armed',
                'message': 'System armed successfully',
                'current_temp': temperature_data['current_temp']
            })
        else:
            return jsonify({'status': 'error', 'message': f'Arduino error: {response}'}), 500
            
    except Exception as e:
        logger.error(f"Arm system error: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/ping', methods=['GET'])
def ping():
    """Ultra-fast health check with temperature"""
    try:
        with state_lock:
            temp_age = (datetime.now() - temperature_data['last_temp_update']).total_seconds()
            
            return jsonify({
                'status': 'ok',
                'timestamp': datetime.now().isoformat(),
                'arduino_connected': arduino_controller.is_connected if arduino_controller else False,
                'temperature': {
                    'current': temperature_data['current_temp'],
                    'alarm': temperature_data['temp_alarm'],
                    'age_seconds': temp_age,
                    'frequency_hz': temperature_data['update_frequency'],
                    'status': 'real-time' if temp_age < 1.0 else 'delayed'
                },
                'performance': {
                    'continuous_reader': arduino_controller.continuous_reader_thread.is_alive() if arduino_controller and arduino_controller.continuous_reader_thread else False,
                    'temp_stats_monitor': arduino_controller.temp_stats_thread.is_alive() if arduino_controller and arduino_controller.temp_stats_thread else False,
                    'optimization': 'ultra-fast'
                },
                'version': '3.4-ULTRA-FAST'
            })
        
    except Exception as e:
        logger.error(f"Ping error: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

# Background monitoring - OPTIMIZED
def optimized_background_monitor():
    """Ultra-fast background monitoring"""
    logger.info("OPTIMIZED background monitor started")
    
    while not shutdown_event.is_set():
        try:
            # Connection monitoring
            if arduino_controller and not arduino_controller.is_connected:
                if arduino_controller.reconnect_attempts < arduino_controller.max_attempts:
                    logger.info("Auto-reconnection attempt...")
                    if arduino_controller.reconnect():
                        logger.info("Auto-reconnection successful")
            
            # Temperature monitoring
            with state_lock:
                temp_age = (datetime.now() - temperature_data['last_temp_update']).total_seconds()
                
                if temp_age > 10:  # 10 seconds is too old
                    logger.warning(f"Temperature data is stale: {temp_age:.1f}s old")
                    
                    # Try to restart continuous reader
                    if arduino_controller and arduino_controller.is_connected:
                        if not arduino_controller.continuous_reader_thread or not arduino_controller.continuous_reader_thread.is_alive():
                            logger.info("Restarting continuous reader...")
                            arduino_controller._start_continuous_reader()
                
                # Update frequency monitoring
                if temperature_data['update_frequency'] < 0.5:  # Less than 0.5 Hz
                    logger.warning(f"Low temperature update frequency: {temperature_data['update_frequency']:.2f} Hz")
            
            shutdown_event.wait(5)  # Monitor every 5 seconds
            
        except Exception as e:
            logger.error(f"Background monitor error: {e}")
            shutdown_event.wait(5)
    
    logger.info("OPTIMIZED background monitor stopped")

# Start optimized background monitor
monitor_thread = threading.Thread(target=optimized_background_monitor, daemon=True, name="OptimizedMonitor")
monitor_thread.start()

# Graceful shutdown handler
def signal_handler(sig, frame):
    """Graceful shutdown handler"""
    logger.info("Shutdown signal received...")
    
    try:
        shutdown_event.set()
        
        if arduino_controller:
            arduino_controller.disconnect()
        
        logger.info("OPTIMIZED backend shutdown completed")
        
    except Exception as e:
        logger.error(f"Shutdown error: {e}")
    finally:
        sys.exit(0)

# Register signal handlers
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

if __name__ == '__main__':
    logger.info("=" * 80)
    logger.info("SpectraLoop Backend OPTIMIZED v3.4 - ULTRA-FAST TEMPERATURE")
    logger.info("=" * 80)
    
    try:
        if arduino_controller and arduino_controller.is_connected:
            logger.info(f"Arduino Status: Connected to {arduino_controller.port}")
            logger.info("ULTRA-FAST FEATURES:")
            logger.info("   ⚡ 50ms Arduino polling (20 Hz)")
            logger.info("   ⚡ Sub-second temperature updates")
            logger.info("   ⚡ Real-time stream processing")
            logger.info("   ⚡ Performance monitoring")
            logger.info("   ⚡ Optimized pattern matching")
            logger.info("   ⚡ Reduced latencies everywhere")
        else:
            logger.warning("Arduino Status: Not Connected")
        
        logger.info("=" * 80)
        logger.info("Starting ULTRA-FAST Flask server...")
        
        app.run(
            host='0.0.0.0', 
            port=5001, 
            debug=False, 
            threaded=True,
            use_reloader=False
        )
        
    except KeyboardInterrupt:
        logger.info("Interrupt received - shutting down...")
        signal_handler(signal.SIGINT, None)
    except Exception as e:
        logger.error(f"Server error: {e}")
        signal_handler(signal.SIGTERM, None)
    finally:
        logger.info("OPTIMIZED server shutdown complete")