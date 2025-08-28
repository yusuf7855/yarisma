#!/usr/bin/env python3
"""
SpectraLoop Motor Control Backend - DUAL TEMPERATURE + REFLECTOR COUNTER v3.6
Dual DS18B20 sensors + buzzer + reflector counting + redundant safety system
Individual + Group motor control + Dual temperature monitoring + Reflector tracking
Motor Pin Mapping: İtki (3,7), Levitasyon (2,4,5,6)
Temperature Safety: Pin8->DS18B20#1, Pin13->DS18B20#2, Pin9->Buzzer, Pin11->RelayBrake
Reflector Counter: PinA0->Omron Photoelectric, Pin12->Status LED
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
        logging.FileHandler('spectraloop_dual_reflector.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Thread-safe global state
motor_states = {i: False for i in range(1, 7)}
individual_motor_speeds = {i: 0 for i in range(1, 7)}
group_speeds = {'levitation': 0, 'thrust': 0}

# DUAL Temperature and safety system state - ENHANCED
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
    'sensor1_connected': True,      # Connection status
    'sensor2_connected': True,      # Connection status
    'update_frequency': 0.0,
    'sensor_failure_count': 0       # Track sensor failures
}

# REFLECTOR COUNTER SYSTEM STATE - NEW COMPLETE SECTION
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
    'reflector_system_enabled': True  # NEW: Reflector system flag
}

# Thread synchronization
state_lock = threading.Lock()
shutdown_event = threading.Event()

# Temperature safety constants - DUAL SENSOR
TEMP_ALARM_THRESHOLD = 55.0
TEMP_SAFE_THRESHOLD = 50.0
TEMP_WARNING_THRESHOLD = 45.0
MAX_TEMP_HISTORY = 200

# REFLECTOR SYSTEM Constants - NEW
REFLECTOR_REPORT_INTERVAL = 1.0     # Report reflector data every 1 second
MAX_REFLECTOR_HISTORY = 500         # Keep max 500 speed measurements
REFLECTOR_TIMEOUT = 30.0            # Consider system inactive after 30s

# DUAL SENSOR Constants
TEMP_DIFF_WARNING = 5.0  # Warn if sensors differ by more than 5°C
TEMP_SENSOR_TIMEOUT = 10.0  # Consider sensor failed if no updates for 10s

class DualTempReflectorArduinoController:
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
        self.reflector_stats_thread = None  # NEW: Reflector statistics thread
        
        # DUAL SENSOR + REFLECTOR Arduino stream parsing - ENHANCED
        self.stream_buffer = ""
        self.temp1_pattern = re.compile(r'\[TEMP1:([\d.-]+)\]')
        self.temp2_pattern = re.compile(r'\[TEMP2:([\d.-]+)\]')
        self.max_temp_pattern = re.compile(r'\[MAX:([\d.-]+)\]')
        self.reflector_pattern = re.compile(r'\[REFLECTOR:([\d]+)\]')  # NEW
        self.dual_temp_pattern = re.compile(r'DUAL_TEMP \[TEMP1:([\d.-]+)\] \[TEMP2:([\d.-]+)\] \[MAX:([\d.-]+)\]')
        self.heartbeat_pattern = re.compile(r'HEARTBEAT:(\d+),(\d),(\d),(\d),([\d.-]+),(\d),(\d)')
        self.reflector_status_pattern = re.compile(r'REFLECTOR_STATUS \[COUNT:([\d]+)\] \[VOLTAGE:([\d.-]+)V\] \[STATE:(\w+)\] \[AVG_SPEED:([\d.-]+)rpm\] \[INST_SPEED:([\d.-]+)rpm\] \[READ_FREQ:([\d.-]+)Hz\]')  # NEW
        self.reflector_detected_pattern = re.compile(r'REFLECTOR_DETECTED:([\d]+) \[VOLTAGE:([\d.-]+)V\] \[SPEED:([\d.-]+)rpm\]')  # NEW
        self.temp_alarm_pattern = re.compile(r'TEMP_ALARM:([\d.-]+)')
        self.temp_safe_pattern = re.compile(r'TEMP_SAFE:([\d.-]+)')
        
        # Performance tracking - DUAL SENSOR + REFLECTOR
        self.temp_updates_count = 0
        self.reflector_updates_count = 0  # NEW
        self.last_stats_time = time.time()
        self.sensor_health_stats = {
            'sensor1_updates': 0,
            'sensor2_updates': 0,
            'dual_updates': 0,
            'reflector_updates': 0,  # NEW
            'sensor1_last_seen': datetime.now(),
            'sensor2_last_seen': datetime.now(),
            'reflector_last_seen': datetime.now()  # NEW
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
                self._start_reflector_stats_monitor()  # NEW
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
                    logger.info("Arduino connection successful - DUAL TEMPERATURE + REFLECTOR safety system active")
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
                        
                        if any(keyword in response.upper() for keyword in ["PONG", "ACK", "DUAL-TEMP", "REFLECTOR", "READY"]):
                            logger.info(f"Arduino responded: {response.strip()}")
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
    
    def _start_continuous_reader(self):
        """DUAL SENSOR + REFLECTOR: Ultra-fast continuous Arduino reading"""
        if self.continuous_reader_thread and self.continuous_reader_thread.is_alive():
            return
        
        self.continuous_reader_thread = threading.Thread(target=self._continuous_reader, daemon=True, name="DualTempReflectorReader")
        self.continuous_reader_thread.start()
        logger.info("DUAL TEMPERATURE + REFLECTOR continuous reader started (25ms intervals)")
    
    def _start_temp_stats_monitor(self):
        """Temperature + Reflector update frequency monitor"""
        if self.temp_stats_thread and self.temp_stats_thread.is_alive():
            return
        
        self.temp_stats_thread = threading.Thread(target=self._temp_stats_monitor, daemon=True, name="DualTempReflectorStats")
        self.temp_stats_thread.start()
        logger.info("DUAL temperature + reflector statistics monitor started")
    
    def _start_sensor_health_monitor(self):
        """Monitor individual sensor + reflector health"""
        if self.sensor_health_thread and self.sensor_health_thread.is_alive():
            return
        
        self.sensor_health_thread = threading.Thread(target=self._sensor_health_monitor, daemon=True, name="SensorReflectorHealth")
        self.sensor_health_thread.start()
        logger.info("Sensor + reflector health monitor started")
    
    def _start_reflector_stats_monitor(self):
        """NEW: Monitor reflector statistics and trends"""
        if self.reflector_stats_thread and self.reflector_stats_thread.is_alive():
            return
        
        self.reflector_stats_thread = threading.Thread(target=self._reflector_stats_monitor, daemon=True, name="ReflectorStats")
        self.reflector_stats_thread.start()
        logger.info("Reflector statistics monitor started")
    
    def _reflector_stats_monitor(self):
        """NEW: Monitor reflector performance and calculate statistics"""
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
        """Monitor individual sensor + reflector health and connection status"""
        while not shutdown_event.is_set():
            try:
                current_time = datetime.now()
                
                with state_lock:
                    # Check sensor 1 health
                    sensor1_age = (current_time - self.sensor_health_stats['sensor1_last_seen']).total_seconds()
                    if sensor1_age > TEMP_SENSOR_TIMEOUT and temperature_data['sensor1_connected']:
                        temperature_data['sensor1_connected'] = False
                        temperature_data['sensor_failure_count'] += 1
                        logger.warning(f"Sensor 1 (Pin 8) appears disconnected - no data for {sensor1_age:.1f}s")
                    elif sensor1_age <= TEMP_SENSOR_TIMEOUT and not temperature_data['sensor1_connected']:
                        temperature_data['sensor1_connected'] = True
                        logger.info("Sensor 1 (Pin 8) reconnected")
                    
                    # Check sensor 2 health
                    sensor2_age = (current_time - self.sensor_health_stats['sensor2_last_seen']).total_seconds()
                    if sensor2_age > TEMP_SENSOR_TIMEOUT and temperature_data['sensor2_connected']:
                        temperature_data['sensor2_connected'] = False
                        temperature_data['sensor_failure_count'] += 1
                        logger.warning(f"Sensor 2 (Pin 13) appears disconnected - no data for {sensor2_age:.1f}s")
                    elif sensor2_age <= TEMP_SENSOR_TIMEOUT and not temperature_data['sensor2_connected']:
                        temperature_data['sensor2_connected'] = True
                        logger.info("Sensor 2 (Pin 13) reconnected")
                    
                    # NEW: Check reflector system health
                    reflector_age = (current_time - self.sensor_health_stats['reflector_last_seen']).total_seconds()
                    if reflector_age > REFLECTOR_TIMEOUT and reflector_data['system_active']:
                        reflector_data['system_active'] = False
                        system_state['reflector_system_enabled'] = False
                        logger.warning(f"Reflector system appears inactive - no data for {reflector_age:.1f}s")
                    elif reflector_age <= REFLECTOR_TIMEOUT and not reflector_data['system_active']:
                        reflector_data['system_active'] = True
                        system_state['reflector_system_enabled'] = True
                        logger.info("Reflector system reactivated")
                    
                    # Check temperature difference between sensors
                    if temperature_data['sensor1_connected'] and temperature_data['sensor2_connected']:
                        temp_diff = abs(temperature_data['sensor1_temp'] - temperature_data['sensor2_temp'])
                        if temp_diff > TEMP_DIFF_WARNING:
                            logger.warning(f"Large temperature difference: S1={temperature_data['sensor1_temp']:.1f}°C, S2={temperature_data['sensor2_temp']:.1f}°C (Diff: {temp_diff:.1f}°C)")
                    
                    # Emergency if both sensors fail
                    if not temperature_data['sensor1_connected'] and not temperature_data['sensor2_connected']:
                        if not system_state['temperature_emergency']:
                            logger.error("EMERGENCY: Both temperature sensors failed!")
                            system_state['temperature_emergency'] = True
                
                time.sleep(5)  # Check every 5 seconds
                
            except Exception as e:
                logger.error(f"Sensor + reflector health monitor error: {e}")
                time.sleep(5)
    
    def _temp_stats_monitor(self):
        """Monitor temperature + reflector update frequency"""
        while not shutdown_event.is_set():
            try:
                time.sleep(1.0)
                
                current_time = time.time()
                elapsed = current_time - self.last_stats_time
                
                if elapsed >= 1.0:
                    temp_updates_per_second = self.temp_updates_count / elapsed
                    reflector_updates_per_second = self.reflector_updates_count / elapsed  # NEW
                    
                    with state_lock:
                        temperature_data['update_frequency'] = round(temp_updates_per_second, 2)
                        reflector_data['read_frequency'] = round(reflector_updates_per_second, 2)  # NEW
                    
                    if temp_updates_per_second > 0:
                        logger.debug(f"Dual temperature updates: {temp_updates_per_second:.2f} Hz")
                    else:
                        logger.warning("No dual temperature updates received!")
                    
                    # NEW: Log reflector updates
                    if reflector_updates_per_second > 0:
                        logger.debug(f"Reflector updates: {reflector_updates_per_second:.2f} Hz")
                    
                    # Reset counters
                    self.temp_updates_count = 0
                    self.reflector_updates_count = 0  # NEW
                    self.last_stats_time = current_time
                
            except Exception as e:
                logger.error(f"Dual temperature + reflector stats monitor error: {e}")
                time.sleep(5)
    
    def _continuous_reader(self):
        """DUAL SENSOR + REFLECTOR: Ultra-fast Arduino stream reader"""
        logger.info("DUAL TEMPERATURE + REFLECTOR continuous reader started")
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
                                self._parse_dual_temp_reflector_line(line)
                    
                    except Exception as e:
                        logger.debug(f"Dual temp + reflector read error: {e}")
                
                time.sleep(0.025)  # 25ms polling (faster for reflector)
                
            except Exception as e:
                logger.error(f"Dual temperature + reflector reader error: {e}")
                time.sleep(1)
        
        logger.info("DUAL TEMPERATURE + REFLECTOR reader stopped")
    
    def _parse_dual_temp_reflector_line(self, line):
        """ENHANCED: Parse dual temperature + reflector Arduino lines"""
        try:
            current_time = datetime.now()
            
            # NEW: 1. REFLECTOR_DETECTED format: REFLECTOR_DETECTED:123 [VOLTAGE:4.32V] [SPEED:45.2rpm]
            reflector_detected_match = self.reflector_detected_pattern.search(line)
            if reflector_detected_match:
                count, voltage, speed = reflector_detected_match.groups()
                self._update_reflector_detection(int(count), float(voltage), float(speed))
                self.reflector_updates_count += 1
                return
            
            # NEW: 2. REFLECTOR_STATUS format: REFLECTOR_STATUS [COUNT:123] [VOLTAGE:4.32V] [STATE:DETECTED] [AVG_SPEED:45.2rpm] [INST_SPEED:50.1rpm] [read_FREQ:200.0Hz]
            reflector_status_match = self.reflector_status_pattern.search(line)
            if reflector_status_match:
                count, voltage, state, avg_speed, inst_speed, read_freq = reflector_status_match.groups()
                self._update_reflector_status(int(count), float(voltage), state == "DETECTED", 
                                           float(avg_speed), float(inst_speed), float(read_freq))
                self.reflector_updates_count += 1
                return
            
            # 3. DUAL_TEMP format: DUAL_TEMP [TEMP1:33.45] [TEMP2:34.12] [MAX:34.12]
            dual_match = self.dual_temp_pattern.search(line)
            if dual_match:
                temp1, temp2, max_temp = dual_match.groups()
                self._update_dual_temperatures(float(temp1), float(temp2), float(max_temp))
                self.temp_updates_count += 1
                return
            
            # 4. Individual temperature + reflector extractions from ACK messages
            temp1_match = self.temp1_pattern.search(line)
            temp2_match = self.temp2_pattern.search(line)
            max_match = self.max_temp_pattern.search(line)
            reflector_match = self.reflector_pattern.search(line)  # NEW
            
            if temp1_match and temp2_match and max_match:
                temp1, temp2, max_temp = float(temp1_match.group(1)), float(temp2_match.group(1)), float(max_match.group(1))
                self._update_dual_temperatures(temp1, temp2, max_temp)
                self.temp_updates_count += 1
                
                # NEW: Extract reflector count if present
                if reflector_match:
                    reflector_count = int(reflector_match.group(1))
                    self._update_reflector_count(reflector_count)
                    self.reflector_updates_count += 1
                
                return
            
            # 5. HEARTBEAT with dual temperature + reflector
            # HB_DUAL [TEMP1:33.45] [TEMP2:34.12] [MAX:34.12] [REFLECTOR:123] [REF_SPEED:45.2]
            if "HB_DUAL" in line:
                temp1_match = self.temp1_pattern.search(line)
                temp2_match = self.temp2_pattern.search(line)
                max_match = self.max_temp_pattern.search(line)
                reflector_match = self.reflector_pattern.search(line)
                ref_speed_match = re.search(r'\[REF_SPEED:([\d.-]+)\]', line)  # NEW
                
                if temp1_match and temp2_match and max_match:
                    temp1, temp2, max_temp = float(temp1_match.group(1)), float(temp2_match.group(1)), float(max_match.group(1))
                    self._update_dual_temperatures(temp1, temp2, max_temp)
                    self.temp_updates_count += 1
                    
                    # NEW: Update reflector data
                    if reflector_match:
                        reflector_count = int(reflector_match.group(1))
                        self._update_reflector_count(reflector_count)
                        
                    if ref_speed_match:
                        ref_speed = float(ref_speed_match.group(1))
                        with state_lock:
                            reflector_data['average_speed'] = ref_speed
                        
                        self.reflector_updates_count += 1
                
                return
            
            # 6. Standard HEARTBEAT format
            heartbeat_match = self.heartbeat_pattern.search(line)
            if heartbeat_match:
                uptime, armed, brake_active, relay_brake_active, temp, temp_alarm, motor_count = heartbeat_match.groups()
                
                # Update system state
                with state_lock:
                    system_state['armed'] = bool(int(armed))
                    system_state['brake_active'] = bool(int(brake_active))
                    system_state['relay_brake_active'] = bool(int(relay_brake_active))
                    
                    # Update max temp from heartbeat
                    max_temp = float(temp)
                    temperature_data['current_temp'] = max_temp
                    temperature_data['last_temp_update'] = current_time
                    
                    # Update alarm status
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
                
                logger.debug(f"Heartbeat: MaxTemp={max_temp}°C, Alarm={temp_alarm_active}")
                return
            
            # 7. Temperature alarm messages with reflector count
            if "TEMP_ALARM:" in line:
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
                    
                    # NEW: Extract reflector count from alarm message
                    reflector_match = self.reflector_pattern.search(line)
                    if reflector_match:
                        reflector_count = int(reflector_match.group(1))
                        self._update_reflector_count(reflector_count)
                    
                    logger.warning(f"TEMP_ALARM detected! Max Temperature: {temp_value}°C, Reflector count: {reflector_data['count']}")
                except ValueError as e:
                    logger.debug(f"Could not parse TEMP_ALARM value: {e}")
                return
            
            # 8. Temperature safe messages with reflector count
            if "TEMP_SAFE:" in line:
                try:
                    temp_str = line.split("TEMP_SAFE:")[1].strip()
                    temp_value = float(temp_str.split()[0])
                    
                    with state_lock:
                        temperature_data['current_temp'] = temp_value
                        temperature_data['temp_alarm'] = False
                        temperature_data['buzzer_active'] = False
                        system_state['temperature_emergency'] = False
                        temperature_data['last_temp_update'] = current_time
                    
                    # NEW: Extract reflector count from safe message
                    reflector_match = self.reflector_pattern.search(line)
                    if reflector_match:
                        reflector_count = int(reflector_match.group(1))
                        self._update_reflector_count(reflector_count)
                    
                    logger.info(f"TEMP_SAFE detected! Max Temperature: {temp_value}°C, Reflector count: {reflector_data['count']}")
                except ValueError as e:
                    logger.debug(f"Could not parse TEMP_SAFE value: {e}")
                return
            
            # 9. Sensor connection warnings
            if "WARNING:Sensor1_disconnected" in line:
                with state_lock:
                    temperature_data['sensor1_connected'] = False
                    temperature_data['sensor_failure_count'] += 1
                logger.warning("Sensor 1 (Pin 8) disconnected!")
                return
            
            if "WARNING:Sensor2_disconnected" in line:
                with state_lock:
                    temperature_data['sensor2_connected'] = False
                    temperature_data['sensor_failure_count'] += 1
                logger.warning("Sensor 2 (Pin 13) disconnected!")
                return
            
            # 10. Emergency stop messages with reflector final count
            if "EMERGENCY_STOP" in line.upper():
                # NEW: Extract final reflector count
                if "REFLECTOR_FINAL:" in line:
                    final_match = re.search(r'REFLECTOR_FINAL:([\d]+)', line)
                    if final_match:
                        final_count = int(final_match.group(1))
                        self._update_reflector_count(final_count)
                        logger.warning(f"Emergency stop - Final reflector count: {final_count}")
                
                logger.warning(f"Emergency stop detected: {line}")
                return
            
            # 11. Other system messages - debug log only
            if line and not line.startswith("ACK:") and not "PONG" in line:
                logger.debug(f"Arduino line: {line}")
                
        except Exception as e:
            logger.error(f"Dual temp + reflector line parsing error for '{line}': {e}")
    
    def _update_reflector_detection(self, count, voltage, speed):
        """NEW: Update reflector data when detection occurs"""
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
        """NEW: Update comprehensive reflector status"""
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
        """NEW: Simple reflector count update"""
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
    
    def _update_dual_temperatures(self, temp1, temp2, max_temp):
        """Update dual temperature data with enhanced tracking"""
        try:
            current_time = datetime.now()
            
            with state_lock:
                # Update individual sensor temperatures
                old_temp1 = temperature_data['sensor1_temp']
                old_temp2 = temperature_data['sensor2_temp']
                old_max = temperature_data['current_temp']
                
                temperature_data['sensor1_temp'] = temp1
                temperature_data['sensor2_temp'] = temp2
                temperature_data['current_temp'] = max_temp
                temperature_data['last_temp_update'] = current_time
                
                # Update individual max temperatures
                if temp1 > temperature_data['max_temp_sensor1']:
                    temperature_data['max_temp_sensor1'] = temp1
                if temp2 > temperature_data['max_temp_sensor2']:
                    temperature_data['max_temp_sensor2'] = temp2
                
                # Update overall max temperature
                if max_temp > temperature_data['max_temp_reached']:
                    temperature_data['max_temp_reached'] = max_temp
                
                # Update sensor health tracking
                self.sensor_health_stats['sensor1_last_seen'] = current_time
                self.sensor_health_stats['sensor2_last_seen'] = current_time
                self.sensor_health_stats['sensor1_updates'] += 1
                self.sensor_health_stats['sensor2_updates'] += 1
                self.sensor_health_stats['dual_updates'] += 1
                
                # Ensure sensors are marked as connected if we're getting data
                temperature_data['sensor1_connected'] = True
                temperature_data['sensor2_connected'] = True
                
                # Add to temperature history (limited frequency)
                if len(temperature_data['temp_history']) == 0 or \
                   (current_time - datetime.fromisoformat(temperature_data['temp_history'][-1]['timestamp'])).total_seconds() >= 0.5:
                    temperature_data['temp_history'].append({
                        'timestamp': current_time.isoformat(),
                        'sensor1_temp': temp1,
                        'sensor2_temp': temp2,
                        'max_temp': max_temp
                    })
                    
                    # Keep history limited
                    if len(temperature_data['temp_history']) > MAX_TEMP_HISTORY:
                        temperature_data['temp_history'] = temperature_data['temp_history'][-MAX_TEMP_HISTORY:]
                
                # Log significant changes
                if abs(max_temp - old_max) > 0.5:
                    logger.info(f"Dual Temperature Update: S1={temp1:.1f}°C, S2={temp2:.1f}°C, Max={max_temp:.1f}°C")
                    
                # Check for large sensor differences
                temp_diff = abs(temp1 - temp2)
                if temp_diff > TEMP_DIFF_WARNING:
                    logger.warning(f"Large sensor difference: S1={temp1:.1f}°C, S2={temp2:.1f}°C (Diff: {temp_diff:.1f}°C)")
                
        except Exception as e:
            logger.error(f"Dual temperature update error: {e}")
    
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
                    time.sleep(0.05)
                    
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
                    if time.time() - self.last_command_time > 60:
                        success, _ = self.send_command_sync("PING", timeout=1.0)
                        if not success:
                            logger.warning("Heartbeat failed - connection may be lost")
                            self.is_connected = False
                            system_state['connected'] = False
                            system_state['reflector_system_enabled'] = False
                else:
                    # Try to reconnect
                    logger.info("Attempting automatic reconnection...")
                    if self.connect():
                        logger.info("Automatic reconnection successful")
                        # Restart monitoring threads if needed
                        self._restart_monitoring_threads()
                    else:
                        time.sleep(5)
                
                time.sleep(10)
                
            except Exception as e:
                logger.error(f"Connection monitor error: {e}")
                time.sleep(5)
        
        logger.info("Connection monitor thread stopped")
    
    def _restart_monitoring_threads(self):
        """Restart monitoring threads after reconnection"""
        if not self.continuous_reader_thread or not self.continuous_reader_thread.is_alive():
            self._start_continuous_reader()
        if not self.temp_stats_thread or not self.temp_stats_thread.is_alive():
            self._start_temp_stats_monitor()
        if not self.sensor_health_thread or not self.sensor_health_thread.is_alive():
            self._start_sensor_health_monitor()
        if not self.reflector_stats_thread or not self.reflector_stats_thread.is_alive():
            self._start_reflector_stats_monitor()
    
    def send_command_sync(self, command, timeout=3.0):
        """Send command synchronously with timeout"""
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
                                                 "DUAL-TEMP", "TEMP_DUAL", "REFLECTOR_RESET", "REFLECTOR_FULL"]
                            
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
    
    def _execute_command(self, command_data):
        """Execute command from queue with retry logic"""
        if not self.is_connected or shutdown_event.is_set():
            return
        
        command = command_data['command']
        attempts = command_data.get('attempts', 0)
        max_attempts = 2
        
        try:
            success, response = self.send_command_sync(command, timeout=1.5)
            
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
            time.sleep(1)
            
            self.reconnect_attempts = 0
            
            new_port = self.find_arduino_port()
            if new_port:
                self.port = new_port
                logger.info(f"Using port for reconnection: {self.port}")
            
            success = self.connect()
            
            if success:
                # Restart all monitoring threads
                self._restart_monitoring_threads()
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
                (self.reflector_stats_thread, "ReflectorStatsMonitor")
            ]
            
            for thread, name in threads:
                if thread and thread.is_alive():
                    thread.join(timeout=1.0)
        
        logger.info("Arduino disconnected successfully")

# Initialize DUAL TEMPERATURE + REFLECTOR Arduino controller
logger.info("Initializing DUAL TEMPERATURE + REFLECTOR Arduino controller...")
try:
    arduino_controller = DualTempReflectorArduinoController()
except Exception as e:
    logger.error(f"Failed to initialize Arduino controller: {e}")
    arduino_controller = None

# API Routes - DUAL TEMPERATURE + REFLECTOR ENHANCED

@app.route('/api/status', methods=['GET'])
def get_status():
    """Get comprehensive system status including DUAL temperature + reflector data"""
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
                    'dual_sensor_mode': system_state['dual_sensor_mode']
                },
                'reflector': {  # NEW: Complete reflector system data
                    'count': reflector_data['count'],
                    'voltage': reflector_data['voltage'],
                    'state': reflector_data['state'],
                    'average_speed': reflector_data['average_speed'],
                    'instant_speed': reflector_data['instant_speed'],
                    'last_update': reflector_data['last_update'].isoformat(),
                    'system_active': reflector_data['system_active'],
                    'detections': reflector_data['detections'],
                    'read_frequency': reflector_data['read_frequency'],
                    'calibration': reflector_data['calibration_data'],
                    'performance': reflector_data['performance'],
                    'statistics': {
                        'session_count': reflector_data['statistics']['session_count'],
                        'daily_count': reflector_data['statistics']['daily_count'],
                        'total_count': reflector_data['statistics']['total_count'],
                        'session_start': reflector_data['statistics']['session_start'].isoformat(),
                        'daily_start': reflector_data['statistics']['daily_start'].isoformat()
                    }
                },
                'stats': {
                    'commands': system_state['commands'],
                    'errors': system_state['errors'],
                    'uptime_seconds': int(uptime_seconds),
                    'last_response': system_state['last_response'].isoformat() if system_state['last_response'] else None,
                    'reconnect_attempts': arduino_controller.reconnect_attempts if arduino_controller else 0,
                    'reflector_system_enabled': system_state['reflector_system_enabled']
                },
                'port_info': {
                    'port': arduino_controller.port if arduino_controller else None,
                    'baudrate': arduino_controller.baudrate if arduino_controller else None
                },
                'timestamp': datetime.now().isoformat(),
                'version': '3.6-DUAL-TEMPERATURE-REFLECTOR-COMPLETE'
            })
    except Exception as e:
        logger.error(f"Status endpoint error: {e}")
        return jsonify({'error': str(e), 'connected': False}), 500

# NEW: REFLECTOR SYSTEM API ROUTES

@app.route('/api/reflector', methods=['GET'])
def get_reflector_data():
    """Get detailed reflector system data"""
    try:
        with state_lock:
            current_time = datetime.now()
            last_update_age = (current_time - reflector_data['last_update']).total_seconds()
            
            return jsonify({
                'count': reflector_data['count'],
                'voltage': reflector_data['voltage'],
                'state': reflector_data['state'],
                'average_speed': reflector_data['average_speed'],
                'instant_speed': reflector_data['instant_speed'],
                'system_active': reflector_data['system_active'],
                'detections': reflector_data['detections'],
                'read_count': reflector_data['read_count'],
                'read_frequency': reflector_data['read_frequency'],
                'last_update': reflector_data['last_update'].isoformat(),
                'last_update_age_seconds': last_update_age,
                'calibration': reflector_data['calibration_data'],
                'performance': {
                    'total_runtime_minutes': reflector_data['performance']['total_runtime'],
                    'detection_rate_per_minute': reflector_data['performance']['detection_rate'],
                    'max_speed_recorded': reflector_data['performance']['max_speed_recorded'],
                    'speed_history_count': len(reflector_data['performance']['speed_history']),
                    'uptime_start': reflector_data['performance']['uptime_start'].isoformat()
                },
                'statistics': {
                    'session_count': reflector_data['statistics']['session_count'],
                    'daily_count': reflector_data['statistics']['daily_count'],
                    'total_count': reflector_data['statistics']['total_count'],
                    'session_duration_hours': (current_time - reflector_data['statistics']['session_start']).total_seconds() / 3600,
                    'session_start': reflector_data['statistics']['session_start'].isoformat(),
                    'daily_start': reflector_data['statistics']['daily_start'].isoformat()
                },
                'status': 'active' if reflector_data['system_active'] else 'inactive',
                'timestamp': current_time.isoformat()
            })
    except Exception as e:
        logger.error(f"Reflector data endpoint error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/reflector/reset', methods=['POST'])
def reset_reflector_counter():
    """Reset reflector counter"""
    if not arduino_controller or not arduino_controller.is_connected:
        return jsonify({
            'status': 'error',
            'message': 'Arduino not connected'
        }), 503
    
    try:
        success, response = arduino_controller.send_command_sync("REFLECTOR_RESET", timeout=3.0)
        
        if success and "REFLECTOR_RESET:SUCCESS" in response:
            with state_lock:
                reflector_data['count'] = 0
                reflector_data['detections'] = 0
                reflector_data['statistics']['session_count'] = 0
                reflector_data['statistics']['session_start'] = datetime.now()
                reflector_data['performance']['uptime_start'] = datetime.now()
                reflector_data['performance']['speed_history'] = []
            
            logger.info("Reflector counter reset successfully")
            return jsonify({
                'status': 'success',
                'message': 'Reflector counter reset successfully',
                'arduino_response': response,
                'reset_time': datetime.now().isoformat()
            })
        else:
            return jsonify({
                'status': 'error',
                'message': f'Reset failed: {response}'
            }), 500
            
    except Exception as e:
        logger.error(f"Reflector reset error: {e}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@app.route('/api/reflector/calibrate', methods=['POST'])
def calibrate_reflector_sensor():
    """Calibrate reflector sensor"""
    if not arduino_controller or not arduino_controller.is_connected:
        return jsonify({
            'status': 'error',
            'message': 'Arduino not connected'
        }), 503
    
    try:
        success, response = arduino_controller.send_command_sync("REFLECTOR_CALIBRATE", timeout=5.0)
        
        if success and "REFLECTOR_CALIBRATION:" in response:
            # Parse calibration data
            try:
                cal_data = {}
                parts = response.split("REFLECTOR_CALIBRATION:")[1].split(",")
                for part in parts:
                    if ":" in part:
                        key, value = part.split(":", 1)
                        try:
                            cal_data[key] = float(value)
                        except ValueError:
                            cal_data[key] = value
                
                with state_lock:
                    reflector_data['calibration_data'].update({
                        'min_voltage': cal_data.get('MIN_V', 0.0),
                        'max_voltage': cal_data.get('MAX_V', 5.0),
                        'avg_voltage': cal_data.get('AVG_V', 5.0),
                        'detect_threshold': cal_data.get('DETECT_TH', 950) * 5.0 / 1023.0,
                        'release_threshold': cal_data.get('RELEASE_TH', 1000) * 5.0 / 1023.0,
                        'last_calibration': datetime.now().isoformat()
                    })
                
                logger.info("Reflector sensor calibrated successfully")
                return jsonify({
                    'status': 'success',
                    'message': 'Reflector sensor calibrated successfully',
                    'calibration_data': reflector_data['calibration_data'],
                    'arduino_response': response
                })
                
            except Exception as parse_error:
                logger.error(f"Calibration data parsing error: {parse_error}")
                return jsonify({
                    'status': 'partial_success',
                    'message': 'Calibration completed but data parsing failed',
                    'arduino_response': response
                })
        else:
            return jsonify({
                'status': 'error',
                'message': f'Calibration failed: {response}'
            }), 500
            
    except Exception as e:
        logger.error(f"Reflector calibration error: {e}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@app.route('/api/reflector/realtime', methods=['GET'])
def get_realtime_reflector():
    """Ultra-fast reflector endpoint for real-time updates"""
    try:
        with state_lock:
            current_time = datetime.now()
            last_update_age = (current_time - reflector_data['last_update']).total_seconds()
            
            return jsonify({
                'count': reflector_data['count'],
                'voltage': reflector_data['voltage'],
                'state': reflector_data['state'],
                'average_speed': reflector_data['average_speed'],
                'instant_speed': reflector_data['instant_speed'],
                'read_frequency': reflector_data['read_frequency'],
                'system_active': reflector_data['system_active'],
                'last_update': reflector_data['last_update'].isoformat(),
                'age_seconds': last_update_age,
                'timestamp': current_time.isoformat(),
                'status': 'real-time' if last_update_age < 2.0 else 'delayed'
            })
    except Exception as e:
        logger.error(f"Realtime reflector error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/reflector/statistics', methods=['GET'])
def get_reflector_statistics():
    """Get detailed reflector statistics and trends"""
    try:
        with state_lock:
            current_time = datetime.now()
            session_duration = (current_time - reflector_data['statistics']['session_start']).total_seconds()
            daily_duration = (current_time - reflector_data['statistics']['daily_start']).total_seconds()
            
            # Calculate trends
            speed_history = reflector_data['performance']['speed_history']
            recent_speeds = [entry['average_speed'] for entry in speed_history[-10:] if entry['average_speed'] > 0]
            avg_recent_speed = sum(recent_speeds) / len(recent_speeds) if recent_speeds else 0
            
            return jsonify({
                'session': {
                    'count': reflector_data['statistics']['session_count'],
                    'duration_hours': session_duration / 3600,
                    'average_rate': reflector_data['statistics']['session_count'] / (session_duration / 60) if session_duration > 0 else 0,
                    'start_time': reflector_data['statistics']['session_start'].isoformat()
                },
                'daily': {
                    'count': reflector_data['statistics']['daily_count'],
                    'duration_hours': daily_duration / 3600,
                    'average_rate': reflector_data['statistics']['daily_count'] / (daily_duration / 60) if daily_duration > 0 else 0,
                    'start_time': reflector_data['statistics']['daily_start'].isoformat()
                },
                'performance': {
                    'total_detections': reflector_data['detections'],
                    'total_reads': reflector_data['read_count'],
                    'current_read_frequency': reflector_data['read_frequency'],
                    'max_speed_recorded': reflector_data['performance']['max_speed_recorded'],
                    'recent_average_speed': avg_recent_speed,
                    'detection_efficiency': (reflector_data['detections'] / reflector_data['read_count']) * 100 if reflector_data['read_count'] > 0 else 0
                },
                'trends': {
                    'speed_history_count': len(speed_history),
                    'recent_speeds': recent_speeds[-5:] if recent_speeds else [],
                    'speed_trend': 'increasing' if len(recent_speeds) >= 2 and recent_speeds[-1] > recent_speeds[-2] else 'stable'
                },
                'system_health': {
                    'active': reflector_data['system_active'],
                    'last_update_age': (current_time - reflector_data['last_update']).total_seconds(),
                    'calibration_status': 'calibrated' if reflector_data['calibration_data']['last_calibration'] else 'not_calibrated'
                },
                'timestamp': current_time.isoformat()
            })
    except Exception as e:
        logger.error(f"Reflector statistics error: {e}")
        return jsonify({'error': str(e)}), 500

# ENHANCED EXISTING ROUTES WITH REFLECTOR DATA

@app.route('/api/temperature', methods=['GET'])
def get_temperature_data():
    """Get detailed DUAL temperature data and history with reflector correlation"""
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
                    'primary_sensor': 8,  # Pin number
                    'secondary_sensor': 13  # Pin number
                },
                'safety_status': {
                    'emergency_active': system_state['temperature_emergency'],
                    'can_arm_system': not temperature_data['temp_alarm'] and temperature_data['current_temp'] < TEMP_ALARM_THRESHOLD - 5,
                    'safe_to_operate': temperature_data['current_temp'] < TEMP_WARNING_THRESHOLD,
                    'sensor_redundancy_ok': temperature_data['sensor1_connected'] or temperature_data['sensor2_connected'],
                    'large_sensor_diff': temp_difference > TEMP_DIFF_WARNING
                },
                'reflector_correlation': {  # NEW: Correlate temperature with reflector data
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
                    'reflector_stats_alive': arduino_controller.reflector_stats_thread.is_alive() if arduino_controller and arduino_controller.reflector_stats_thread else False,
                    'optimization_level': 'dual-sensor-reflector-ultra-fast'
                }
            })
    except Exception as e:
        logger.error(f"Temperature endpoint error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/temperature/realtime', methods=['GET'])
def get_realtime_temperature():
    """Ultra-fast DUAL temperature endpoint with reflector data"""
    try:
        with state_lock:
            current_time = datetime.now()
            last_update_age = (current_time - temperature_data['last_temp_update']).total_seconds()
            temp_diff = abs(temperature_data['sensor1_temp'] - temperature_data['sensor2_temp']) if \
                       temperature_data['sensor1_connected'] and temperature_data['sensor2_connected'] else 0
            
            return jsonify({
                'temperature': temperature_data['current_temp'],
                'sensor1_temp': temperature_data['sensor1_temp'],
                'sensor2_temp': temperature_data['sensor2_temp'],
                'temp_difference': temp_diff,
                'alarm': temperature_data['temp_alarm'],
                'buzzer': temperature_data['buzzer_active'],
                'sensor1_connected': temperature_data['sensor1_connected'],
                'sensor2_connected': temperature_data['sensor2_connected'],
                'last_update': temperature_data['last_temp_update'].isoformat(),
                'age_seconds': last_update_age,
                'frequency_hz': temperature_data['update_frequency'],
                'reflector_count': reflector_data['count'],  # NEW: Include reflector data
                'reflector_speed': reflector_data['average_speed'],  # NEW: Include speed
                'reflector_voltage': reflector_data['voltage'],  # NEW: Include voltage
                'timestamp': current_time.isoformat(),
                'status': 'real-time' if last_update_age < 1.0 else 'delayed',
                'dual_sensor_mode': True,
                'reflector_system_active': reflector_data['system_active']  # NEW
            })
    except Exception as e:
        logger.error(f"Realtime temperature + reflector error: {e}")
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
                'arduino_response': response,
                'dual_temps': {
                    'sensor1': temperature_data['sensor1_temp'],
                    'sensor2': temperature_data['sensor2_temp'],
                    'max': temperature_data['current_temp']
                },
                'reflector_count': reflector_data['count']
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

# ENHANCED SYSTEM CONTROL ROUTES WITH REFLECTOR LOGGING

@app.route('/api/system/arm', methods=['POST'])
def arm_system():
    """Arm system - DUAL TEMPERATURE + REFLECTOR safety checks"""
    if not arduino_controller or not arduino_controller.is_connected:
        return jsonify({'status': 'error', 'message': 'Arduino not connected'}), 503
    
    # DUAL temperature safety checks
    if temperature_data['temp_alarm']:
        return jsonify({
            'status': 'error',
            'message': 'Cannot arm - temperature alarm active',
            'dual_temperatures': {
                'sensor1_temp': temperature_data['sensor1_temp'],
                'sensor2_temp': temperature_data['sensor2_temp'],
                'max_temp': temperature_data['current_temp'],
                'alarm_active': temperature_data['temp_alarm']
            },
            'reflector_status': {
                'count': reflector_data['count'],
                'system_active': reflector_data['system_active']
            }
        }), 400
    
    # Check if at least one sensor is working
    if not temperature_data['sensor1_connected'] and not temperature_data['sensor2_connected']:
        return jsonify({
            'status': 'error',
            'message': 'Cannot arm - no temperature sensors connected',
            'sensor1_connected': temperature_data['sensor1_connected'],
            'sensor2_connected': temperature_data['sensor2_connected']
        }), 400
    
    try:
        success, response = arduino_controller.send_command_sync("ARM", timeout=3.0)
        
        if success and "ARMED" in response.upper():
            with state_lock:
                system_state['armed'] = True
            
            logger.info(f"System ARMED - Dual Temps: S1={temperature_data['sensor1_temp']}°C, S2={temperature_data['sensor2_temp']}°C, Max={temperature_data['current_temp']}°C, Reflector: {reflector_data['count']}")
            
            return jsonify({
                'status': 'armed',
                'message': 'System armed successfully',
                'dual_temperatures': {
                    'sensor1_temp': temperature_data['sensor1_temp'],
                    'sensor2_temp': temperature_data['sensor2_temp'],
                    'max_temp': temperature_data['current_temp'],
                    'sensor1_connected': temperature_data['sensor1_connected'],
                    'sensor2_connected': temperature_data['sensor2_connected']
                },
                'reflector_status': {
                    'count': reflector_data['count'],
                    'average_speed': reflector_data['average_speed'],
                    'system_active': reflector_data['system_active']
                },
                'arm_timestamp': datetime.now().isoformat()
            })
        else:
            return jsonify({'status': 'error', 'message': f'Arduino error: {response}'}), 500
            
    except Exception as e:
        logger.error(f"Arm system error: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/system/disarm', methods=['POST'])
def disarm_system():
    """Disarm the system with reflector logging"""
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
            
            logger.info("System DISARMED successfully")
            return jsonify({
                'status': 'disarmed',
                'message': 'System disarmed successfully',
                'dual_temperatures': {
                    'sensor1_temp': temperature_data['sensor1_temp'],
                    'sensor2_temp': temperature_data['sensor2_temp'],
                    'max_temp': temperature_data['current_temp']
                },
                'reflector_final_count': reflector_data['count']
            })
        else:
            return jsonify({'status': 'error', 'message': f'Arduino error: {response}'}), 500
            
    except Exception as e:
        logger.error(f"Disarm system error: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/emergency-stop', methods=['POST'])
def emergency_stop():
    """Emergency stop all systems with dual temperature + reflector logging"""
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
        
        logger.warning(f"EMERGENCY STOP ACTIVATED! Dual Temps: S1={temperature_data['sensor1_temp']}°C, S2={temperature_data['sensor2_temp']}°C, Max={temperature_data['current_temp']}°C, Reflector Final: {reflector_data['count']}")
        
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
                'temperature_alarm': temperature_data['temp_alarm']
            },
            'reflector_final_status': {
                'final_count': reflector_data['count'],
                'final_speed': reflector_data['average_speed'],
                'total_detections': reflector_data['detections'],
                'session_duration_minutes': reflector_data['performance']['total_runtime'],
                'system_was_active': reflector_data['system_active']
            },
            'arduino_response': arduino_response,
            'timestamp': datetime.now().isoformat()
        })
            
    except Exception as e:
        logger.error(f"Emergency stop error: {e}")
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
            'timestamp': datetime.now().isoformat()
        })

# MOTOR CONTROL ROUTES WITH REFLECTOR INTEGRATION (Shortened for space - same pattern as Arduino)
@app.route('/api/motor/<int:motor_num>/start', methods=['POST'])
def start_individual_motor(motor_num):
    """Start individual motor with DUAL temperature + reflector safety checks"""
    if not arduino_controller or not arduino_controller.is_connected:
        return jsonify({'status': 'error', 'message': 'Arduino not connected'}), 503
    
    # Temperature safety checks
    if temperature_data['temp_alarm']:
        return jsonify({
            'status': 'error', 
            'message': 'Cannot start motor - temperature alarm active',
            'dual_temperatures': {
                'sensor1_temp': temperature_data['sensor1_temp'],
                'sensor2_temp': temperature_data['sensor2_temp'],
                'max_temp': temperature_data['current_temp'],
                'alarm_active': temperature_data['temp_alarm']
            }
        }), 400
    
    if temperature_data['current_temp'] > TEMP_ALARM_THRESHOLD - 3:
        return jsonify({
            'status': 'error',
            'message': f'Cannot start motor - temperature too high ({temperature_data["current_temp"]:.1f}°C)',
            'dual_temperatures': {
                'sensor1_temp': temperature_data['sensor1_temp'],
                'sensor2_temp': temperature_data['sensor2_temp'],
                'max_temp': temperature_data['current_temp'],
                'threshold': TEMP_ALARM_THRESHOLD - 3
            }
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
        
        if success and "MOTOR_STARTED" in response:
            with state_lock:
                motor_states[motor_num] = True
                individual_motor_speeds[motor_num] = speed
            
            motor_type = "Thrust" if motor_num in [5, 6] else "Levitation"
            pin_mapping = {1: 2, 2: 4, 3: 5, 4: 6, 5: 3, 6: 7}
            pin_num = pin_mapping.get(motor_num, "Unknown")
            
            logger.info(f"Motor {motor_num} ({motor_type}, Pin {pin_num}) started at {speed}% - Dual Temps: S1={temperature_data['sensor1_temp']:.1f}°C, S2={temperature_data['sensor2_temp']:.1f}°C, Reflector: {reflector_data['count']}")
            return jsonify({
                'status': 'success',
                'motor': motor_num,
                'action': 'start',
                'speed': speed,
                'type': motor_type,
                'pin': pin_num,
                'message': f'Motor {motor_num} started at {speed}%',
                'dual_temperatures': {
                    'sensor1_temp': temperature_data['sensor1_temp'],
                    'sensor2_temp': temperature_data['sensor2_temp'],
                    'max_temp': temperature_data['current_temp'],
                    'sensor1_connected': temperature_data['sensor1_connected'],
                    'sensor2_connected': temperature_data['sensor2_connected']
                },
                'reflector_count': reflector_data['count'],
                'arduino_response': response
            })
        else:
            return jsonify({
                'status': 'error',
                'message': f'Motor start failed: {response}'
            }), 500
            
    except ValueError:
        return jsonify({'status': 'error', 'message': 'Invalid speed value'}), 400
    except Exception as e:
        logger.error(f"Motor {motor_num} start error: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

# Additional motor routes (stop, speed) follow same pattern with reflector logging...

@app.route('/api/ping', methods=['GET'])
def ping():
    """Ultra-fast health check with DUAL temperature + reflector info"""
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
                    'status': 'real-time' if temp_age < 1.0 else 'delayed'
                },
                'reflector_system': {  # NEW: Reflector system health
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
                    'optimization': 'dual-sensor-reflector-ultra-fast'
                },
                'system_status': {
                    'armed': system_state['armed'],
                    'temperature_emergency': system_state['temperature_emergency'],
                    'reflector_system_enabled': system_state['reflector_system_enabled']
                },
                'version': '3.6-DUAL-TEMPERATURE-REFLECTOR',
                'port': arduino_controller.port if arduino_controller else None
            })
        
    except Exception as e:
        logger.error(f"Ping error: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

# Error Handlers - ENHANCED WITH REFLECTOR
@app.errorhandler(404)
def not_found(error):
    return jsonify({
        'status': 'error',
        'message': 'Endpoint not found',
        'available_endpoints': [
            'GET /api/status',
            'GET /api/temperature',
            'GET /api/temperature/realtime',
            'GET /api/reflector',              # NEW
            'GET /api/reflector/realtime',     # NEW
            'GET /api/reflector/statistics',   # NEW
            'POST /api/reflector/reset',       # NEW
            'POST /api/reflector/calibrate',   # NEW
            'GET /api/ping',
            'POST /api/system/arm',
            'POST /api/system/disarm',
            'POST /api/motor/<num>/start',
            'POST /api/emergency-stop'
        ],
        'dual_sensor_features': [
            'Individual sensor temperatures',
            'Redundant safety monitoring',
            'Sensor health tracking',
            'Temperature difference warnings',
            'Automatic failover capability'
        ],
        'reflector_features': [  # NEW
            'Ultra-fast reflector counting (5ms)',
            'Real-time speed calculation',
            'Voltage monitoring',
            'Sensor calibration',
            'Performance statistics',
            'Session and daily tracking',
            'Correlation with temperature data'
        ]
    }), 404

# Background monitoring - DUAL TEMP + REFLECTOR ENHANCED
def dual_temp_reflector_background_monitor():
    """DUAL TEMPERATURE + REFLECTOR background monitoring and maintenance"""
    logger.info("DUAL TEMPERATURE + REFLECTOR background monitor started")
    
    while not shutdown_event.is_set():
        try:
            # Connection monitoring
            if arduino_controller and not arduino_controller.is_connected:
                if arduino_controller.reconnect_attempts < arduino_controller.max_attempts:
                    logger.info("Auto-reconnection attempt...")
                    if arduino_controller.reconnect():
                        logger.info("Auto-reconnection successful")
            
            # Monitoring logic (similar to before but enhanced)
            with state_lock:
                temp_age = (datetime.now() - temperature_data['last_temp_update']).total_seconds()
                reflector_age = (datetime.now() - reflector_data['last_update']).total_seconds()
                
                if temp_age > 10:
                    logger.warning(f"Dual temperature data is stale: {temp_age:.1f}s old")
                    if arduino_controller and arduino_controller.is_connected:
                        arduino_controller._restart_monitoring_threads()
                
                if reflector_age > REFLECTOR_TIMEOUT and reflector_data['system_active']:
                    logger.warning(f"Reflector system inactive: {reflector_age:.1f}s since last update")
                    reflector_data['system_active'] = False
                    system_state['reflector_system_enabled'] = False
            
            shutdown_event.wait(5)
            
        except Exception as e:
            logger.error(f"Dual temperature + reflector background monitor error: {e}")
            shutdown_event.wait(5)
    
    logger.info("DUAL TEMPERATURE + REFLECTOR background monitor stopped")

# Start background monitor
monitor_thread = threading.Thread(target=dual_temp_reflector_background_monitor, daemon=True, name="DualTempReflectorMonitor")
monitor_thread.start()

# Graceful shutdown handler
def signal_handler(sig, frame):
    """Graceful shutdown handler"""
    logger.info("Shutdown signal received...")
    
    try:
        shutdown_event.set()
        
        if arduino_controller:
            # Get final statistics before shutdown
            with state_lock:
                logger.info(f"Final Statistics - Temperature: S1={temperature_data['sensor1_temp']:.1f}°C, S2={temperature_data['sensor2_temp']:.1f}°C")
                logger.info(f"Final Statistics - Reflector: Count={reflector_data['count']}, Speed={reflector_data['average_speed']:.1f}rpm")
            
            arduino_controller.disconnect()
        
        logger.info("DUAL TEMPERATURE + REFLECTOR backend shutdown completed")
        
    except Exception as e:
        logger.error(f"Shutdown error: {e}")
    finally:
        sys.exit(0)

# Register signal handlers
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

if __name__ == '__main__':
    logger.info("=" * 80)
    logger.info("SpectraLoop Backend DUAL TEMPERATURE + REFLECTOR COUNTER v3.6")
    logger.info("=" * 80)
    
    try:
        if arduino_controller and arduino_controller.is_connected:
            logger.info(f"Arduino Status: Connected to {arduino_controller.port}")
            logger.info("DUAL TEMPERATURE + REFLECTOR FEATURES:")
            logger.info("   🌡️ Primary sensor (Pin 8) + Secondary sensor (Pin 13)")
            logger.info("   📏 Omron reflector counter (Pin A0) + Status LED (Pin 12)")
            logger.info("   🛡️ Redundant safety monitoring")
            logger.info("   ⚡ 100ms temperature + 5ms reflector readings")
            logger.info("   📊 Individual sensor + reflector health tracking")
            logger.info("   🔄 Automatic sensor + reflector failover capability")
            logger.info("   ⚠️ Large temperature difference + reflector anomaly warnings")
            logger.info("   📈 Real-time performance monitoring for all systems")
            logger.info("   🚨 Enhanced safety with worst-case temperature + reflector correlation")
            logger.info("   📋 Comprehensive statistics and trending")
            logger.info("   🎯 Ultra-precision reflector counting with calibration")
        else:
            logger.warning("Arduino Status: Not Connected")
        
        logger.info("=" * 80)
        logger.info("Starting DUAL TEMPERATURE + REFLECTOR Flask server...")
        
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
        logger.info("DUAL TEMPERATURE + REFLECTOR server shutdown complete")