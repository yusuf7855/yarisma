#!/usr/bin/env python3
"""
SpectraLoop Motor Control Backend - Final v3.3 - Temperature Safety System
Arduino sıcaklık sensörü + buzzer + güvenlik sistemi entegrasyonu
Individual + Group motor control + Temperature monitoring + Safety features
Motor Pin Mapping: İtki (3,7), Levitasyon (2,4,5,6)
Temperature Safety: Pin8->DS18B20, Pin9->Buzzer, Pin11->RelayBrake
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

# Temperature and safety system state
temperature_data = {
    'current_temp': 25.0,
    'temp_alarm': False,
    'buzzer_active': False,
    'last_temp_update': datetime.now(),
    'temp_history': [],
    'max_temp_reached': 25.0,
    'alarm_start_time': None,
    'alarm_count': 0
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

# Temperature safety constants
TEMP_ALARM_THRESHOLD = 55.0
TEMP_SAFE_THRESHOLD = 50.0
TEMP_WARNING_THRESHOLD = 45.0
MAX_TEMP_HISTORY = 100

class ProductionArduinoController:
    def __init__(self, port=None, baudrate=115200):
        self.port = port or self.find_arduino_port()
        self.baudrate = baudrate
        self.connection = None
        self.is_connected = False
        self.last_command_time = 0
        self.reconnect_attempts = 0
        self.max_attempts = 5
        
        # Command processing
        self.command_queue = queue.Queue(maxsize=100)
        self.response_timeout = 3.0
        
        # Connection management
        self.connection_lock = threading.Lock()
        
        # Background threads
        self.processor_thread = None
        self.monitor_thread = None
        
        # Temperature monitoring
        self.temp_monitor_thread = None
        self.last_temp_request = 0
        
        # Initialize connection safely
        try:
            if self.port:
                self.connect()
                self._start_command_processor()
                self._start_connection_monitor()
                self._start_temperature_monitor()
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
                
                # Check if port exists (for Unix-like systems)
                if not self.port.startswith('COM') and not os.path.exists(self.port):
                    logger.error(f"Port {self.port} does not exist")
                    new_port = self.find_arduino_port()
                    if new_port:
                        self.port = new_port
                        logger.info(f"Switching to new port: {self.port}")
                    else:
                        raise Exception("No valid Arduino port available")
                
                # Create connection
                self.connection = serial.Serial(
                    port=self.port,
                    baudrate=self.baudrate,
                    timeout=3,
                    write_timeout=2,
                    parity=serial.PARITY_NONE,
                    stopbits=serial.STOPBITS_ONE,
                    bytesize=serial.EIGHTBITS,
                    rtscts=False,
                    dsrdtr=False
                )
                
                logger.info(f"Serial connection opened: {self.port} @ {self.baudrate}")
                
                # Wait for Arduino to initialize
                time.sleep(3)
                self.connection.flushInput()
                self.connection.flushOutput()
                
                # Test connection with multiple attempts
                connection_success = False
                for attempt in range(3):
                    if self._test_connection():
                        connection_success = True
                        break
                    time.sleep(1)
                
                if connection_success:
                    self.is_connected = True
                    self.reconnect_attempts = 0
                    system_state['connected'] = True
                    logger.info("Arduino connection successful - Temperature safety system active")
                    return True
                else:
                    raise Exception("Connection test failed after multiple attempts")
        
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
        """Test Arduino connection with improved reliability"""
        try:
            if not self.connection:
                return False
            
            # Send PING command
            self.connection.write(b"PING\n")
            self.connection.flush()
            
            start_time = time.time()
            response = ""
            
            while time.time() - start_time < 3.0:
                if self.connection.in_waiting > 0:
                    try:
                        data = self.connection.read(self.connection.in_waiting)
                        response += data.decode('utf-8', errors='ignore')
                        
                        # Check for valid Arduino responses
                        if any(keyword in response.upper() for keyword in ["PONG", "ACK", "SPECTRALOOP", "READY"]):
                            logger.info(f"Arduino responded: {response.strip()}")
                            return True
                    except Exception as e:
                        logger.debug(f"Read error during test: {e}")
                        break
                time.sleep(0.1)
            
            logger.warning(f"Arduino test failed. Response: '{response.strip()}'")
            return False
            
        except Exception as e:
            logger.error(f"Connection test error: {e}")
            return False
    
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
    
    def _start_temperature_monitor(self):
        """Start background temperature monitor thread"""
        if self.temp_monitor_thread and self.temp_monitor_thread.is_alive():
            return
        
        self.temp_monitor_thread = threading.Thread(target=self._temperature_monitor, daemon=True, name="TemperatureMonitor")
        self.temp_monitor_thread.start()
        logger.info("Temperature monitor started")
    
    def _temperature_monitor(self):
        """Background temperature monitoring with safety checks"""
        logger.info("Temperature monitor thread started")
        while not shutdown_event.is_set():
            try:
                if self.is_connected:
                    # Request temperature status every 5 seconds
                    current_time = time.time()
                    if current_time - self.last_temp_request > 5.0:
                        self._request_temperature_status()
                        self.last_temp_request = current_time
                
                shutdown_event.wait(2)
                
            except Exception as e:
                logger.error(f"Temperature monitor error: {e}")
                shutdown_event.wait(5)
        
        logger.info("Temperature monitor thread stopped")
    
    def _request_temperature_status(self):
        """Request temperature status from Arduino"""
        try:
            logger.info("Requesting temperature status from Arduino...")  # INFO seviyesine çık
            success, response = self.send_command_sync("TEMP_STATUS", timeout=3.0)
            
            if success and response:
                logger.info(f"Temperature response received: {response}")  # INFO seviyesine çık
                self._parse_temperature_response(response)
            else:
                logger.warning(f"Temperature request failed: {response}")  # WARNING seviyesine çık
                
        except Exception as e:
            logger.error(f"Temperature request error: {e}") # ERROR seviyesine çık
    
    def _parse_temperature_response(self, response):
        """Parse temperature response from Arduino - Enhanced Debug"""
        try:
            logger.info(f"Parsing temperature response: '{response}'")
            lines = response.split('\n')
            temp_data = {}
            
            for line in lines:
                line = line.strip()
                logger.debug(f"Processing line: '{line}'")
                if ':' in line:
                    key, value = line.split(':', 1)
                    temp_data[key] = value
                    logger.debug(f"Extracted: {key} = {value}")
            
            logger.info(f"Parsed temp_data: {temp_data}")
            
            # Update temperature data
            if 'Temperature' in temp_data:
                try:
                    current_temp = float(temp_data['Temperature'])
                    logger.info(f"Temperature value extracted: {current_temp}")
                    
                    with state_lock:
                        old_temp = temperature_data['current_temp']
                        temperature_data['current_temp'] = current_temp
                        temperature_data['last_temp_update'] = datetime.now()
                        
                        logger.info(f"Temperature updated: {old_temp} -> {current_temp}")
                        
                        # Update max temperature
                        if current_temp > temperature_data['max_temp_reached']:
                            temperature_data['max_temp_reached'] = current_temp
                            logger.info(f"New max temperature: {current_temp}")
                        
                        # Add to temperature history
                        temperature_data['temp_history'].append({
                            'timestamp': datetime.now().isoformat(),
                            'temperature': current_temp
                        })
                        
                        # Keep only last 100 readings
                        if len(temperature_data['temp_history']) > MAX_TEMP_HISTORY:
                            temperature_data['temp_history'] = temperature_data['temp_history'][-MAX_TEMP_HISTORY:]
                        
                        # Update alarm status
                        old_alarm = temperature_data['temp_alarm']
                        temperature_data['temp_alarm'] = temp_data.get('TempAlarm', '0') == '1'
                        temperature_data['buzzer_active'] = temp_data.get('BuzzerActive', '0') == '1'
                        
                        logger.info(f"Alarm status: {old_alarm} -> {temperature_data['temp_alarm']}")
                        
                        # Log temperature alarm changes
                        if temperature_data['temp_alarm'] and not old_alarm:
                            temperature_data['alarm_start_time'] = datetime.now()
                            temperature_data['alarm_count'] += 1
                            system_state['temperature_emergency'] = True
                            logger.warning(f"TEMPERATURE ALARM! Current: {current_temp}°C - Emergency procedures activated")
                            
                        elif not temperature_data['temp_alarm'] and old_alarm:
                            system_state['temperature_emergency'] = False
                            logger.info(f"Temperature returned to safe level: {current_temp}°C - Systems can be restarted")
                
                except ValueError as ve:
                    logger.error(f"Invalid temperature value '{temp_data['Temperature']}': {ve}")
            else:
                logger.warning("No 'Temperature' key found in response")
            
        except Exception as e:
            logger.error(f"Temperature parsing error: {e}, response was: '{response}'")
            """Parse temperature response from Arduino"""
            try:
                lines = response.split('\n')
                temp_data = {}
                
                for line in lines:
                    line = line.strip()
                    if ':' in line:
                        key, value = line.split(':', 1)
                        temp_data[key] = value
                
                # Update temperature data
                if 'Temperature' in temp_data:
                    try:
                        current_temp = float(temp_data['Temperature'])
                        with state_lock:
                            temperature_data['current_temp'] = current_temp
                            temperature_data['last_temp_update'] = datetime.now()
                            
                            # Update max temperature
                            if current_temp > temperature_data['max_temp_reached']:
                                temperature_data['max_temp_reached'] = current_temp
                            
                            # Add to temperature history
                            temperature_data['temp_history'].append({
                                'timestamp': datetime.now().isoformat(),
                                'temperature': current_temp
                            })
                            
                            # Keep only last 100 readings
                            if len(temperature_data['temp_history']) > MAX_TEMP_HISTORY:
                                temperature_data['temp_history'] = temperature_data['temp_history'][-MAX_TEMP_HISTORY:]
                            
                            # Update alarm status
                            old_alarm = temperature_data['temp_alarm']
                            temperature_data['temp_alarm'] = temp_data.get('TempAlarm', '0') == '1'
                            temperature_data['buzzer_active'] = temp_data.get('BuzzerActive', '0') == '1'
                            
                            # Log temperature alarm changes
                            if temperature_data['temp_alarm'] and not old_alarm:
                                temperature_data['alarm_start_time'] = datetime.now()
                                temperature_data['alarm_count'] += 1
                                system_state['temperature_emergency'] = True
                                logger.warning(f"TEMPERATURE ALARM! Current: {current_temp}°C - Emergency procedures activated")
                                
                            elif not temperature_data['temp_alarm'] and old_alarm:
                                system_state['temperature_emergency'] = False
                                logger.info(f"Temperature returned to safe level: {current_temp}°C - Systems can be restarted")
                    
                    except ValueError:
                        logger.debug("Invalid temperature value received")
                
            except Exception as e:
                logger.debug(f"Temperature parsing error: {e}")
    
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
                    time.sleep(0.1)
                    
            except Exception as e:
                logger.error(f"Command processor error: {e}")
                time.sleep(0.5)
        
        logger.info("Command processor thread stopped")
    
    def _connection_monitor(self):
        """Background connection monitor"""
        logger.info("Connection monitor thread started")
        while not shutdown_event.is_set():
            try:
                if self.is_connected:
                    # Send periodic heartbeat
                    if time.time() - self.last_command_time > 30:
                        success, _ = self.send_command_sync("PING", timeout=2.0)
                        if not success:
                            logger.warning("Heartbeat failed - connection may be lost")
                            self.is_connected = False
                            system_state['connected'] = False
                else:
                    # Try to reconnect
                    logger.info("Attempting automatic reconnection...")
                    if self.connect():
                        logger.info("Automatic reconnection successful")
                    else:
                        time.sleep(10)
                
                time.sleep(15)
                
            except Exception as e:
                logger.error(f"Connection monitor error: {e}")
                time.sleep(10)
        
        logger.info("Connection monitor thread stopped")
    
    def send_command_sync(self, command, timeout=5.0):
        """Send command synchronously with timeout - TÜM MOTOR KOMUTLARI İÇİN"""
        if not self.is_connected or not self.connection or shutdown_event.is_set():
            return False, "Not connected"
        
        try:
            with self.connection_lock:
                # Rate limiting
                current_time = time.time()
                time_since_last = current_time - self.last_command_time
                if time_since_last < 0.05:
                    time.sleep(0.05 - time_since_last)
                
                # Send command
                command_bytes = f"{command}\n".encode('utf-8')
                self.connection.write(command_bytes)
                self.connection.flush()
                self.last_command_time = time.time()
                
                # Read response with longer timeout for motor commands
                start_time = time.time()
                response = ""
                
                while time.time() - start_time < timeout:
                    if shutdown_event.is_set():
                        return False, "Shutdown requested"
                    
                    if self.connection.in_waiting > 0:
                        try:
                            data = self.connection.read(self.connection.in_waiting)
                            response += data.decode('utf-8', errors='ignore')
                            
                            # Motor komutları ve temperature için özel kontrol
                            if any(keyword in response for keyword in ["MOTOR_STARTED", "MOTOR_STOPPED", "LEV_GROUP_STARTED", 
                                                                       "THR_GROUP_STARTED", "ARMED", "RELAY_BRAKE:", 
                                                                       "Temperature:", "TEMP_ALARM:", "EMERGENCY_STOP"]):
                                break
                            
                            if '\n' in response or len(response) > 200:
                                break
                        except Exception as e:
                            logger.debug(f"Read error: {e}")
                            break
                    
                    time.sleep(0.02)
                
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
                
        except serial.SerialException as e:
            logger.error(f"Serial error for command '{command}': {e}")
            self.is_connected = False
            system_state['connected'] = False
            with state_lock:
                system_state['errors'] += 1
            return False, f"Serial error: {e}"
            
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
            success, response = self.send_command_sync(command, timeout=2.0)
            
            if success:
                logger.debug(f"Async command executed successfully: {command}")
            else:
                if attempts < max_attempts:
                    command_data['attempts'] = attempts + 1
                    try:
                        self.command_queue.put(command_data, timeout=0.1)
                        logger.debug(f"Retrying command: {command} (attempt {attempts + 1})")
                    except queue.Full:
                        logger.warning(f"Cannot retry command, queue full: {command}")
                else:
                    logger.error(f"Command failed after {max_attempts} attempts: {command}")
                
        except Exception as e:
            logger.error(f"Command execution error: {e}")
    
    def reconnect(self):
        """Manual reconnect with full reset"""
        logger.info("Manual reconnection requested")
        
        old_connected = self.is_connected
        self.is_connected = False
        
        try:
            self.disconnect(keep_threads=True)
            time.sleep(2)
            
            self.reconnect_attempts = 0
            
            new_port = self.find_arduino_port()
            if new_port:
                self.port = new_port
                logger.info(f"Using port for reconnection: {self.port}")
            
            success = self.connect()
            
            if success:
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
                acquired = self.connection_lock.acquire(timeout=3.0)
                try:
                    if acquired:
                        self.connection.close()
                        logger.info("Serial connection closed successfully")
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
            
            if self.processor_thread and self.processor_thread.is_alive():
                self.processor_thread.join(timeout=2.0)
            
            if self.monitor_thread and self.monitor_thread.is_alive():
                self.monitor_thread.join(timeout=2.0)
                
            if self.temp_monitor_thread and self.temp_monitor_thread.is_alive():
                self.temp_monitor_thread.join(timeout=2.0)
        
        logger.info("Arduino disconnected successfully")

# Initialize Arduino controller
logger.info("Initializing Arduino controller with temperature safety system...")
try:
    arduino_controller = ProductionArduinoController()
except Exception as e:
    logger.error(f"Failed to initialize Arduino controller: {e}")
    arduino_controller = None

# API Routes

@app.route('/api/status', methods=['GET'])
def get_status():
    """Get comprehensive system status including temperature data"""
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
                    'history_count': len(temperature_data['temp_history'])
                },
                'stats': {
                    'commands': system_state['commands'],
                    'errors': system_state['errors'],
                    'uptime_seconds': int(uptime_seconds),
                    'last_response': system_state['last_response'].isoformat() if system_state['last_response'] else None,
                    'reconnect_attempts': arduino_controller.reconnect_attempts if arduino_controller else 0
                },
                'port_info': {
                    'port': arduino_controller.port if arduino_controller else None,
                    'baudrate': arduino_controller.baudrate if arduino_controller else None
                },
                'timestamp': datetime.now().isoformat(),
                'version': '3.3-temperature-safety'
            })
    except Exception as e:
        logger.error(f"Status endpoint error: {e}")
        return jsonify({'error': str(e), 'connected': False}), 500

@app.route('/api/temperature', methods=['GET'])
def get_temperature_data():
    """Get detailed temperature data and history"""
    try:
        with state_lock:
            alarm_duration = None
            if temperature_data['temp_alarm'] and temperature_data['alarm_start_time']:
                alarm_duration = (datetime.now() - temperature_data['alarm_start_time']).total_seconds()
            
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
                'history': temperature_data['temp_history'][-20:],  # Son 20 okuma
                'timestamp': datetime.now().isoformat()
            })
    except Exception as e:
        logger.error(f"Temperature endpoint error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/temperature/buzzer/off', methods=['POST'])
def turn_off_buzzer():
    """Manuel buzzer kapatma - sadece alarm yokken"""
    if not arduino_controller or not arduino_controller.is_connected:
        return jsonify({
            'status': 'error',
            'message': 'Arduino not connected'
        }), 503
    
    try:
        success, response = arduino_controller.send_command_sync("BUZZER_OFF", timeout=3.0)
        
        if success and "BUZZER_OFF" in response:
            with state_lock:
                temperature_data['buzzer_active'] = False
            
            logger.info("Buzzer manually turned off")
            return jsonify({
                'status': 'success',
                'message': 'Buzzer turned off',
                'arduino_response': response
            })
        else:
            return jsonify({
                'status': 'error',
                'message': f'Could not turn off buzzer: {response}'
            }), 500
            
    except Exception as e:
        logger.error(f"Buzzer off error: {e}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@app.route('/api/system/arm', methods=['POST'])
def arm_system():
    """Arm the system - relay must be active and temperature safe"""
    if not arduino_controller or not arduino_controller.is_connected:
        return jsonify({
            'status': 'error',
            'message': 'Arduino not connected'
        }), 503
    
    # Temperature safety check
    if temperature_data['temp_alarm']:
        return jsonify({
            'status': 'error',
            'message': 'Cannot arm - temperature alarm active',
            'current_temp': temperature_data['current_temp']
        }), 400
    
    if temperature_data['current_temp'] > TEMP_ALARM_THRESHOLD - 5:
        return jsonify({
            'status': 'error',
            'message': f'Cannot arm - temperature too high ({temperature_data["current_temp"]}°C)',
            'max_safe_temp': TEMP_ALARM_THRESHOLD - 5
        }), 400
    
    if not system_state['relay_brake_active']:
        return jsonify({
            'status': 'error', 
            'message': 'Cannot arm while relay brake is inactive'
        }), 400
    
    if system_state['brake_active']:
        return jsonify({
            'status': 'error',
            'message': 'Cannot arm while software brake is active'
        }), 400
    
    try:
        if arduino_controller.connection:
            arduino_controller.connection.flushInput()
            arduino_controller.connection.flushOutput()
        
        success, response = arduino_controller.send_command_sync("ARM", timeout=5.0)
        
        if success and response:
            response_lines = [line.strip() for line in response.split('\n') if line.strip()]
            
            for line in response_lines:
                line_upper = line.upper()
                
                if "ARMED" in line_upper and "ERROR" not in line_upper:
                    with state_lock:
                        system_state['armed'] = True
                    logger.info(f"System ARMED successfully - Temperature: {temperature_data['current_temp']}°C")
                    return jsonify({
                        'status': 'armed',
                        'message': 'System armed successfully',
                        'current_temp': temperature_data['current_temp'],
                        'response': line
                    })
                
                elif "ERROR:" in line_upper:
                    if "TEMP" in line_upper:
                        return jsonify({
                            'status': 'error',
                            'message': 'Cannot arm - temperature safety restriction',
                            'current_temp': temperature_data['current_temp']
                        }), 400
                    elif "RELAY_INACTIVE" in line_upper or "CANNOT_ARM_RELAY" in line_upper:
                        return jsonify({
                            'status': 'error',
                            'message': 'Cannot arm - relay brake inactive'
                        }), 400
                    elif "BRAKE_ACTIVE" in line_upper or "CANNOT_ARM_BRAKE" in line_upper:
                        return jsonify({
                            'status': 'error',
                            'message': 'Cannot arm - software brake active'
                        }), 400
                    else:
                        return jsonify({
                            'status': 'error',
                            'message': f'Arduino error: {line}'
                        }), 400
            
            return jsonify({
                'status': 'error',
                'message': f'Unexpected Arduino response: {response}',
                'debug_response': response
            }), 500
        
        else:
            return jsonify({
                'status': 'error',
                'message': f'Arduino communication failed: {response}'
            }), 500
            
    except Exception as e:
        logger.error(f"Arm system error: {e}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@app.route('/api/system/disarm', methods=['POST'])
def disarm_system():
    """Disarm the system"""
    if not arduino_controller or not arduino_controller.is_connected:
        return jsonify({
            'status': 'error',
            'message': 'Arduino not connected'
        }), 503
    
    try:
        success, response = arduino_controller.send_command_sync("DISARM", timeout=3.0)
        
        if success and "DISARMED" in response.upper():
            with state_lock:
                system_state['armed'] = False
                for i in range(1, 7):
                    motor_states[i] = False
                    individual_motor_speeds[i] = 0
                group_speeds['levitation'] = 0
                group_speeds['thrust'] = 0
            
            logger.info("System DISARMED successfully")
            return jsonify({
                'status': 'disarmed',
                'message': 'System disarmed successfully',
                'current_temp': temperature_data['current_temp'],
                'response': response
            })
        else:
            return jsonify({
                'status': 'error', 
                'message': f'Arduino did not confirm disarm: {response}'
            }), 500
            
    except Exception as e:
        logger.error(f"Disarm system error: {e}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

# Individual Motor Control Routes - Temperature checks added
@app.route('/api/motor/<int:motor_num>/start', methods=['POST'])
def start_individual_motor(motor_num):
    """Start individual motor with temperature safety checks"""
    if not arduino_controller or not arduino_controller.is_connected:
        return jsonify({'status': 'error', 'message': 'Arduino not connected'}), 503
    
    if not system_state['armed']:
        return jsonify({'status': 'error', 'message': 'System not armed'}), 400
    
    if not system_state['relay_brake_active']:
        return jsonify({'status': 'error', 'message': 'Relay brake must be active to start motors'}), 400
    
    # Temperature safety checks
    if temperature_data['temp_alarm']:
        return jsonify({
            'status': 'error', 
            'message': 'Cannot start motor - temperature alarm active',
            'current_temp': temperature_data['current_temp']
        }), 400
    
    if temperature_data['current_temp'] > TEMP_ALARM_THRESHOLD - 3:
        return jsonify({
            'status': 'error', 
            'message': f'Cannot start motor - temperature too high ({temperature_data["current_temp"]}°C)',
            'max_safe_temp': TEMP_ALARM_THRESHOLD - 3
        }), 400
    
    if motor_num not in range(1, 7):
        return jsonify({'status': 'error', 'message': 'Invalid motor number (1-6)'}), 400
    
    try:
        data = request.get_json() or {}
        speed = int(data.get('speed', 50))
        
        if not 0 <= speed <= 100:
            return jsonify({'status': 'error', 'message': 'Speed must be 0-100'}), 400
        
        command = f"MOTOR:{motor_num}:START:{speed}"
        success, response = arduino_controller.send_command_sync(command, timeout=5.0)
        
        if success and response:
            if "MOTOR_STARTED" in response:
                with state_lock:
                    motor_states[motor_num] = True
                    individual_motor_speeds[motor_num] = speed
                
                motor_type = "Thrust" if motor_num in [5, 6] else "Levitation"
                pin_mapping = {1: 2, 2: 4, 3: 5, 4: 6, 5: 3, 6: 7}
                pin_num = pin_mapping.get(motor_num, "Unknown")
                
                logger.info(f"Motor {motor_num} ({motor_type}, Pin {pin_num}) started at {speed}% - Temp: {temperature_data['current_temp']}°C")
                return jsonify({
                    'status': 'success',
                    'motor': motor_num,
                    'action': 'start',
                    'speed': speed,
                    'type': motor_type,
                    'pin': pin_num,
                    'message': f'Motor {motor_num} started at {speed}%',
                    'current_temp': temperature_data['current_temp'],
                    'arduino_response': response
                })
            else:
                return jsonify({
                    'status': 'error',
                    'message': f'Motor start failed: {response}'
                }), 500
        else:
            return jsonify({
                'status': 'error', 
                'message': f'Arduino communication failed: {response}'
            }), 500
            
    except ValueError:
        return jsonify({'status': 'error', 'message': 'Invalid speed value'}), 400
    except Exception as e:
        logger.error(f"Motor {motor_num} start error: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/motor/<int:motor_num>/stop', methods=['POST'])
def stop_individual_motor(motor_num):
    """Stop individual motor"""
    if not arduino_controller or not arduino_controller.is_connected:
        return jsonify({'status': 'error', 'message': 'Arduino not connected'}), 503
    
    if motor_num not in range(1, 7):
        return jsonify({'status': 'error', 'message': 'Invalid motor number (1-6)'}), 400
    
    try:
        command = f"MOTOR:{motor_num}:STOP"
        success, response = arduino_controller.send_command_sync(command, timeout=5.0)
        
        if success and response:
            if "MOTOR_STOPPED" in response:
                with state_lock:
                    motor_states[motor_num] = False
                    individual_motor_speeds[motor_num] = 0
                
                logger.info(f"Motor {motor_num} stopped - Temp: {temperature_data['current_temp']}°C")
                return jsonify({
                    'status': 'success',
                    'motor': motor_num,
                    'action': 'stop',
                    'speed': 0,
                    'message': f'Motor {motor_num} stopped',
                    'current_temp': temperature_data['current_temp'],
                    'arduino_response': response
                })
            else:
                return jsonify({
                    'status': 'error',
                    'message': f'Motor stop failed: {response}'
                }), 500
        else:
            return jsonify({
                'status': 'error',
                'message': f'Arduino communication failed: {response}'
            }), 500
            
    except Exception as e:
        logger.error(f"Motor {motor_num} stop error: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/motor/<int:motor_num>/speed', methods=['POST'])
def set_individual_motor_speed(motor_num):
    """Set individual motor speed with temperature safety checks"""
    if not arduino_controller or not arduino_controller.is_connected:
        return jsonify({'status': 'error', 'message': 'Arduino not connected'}), 503
    
    if not system_state['armed']:
        return jsonify({'status': 'error', 'message': 'System not armed'}), 400
    
    if not system_state['relay_brake_active']:
        return jsonify({'status': 'error', 'message': 'Relay brake must be active to control motors'}), 400
    
    # Temperature safety checks
    if temperature_data['temp_alarm']:
        return jsonify({
            'status': 'error', 
            'message': 'Cannot control motor - temperature alarm active',
            'current_temp': temperature_data['current_temp']
        }), 400
    
    if motor_num not in range(1, 7):
        return jsonify({'status': 'error', 'message': 'Invalid motor number (1-6)'}), 400
    
    try:
        data = request.get_json()
        if not data or 'speed' not in data:
            return jsonify({'status': 'error', 'message': 'Speed parameter required'}), 400
        
        speed = int(data.get('speed'))
        
        if not 0 <= speed <= 100:
            return jsonify({'status': 'error', 'message': 'Speed must be 0-100'}), 400
        
        command = f"MOTOR:{motor_num}:SPEED:{speed}"
        success, response = arduino_controller.send_command_sync(command, timeout=5.0)
        
        if success and response:
            if "MOTOR_SPEED" in response:
                with state_lock:
                    individual_motor_speeds[motor_num] = speed
                
                logger.info(f"Motor {motor_num} speed set to {speed}% - Temp: {temperature_data['current_temp']}°C")
                return jsonify({
                    'status': 'success',
                    'motor': motor_num,
                    'speed': speed,
                    'message': f'Motor {motor_num} speed set to {speed}%',
                    'current_temp': temperature_data['current_temp'],
                    'arduino_response': response
                })
            else:
                return jsonify({
                    'status': 'error',
                    'message': f'Motor speed failed: {response}'
                }), 500
        else:
            return jsonify({
                'status': 'error',
                'message': f'Arduino communication failed: {response}'
            }), 500
            
    except ValueError:
        return jsonify({'status': 'error', 'message': 'Invalid speed value'}), 400
    except Exception as e:
        logger.error(f"Motor {motor_num} speed error: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

# Group Motor Control Routes with Temperature Safety
@app.route('/api/levitation/start', methods=['POST'])
def start_levitation_group():
    """Start levitation group with temperature safety checks"""
    if not arduino_controller or not arduino_controller.is_connected:
        return jsonify({'status': 'error', 'message': 'Arduino not connected'}), 503
    
    if not system_state['armed']:
        return jsonify({'status': 'error', 'message': 'System not armed'}), 400
    
    if not system_state['relay_brake_active']:
        return jsonify({'status': 'error', 'message': 'Relay brake must be active to start motors'}), 400
    
    # Temperature safety checks
    if temperature_data['temp_alarm']:
        return jsonify({
            'status': 'error', 
            'message': 'Cannot start levitation group - temperature alarm active',
            'current_temp': temperature_data['current_temp']
        }), 400
    
    if temperature_data['current_temp'] > TEMP_ALARM_THRESHOLD - 3:
        return jsonify({
            'status': 'error', 
            'message': f'Cannot start levitation group - temperature too high ({temperature_data["current_temp"]}°C)',
            'max_safe_temp': TEMP_ALARM_THRESHOLD - 3
        }), 400
    
    try:
        data = request.get_json() or {}
        speed = int(data.get('speed', group_speeds['levitation'] or 50))
        
        if not 0 <= speed <= 100:
            return jsonify({'status': 'error', 'message': 'Speed must be 0-100'}), 400
        
        command = f"LEV_GROUP:START:{speed}"
        success, response = arduino_controller.send_command_sync(command, timeout=5.0)
        
        if success and response:
            if "LEV_GROUP_STARTED" in response:
                with state_lock:
                    group_speeds['levitation'] = speed
                    for i in range(1, 5):
                        motor_states[i] = True
                        individual_motor_speeds[i] = speed
                
                logger.info(f"Levitation group (Motors 1,2,3,4) started at {speed}% - Temp: {temperature_data['current_temp']}°C")
                return jsonify({
                    'status': 'success',
                    'action': 'start',
                    'speed': speed,
                    'motors': list(range(1, 5)),
                    'pins': [2, 4, 5, 6],
                    'message': 'Levitation group started',
                    'group': 'levitation',
                    'current_temp': temperature_data['current_temp'],
                    'arduino_response': response
                })
            else:
                return jsonify({
                    'status': 'error',
                    'message': f'Levitation start failed: {response}'
                }), 500
        else:
            return jsonify({
                'status': 'error',
                'message': f'Arduino communication failed: {response}'
            }), 500
            
    except ValueError:
        return jsonify({'status': 'error', 'message': 'Invalid speed value'}), 400
    except Exception as e:
        logger.error(f"Levitation start error: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/levitation/stop', methods=['POST'])
def stop_levitation_group():
    """Stop levitation group"""
    if not arduino_controller or not arduino_controller.is_connected:
        return jsonify({'status': 'error', 'message': 'Arduino not connected'}), 503
    
    try:
        command = "LEV_GROUP:STOP"
        success, response = arduino_controller.send_command_sync(command, timeout=5.0)
        
        if success and response:
            if "LEV_GROUP_STOPPED" in response:
                with state_lock:
                    group_speeds['levitation'] = 0
                    for i in range(1, 5):
                        motor_states[i] = False
                        individual_motor_speeds[i] = 0
                
                logger.info(f"Levitation group stopped - Temp: {temperature_data['current_temp']}°C")
                return jsonify({
                    'status': 'success',
                    'action': 'stop',
                    'speed': 0,
                    'motors': list(range(1, 5)),
                    'message': 'Levitation group stopped',
                    'group': 'levitation',
                    'current_temp': temperature_data['current_temp'],
                    'arduino_response': response
                })
            else:
                return jsonify({
                    'status': 'error',
                    'message': f'Levitation stop failed: {response}'
                }), 500
        else:
            return jsonify({
                'status': 'error',
                'message': f'Arduino communication failed: {response}'
            }), 500
            
    except Exception as e:
        logger.error(f"Levitation stop error: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/levitation/speed', methods=['POST'])
def set_levitation_speed():
    """Set levitation group speed with temperature safety checks"""
    if not arduino_controller or not arduino_controller.is_connected:
        return jsonify({'status': 'error', 'message': 'Arduino not connected'}), 503
    
    if not system_state['armed']:
        return jsonify({'status': 'error', 'message': 'System not armed'}), 400
    
    if not system_state['relay_brake_active']:
        return jsonify({'status': 'error', 'message': 'Relay brake must be active to control motors'}), 400
    
    # Temperature safety checks
    if temperature_data['temp_alarm']:
        return jsonify({
            'status': 'error', 
            'message': 'Cannot control levitation group - temperature alarm active',
            'current_temp': temperature_data['current_temp']
        }), 400
    
    try:
        data = request.get_json()
        if not data or 'speed' not in data:
            return jsonify({'status': 'error', 'message': 'Speed parameter required'}), 400
        
        speed = int(data.get('speed'))
        
        if not 0 <= speed <= 100:
            return jsonify({'status': 'error', 'message': 'Speed must be 0-100'}), 400
        
        command = f"LEV_GROUP:SPEED:{speed}"
        success, response = arduino_controller.send_command_sync(command, timeout=5.0)
        
        if success and response:
            if "LEV_GROUP_SPEED" in response:
                with state_lock:
                    group_speeds['levitation'] = speed
                    for i in range(1, 5):
                        if motor_states[i]:
                            individual_motor_speeds[i] = speed
                
                logger.info(f"Levitation group speed set to {speed}% - Temp: {temperature_data['current_temp']}°C")
                return jsonify({
                    'status': 'success',
                    'speed': speed,
                    'motors': list(range(1, 5)),
                    'message': 'Levitation group speed updated',
                    'group': 'levitation',
                    'current_temp': temperature_data['current_temp'],
                    'arduino_response': response
                })
            else:
                return jsonify({
                    'status': 'error',
                    'message': f'Levitation speed failed: {response}'
                }), 500
        else:
            return jsonify({
                'status': 'error',
                'message': f'Arduino communication failed: {response}'
            }), 500
            
    except ValueError:
        return jsonify({'status': 'error', 'message': 'Invalid speed value'}), 400
    except Exception as e:
        logger.error(f"Levitation speed error: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/thrust/start', methods=['POST'])
def start_thrust_group():
    """Start thrust group with temperature safety checks"""
    if not arduino_controller or not arduino_controller.is_connected:
        return jsonify({'status': 'error', 'message': 'Arduino not connected'}), 503
    
    if not system_state['armed']:
        return jsonify({'status': 'error', 'message': 'System not armed'}), 400
    
    if not system_state['relay_brake_active']:
        return jsonify({'status': 'error', 'message': 'Relay brake must be active to start motors'}), 400
    
    # Temperature safety checks
    if temperature_data['temp_alarm']:
        return jsonify({
            'status': 'error', 
            'message': 'Cannot start thrust group - temperature alarm active',
            'current_temp': temperature_data['current_temp']
        }), 400
    
    if temperature_data['current_temp'] > TEMP_ALARM_THRESHOLD - 3:
        return jsonify({
            'status': 'error', 
            'message': f'Cannot start thrust group - temperature too high ({temperature_data["current_temp"]}°C)',
            'max_safe_temp': TEMP_ALARM_THRESHOLD - 3
        }), 400
    
    try:
        data = request.get_json() or {}
        speed = int(data.get('speed', group_speeds['thrust'] or 50))
        
        if not 0 <= speed <= 100:
            return jsonify({'status': 'error', 'message': 'Speed must be 0-100'}), 400
        
        command = f"THR_GROUP:START:{speed}"
        success, response = arduino_controller.send_command_sync(command, timeout=5.0)
        
        if success and response:
            if "THR_GROUP_STARTED" in response:
                with state_lock:
                    group_speeds['thrust'] = speed
                    for i in range(5, 7):
                        motor_states[i] = True
                        individual_motor_speeds[i] = speed
                
                logger.info(f"Thrust group (Motors 5,6) started at {speed}% - Temp: {temperature_data['current_temp']}°C")
                return jsonify({
                    'status': 'success',
                    'action': 'start',
                    'speed': speed,
                    'motors': list(range(5, 7)),
                    'pins': [3, 7],
                    'message': 'Thrust group started',
                    'group': 'thrust',
                    'current_temp': temperature_data['current_temp'],
                    'arduino_response': response
                })
            else:
                return jsonify({
                    'status': 'error',
                    'message': f'Thrust start failed: {response}'
                }), 500
        else:
            return jsonify({
                'status': 'error',
                'message': f'Arduino communication failed: {response}'
            }), 500
            
    except ValueError:
        return jsonify({'status': 'error', 'message': 'Invalid speed value'}), 400
    except Exception as e:
        logger.error(f"Thrust start error: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/thrust/stop', methods=['POST'])
def stop_thrust_group():
    """Stop thrust group"""
    if not arduino_controller or not arduino_controller.is_connected:
        return jsonify({'status': 'error', 'message': 'Arduino not connected'}), 503
    
    try:
        command = "THR_GROUP:STOP"
        success, response = arduino_controller.send_command_sync(command, timeout=5.0)
        
        if success and response:
            if "THR_GROUP_STOPPED" in response:
                with state_lock:
                    group_speeds['thrust'] = 0
                    for i in range(5, 7):
                        motor_states[i] = False
                        individual_motor_speeds[i] = 0
                
                logger.info(f"Thrust group stopped - Temp: {temperature_data['current_temp']}°C")
                return jsonify({
                    'status': 'success',
                    'action': 'stop',
                    'speed': 0,
                    'motors': list(range(5, 7)),
                    'message': 'Thrust group stopped',
                    'group': 'thrust',
                    'current_temp': temperature_data['current_temp'],
                    'arduino_response': response
                })
            else:
                return jsonify({
                    'status': 'error',
                    'message': f'Thrust stop failed: {response}'
                }), 500
        else:
            return jsonify({
                'status': 'error',
                'message': f'Arduino communication failed: {response}'
            }), 500
            
    except Exception as e:
        logger.error(f"Thrust stop error: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/thrust/speed', methods=['POST'])
def set_thrust_speed():
    """Set thrust group speed with temperature safety checks"""
    if not arduino_controller or not arduino_controller.is_connected:
        return jsonify({'status': 'error', 'message': 'Arduino not connected'}), 503
    
    if not system_state['armed']:
        return jsonify({'status': 'error', 'message': 'System not armed'}), 400
    
    if not system_state['relay_brake_active']:
        return jsonify({'status': 'error', 'message': 'Relay brake must be active to control motors'}), 400
    
    # Temperature safety checks
    if temperature_data['temp_alarm']:
        return jsonify({
            'status': 'error', 
            'message': 'Cannot control thrust group - temperature alarm active',
            'current_temp': temperature_data['current_temp']
        }), 400
    
    try:
        data = request.get_json()
        if not data or 'speed' not in data:
            return jsonify({'status': 'error', 'message': 'Speed parameter required'}), 400
        
        speed = int(data.get('speed'))
        
        if not 0 <= speed <= 100:
            return jsonify({'status': 'error', 'message': 'Speed must be 0-100'}), 400
        
        command = f"THR_GROUP:SPEED:{speed}"
        success, response = arduino_controller.send_command_sync(command, timeout=5.0)
        
        if success and response:
            if "THR_GROUP_SPEED" in response:
                with state_lock:
                    group_speeds['thrust'] = speed
                    for i in range(5, 7):
                        if motor_states[i]:
                            individual_motor_speeds[i] = speed
                
                logger.info(f"Thrust group speed set to {speed}% - Temp: {temperature_data['current_temp']}°C")
                return jsonify({
                    'status': 'success',
                    'speed': speed,
                    'motors': list(range(5, 7)),
                    'message': 'Thrust group speed updated',
                    'group': 'thrust',
                    'current_temp': temperature_data['current_temp'],
                    'arduino_response': response
                })
            else:
                return jsonify({
                    'status': 'error',
                    'message': f'Thrust speed failed: {response}'
                }), 500
        else:
            return jsonify({
                'status': 'error',
                'message': f'Arduino communication failed: {response}'
            }), 500
            
    except ValueError:
        return jsonify({'status': 'error', 'message': 'Invalid speed value'}), 400
    except Exception as e:
        logger.error(f"Thrust speed error: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

# Brake Control Routes
@app.route('/api/brake/<action>', methods=['POST'])
def control_brake(action):
    """Control software brake system"""
    if not arduino_controller or not arduino_controller.is_connected:
        return jsonify({'status': 'error', 'message': 'Arduino not connected'}), 503
    
    if action not in ['on', 'off']:
        return jsonify({'status': 'error', 'message': 'Invalid action. Use "on" or "off"'}), 400
    
    try:
        command = "BRAKE_ON" if action == 'on' else "BRAKE_OFF"
        success, response = arduino_controller.send_command_sync(command, timeout=3.0)
        
        if success and response:
            if "BRAKE_ON" in response or "BRAKE_OFF" in response:
                with state_lock:
                    system_state['brake_active'] = (action == 'on')
                    
                    if system_state['brake_active']:
                        for i in range(1, 7):
                            motor_states[i] = False
                            individual_motor_speeds[i] = 0
                        group_speeds['levitation'] = 0
                        group_speeds['thrust'] = 0
                
                status = 'activated' if system_state['brake_active'] else 'deactivated'
                logger.info(f"Software brake {status} - Temp: {temperature_data['current_temp']}°C")
                
                return jsonify({
                    'status': 'success',
                    'action': action,
                    'brake_active': system_state['brake_active'],
                    'message': f'Software brake {status}',
                    'current_temp': temperature_data['current_temp'],
                    'arduino_response': response
                })
            else:
                return jsonify({
                    'status': 'error',
                    'message': f'Brake control failed: {response}'
                }), 500
        else:
            return jsonify({
                'status': 'error', 
                'message': f'Arduino communication failed: {response}'
            }), 500
            
    except Exception as e:
        logger.error(f"Software brake control error: {e}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@app.route('/api/relay-brake/<action>', methods=['POST'])
def control_relay_brake(action):
    """Control relay brake system with temperature checks"""
    if not arduino_controller or not arduino_controller.is_connected:
        return jsonify({'status': 'error', 'message': 'Arduino not connected'}), 503
    
    if action not in ['on', 'off']:
        return jsonify({'status': 'error', 'message': 'Invalid action. Use "on" or "off"'}), 400
    
    # Temperature safety check for relay activation
    if action == 'on' and temperature_data['temp_alarm']:
        return jsonify({
            'status': 'error',
            'message': 'Cannot activate relay brake - temperature alarm active',
            'current_temp': temperature_data['current_temp']
        }), 400
    
    try:
        command = "RELAY_BRAKE_ON" if action == 'on' else "RELAY_BRAKE_OFF"
        success, response = arduino_controller.send_command_sync(command, timeout=3.0)
        
        if success and response:
            if "RELAY_BRAKE:" in response:
                with state_lock:
                    system_state['relay_brake_active'] = (action == 'on')
                    
                    if not system_state['relay_brake_active']:
                        system_state['armed'] = False
                        for i in range(1, 7):
                            motor_states[i] = False
                            individual_motor_speeds[i] = 0
                        group_speeds['levitation'] = 0
                        group_speeds['thrust'] = 0
                
                status = 'activated' if system_state['relay_brake_active'] else 'deactivated'
                logger.info(f"Relay brake {status} - Temp: {temperature_data['current_temp']}°C")
                
                return jsonify({
                    'status': 'success',
                    'action': action,
                    'relay_brake_active': system_state['relay_brake_active'],
                    'system_disarmed': not system_state['relay_brake_active'],
                    'message': f'Relay brake {status}',
                    'current_temp': temperature_data['current_temp'],
                    'arduino_response': response
                })
            else:
                return jsonify({
                    'status': 'error',
                    'message': f'Relay brake failed: {response}'
                }), 500
        else:
            return jsonify({
                'status': 'error', 
                'message': f'Arduino communication failed: {response}'
            }), 500
            
    except Exception as e:
        logger.error(f"Relay brake control error: {e}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

# Emergency Stop Route
@app.route('/api/emergency-stop', methods=['POST'])
def emergency_stop():
    """Emergency stop all systems"""
    try:
        # Immediate local emergency actions
        with state_lock:
            system_state['armed'] = False
            system_state['brake_active'] = True
            system_state['relay_brake_active'] = False
            system_state['temperature_emergency'] = True
            for i in range(1, 7):
                motor_states[i] = False
                individual_motor_speeds[i] = 0
            group_speeds['levitation'] = 0
            group_speeds['thrust'] = 0
        
        # Send emergency stop to Arduino if connected
        if arduino_controller and arduino_controller.is_connected:
            try:
                success, response = arduino_controller.send_command_sync("EMERGENCY_STOP", timeout=2.0)
                if success:
                    logger.info(f"Emergency stop sent to Arduino: {response}")
            except Exception as e:
                logger.warning(f"Could not send emergency stop to Arduino: {e}")
        
        logger.warning(f"EMERGENCY STOP ACTIVATED! All systems stopped! Temp: {temperature_data['current_temp']}°C")
        
        return jsonify({
            'status': 'emergency_stop',
            'message': 'Emergency stop activated! All systems stopped and relay brake deactivated.',
            'all_stopped': True,
            'system_disarmed': True,
            'brake_activated': True,
            'relay_brake_activated': False,
            'current_temp': temperature_data['current_temp'],
            'temperature_alarm': temperature_data['temp_alarm'],
            'timestamp': datetime.now().isoformat()
        })
            
    except Exception as e:
        logger.error(f"Emergency stop error: {e}")
        return jsonify({
            'status': 'emergency_stop',
            'message': 'Emergency stop activated with error',
            'error': str(e),
            'current_temp': temperature_data['current_temp'],
            'timestamp': datetime.now().isoformat()
        })

# Utility Routes
@app.route('/api/test-connection', methods=['GET'])
def test_connection():
    """Test Arduino connection"""
    if not arduino_controller:
        return jsonify({
            'status': 'error',
            'message': 'Arduino controller not initialized'
        }), 503
    
    try:
        if arduino_controller._test_connection():
            return jsonify({
                'status': 'success',
                'message': 'Arduino connection successful',
                'port': arduino_controller.port,
                'baudrate': arduino_controller.baudrate,
                'attempts': arduino_controller.reconnect_attempts,
                'current_temp': temperature_data['current_temp'],
                'temperature_system': 'active'
            })
        else:
            return jsonify({
                'status': 'error',
                'message': 'Arduino connection test failed',
                'port': arduino_controller.port,
                'attempts': arduino_controller.reconnect_attempts
            }), 500
            
    except Exception as e:
        logger.error(f"Connection test error: {e}")
        return jsonify({
            'status': 'error',
            'message': str(e),
            'port': arduino_controller.port if arduino_controller else None
        }), 500

@app.route('/api/reconnect', methods=['POST'])
def reconnect_arduino():
    """Reconnect to Arduino"""
    if not arduino_controller:
        return jsonify({
            'status': 'error',
            'message': 'Arduino controller not initialized'
        }), 503
    
    try:
        success = arduino_controller.reconnect()
        
        if success:
            return jsonify({
                'status': 'success',
                'message': 'Arduino reconnected successfully',
                'port': arduino_controller.port,
                'baudrate': arduino_controller.baudrate,
                'temperature_monitoring': 'restarted'
            })
        else:
            return jsonify({
                'status': 'error',
                'message': 'Arduino reconnection failed',
                'port': arduino_controller.port,
                'attempts': arduino_controller.reconnect_attempts
            }), 500
            
    except Exception as e:
        logger.error(f"Reconnect error: {e}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@app.route('/api/ping', methods=['GET'])
def ping():
    """Health check endpoint"""
    try:
        active_motors = sum(1 for state in motor_states.values() if state)
        uptime_seconds = (datetime.now() - system_state['uptime']).total_seconds()
        
        return jsonify({
            'status': 'ok',
            'timestamp': datetime.now().isoformat(),
            'arduino_connected': arduino_controller.is_connected if arduino_controller else False,
            'system_armed': system_state['armed'],
            'brake_active': system_state['brake_active'],
            'relay_brake_active': system_state['relay_brake_active'],
            'active_motors': active_motors,
            'uptime_seconds': int(uptime_seconds),
            'temperature': {
                'current': temperature_data['current_temp'],
                'alarm': temperature_data['temp_alarm'],
                'buzzer_active': temperature_data['buzzer_active'],
                'emergency_active': system_state['temperature_emergency'],
                'thresholds': {
                    'alarm': TEMP_ALARM_THRESHOLD,
                    'safe': TEMP_SAFE_THRESHOLD,
                    'warning': TEMP_WARNING_THRESHOLD
                }
            },
            'motor_pins': {
                'thrust': [3, 7],
                'levitation': [2, 4, 5, 6]
            },
            'safety_pins': {
                'temperature_sensor': 8,
                'buzzer': 9,
                'relay_brake': 11
            },
            'version': '3.3-temperature-safety',
            'port': arduino_controller.port if arduino_controller else None
        })
        
    except Exception as e:
        logger.error(f"Ping endpoint error: {e}")
        return jsonify({
            'status': 'error',
            'message': str(e),
            'timestamp': datetime.now().isoformat()
        }), 500

# Error Handlers
@app.errorhandler(404)
def not_found(error):
    return jsonify({
        'status': 'error',
        'message': 'Endpoint not found',
        'available_endpoints': [
            'GET /api/status',
            'GET /api/temperature',
            'GET /api/ping',
            'GET /api/test-connection',
            'POST /api/temperature/buzzer/off',
            'POST /api/system/arm',
            'POST /api/system/disarm',
            'POST /api/motor/<num>/start',
            'POST /api/motor/<num>/stop',
            'POST /api/motor/<num>/speed',
            'POST /api/levitation/start',
            'POST /api/levitation/stop',
            'POST /api/levitation/speed',
            'POST /api/thrust/start',
            'POST /api/thrust/stop',
            'POST /api/thrust/speed',
            'POST /api/brake/on',
            'POST /api/brake/off',
            'POST /api/relay-brake/on',
            'POST /api/relay-brake/off',
            'POST /api/emergency-stop',
            'POST /api/reconnect'
        ]
    }), 404

@app.errorhandler(500)
def internal_error(error):
    logger.error(f"Internal server error: {error}")
    return jsonify({
        'status': 'error',
        'message': 'Internal server error',
        'timestamp': datetime.now().isoformat()
    }), 500

# Background monitoring
def background_monitor():
    """Background monitoring and maintenance"""
    logger.info("Background monitor started")
    
    while not shutdown_event.is_set():
        try:
            if arduino_controller and not arduino_controller.is_connected:
                if arduino_controller.reconnect_attempts < arduino_controller.max_attempts:
                    logger.info("Attempting automatic reconnection...")
                    if arduino_controller.reconnect():
                        logger.info("Automatic reconnection successful")
                else:
                    logger.warning("Max reconnection attempts reached, waiting...")
            
            if arduino_controller and arduino_controller.command_queue.qsize() > 50:
                logger.warning("Command queue getting full, clearing old commands")
                try:
                    while arduino_controller.command_queue.qsize() > 25:
                        arduino_controller.command_queue.get_nowait()
                        arduino_controller.command_queue.task_done()
                except queue.Empty:
                    pass
            
            # Temperature safety monitoring
            with state_lock:
                if temperature_data['temp_alarm'] and not system_state['temperature_emergency']:
                    logger.warning("Temperature alarm detected but emergency not set - correcting state")
                    system_state['temperature_emergency'] = True
                
                # Clean old temperature history
                if len(temperature_data['temp_history']) > MAX_TEMP_HISTORY:
                    temperature_data['temp_history'] = temperature_data['temp_history'][-MAX_TEMP_HISTORY:]
            
            shutdown_event.wait(30)
            
        except Exception as e:
            logger.error(f"Background monitor error: {e}")
            shutdown_event.wait(10)
    
    logger.info("Background monitor stopped")

# Start background monitor
monitor_thread = threading.Thread(target=background_monitor, daemon=True, name="BackgroundMonitor")
monitor_thread.start()

# Graceful shutdown handler
def signal_handler(sig, frame):
    """Graceful shutdown handler"""
    logger.info("Shutdown signal received, initiating graceful shutdown...")
    
    try:
        shutdown_event.set()
        
        if system_state.get('armed', False):
            logger.info("System is armed - performing emergency stop...")
            try:
                emergency_stop()
            except Exception as e:
                logger.error(f"Emergency stop during shutdown error: {e}")
        
        if arduino_controller:
            logger.info("Disconnecting Arduino...")
            arduino_controller.disconnect()
        
        logger.info("Waiting for background threads to finish...")
        if monitor_thread.is_alive():
            monitor_thread.join(timeout=5.0)
        
        logger.info("Graceful shutdown completed")
        
    except Exception as e:
        logger.error(f"Shutdown error: {e}")
    finally:
        sys.exit(0)

# Register signal handlers
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

if __name__ == '__main__':
    logger.info("=" * 70)
    logger.info("SpectraLoop Backend Final v3.3 - TEMPERATURE SAFETY SYSTEM")
    logger.info("=" * 70)
    
    try:
        if arduino_controller and arduino_controller.is_connected:
            logger.info(f"Arduino Status: Connected")
            logger.info(f"Arduino Port: {arduino_controller.port}")
            logger.info(f"Arduino Baudrate: {arduino_controller.baudrate}")
        else:
            logger.warning("Arduino Status: Not Connected")
        
        logger.info("Motor Pin Mapping:")
        logger.info("   Thrust Motors: M5->Pin3, M6->Pin7")
        logger.info("   Levitation Motors: M1->Pin2, M2->Pin4, M3->Pin5, M4->Pin6")
        
        logger.info("Safety System:")
        logger.info("   Temperature Sensor: DS18B20 on Pin8")
        logger.info("   Buzzer Alarm: Pin9")
        logger.info("   Relay Brake: Pin11")
        
        logger.info("Temperature Safety Thresholds:")
        logger.info(f"   Emergency Stop: {TEMP_ALARM_THRESHOLD}°C")
        logger.info(f"   Safe Return: {TEMP_SAFE_THRESHOLD}°C")
        logger.info(f"   Warning Level: {TEMP_WARNING_THRESHOLD}°C")
        
        logger.info("NEW FEATURES:")
        logger.info("   ✅ Real-time temperature monitoring")
        logger.info("   ✅ Automatic emergency stop at 55°C")
        logger.info("   ✅ Buzzer alarm system")
        logger.info("   ✅ Temperature history tracking")
        logger.info("   ✅ Motor start prevention when hot")
        logger.info("   ✅ Enhanced safety checks")
        
        logger.info("Server Configuration:")
        logger.info("   Host: 0.0.0.0")
        logger.info("   Port: 5001")
        logger.info("   Debug: False")
        logger.info("   Threaded: True")
        
        logger.info("=" * 70)
        logger.info("Starting Flask server with temperature safety system...")
        
        app.run(
            host='0.0.0.0', 
            port=5001, 
            debug=False, 
            threaded=True,
            use_reloader=False
        )
        
    except KeyboardInterrupt:
        logger.info("Received interrupt signal - shutting down gracefully...")
        signal_handler(signal.SIGINT, None)
    except Exception as e:
        logger.error(f"Server startup error: {e}")
        signal_handler(signal.SIGTERM, None)
    finally:
        logger.info("Server shutdown complete")