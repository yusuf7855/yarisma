#!/usr/bin/env python3
"""
SpectraLoop Motor Control Backend - FAULT TOLERANT DUAL TEMPERATURE + REFLECTOR v3.7
FAULT TOLERANT: System works with 0, 1, or 2 temperature sensors
Dual DS18B20 sensors + buzzer + reflector counting + redundant safety system
Individual + Group motor control + Fault tolerant temperature monitoring + Reflector tracking
Motor Pin Mapping: İtki (3,7), Levitasyon (2,4,5,6)
Temperature Sensors: Pin8->DS18B20#1, Pin13->DS18B20#2, Pin9->Buzzer, Pin11->RelayBrake
Reflector Counter: PinA0->Omron Photoelectric, Pin12->Status LED
FAULT TOLERANCE: Continues operation even with failed temperature sensors
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
        logging.FileHandler('spectraloop_fault_tolerant.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Thread-safe global state
motor_states = {i: False for i in range(1, 7)}
individual_motor_speeds = {i: 0 for i in range(1, 7)}
group_speeds = {'levitation': 0, 'thrust': 0}

# FAULT TOLERANT Temperature and safety system state - ENHANCED
temperature_data = {
    'sensor1_temp': 25.0,           # Primary sensor (Pin 8)
    'sensor2_temp': 25.0,           # Secondary sensor (Pin 13)
    'current_temp': 25.0,           # Max of both sensors for safety
    'temp_alarm': False,
    'buzzer_active': False,
    'last_temp_update': datetime.now(),
    'temp_history': [],
    'max_temp_reached': 25.0,
    'max_temp_sensor1': 25.0,       # Individual max temps
    'max_temp_sensor2': 25.0,       # Individual max temps
    'alarm_start_time': None,
    'alarm_count': 0,
    'sensor1_connected': False,     # Default: assume disconnected
    'sensor2_connected': False,     # Default: assume disconnected
    'update_frequency': 0.0,
    'sensor_failure_count': 0,      # Track sensor failures
    'temp_monitoring_required': False,  # NEW: Is temperature monitoring required?
    'allow_operation_without_temp': True,  # NEW: Allow operation without temperature sensors
    'last_valid_temp1': 25.0,       # NEW: Last valid temperature reading
    'last_valid_temp2': 25.0,       # NEW: Last valid temperature reading
    'sensor1_fail_count': 0,        # NEW: Individual sensor failure counters
    'sensor2_fail_count': 0,        # NEW: Individual sensor failure counters
    'sensor_recovery_attempts': 0,   # NEW: Recovery attempts
    'fault_tolerant_mode': True     # NEW: Operating in fault tolerant mode
}

# REFLECTOR COUNTER SYSTEM STATE - SAME AS BEFORE
reflector_data = {
    'count': 0,                     # Total reflector count
    'voltage': 5.0,                 # Current sensor voltage
    'state': False,                 # Current detection state
    'average_speed': 0.0,           # Average speed (reflectors/min)
    'instant_speed': 0.0,           # Instantaneous speed
    'last_update': datetime.now(),  # Last update timestamp
    'system_active': True,          # Reflector system status
    'detections': 0,                # Total detection events
    'read_count': 0,                # Total sensor reads
    'read_frequency': 0.0,          # Read frequency (Hz)
    'calibration_data': {           # Calibration information
        'min_voltage': 0.0,
        'max_voltage': 5.0,
        'avg_voltage': 5.0,
        'detect_threshold': 4.64,
        'release_threshold': 4.89,
        'last_calibration': None
    },
    'performance': {                # Performance tracking
        'total_runtime': 0.0,       # Total runtime in minutes
        'uptime_start': datetime.now(),
        'detection_rate': 0.0,      # Detections per minute
        'max_speed_recorded': 0.0,  # Maximum speed recorded
        'speed_history': []         # Speed history for trends
    },
    'statistics': {                 # Statistical data
        'session_count': 0,         # Count for current session
        'session_start': datetime.now(),
        'daily_count': 0,           # Daily accumulator
        'daily_start': datetime.now().replace(hour=0, minute=0, second=0, microsecond=0),
        'total_count': 0            # All-time counter
    }
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
    'temperature_emergency': False,
    'dual_sensor_mode': True,       # Flag for dual sensor operation
    'reflector_system_enabled': True,  # Reflector system flag
    'fault_tolerant_mode': True,    # NEW: Fault tolerant operation mode
    'can_operate_without_temp': True  # NEW: Can operate without temperature sensors
}

# Thread synchronization
state_lock = threading.Lock()
shutdown_event = threading.Event()

# FAULT TOLERANT Temperature safety constants
TEMP_ALARM_THRESHOLD = 55.0
TEMP_SAFE_THRESHOLD = 50.0
TEMP_WARNING_THRESHOLD = 45.0
MAX_TEMP_HISTORY = 200
SENSOR_TIMEOUT = 30.0               # Consider sensor failed after 30 seconds
MAX_TEMP_CHANGE = 50.0              # Maximum realistic temperature change
TEMP_SENSOR_RETRY_INTERVAL = 10.0   # Retry sensor every 10 seconds

# REFLECTOR SYSTEM Constants - SAME
REFLECTOR_REPORT_INTERVAL = 1.0
MAX_REFLECTOR_HISTORY = 500
REFLECTOR_TIMEOUT = 30.0

# DUAL SENSOR Constants
TEMP_DIFF_WARNING = 5.0
TEMP_SENSOR_TIMEOUT = 10.0

class FaultTolerantDualTempReflectorArduinoController:
    def __init__(self, port=None, baudrate=115200):
        self.port = port or self.find_arduino_port()
        self.baudrate = baudrate
        self.connection = None
        self.is_connected = False
        self.last_command_time = 0
        self.reconnect_attempts = 0
        self.max_attempts = 5
        
        # Command processing
        self.command_queue = queue.Queue(maxsize=200)
        self.response_timeout = 2.0
        
        # Connection management
        self.connection_lock = threading.Lock()
        
        # Background threads
        self.processor_thread = None
        self.monitor_thread = None
        self.continuous_reader_thread = None
        self.temp_stats_thread = None
        self.sensor_health_thread = None
        self.reflector_stats_thread = None
        self.sensor_recovery_thread = None  # NEW: Sensor recovery thread
        
        # FAULT TOLERANT Arduino stream parsing - ENHANCED
        self.stream_buffer = ""
        self.temp1_pattern = re.compile(r'\[TEMP1:([\d.-]+)\]')
        self.temp2_pattern = re.compile(r'\[TEMP2:([\d.-]+)\]')
        self.max_temp_pattern = re.compile(r'\[MAX:([\d.-]+)\]')
        self.reflector_pattern = re.compile(r'\[REFLECTOR:([\d]+)\]')
        self.dual_temp_pattern = re.compile(r'DUAL_TEMP \[TEMP1:([\d.-]+)\] \[TEMP2:([\d.-]+)\] \[MAX:([\d.-]+)\] \[S1_CONN:([01])\] \[S2_CONN:([01])\] \[TEMP_REQ:([01])\]')
        self.heartbeat_pattern = re.compile(r'HEARTBEAT:(\d+),(\d),(\d),(\d),([\d.-]+),(\d),(\d)')
        self.reflector_status_pattern = re.compile(r'REFLECTOR_STATUS \[COUNT:([\d]+)\] \[VOLTAGE:([\d.-]+)V\] \[STATE:(\w+)\] \[AVG_SPEED:([\d.-]+)rpm\] \[INST_SPEED:([\d.-]+)rpm\] \[read_FREQ:([\d.-]+)Hz\]')
        self.reflector_detected_pattern = re.compile(r'REFLECTOR_DETECTED:([\d]+) \[VOLTAGE:([\d.-]+)V\] \[SPEED:([\d.-]+)rpm\]')
        self.temp_alarm_pattern = re.compile(r'TEMP_ALARM:([\d.-]+)')
        self.temp_safe_pattern = re.compile(r'TEMP_SAFE:([\d.-]+)')
        self.fault_tolerant_heartbeat_pattern = re.compile(r'HB_DUAL_FT \[TEMP1:([\d.-]+)\] \[TEMP2:([\d.-]+)\] \[MAX:([\d.-]+)\] \[S1_CONN:(\w+)\] \[S2_CONN:(\w+)\] \[TEMP_REQ:(\w+)\] \[REFLECTOR:([\d]+)\] \[REF_SPEED:([\d.-]+)\]')
        
        # Performance tracking - FAULT TOLERANT
        self.temp_updates_count = 0
        self.reflector_updates_count = 0
        self.last_stats_time = time.time()
        self.sensor_health_stats = {
            'sensor1_updates': 0,
            'sensor2_updates': 0,
            'dual_updates': 0,
            'reflector_updates': 0,
            'sensor1_last_seen': datetime.now(),
            'sensor2_last_seen': datetime.now(),
            'reflector_last_seen': datetime.now(),
            'sensor1_recovery_attempts': 0,  # NEW
            'sensor2_recovery_attempts': 0,  # NEW
            'last_recovery_attempt': datetime.now()  # NEW
        }
        
        # Initialize connection safely
        try:
            if self.port:
                self.connect()
                self._start_command_processor()
                self._start_connection_monitor()
                self._start_continuous_reader()
                self._start_temp_stats_monitor()
                self._start_sensor_health_monitor()
                self._start_reflector_stats_monitor()
                self._start_sensor_recovery_monitor()  # NEW
            else:
                logger.error("No Arduino port found")
                system_state['connected'] = False
                system_state['reflector_system_enabled'] = False
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
                
                # Create connection
                self.connection = serial.Serial(
                    port=self.port,
                    baudrate=self.baudrate,
                    timeout=1,
                    write_timeout=1,
                    parity=serial.PARITY_NONE,
                    stopbits=serial.STOPBITS_ONE,
                    bytesize=serial.EIGHTBITS,
                    rtscts=False,
                    dsrdtr=False
                )
                
                logger.info(f"Serial connection opened: {self.port} @ {self.baudrate}")
                
                # Wait for Arduino to initialize
                time.sleep(2)
                self.connection.flushInput()
                self.connection.flushOutput()
                
                # Test connection
                if self._test_connection():
                    self.is_connected = True
                    self.reconnect_attempts = 0
                    system_state['connected'] = True
                    system_state['reflector_system_enabled'] = True
                    system_state['fault_tolerant_mode'] = True
                    logger.info("Arduino connection successful - FAULT TOLERANT DUAL TEMPERATURE + REFLECTOR safety system active")
                    return True
                else:
                    raise Exception("Connection test failed")
        
        except Exception as e:
            self.reconnect_attempts += 1
            logger.error(f"Connection error (attempt {self.reconnect_attempts}/{self.max_attempts}): {e}")
            system_state['connected'] = False
            system_state['reflector_system_enabled'] = False
            self.is_connected = False
            if self.connection:
                try:
                    self.connection.close()
                except:
                    pass
                self.connection = None
            return False
    
    def _test_connection(self):
        """Test Arduino connection"""
        try:
            if not self.connection:
                return False
            
            # Send PING command
            self.connection.write(b"PING\n")
            self.connection.flush()
            
            start_time = time.time()
            response = ""
            
            while time.time() - start_time < 2.0:
                if self.connection.in_waiting > 0:
                    try:
                        data = self.connection.read(self.connection.in_waiting)
                        response += data.decode('utf-8', errors='ignore')
                        
                        if any(keyword in response.upper() for keyword in ["PONG", "ACK", "FAULT-TOLERANT", "REFLECTOR", "READY"]):
                            logger.info(f"Arduino responded: {response.strip()}")
                            # Check for fault tolerant mode indicator
                            if "FAULT-TOLERANT" in response.upper():
                                system_state['fault_tolerant_mode'] = True
                                logger.info("Arduino is running in FAULT TOLERANT mode")
                            return True
                    except Exception as e:
                        logger.debug(f"Read error during test: {e}")
                        break
                time.sleep(0.05)
            
            logger.warning(f"Arduino test failed. Response: '{response.strip()}'")
            return False
            
        except Exception as e:
            logger.error(f"Connection test error: {e}")
            return False
    
    def _start_sensor_recovery_monitor(self):
        """NEW: Start sensor recovery monitoring thread"""
        if self.sensor_recovery_thread and self.sensor_recovery_thread.is_alive():
            return
        
        self.sensor_recovery_thread = threading.Thread(target=self._sensor_recovery_monitor, daemon=True, name="SensorRecovery")
        self.sensor_recovery_thread.start()
        logger.info("Sensor recovery monitor started")
    
    def _sensor_recovery_monitor(self):
        """NEW: Monitor and attempt to recover failed sensors"""
        while not shutdown_event.is_set():
            try:
                current_time = datetime.now()
                
                with state_lock:
                    # Check if we need to attempt sensor recovery
                    time_since_last_attempt = (current_time - self.sensor_health_stats['last_recovery_attempt']).total_seconds()
                    
                    if time_since_last_attempt >= TEMP_SENSOR_RETRY_INTERVAL:
                        recovery_needed = False
                        
                        # Check if sensor 1 needs recovery
                        if not temperature_data['sensor1_connected']:
                            recovery_needed = True
                            self.sensor_health_stats['sensor1_recovery_attempts'] += 1
                            logger.info(f"Attempting sensor 1 recovery (attempt {self.sensor_health_stats['sensor1_recovery_attempts']})")
                        
                        # Check if sensor 2 needs recovery
                        if not temperature_data['sensor2_connected']:
                            recovery_needed = True
                            self.sensor_health_stats['sensor2_recovery_attempts'] += 1
                            logger.info(f"Attempting sensor 2 recovery (attempt {self.sensor_health_stats['sensor2_recovery_attempts']})")
                        
                        if recovery_needed:
                            self.sensor_health_stats['last_recovery_attempt'] = current_time
                            # Send temperature status request to trigger sensor check
                            if self.is_connected:
                                try:
                                    success, response = self.send_command_sync("TEMP_STATUS", timeout=3.0)
                                    if success:
                                        logger.debug("Sensor recovery check sent")
                                except Exception as e:
                                    logger.debug(f"Sensor recovery check failed: {e}")
                
                time.sleep(5)  # Check every 5 seconds
                
            except Exception as e:
                logger.error(f"Sensor recovery monitor error: {e}")
                time.sleep(10)
    
    def _start_continuous_reader(self):
        """FAULT TOLERANT continuous Arduino reading"""
        if self.continuous_reader_thread and self.continuous_reader_thread.is_alive():
            return
        
        self.continuous_reader_thread = threading.Thread(target=self._continuous_reader, daemon=True, name="FaultTolerantReader")
        self.continuous_reader_thread.start()
        logger.info("FAULT TOLERANT continuous reader started (25ms intervals)")
    
    def _start_temp_stats_monitor(self):
        """Temperature + Reflector update frequency monitor"""
        if self.temp_stats_thread and self.temp_stats_thread.is_alive():
            return
        
        self.temp_stats_thread = threading.Thread(target=self._temp_stats_monitor, daemon=True, name="FaultTolerantTempStats")
        self.temp_stats_thread.start()
        logger.info("FAULT TOLERANT temperature + reflector statistics monitor started")
    
    def _start_sensor_health_monitor(self):
        """Monitor individual sensor + reflector health with fault tolerance"""
        if self.sensor_health_thread and self.sensor_health_thread.is_alive():
            return
        
        self.sensor_health_thread = threading.Thread(target=self._sensor_health_monitor, daemon=True, name="FaultTolerantSensorHealth")
        self.sensor_health_thread.start()
        logger.info("FAULT TOLERANT sensor + reflector health monitor started")
    
    def _start_reflector_stats_monitor(self):
        """Monitor reflector statistics and trends - SAME"""
        if self.reflector_stats_thread and self.reflector_stats_thread.is_alive():
            return
        
        self.reflector_stats_thread = threading.Thread(target=self._reflector_stats_monitor, daemon=True, name="ReflectorStats")
        self.reflector_stats_thread.start()
        logger.info("Reflector statistics monitor started")
    
    def _reflector_stats_monitor(self):
        """Monitor reflector performance and calculate statistics - SAME AS BEFORE"""
        while not shutdown_event.is_set():
            try:
                current_time = datetime.now()
                
                with state_lock:
                    # Update runtime statistics
                    total_runtime = (current_time - reflector_data['performance']['uptime_start']).total_seconds() / 60.0
                    reflector_data['performance']['total_runtime'] = total_runtime
                    
                    # Calculate detection rate
                    if total_runtime > 0:
                        reflector_data['performance']['detection_rate'] = reflector_data['count'] / total_runtime
                    
                    # Update max speed if necessary
                    if reflector_data['instant_speed'] > reflector_data['performance']['max_speed_recorded']:
                        reflector_data['performance']['max_speed_recorded'] = reflector_data['instant_speed']
                    
                    # Add to speed history (limited to prevent memory issues)
                    speed_history = reflector_data['performance']['speed_history']
                    if len(speed_history) == 0 or (current_time - datetime.fromisoformat(speed_history[-1]['timestamp'])).total_seconds() >= 5:
                        speed_history.append({
                            'timestamp': current_time.isoformat(),
                            'average_speed': reflector_data['average_speed'],
                            'instant_speed': reflector_data['instant_speed'],
                            'count': reflector_data['count']
                        })
                        
                        # Keep history limited
                        if len(speed_history) > MAX_REFLECTOR_HISTORY:
                            speed_history = speed_history[-MAX_REFLECTOR_HISTORY:]
                            reflector_data['performance']['speed_history'] = speed_history
                    
                    # Daily reset check
                    daily_start = reflector_data['statistics']['daily_start']
                    if current_time.date() > daily_start.date():
                        reflector_data['statistics']['daily_count'] = 0
                        reflector_data['statistics']['daily_start'] = current_time.replace(hour=0, minute=0, second=0, microsecond=0)
                        logger.info(f"Daily reflector count reset. Yesterday's count: {reflector_data['count']}")
                
                time.sleep(5)  # Update every 5 seconds
                
            except Exception as e:
                logger.error(f"Reflector stats monitor error: {e}")
                time.sleep(5)
    
    def _sensor_health_monitor(self):
        """FAULT TOLERANT sensor health monitoring"""
        while not shutdown_event.is_set():
            try:
                current_time = datetime.now()
                
                with state_lock:
                    # FAULT TOLERANT sensor 1 health check
                    sensor1_age = (current_time - self.sensor_health_stats['sensor1_last_seen']).total_seconds()
                    if sensor1_age > TEMP_SENSOR_TIMEOUT and temperature_data['sensor1_connected']:
                        temperature_data['sensor1_connected'] = False
                        temperature_data['sensor1_fail_count'] += 1
                        temperature_data['sensor_failure_count'] += 1
                        logger.warning(f"Sensor 1 (Pin 8) appears disconnected - no data for {sensor1_age:.1f}s")
                    elif sensor1_age <= TEMP_SENSOR_TIMEOUT and not temperature_data['sensor1_connected']:
                        temperature_data['sensor1_connected'] = True
                        logger.info("Sensor 1 (Pin 8) reconnected")
                    
                    # FAULT TOLERANT sensor 2 health check
                    sensor2_age = (current_time - self.sensor_health_stats['sensor2_last_seen']).total_seconds()
                    if sensor2_age > TEMP_SENSOR_TIMEOUT and temperature_data['sensor2_connected']:
                        temperature_data['sensor2_connected'] = False
                        temperature_data['sensor2_fail_count'] += 1
                        temperature_data['sensor_failure_count'] += 1
                        logger.warning(f"Sensor 2 (Pin 13) appears disconnected - no data for {sensor2_age:.1f}s")
                    elif sensor2_age <= TEMP_SENSOR_TIMEOUT and not temperature_data['sensor2_connected']:
                        temperature_data['sensor2_connected'] = True
                        logger.info("Sensor 2 (Pin 13) reconnected")
                    
                    # Check reflector system health - SAME
                    reflector_age = (current_time - self.sensor_health_stats['reflector_last_seen']).total_seconds()
                    if reflector_age > REFLECTOR_TIMEOUT and reflector_data['system_active']:
                        reflector_data['system_active'] = False
                        system_state['reflector_system_enabled'] = False
                        logger.warning(f"Reflector system appears inactive - no data for {reflector_age:.1f}s")
                    elif reflector_age <= REFLECTOR_TIMEOUT and not reflector_data['system_active']:
                        reflector_data['system_active'] = True
                        system_state['reflector_system_enabled'] = True
                        logger.info("Reflector system reactivated")
                    
                    # FAULT TOLERANT temperature difference check
                    if temperature_data['sensor1_connected'] and temperature_data['sensor2_connected']:
                        temp_diff = abs(temperature_data['sensor1_temp'] - temperature_data['sensor2_temp'])
                        if temp_diff > TEMP_DIFF_WARNING:
                            logger.warning(f"Large temperature difference: S1={temperature_data['sensor1_temp']:.1f}°C, S2={temperature_data['sensor2_temp']:.1f}°C (Diff: {temp_diff:.1f}°C)")
                    
                    # Update temperature monitoring requirements - FAULT TOLERANT
                    any_sensor_connected = temperature_data['sensor1_connected'] or temperature_data['sensor2_connected']
                    
                    if any_sensor_connected:
                        temperature_data['temp_monitoring_required'] = True
                        temperature_data['allow_operation_without_temp'] = False
                        temperature_data['fault_tolerant_mode'] = True
                        system_state['can_operate_without_temp'] = False
                    else:
                        # FAULT TOLERANCE: Allow operation without temperature sensors
                        temperature_data['temp_monitoring_required'] = False
                        temperature_data['allow_operation_without_temp'] = True
                        temperature_data['fault_tolerant_mode'] = True
                        system_state['can_operate_without_temp'] = True
                        
                        # Clear any temperature alarms if no sensors are connected
                        if temperature_data['temp_alarm']:
                            logger.info("FAULT TOLERANCE: Clearing temperature alarm - no sensors connected")
                            temperature_data['temp_alarm'] = False
                            temperature_data['buzzer_active'] = False
                            system_state['temperature_emergency'] = False
                
                time.sleep(5)  # Check every 5 seconds
                
            except Exception as e:
                logger.error(f"FAULT TOLERANT sensor health monitor error: {e}")
                time.sleep(5)
    
    def _temp_stats_monitor(self):
        """Monitor temperature + reflector update frequency with fault tolerance"""
        while not shutdown_event.is_set():
            try:
                time.sleep(1.0)
                
                current_time = time.time()
                elapsed = current_time - self.last_stats_time
                
                if elapsed >= 1.0:
                    temp_updates_per_second = self.temp_updates_count / elapsed
                    reflector_updates_per_second = self.reflector_updates_count / elapsed
                    
                    with state_lock:
                        temperature_data['update_frequency'] = round(temp_updates_per_second, 2)
                        reflector_data['read_frequency'] = round(reflector_updates_per_second, 2)
                    
                    if temp_updates_per_second > 0:
                        logger.debug(f"FAULT TOLERANT temperature updates: {temp_updates_per_second:.2f} Hz")
                    else:
                        logger.debug("FAULT TOLERANCE: No temperature updates received")
                    
                    if reflector_updates_per_second > 0:
                        logger.debug(f"Reflector updates: {reflector_updates_per_second:.2f} Hz")
                    
                    # Reset counters
                    self.temp_updates_count = 0
                    self.reflector_updates_count = 0
                    self.last_stats_time = current_time
                
            except Exception as e:
                logger.error(f"FAULT TOLERANT temp + reflector stats monitor error: {e}")
                time.sleep(5)
    
    def _continuous_reader(self):
        """FAULT TOLERANT Arduino stream reader"""
        logger.info("FAULT TOLERANT continuous reader started")
        buffer = ""
        
        while not shutdown_event.is_set():
            try:
                if not self.is_connected or not self.connection:
                    time.sleep(0.5)
                    continue
                
                # Ultra-fast reading
                if self.connection.in_waiting > 0:
                    try:
                        data = self.connection.read(self.connection.in_waiting)
                        new_data = data.decode('utf-8', errors='ignore')
                        buffer += new_data
                        
                        # Process complete lines
                        while '\n' in buffer:
                            line, buffer = buffer.split('\n', 1)
                            line = line.strip()
                            
                            if line:
                                self._parse_fault_tolerant_line(line)
                    
                    except Exception as e:
                        logger.debug(f"FAULT TOLERANT read error: {e}")
                
                time.sleep(0.025)  # 25ms polling
                
            except Exception as e:
                logger.error(f"FAULT TOLERANT reader error: {e}")
                time.sleep(1)
        
        logger.info("FAULT TOLERANT reader stopped")
    
    def _parse_fault_tolerant_line(self, line):
        """FAULT TOLERANT: Parse dual temperature + reflector Arduino lines"""
        try:
            current_time = datetime.now()
            
            # 1. FAULT TOLERANT HEARTBEAT format: HB_DUAL_FT [TEMP1:33.45] [TEMP2:34.12] [MAX:34.12] [S1_CONN:OK] [S2_CONN:FAIL] [TEMP_REQ:YES] [REFLECTOR:123] [REF_SPEED:45.2]
            ft_heartbeat_match = self.fault_tolerant_heartbeat_pattern.search(line)
            if ft_heartbeat_match:
                temp1, temp2, max_temp, s1_conn, s2_conn, temp_req, ref_count, ref_speed = ft_heartbeat_match.groups()
                self._update_fault_tolerant_temperatures(float(temp1), float(temp2), float(max_temp), 
                                                       s1_conn == "OK", s2_conn == "OK", temp_req == "YES")
                self._update_reflector_count(int(ref_count))
                with state_lock:
                    reflector_data['average_speed'] = float(ref_speed)
                self.temp_updates_count += 1
                self.reflector_updates_count += 1
                return
            
            # 2. REFLECTOR_DETECTED format: REFLECTOR_DETECTED:123 [VOLTAGE:4.32V] [SPEED:45.2rpm]
            reflector_detected_match = self.reflector_detected_pattern.search(line)
            if reflector_detected_match:
                count, voltage, speed = reflector_detected_match.groups()
                self._update_reflector_detection(int(count), float(voltage), float(speed))
                self.reflector_updates_count += 1
                return
            
            # 3. REFLECTOR_STATUS format: REFLECTOR_STATUS [COUNT:123] [VOLTAGE:4.32V] [STATE:DETECTED] [AVG_SPEED:45.2rpm] [INST_SPEED:50.1rpm] [read_FREQ:200.0Hz]
            reflector_status_match = self.reflector_status_pattern.search(line)
            if reflector_status_match:
                count, voltage, state, avg_speed, inst_speed, read_freq = reflector_status_match.groups()
                self._update_reflector_status(int(count), float(voltage), state == "DETECTED", 
                                           float(avg_speed), float(inst_speed), float(read_freq))
                self.reflector_updates_count += 1
                return
            
            # 4. FAULT TOLERANT DUAL_TEMP format: DUAL_TEMP [TEMP1:33.45] [TEMP2:34.12] [MAX:34.12] [S1_CONN:1] [S2_CONN:0] [TEMP_REQ:1]
            dual_match = self.dual_temp_pattern.search(line)
            if dual_match:
                temp1, temp2, max_temp, s1_conn, s2_conn, temp_req = dual_match.groups()
                self._update_fault_tolerant_temperatures(float(temp1), float(temp2), float(max_temp),
                                                       s1_conn == "1", s2_conn == "1", temp_req == "1")
                self.temp_updates_count += 1
                return
            
            # 5. Individual temperature + reflector extractions from ACK messages
            temp1_match = self.temp1_pattern.search(line)
            temp2_match = self.temp2_pattern.search(line)
            max_match = self.max_temp_pattern.search(line)
            reflector_match = self.reflector_pattern.search(line)
            
            if temp1_match and temp2_match and max_match:
                temp1, temp2, max_temp = float(temp1_match.group(1)), float(temp2_match.group(1)), float(max_match.group(1))
                # Check for TEMP_OK flag in ACK
                temp_ok = "[TEMP_OK:1]" in line
                if not temp_ok and "[TEMP_OK:0]" in line:
                    temp_ok = False
                else:
                    temp_ok = True  # Default to OK if not specified
                
                self._update_fault_tolerant_temperatures(temp1, temp2, max_temp, True, True, temp_ok)
                self.temp_updates_count += 1
                
                # Extract reflector count if present
                if reflector_match:
                    reflector_count = int(reflector_match.group(1))
                    self._update_reflector_count(reflector_count)
                    self.reflector_updates_count += 1
                
                return
            
            # 6. Standard HEARTBEAT format with fault tolerance enhancement
            heartbeat_match = self.heartbeat_pattern.search(line)
            if heartbeat_match:
                uptime, armed, brake_active, relay_brake_active, temp, temp_alarm, motor_count = heartbeat_match.groups()
                
                # Update system state
                with state_lock:
                    system_state['armed'] = bool(int(armed))
                    system_state['brake_active'] = bool(int(brake_active))
                    system_state['relay_brake_active'] = bool(int(relay_brake_active))
                    
                    # Update max temp from heartbeat with fault tolerance
                    max_temp = float(temp)
                    if temperature_data['temp_monitoring_required']:
                        temperature_data['current_temp'] = max_temp
                        temperature_data['last_temp_update'] = current_time
                        
                        # Update alarm status only if temperature monitoring is required
                        temp_alarm_active = bool(int(temp_alarm))
                        if temp_alarm_active != temperature_data['temp_alarm']:
                            temperature_data['temp_alarm'] = temp_alarm_active
                            if temp_alarm_active:
                                temperature_data['alarm_start_time'] = current_time
                                temperature_data['alarm_count'] += 1
                                system_state['temperature_emergency'] = True
                                logger.warning(f"Temperature alarm via heartbeat! Max temp: {max_temp}°C")
                            else:
                                system_state['temperature_emergency'] = False
                                logger.info(f"Temperature alarm cleared via heartbeat - Max temp: {max_temp}°C")
                    else:
                        # FAULT TOLERANCE: Use fallback temperature
                        temperature_data['current_temp'] = 25.0
                        temperature_data['temp_alarm'] = False
                        temperature_data['buzzer_active'] = False
                        system_state['temperature_emergency'] = False
                
                logger.debug(f"FAULT TOLERANT Heartbeat: MaxTemp={max_temp}°C, Alarm={temp_alarm}, TempReq={temperature_data['temp_monitoring_required']}")
                return
            
            # 7. Temperature alarm messages with fault tolerance
            if "TEMP_ALARM:" in line and temperature_data['temp_monitoring_required']:
                try:
                    temp_str = line.split("TEMP_ALARM:")[1].strip()
                    temp_value = float(temp_str.split()[0])
                    
                    with state_lock:
                        temperature_data['current_temp'] = max(temperature_data['current_temp'], temp_value)
                        temperature_data['temp_alarm'] = True
                        temperature_data['buzzer_active'] = True
                        temperature_data['alarm_start_time'] = current_time
                        temperature_data['alarm_count'] += 1
                        system_state['temperature_emergency'] = True
                        temperature_data['last_temp_update'] = current_time
                    
                    # Extract reflector count from alarm message
                    reflector_match = self.reflector_pattern.search(line)
                    if reflector_match:
                        reflector_count = int(reflector_match.group(1))
                        self._update_reflector_count(reflector_count)
                    
                    logger.warning(f"FAULT TOLERANT TEMP_ALARM detected! Max Temperature: {temp_value}°C, Reflector count: {reflector_data['count']}")
                except ValueError as e:
                    logger.debug(f"Could not parse TEMP_ALARM value: {e}")
                return
            
            # 8. Temperature safe messages with fault tolerance
            if "TEMP_SAFE:" in line and temperature_data['temp_monitoring_required']:
                try:
                    temp_str = line.split("TEMP_SAFE:")[1].strip()
                    temp_value = float(temp_str.split()[0])
                    
                    with state_lock:
                        temperature_data['current_temp'] = temp_value
                        temperature_data['temp_alarm'] = False
                        temperature_data['buzzer_active'] = False
                        system_state['temperature_emergency'] = False
                        temperature_data['last_temp_update'] = current_time
                    
                    # Extract reflector count from safe message
                    reflector_match = self.reflector_pattern.search(line)
                    if reflector_match:
                        reflector_count = int(reflector_match.group(1))
                        self._update_reflector_count(reflector_count)
                    
                    logger.info(f"FAULT TOLERANT TEMP_SAFE detected! Max Temperature: {temp_value}°C, Reflector count: {reflector_data['count']}")
                except ValueError as e:
                    logger.debug(f"Could not parse TEMP_SAFE value: {e}")
                return
            
            # 9. Sensor connection warnings with fault tolerance
            if "WARNING:Sensor1_disconnected" in line:
                with state_lock:
                    temperature_data['sensor1_connected'] = False
                    temperature_data['sensor_failure_count'] += 1
                logger.warning("FAULT TOLERANT: Sensor 1 (Pin 8) disconnected!")
                return
            
            if "WARNING:Sensor2_disconnected" in line:
                with state_lock:
                    temperature_data['sensor2_connected'] = False
                    temperature_data['sensor_failure_count'] += 1
                logger.warning("FAULT TOLERANT: Sensor 2 (Pin 13) disconnected!")
                return
            
            # 10. FAULT TOLERANCE status messages
            if "FAULT TOLERANCE: Both sensors failed" in line:
                with state_lock:
                    temperature_data['sensor1_connected'] = False
                    temperature_data['sensor2_connected'] = False
                    temperature_data['temp_monitoring_required'] = False
                    temperature_data['allow_operation_without_temp'] = True
                    system_state['can_operate_without_temp'] = True
                    temperature_data['temp_alarm'] = False
                    temperature_data['buzzer_active'] = False
                    system_state['temperature_emergency'] = False
                logger.warning("FAULT TOLERANCE: Both temperature sensors failed - temperature monitoring disabled")
                return
            
            if "Temperature monitoring RESTORED" in line:
                with state_lock:
                    temperature_data['temp_monitoring_required'] = True
                    temperature_data['allow_operation_without_temp'] = False
                    system_state['can_operate_without_temp'] = False
                logger.info("FAULT TOLERANCE: Temperature monitoring restored")
                return
            
            # 11. Emergency stop messages with reflector final count
            if "EMERGENCY_STOP" in line.upper():
                # Extract final reflector count
                if "REFLECTOR_FINAL:" in line:
                    final_match = re.search(r'REFLECTOR_FINAL:([\d]+)', line)
                    if final_match:
                        final_count = int(final_match.group(1))
                        self._update_reflector_count(final_count)
                        logger.warning(f"FAULT TOLERANT Emergency stop - Final reflector count: {final_count}")
                
                logger.warning(f"FAULT TOLERANT Emergency stop detected: {line}")
                return
            
            # 12. Other system messages - debug log only
            if line and not line.startswith("ACK:") and not "PONG" in line:
                logger.debug(f"FAULT TOLERANT Arduino line: {line}")
                
        except Exception as e:
            logger.error(f"FAULT TOLERANT line parsing error for '{line}': {e}")
    
    def _update_fault_tolerant_temperatures(self, temp1, temp2, max_temp, s1_connected, s2_connected, temp_required):
        """FAULT TOLERANT: Update dual temperature data with enhanced fault tolerance"""
        try:
            current_time = datetime.now()
            
            with state_lock:
                # Update individual sensor temperatures with fault tolerance
                old_temp1 = temperature_data['sensor1_temp']
                old_temp2 = temperature_data['sensor2_temp']
                old_max = temperature_data['current_temp']
                
                # Validate temperature changes for realism
                if abs(temp1 - old_temp1) <= MAX_TEMP_CHANGE:
                    temperature_data['sensor1_temp'] = temp1
                    temperature_data['last_valid_temp1'] = temp1
                else:
                    logger.warning(f"FAULT TOLERANT: Sensor 1 unrealistic temp change: {old_temp1} -> {temp1}")
                
                if abs(temp2 - old_temp2) <= MAX_TEMP_CHANGE:
                    temperature_data['sensor2_temp'] = temp2
                    temperature_data['last_valid_temp2'] = temp2
                else:
                    logger.warning(f"FAULT TOLERANT: Sensor 2 unrealistic temp change: {old_temp2} -> {temp2}")
                
                temperature_data['current_temp'] = max_temp
                temperature_data['last_temp_update'] = current_time
                
                # Update connection status
                temperature_data['sensor1_connected'] = s1_connected
                temperature_data['sensor2_connected'] = s2_connected
                
                # Update temperature monitoring requirements
                temperature_data['temp_monitoring_required'] = temp_required
                temperature_data['allow_operation_without_temp'] = not temp_required
                system_state['can_operate_without_temp'] = not temp_required
                
                # Update individual max temperatures
                if s1_connected and temp1 > temperature_data['max_temp_sensor1']:
                    temperature_data['max_temp_sensor1'] = temp1
                if s2_connected and temp2 > temperature_data['max_temp_sensor2']:
                    temperature_data['max_temp_sensor2'] = temp2
                
                # Update overall max temperature
                if max_temp > temperature_data['max_temp_reached']:
                    temperature_data['max_temp_reached'] = max_temp
                
                # Update sensor health tracking
                if s1_connected:
                    self.sensor_health_stats['sensor1_last_seen'] = current_time
                    self.sensor_health_stats['sensor1_updates'] += 1
                
                if s2_connected:
                    self.sensor_health_stats['sensor2_last_seen'] = current_time
                    self.sensor_health_stats['sensor2_updates'] += 1
                
                self.sensor_health_stats['dual_updates'] += 1
                
                # Add to temperature history (limited frequency)
                if len(temperature_data['temp_history']) == 0 or \
                   (current_time - datetime.fromisoformat(temperature_data['temp_history'][-1]['timestamp'])).total_seconds() >= 0.5:
                    temperature_data['temp_history'].append({
                        'timestamp': current_time.isoformat(),
                        'sensor1_temp': temp1,
                        'sensor2_temp': temp2,
                        'max_temp': max_temp,
                        'sensor1_connected': s1_connected,
                        'sensor2_connected': s2_connected,
                        'temp_monitoring_required': temp_required
                    })
                    
                    # Keep history limited
                    if len(temperature_data['temp_history']) > MAX_TEMP_HISTORY:
                        temperature_data['temp_history'] = temperature_data['temp_history'][-MAX_TEMP_HISTORY:]
                
                # Log significant changes
                if abs(max_temp - old_max) > 0.5:
                    sensor_status = f"S1:{'OK' if s1_connected else 'FAIL'} S2:{'OK' if s2_connected else 'FAIL'}"
                    temp_req_status = "REQ" if temp_required else "BYPASS"
                    logger.info(f"FAULT TOLERANT Temperature Update: S1={temp1:.1f}°C, S2={temp2:.1f}°C, Max={max_temp:.1f}°C [{sensor_status}] [{temp_req_status}]")
                    
                # Check for large sensor differences (only if both connected)
                if s1_connected and s2_connected:
                    temp_diff = abs(temp1 - temp2)
                    if temp_diff > TEMP_DIFF_WARNING:
                        logger.warning(f"FAULT TOLERANT: Large sensor difference: S1={temp1:.1f}°C, S2={temp2:.1f}°C (Diff: {temp_diff:.1f}°C)")
                
        except Exception as e:
            logger.error(f"FAULT TOLERANT temperature update error: {e}")
    
    # Reflector functions remain the same
    def _update_reflector_detection(self, count, voltage, speed):
        """Update reflector data when detection occurs - SAME AS BEFORE"""
        try:
            current_time = datetime.now()
            
            with state_lock:
                reflector_data['count'] = count
                reflector_data['voltage'] = voltage
                reflector_data['instant_speed'] = speed
                reflector_data['state'] = True  # Detection event
                reflector_data['last_update'] = current_time
                reflector_data['detections'] += 1
                
                # Update session and daily counters
                reflector_data['statistics']['session_count'] = count
                reflector_data['statistics']['daily_count'] = count
                reflector_data['statistics']['total_count'] = count
                
                # Update health tracking
                self.sensor_health_stats['reflector_last_seen'] = current_time
                self.sensor_health_stats['reflector_updates'] += 1
                
                reflector_data['system_active'] = True
            
            logger.debug(f"Reflector detection #{count}: {voltage:.2f}V, Speed: {speed:.1f}rpm")
            
        except Exception as e:
            logger.error(f"Reflector detection update error: {e}")
    
    def _update_reflector_status(self, count, voltage, state, avg_speed, inst_speed, read_freq):
        """Update comprehensive reflector status - SAME AS BEFORE"""
        try:
            current_time = datetime.now()
            
            with state_lock:
                reflector_data['count'] = count
                reflector_data['voltage'] = voltage
                reflector_data['state'] = state
                reflector_data['average_speed'] = avg_speed
                reflector_data['instant_speed'] = inst_speed
                reflector_data['read_frequency'] = read_freq
                reflector_data['last_update'] = current_time
                reflector_data['system_active'] = True
                
                # Update health tracking
                self.sensor_health_stats['reflector_last_seen'] = current_time
                self.sensor_health_stats['reflector_updates'] += 1
            
            logger.debug(f"Reflector status update: Count={count}, Voltage={voltage:.2f}V, AvgSpeed={avg_speed:.1f}rpm")
            
        except Exception as e:
            logger.error(f"Reflector status update error: {e}")
    
    def _update_reflector_count(self, count):
        """Simple reflector count update - SAME AS BEFORE"""
        try:
            current_time = datetime.now()
            
            with state_lock:
                old_count = reflector_data['count']
                reflector_data['count'] = count
                reflector_data['last_update'] = current_time
                
                # Update session statistics if count increased
                if count > old_count:
                    reflector_data['statistics']['session_count'] = count
                    reflector_data['statistics']['daily_count'] = count
                    reflector_data['statistics']['total_count'] = count
                
                # Update health tracking
                self.sensor_health_stats['reflector_last_seen'] = current_time
                reflector_data['system_active'] = True
            
            if count != old_count:
                logger.debug(f"Reflector count updated: {old_count} -> {count}")
            
        except Exception as e:
            logger.error(f"Reflector count update error: {e}")
    
    # Rest of the methods remain similar but with FAULT TOLERANT enhancements...
    def send_command_sync(self, command, timeout=3.0):
        """Send command synchronously with timeout - SAME AS BEFORE"""
        if not self.is_connected or not self.connection or shutdown_event.is_set():
            return False, "Not connected"
        
        try:
            with self.connection_lock:
                # Rate limiting
                current_time = time.time()
                time_since_last = current_time - self.last_command_time
                if time_since_last < 0.02:
                    time.sleep(0.02 - time_since_last)
                
                # Send command
                command_bytes = f"{command}\n".encode('utf-8')
                self.connection.write(command_bytes)
                self.connection.flush()
                self.last_command_time = time.time()
                
                # Read response
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
                            completion_keywords = ["MOTOR_STARTED", "MOTOR_STOPPED", "LEV_GROUP_STARTED", 
                                                 "THR_GROUP_STARTED", "ARMED", "RELAY_BRAKE:", 
                                                 "PONG", "ACK:", "BRAKE_", "DISARMED", "EMERGENCY_STOP",
                                                 "FAULT-TOLERANT", "TEMP_DUAL", "REFLECTOR_RESET", "REFLECTOR_FULL",
                                                 "TEMP_BYPASS"]
                            
                            if any(keyword in response for keyword in completion_keywords):
                                break
                            
                            if '\n' in response or len(response) > 150:
                                break
                        except Exception as e:
                            logger.debug(f"Read error: {e}")
                            break
                    
                    time.sleep(0.01)
                
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
    
    # Rest of the controller methods remain the same but with fault tolerant logging...
    def disconnect(self, keep_threads=False):
        """Safely disconnect from Arduino"""
        logger.info("Disconnecting FAULT TOLERANT Arduino...")
        
        self.is_connected = False
        system_state['connected'] = False
        system_state['reflector_system_enabled'] = False
        
        if self.connection:
            try:
                acquired = self.connection_lock.acquire(timeout=2.0)
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
                (self.temp_stats_thread, "TempStatsMonitor"),
                (self.sensor_health_thread, "SensorHealthMonitor"),
                (self.reflector_stats_thread, "ReflectorStatsMonitor"),
                (self.sensor_recovery_thread, "SensorRecoveryMonitor")  # NEW
            ]
            
            for thread, name in threads:
                if thread and thread.is_alive():
                    thread.join(timeout=1.0)
        
        logger.info("FAULT TOLERANT Arduino disconnected successfully")

# Initialize FAULT TOLERANT Arduino controller
logger.info("Initializing FAULT TOLERANT DUAL TEMPERATURE + REFLECTOR Arduino controller...")
try:
    arduino_controller = FaultTolerantDualTempReflectorArduinoController()
except Exception as e:
    logger.error(f"Failed to initialize FAULT TOLERANT Arduino controller: {e}")
    arduino_controller = None

# Rest of the API routes remain mostly the same but with fault tolerant enhancements...

@app.route('/api/status', methods=['GET'])
def get_status():
    """Get comprehensive system status including FAULT TOLERANT dual temperature + reflector data"""
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
                    'sensor1_temp': temperature_data['sensor1_temp'],
                    'sensor2_temp': temperature_data['sensor2_temp'],
                    'current': temperature_data['current_temp'],
                    'alarm': temperature_data['temp_alarm'],
                    'buzzer_active': temperature_data['buzzer_active'],
                    'max_reached': temperature_data['max_temp_reached'],
                    'max_sensor1': temperature_data['max_temp_sensor1'],
                    'max_sensor2': temperature_data['max_temp_sensor2'],
                    'last_update': temperature_data['last_temp_update'].isoformat(),
                    'alarm_threshold': TEMP_ALARM_THRESHOLD,
                    'safe_threshold': TEMP_SAFE_THRESHOLD,
                    'warning_threshold': TEMP_WARNING_THRESHOLD,
                    'emergency_active': system_state['temperature_emergency'],
                    'alarm_count': temperature_data['alarm_count'],
                    'history_count': len(temperature_data['temp_history']),
                    'update_frequency': temperature_data['update_frequency'],
                    'sensor1_connected': temperature_data['sensor1_connected'],
                    'sensor2_connected': temperature_data['sensor2_connected'],
                    'sensor_failure_count': temperature_data['sensor_failure_count'],
                    'dual_sensor_mode': system_state['dual_sensor_mode'],
                    # FAULT TOLERANT fields
                    'temp_monitoring_required': temperature_data['temp_monitoring_required'],
                    'allow_operation_without_temp': temperature_data['allow_operation_without_temp'],
                    'fault_tolerant_mode': temperature_data['fault_tolerant_mode'],
                    'last_valid_temp1': temperature_data['last_valid_temp1'],
                    'last_valid_temp2': temperature_data['last_valid_temp2'],
                    'sensor1_fail_count': temperature_data['sensor1_fail_count'],
                    'sensor2_fail_count': temperature_data['sensor2_fail_count'],
                    'sensor_recovery_attempts': temperature_data['sensor_recovery_attempts']
                },
                'reflector': reflector_data.copy(),  # Same as before
                'stats': {
                    'commands': system_state['commands'],
                    'errors': system_state['errors'],
                    'uptime_seconds': int(uptime_seconds),
                    'last_response': system_state['last_response'].isoformat() if system_state['last_response'] else None,
                    'reconnect_attempts': arduino_controller.reconnect_attempts if arduino_controller else 0,
                    'reflector_system_enabled': system_state['reflector_system_enabled'],
                    'fault_tolerant_mode': system_state['fault_tolerant_mode'],  # NEW
                    'can_operate_without_temp': system_state['can_operate_without_temp']  # NEW
                },
                'port_info': {
                    'port': arduino_controller.port if arduino_controller else None,
                    'baudrate': arduino_controller.baudrate if arduino_controller else None
                },
                'timestamp': datetime.now().isoformat(),
                'version': '3.7-FAULT-TOLERANT-DUAL-TEMPERATURE-REFLECTOR'
            })
    except Exception as e:
        logger.error(f"Status endpoint error: {e}")
        return jsonify({'error': str(e), 'connected': False}), 500

# NEW: Temperature bypass control routes
@app.route('/api/temperature/bypass/enable', methods=['POST'])
def enable_temperature_bypass():
    """Enable operation without temperature sensors"""
    if not arduino_controller or not arduino_controller.is_connected:
        return jsonify({
            'status': 'error',
            'message': 'Arduino not connected'
        }), 503
    
    try:
        success, response = arduino_controller.send_command_sync("TEMP_BYPASS_ON", timeout=3.0)
        
        if success and "TEMP_BYPASS:ENABLED" in response:
            with state_lock:
                temperature_data['allow_operation_without_temp'] = True
                temperature_data['temp_monitoring_required'] = False
                temperature_data['temp_alarm'] = False
                temperature_data['buzzer_active'] = False
                system_state['temperature_emergency'] = False
                system_state['can_operate_without_temp'] = True
            
            logger.info("FAULT TOLERANCE: Temperature bypass enabled - system will operate without temperature monitoring")
            return jsonify({
                'status': 'success',
                'message': 'Temperature bypass enabled - system will operate without temperature sensors',
                'bypass_enabled': True,
                'temp_monitoring_required': False,
                'arduino_response': response
            })
        else:
            return jsonify({
                'status': 'error',
                'message': f'Could not enable temperature bypass: {response}'
            }), 500
            
    except Exception as e:
        logger.error(f"Temperature bypass enable error: {e}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@app.route('/api/temperature/bypass/disable', methods=['POST'])
def disable_temperature_bypass():
    """Disable temperature bypass (if sensors are available)"""
    if not arduino_controller or not arduino_controller.is_connected:
        return jsonify({
            'status': 'error',
            'message': 'Arduino not connected'
        }), 503
    
    try:
        success, response = arduino_controller.send_command_sync("TEMP_BYPASS_OFF", timeout=3.0)
        
        if success:
            if "TEMP_BYPASS:DISABLED" in response:
                with state_lock:
                    temperature_data['temp_monitoring_required'] = True
                    temperature_data['allow_operation_without_temp'] = False
                    system_state['can_operate_without_temp'] = False
                
                logger.info("FAULT TOLERANCE: Temperature monitoring restored")
                return jsonify({
                    'status': 'success',
                    'message': 'Temperature monitoring restored',
                    'bypass_enabled': False,
                    'temp_monitoring_required': True,
                    'arduino_response': response
                })
            elif "TEMP_BYPASS:CANNOT_DISABLE" in response:
                return jsonify({
                    'status': 'warning',
                    'message': 'Cannot disable temperature bypass - no temperature sensors available',
                    'bypass_enabled': True,
                    'temp_monitoring_required': False,
                    'arduino_response': response
                })
        
        return jsonify({
            'status': 'error',
            'message': f'Could not disable temperature bypass: {response}'
        }), 500
            
    except Exception as e:
        logger.error(f"Temperature bypass disable error: {e}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

# Enhanced temperature endpoint with fault tolerance
@app.route('/api/temperature', methods=['GET'])
def get_temperature_data():
    """Get detailed FAULT TOLERANT dual temperature data and history"""
    try:
        with state_lock:
            current_time = datetime.now()
            last_update_age = (current_time - temperature_data['last_temp_update']).total_seconds()
            
            alarm_duration = None
            if temperature_data['temp_alarm'] and temperature_data['alarm_start_time']:
                alarm_duration = (current_time - temperature_data['alarm_start_time']).total_seconds()
            
            # Calculate temperature difference
            temp_difference = abs(temperature_data['sensor1_temp'] - temperature_data['sensor2_temp']) if \
                             temperature_data['sensor1_connected'] and temperature_data['sensor2_connected'] else 0
            
            return jsonify({
                'current_temperature': temperature_data['current_temp'],
                'sensor1_temperature': temperature_data['sensor1_temp'],
                'sensor2_temperature': temperature_data['sensor2_temp'],
                'temperature_difference': temp_difference,
                'temperature_alarm': temperature_data['temp_alarm'],
                'buzzer_active': temperature_data['buzzer_active'],
                'max_temperature_reached': temperature_data['max_temp_reached'],
                'max_temperature_sensor1': temperature_data['max_temp_sensor1'],
                'max_temperature_sensor2': temperature_data['max_temp_sensor2'],
                'last_update': temperature_data['last_temp_update'].isoformat(),
                'thresholds': {
                    'alarm': TEMP_ALARM_THRESHOLD,
                    'safe': TEMP_SAFE_THRESHOLD,
                    'warning': TEMP_WARNING_THRESHOLD,
                    'sensor_diff_warning': TEMP_DIFF_WARNING
                },
                'alarm_info': {
                    'count': temperature_data['alarm_count'],
                    'start_time': temperature_data['alarm_start_time'].isoformat() if temperature_data['alarm_start_time'] else None,
                    'duration_seconds': alarm_duration
                },
                'sensor_status': {
                    'sensor1_connected': temperature_data['sensor1_connected'],
                    'sensor2_connected': temperature_data['sensor2_connected'],
                    'sensor_failure_count': temperature_data['sensor_failure_count'],
                    'both_sensors_active': temperature_data['sensor1_connected'] and temperature_data['sensor2_connected'],
                    'any_sensor_active': temperature_data['sensor1_connected'] or temperature_data['sensor2_connected'],
                    'primary_sensor': 8,  # Pin number
                    'secondary_sensor': 13,  # Pin number
                    'sensor1_fail_count': temperature_data['sensor1_fail_count'],
                    'sensor2_fail_count': temperature_data['sensor2_fail_count']
                },
                'fault_tolerance': {  # NEW: Fault tolerance status
                    'fault_tolerant_mode': temperature_data['fault_tolerant_mode'],
                    'temp_monitoring_required': temperature_data['temp_monitoring_required'],
                    'allow_operation_without_temp': temperature_data['allow_operation_without_temp'],
                    'can_operate_without_temp': system_state['can_operate_without_temp'],
                    'last_valid_temp1': temperature_data['last_valid_temp1'],
                    'last_valid_temp2': temperature_data['last_valid_temp2'],
                    'sensor_recovery_attempts': temperature_data['sensor_recovery_attempts']
                },
                'safety_status': {
                    'emergency_active': system_state['temperature_emergency'],
                    'can_arm_system': (not temperature_data['temp_alarm'] and 
                                     (not temperature_data['temp_monitoring_required'] or 
                                      temperature_data['current_temp'] < TEMP_ALARM_THRESHOLD - 5)),
                    'safe_to_operate': (not temperature_data['temp_monitoring_required'] or 
                                      temperature_data['current_temp'] < TEMP_WARNING_THRESHOLD),
                    'sensor_redundancy_ok': (temperature_data['sensor1_connected'] or 
                                           temperature_data['sensor2_connected'] or 
                                           temperature_data['allow_operation_without_temp']),
                    'large_sensor_diff': temp_difference > TEMP_DIFF_WARNING
                },
                'reflector_correlation': {  # Correlate temperature with reflector data
                    'current_count': reflector_data['count'],
                    'current_speed': reflector_data['average_speed'],
                    'temp_vs_speed_ratio': reflector_data['average_speed'] / temperature_data['current_temp'] if temperature_data['current_temp'] > 0 else 0,
                    'system_load_indicator': 'high' if temperature_data['current_temp'] > 40 and reflector_data['average_speed'] > 30 else 'normal'
                },
                'history': temperature_data['temp_history'][-30:],
                'timestamp': current_time.isoformat(),
                'performance': {
                    'update_frequency_hz': temperature_data['update_frequency'],
                    'last_update_ago_seconds': last_update_age,
                    'status': 'real-time' if last_update_age < 2.0 else 'delayed',
                    'continuous_reader_alive': arduino_controller.continuous_reader_thread.is_alive() if arduino_controller and arduino_controller.continuous_reader_thread else False,
                    'sensor_health_alive': arduino_controller.sensor_health_thread.is_alive() if arduino_controller and arduino_controller.sensor_health_thread else False,
                    'sensor_recovery_alive': arduino_controller.sensor_recovery_thread.is_alive() if arduino_controller and arduino_controller.sensor_recovery_thread else False,
                    'optimization_level': 'fault-tolerant-dual-sensor-reflector'
                }
            })
    except Exception as e:
        logger.error(f"FAULT TOLERANT temperature endpoint error: {e}")
        return jsonify({'error': str(e)}), 500

# Enhanced system control routes with fault tolerance
@app.route('/api/system/arm', methods=['POST'])
def arm_system():
    """Arm system - FAULT TOLERANT temperature + reflector safety checks"""
    if not arduino_controller or not arduino_controller.is_connected:
        return jsonify({'status': 'error', 'message': 'Arduino not connected'}), 503
    
    # FAULT TOLERANT temperature safety checks
    if temperature_data['temp_monitoring_required'] and temperature_data['temp_alarm']:
        return jsonify({
            'status': 'error',
            'message': 'Cannot arm - temperature alarm active',
            'dual_temperatures': {
                'sensor1_temp': temperature_data['sensor1_temp'],
                'sensor2_temp': temperature_data['sensor2_temp'],
                'max_temp': temperature_data['current_temp'],
                'alarm_active': temperature_data['temp_alarm'],
                'temp_monitoring_required': temperature_data['temp_monitoring_required']
            },
            'reflector_status': {
                'count': reflector_data['count'],
                'system_active': reflector_data['system_active']
            }
        }), 400
    
    # FAULT TOLERANT: Check sensor requirements only if temperature monitoring is required
    if temperature_data['temp_monitoring_required']:
        if not temperature_data['sensor1_connected'] and not temperature_data['sensor2_connected']:
            return jsonify({
                'status': 'error',
                'message': 'Cannot arm - no temperature sensors connected (temperature monitoring required)',
                'sensor1_connected': temperature_data['sensor1_connected'],
                'sensor2_connected': temperature_data['sensor2_connected'],
                'fault_tolerance': {
                    'can_bypass': temperature_data['allow_operation_without_temp'],
                    'temp_monitoring_required': temperature_data['temp_monitoring_required']
                }
            }), 400
    
    try:
        success, response = arduino_controller.send_command_sync("ARM", timeout=3.0)
        
        if success and "ARMED" in response.upper():
            with state_lock:
                system_state['armed'] = True
            
            # Log with fault tolerant status
            temp_status = "MONITORED" if temperature_data['temp_monitoring_required'] else "BYPASSED"
            sensor_status = f"S1:{'OK' if temperature_data['sensor1_connected'] else 'FAIL'} S2:{'OK' if temperature_data['sensor2_connected'] else 'FAIL'}"
            
            logger.info(f"FAULT TOLERANT System ARMED - Temps: S1={temperature_data['sensor1_temp']}°C, S2={temperature_data['sensor2_temp']}°C, Max={temperature_data['current_temp']}°C [{sensor_status}] [TEMP:{temp_status}], Reflector: {reflector_data['count']}")
            
            return jsonify({
                'status': 'armed',
                'message': 'System armed successfully',
                'dual_temperatures': {
                    'sensor1_temp': temperature_data['sensor1_temp'],
                    'sensor2_temp': temperature_data['sensor2_temp'],
                    'max_temp': temperature_data['current_temp'],
                    'sensor1_connected': temperature_data['sensor1_connected'],
                    'sensor2_connected': temperature_data['sensor2_connected'],
                    'temp_monitoring_required': temperature_data['temp_monitoring_required'],
                    'allow_operation_without_temp': temperature_data['allow_operation_without_temp']
                },
                'reflector_status': {
                    'count': reflector_data['count'],
                    'average_speed': reflector_data['average_speed'],
                    'system_active': reflector_data['system_active']
                },
                'fault_tolerance': {
                    'fault_tolerant_mode': temperature_data['fault_tolerant_mode'],
                    'temperature_bypass_enabled': temperature_data['allow_operation_without_temp']
                },
                'arm_timestamp': datetime.now().isoformat()
            })
        else:
            return jsonify({'status': 'error', 'message': f'Arduino error: {response}'}), 500
            
    except Exception as e:
        logger.error(f"FAULT TOLERANT arm system error: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/system/disarm', methods=['POST'])
def disarm_system():
    """Disarm the system with fault tolerant reflector logging"""
    if not arduino_controller or not arduino_controller.is_connected:
        return jsonify({'status': 'error', 'message': 'Arduino not connected'}), 503
    
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
            
            logger.info("FAULT TOLERANT System DISARMED successfully")
            return jsonify({
                'status': 'disarmed',
                'message': 'System disarmed successfully',
                'dual_temperatures': {
                    'sensor1_temp': temperature_data['sensor1_temp'],
                    'sensor2_temp': temperature_data['sensor2_temp'],
                    'max_temp': temperature_data['current_temp'],
                    'temp_monitoring_required': temperature_data['temp_monitoring_required']
                },
                'reflector_final_count': reflector_data['count'],
                'fault_tolerance': {
                    'fault_tolerant_mode': temperature_data['fault_tolerant_mode']
                }
            })
        else:
            return jsonify({'status': 'error', 'message': f'Arduino error: {response}'}), 500
            
    except Exception as e:
        logger.error(f"FAULT TOLERANT disarm system error: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/emergency-stop', methods=['POST'])
def emergency_stop():
    """Emergency stop all systems with fault tolerant dual temperature + reflector logging"""
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
        arduino_response = None
        if arduino_controller and arduino_controller.is_connected:
            try:
                success, response = arduino_controller.send_command_sync("EMERGENCY_STOP", timeout=2.0)
                if success:
                    arduino_response = response
                    logger.info(f"Emergency stop sent to Arduino: {response}")
            except Exception as e:
                logger.warning(f"Could not send emergency stop to Arduino: {e}")
        
        # Log with fault tolerant status
        temp_status = "MONITORED" if temperature_data['temp_monitoring_required'] else "BYPASSED"
        sensor_status = f"S1:{'OK' if temperature_data['sensor1_connected'] else 'FAIL'} S2:{'OK' if temperature_data['sensor2_connected'] else 'FAIL'}"
        
        logger.warning(f"FAULT TOLERANT EMERGENCY STOP ACTIVATED! Temps: S1={temperature_data['sensor1_temp']}°C, S2={temperature_data['sensor2_temp']}°C, Max={temperature_data['current_temp']}°C [{sensor_status}] [TEMP:{temp_status}], Reflector Final: {reflector_data['count']}")
        
        return jsonify({
            'status': 'emergency_stop',
            'message': 'Emergency stop activated! All systems stopped and relay brake deactivated.',
            'all_stopped': True,
            'system_disarmed': True,
            'brake_activated': True,
            'relay_brake_activated': False,
            'dual_temperatures': {
                'sensor1_temp': temperature_data['sensor1_temp'],
                'sensor2_temp': temperature_data['sensor2_temp'],
                'max_temp': temperature_data['current_temp'],
                'sensor1_connected': temperature_data['sensor1_connected'],
                'sensor2_connected': temperature_data['sensor2_connected'],
                'temperature_alarm': temperature_data['temp_alarm'],
                'temp_monitoring_required': temperature_data['temp_monitoring_required']
            },
            'reflector_final_status': {
                'final_count': reflector_data['count'],
                'final_speed': reflector_data['average_speed'],
                'total_detections': reflector_data['detections'],
                'session_duration_minutes': reflector_data['performance']['total_runtime'],
                'system_was_active': reflector_data['system_active']
            },
            'fault_tolerance': {
                'fault_tolerant_mode': temperature_data['fault_tolerant_mode'],
                'temperature_bypass_enabled': temperature_data['allow_operation_without_temp'],
                'can_operate_without_temp': system_state['can_operate_without_temp']
            },
            'arduino_response': arduino_response,
            'timestamp': datetime.now().isoformat()
        })
            
    except Exception as e:
        logger.error(f"FAULT TOLERANT emergency stop error: {e}")
        return jsonify({
            'status': 'emergency_stop',
            'message': 'Emergency stop activated with error',
            'error': str(e),
            'dual_temperatures': {
                'sensor1_temp': temperature_data['sensor1_temp'],
                'sensor2_temp': temperature_data['sensor2_temp'],
                'max_temp': temperature_data['current_temp']
            },
            'reflector_final_count': reflector_data['count'],
            'fault_tolerance': {
                'fault_tolerant_mode': temperature_data['fault_tolerant_mode']
            },
            'timestamp': datetime.now().isoformat()
        })

# Enhanced ping endpoint with fault tolerance status
@app.route('/api/ping', methods=['GET'])
def ping():
    """Ultra-fast health check with FAULT TOLERANT dual temperature + reflector info"""
    try:
        with state_lock:
            temp_age = (datetime.now() - temperature_data['last_temp_update']).total_seconds()
            reflector_age = (datetime.now() - reflector_data['last_update']).total_seconds()
            temp_diff = abs(temperature_data['sensor1_temp'] - temperature_data['sensor2_temp']) if \
                       temperature_data['sensor1_connected'] and temperature_data['sensor2_connected'] else 0
            
            return jsonify({
                'status': 'ok',
                'timestamp': datetime.now().isoformat(),
                'arduino_connected': arduino_controller.is_connected if arduino_controller else False,
                'fault_tolerant_mode': system_state['fault_tolerant_mode'],  # NEW
                'dual_temperatures': {
                    'sensor1_temp': temperature_data['sensor1_temp'],
                    'sensor2_temp': temperature_data['sensor2_temp'],
                    'max_temp': temperature_data['current_temp'],
                    'temperature_difference': temp_diff,
                    'sensor1_connected': temperature_data['sensor1_connected'],
                    'sensor2_connected': temperature_data['sensor2_connected'],
                    'alarm': temperature_data['temp_alarm'],
                    'age_seconds': temp_age,
                    'frequency_hz': temperature_data['update_frequency'],
                    'status': 'real-time' if temp_age < 1.0 else 'delayed',
                    # FAULT TOLERANT fields
                    'temp_monitoring_required': temperature_data['temp_monitoring_required'],
                    'allow_operation_without_temp': temperature_data['allow_operation_without_temp'],
                    'fault_tolerant_mode': temperature_data['fault_tolerant_mode'],
                    'sensor1_fail_count': temperature_data['sensor1_fail_count'],
                    'sensor2_fail_count': temperature_data['sensor2_fail_count']
                },
                'reflector_system': {  # Reflector system health
                    'count': reflector_data['count'],
                    'voltage': reflector_data['voltage'],
                    'average_speed': reflector_data['average_speed'],
                    'instant_speed': reflector_data['instant_speed'],
                    'system_active': reflector_data['system_active'],
                    'read_frequency': reflector_data['read_frequency'],
                    'age_seconds': reflector_age,
                    'status': 'real-time' if reflector_age < 2.0 else 'delayed'
                },
                'performance': {
                    'continuous_reader': arduino_controller.continuous_reader_thread.is_alive() if arduino_controller and arduino_controller.continuous_reader_thread else False,
                    'temp_stats_monitor': arduino_controller.temp_stats_thread.is_alive() if arduino_controller and arduino_controller.temp_stats_thread else False,
                    'sensor_health_monitor': arduino_controller.sensor_health_thread.is_alive() if arduino_controller and arduino_controller.sensor_health_thread else False,
                    'reflector_stats_monitor': arduino_controller.reflector_stats_thread.is_alive() if arduino_controller and arduino_controller.reflector_stats_thread else False,
                    'sensor_recovery_monitor': arduino_controller.sensor_recovery_thread.is_alive() if arduino_controller and arduino_controller.sensor_recovery_thread else False,  # NEW
                    'optimization': 'fault-tolerant-dual-sensor-reflector'
                },
                'system_status': {
                    'armed': system_state['armed'],
                    'temperature_emergency': system_state['temperature_emergency'],
                    'reflector_system_enabled': system_state['reflector_system_enabled'],
                    'can_operate_without_temp': system_state['can_operate_without_temp']  # NEW
                },
                'version': '3.7-FAULT-TOLERANT-DUAL-TEMPERATURE-REFLECTOR',
                'port': arduino_controller.port if arduino_controller else None
            })
        
    except Exception as e:
        logger.error(f"FAULT TOLERANT ping error: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

# Enhanced error handlers with fault tolerance info
@app.errorhandler(404)
def not_found(error):
    return jsonify({
        'status': 'error',
        'message': 'Endpoint not found',
        'available_endpoints': [
            'GET /api/status',
            'GET /api/temperature',
            'GET /api/temperature/realtime',
            'POST /api/temperature/bypass/enable',   # NEW
            'POST /api/temperature/bypass/disable',  # NEW
            'GET /api/reflector',
            'GET /api/reflector/realtime',
            'GET /api/reflector/statistics',
            'POST /api/reflector/reset',
            'POST /api/reflector/calibrate',
            'GET /api/ping',
            'POST /api/system/arm',
            'POST /api/system/disarm',
            'POST /api/motor/<num>/start',
            'POST /api/emergency-stop'
        ],
        'fault_tolerant_features': [  # NEW
            'Works with 0, 1, or 2 temperature sensors',
            'Automatic sensor failure detection',
            'Sensor recovery attempts',
            'Temperature monitoring bypass',
            'Fallback temperature values',
            'Enhanced safety with fault tolerance',
            'Operation continuity without sensors'
        ],
        'dual_sensor_features': [
            'Individual sensor temperatures',
            'Redundant safety monitoring',
            'Sensor health tracking',
            'Temperature difference warnings',
            'Automatic failover capability'
        ],
        'reflector_features': [
            'Ultra-fast reflector counting (5ms)',
            'Real-time speed calculation',
            'Voltage monitoring',
            'Sensor calibration',
            'Performance statistics',
            'Session and daily tracking',
            'Correlation with temperature data'
        ]
    }), 404

# Background monitoring - FAULT TOLERANT ENHANCED
def fault_tolerant_background_monitor():
    """FAULT TOLERANT background monitoring and maintenance"""
    logger.info("FAULT TOLERANT background monitor started")
    
    while not shutdown_event.is_set():
        try:
            # Connection monitoring
            if arduino_controller and not arduino_controller.is_connected:
                if arduino_controller.reconnect_attempts < arduino_controller.max_attempts:
                    logger.info("Auto-reconnection attempt...")
                    if arduino_controller.reconnect():
                        logger.info("Auto-reconnection successful")
            
            # FAULT TOLERANT monitoring logic
            with state_lock:
                temp_age = (datetime.now() - temperature_data['last_temp_update']).total_seconds()
                reflector_age = (datetime.now() - reflector_data['last_update']).total_seconds()
                
                # Temperature monitoring with fault tolerance
                if temp_age > 10 and temperature_data['temp_monitoring_required']:
                    logger.warning(f"FAULT TOLERANT: Temperature data is stale: {temp_age:.1f}s old")
                    if arduino_controller and arduino_controller.is_connected:
                        arduino_controller._restart_monitoring_threads()
                elif temp_age > 30 and not temperature_data['temp_monitoring_required']:
                    logger.info(f"FAULT TOLERANT: Temperature data stale ({temp_age:.1f}s) but monitoring not required")
                
                # Reflector monitoring - same as before
                if reflector_age > REFLECTOR_TIMEOUT and reflector_data['system_active']:
                    logger.warning(f"Reflector system inactive: {reflector_age:.1f}s since last update")
                    reflector_data['system_active'] = False
                    system_state['reflector_system_enabled'] = False
                
                # FAULT TOLERANT: Check if we can enable temperature bypass automatically
                if not temperature_data['sensor1_connected'] and not temperature_data['sensor2_connected']:
                    if temperature_data['temp_monitoring_required'] and not temperature_data['allow_operation_without_temp']:
                        logger.info("FAULT TOLERANT: Both sensors failed, considering automatic temperature bypass")
                        # Don't auto-enable bypass, but log the capability
                        logger.info("FAULT TOLERANT: Temperature bypass available if needed")
            
            shutdown_event.wait(5)
            
        except Exception as e:
            logger.error(f"FAULT TOLERANT background monitor error: {e}")
            shutdown_event.wait(5)
    
    logger.info("FAULT TOLERANT background monitor stopped")

# Start background monitor
monitor_thread = threading.Thread(target=fault_tolerant_background_monitor, daemon=True, name="FaultTolerantMonitor")
monitor_thread.start()

# Graceful shutdown handler
def signal_handler(sig, frame):
    """Graceful shutdown handler"""
    logger.info("FAULT TOLERANT shutdown signal received...")
    
    try:
        shutdown_event.set()
        
        if arduino_controller:
            # Get final statistics before shutdown
            with state_lock:
                sensor_status = f"S1:{'OK' if temperature_data['sensor1_connected'] else 'FAIL'} S2:{'OK' if temperature_data['sensor2_connected'] else 'FAIL'}"
                temp_status = "MONITORED" if temperature_data['temp_monitoring_required'] else "BYPASSED"
                logger.info(f"Final FAULT TOLERANT Statistics - Temperature: S1={temperature_data['sensor1_temp']:.1f}°C, S2={temperature_data['sensor2_temp']:.1f}°C [{sensor_status}] [TEMP:{temp_status}]")
                logger.info(f"Final Statistics - Reflector: Count={reflector_data['count']}, Speed={reflector_data['average_speed']:.1f}rpm")
                logger.info(f"Final FAULT TOLERANCE Status - Sensor1 Fails: {temperature_data['sensor1_fail_count']}, Sensor2 Fails: {temperature_data['sensor2_fail_count']}")
            
            arduino_controller.disconnect()
        
        logger.info("FAULT TOLERANT backend shutdown completed")
        
    except Exception as e:
        logger.error(f"FAULT TOLERANT shutdown error: {e}")
    finally:
        sys.exit(0)

# Register signal handlers
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

if __name__ == '__main__':
    logger.info("=" * 80)
    logger.info("SpectraLoop Backend FAULT TOLERANT DUAL TEMPERATURE + REFLECTOR v3.7")
    logger.info("=" * 80)
    
    try:
        if arduino_controller and arduino_controller.is_connected:
            logger.info(f"Arduino Status: Connected to {arduino_controller.port}")
            logger.info("FAULT TOLERANT DUAL TEMPERATURE + REFLECTOR FEATURES:")
            logger.info("   🌡️ Primary sensor (Pin 8) + Secondary sensor (Pin 13) - FAULT TOLERANT")
            logger.info("   📏 Omron reflector counter (Pin A0) + Status LED (Pin 12)")
            logger.info("   🛡️ FAULT TOLERANT: Works with 0, 1, or 2 temperature sensors")
            logger.info("   ⚡ 100ms temperature + 5ms reflector readings")
            logger.info("   📊 Automatic sensor failure detection and recovery")
            logger.info("   🔄 Temperature monitoring bypass capability")
            logger.info("   ⚠️ Enhanced safety with fault tolerance")
            logger.info("   📈 Real-time performance monitoring for all systems")
            logger.info("   🚨 Operation continuity even with sensor failures")
            logger.info("   📋 Comprehensive statistics and trending")
            logger.info("   🎯 Ultra-precision reflector counting with calibration")
            logger.info("   🔧 FAULT TOLERANCE: System continues operation without temperature sensors when needed")
        else:
            logger.warning("Arduino Status: Not Connected - will run in fault tolerant mode")
        
        logger.info("=" * 80)
        logger.info("Starting FAULT TOLERANT Flask server...")
        
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
        logger.error(f"FAULT TOLERANT server error: {e}")
        signal_handler(signal.SIGTERM, None)
    finally:
        logger.info("FAULT TOLERANT server shutdown complete")
                