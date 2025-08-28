#!/usr/bin/env python3
"""
SpectraLoop Motor Control Backend - DUAL TEMPERATURE v3.5 - Complete System
Dual DS18B20 sensors + buzzer + redundant safety system
Individual + Group motor control + Dual temperature monitoring + Safety features
Motor Pin Mapping: İtki (3,7), Levitasyon (2,4,5,6)
Temperature Safety: Pin8->DS18B20#1, Pin13->DS18B20#2, Pin9->Buzzer, Pin11->RelayBrake
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
        logging.FileHandler('spectraloop_dual.log'),
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
    'max_temp_sensor1': 25.0,       # NEW: Individual max temps
    'max_temp_sensor2': 25.0,       # NEW: Individual max temps
    'alarm_start_time': None,
    'alarm_count': 0,
    'sensor1_connected': True,      # NEW: Connection status
    'sensor2_connected': True,      # NEW: Connection status
    'update_frequency': 0.0,
    'sensor_failure_count': 0       # NEW: Track sensor failures
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
    'dual_sensor_mode': True        # NEW: Flag for dual sensor operation
}

# Thread synchronization
state_lock = threading.Lock()
shutdown_event = threading.Event()

# Temperature safety constants - DUAL SENSOR
TEMP_ALARM_THRESHOLD = 55.0
TEMP_SAFE_THRESHOLD = 50.0
TEMP_WARNING_THRESHOLD = 45.0
MAX_TEMP_HISTORY = 200

# DUAL SENSOR Constants
TEMP_DIFF_WARNING = 5.0  # Warn if sensors differ by more than 5°C
TEMP_SENSOR_TIMEOUT = 10.0  # Consider sensor failed if no updates for 10s

class DualTempArduinoController:
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
        self.sensor_health_thread = None  # NEW: Monitor sensor health
        
        # DUAL SENSOR Arduino stream parsing - ENHANCED
        self.stream_buffer = ""
        self.temp1_pattern = re.compile(r'\[TEMP1:([\d.-]+)\]')
        self.temp2_pattern = re.compile(r'\[TEMP2:([\d.-]+)\]')
        self.max_temp_pattern = re.compile(r'\[MAX:([\d.-]+)\]')
        self.dual_temp_pattern = re.compile(r'DUAL_TEMP \[TEMP1:([\d.-]+)\] \[TEMP2:([\d.-]+)\] \[MAX:([\d.-]+)\]')
        self.heartbeat_pattern = re.compile(r'HEARTBEAT:(\d+),(\d),(\d),(\d),([\d.-]+),(\d),(\d)')
        self.temp_alarm_pattern = re.compile(r'TEMP_ALARM:([\d.-]+)')
        self.temp_safe_pattern = re.compile(r'TEMP_SAFE:([\d.-]+)')
        
        # Performance tracking - DUAL SENSOR
        self.temp_updates_count = 0
        self.last_stats_time = time.time()
        self.sensor_health_stats = {
            'sensor1_updates': 0,
            'sensor2_updates': 0,
            'dual_updates': 0,
            'sensor1_last_seen': datetime.now(),
            'sensor2_last_seen': datetime.now()
        }
        
        # Initialize connection safely
        try:
            if self.port:
                self.connect()
                self._start_command_processor()
                self._start_connection_monitor()
                self._start_continuous_reader()
                self._start_temp_stats_monitor()
                self._start_sensor_health_monitor()  # NEW
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
                    logger.info("Arduino connection successful - DUAL TEMPERATURE safety system active")
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
                        
                        if any(keyword in response.upper() for keyword in ["PONG", "ACK", "DUAL-TEMP", "READY"]):
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
        """DUAL SENSOR: Ultra-fast continuous Arduino reading"""
        if self.continuous_reader_thread and self.continuous_reader_thread.is_alive():
            return
        
        self.continuous_reader_thread = threading.Thread(target=self._continuous_reader, daemon=True, name="DualTempReader")
        self.continuous_reader_thread.start()
        logger.info("DUAL TEMPERATURE continuous reader started (50ms intervals)")
    
    def _start_temp_stats_monitor(self):
        """Temperature update frequency monitor - DUAL SENSOR"""
        if self.temp_stats_thread and self.temp_stats_thread.is_alive():
            return
        
        self.temp_stats_thread = threading.Thread(target=self._temp_stats_monitor, daemon=True, name="DualTempStats")
        self.temp_stats_thread.start()
        logger.info("DUAL temperature statistics monitor started")
    
    def _start_sensor_health_monitor(self):
        """NEW: Monitor individual sensor health"""
        if self.sensor_health_thread and self.sensor_health_thread.is_alive():
            return
        
        self.sensor_health_thread = threading.Thread(target=self._sensor_health_monitor, daemon=True, name="SensorHealth")
        self.sensor_health_thread.start()
        logger.info("Sensor health monitor started")
    
    def _sensor_health_monitor(self):
        """Monitor individual sensor health and connection status"""
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
                            # Could trigger emergency stop here
                
                time.sleep(5)  # Check every 5 seconds
                
            except Exception as e:
                logger.error(f"Sensor health monitor error: {e}")
                time.sleep(5)
    
    def _temp_stats_monitor(self):
        """Monitor temperature update frequency - DUAL SENSOR"""
        while not shutdown_event.is_set():
            try:
                time.sleep(1.0)
                
                current_time = time.time()
                elapsed = current_time - self.last_stats_time
                
                if elapsed >= 1.0:
                    updates_per_second = self.temp_updates_count / elapsed
                    
                    with state_lock:
                        temperature_data['update_frequency'] = round(updates_per_second, 2)
                    
                    if updates_per_second > 0:
                        logger.debug(f"Dual temperature updates: {updates_per_second:.2f} Hz")
                    else:
                        logger.warning("No dual temperature updates received!")
                    
                    # Reset counters
                    self.temp_updates_count = 0
                    self.last_stats_time = current_time
                
            except Exception as e:
                logger.error(f"Dual temperature stats monitor error: {e}")
                time.sleep(5)
    
    def _continuous_reader(self):
        """DUAL SENSOR: Ultra-fast Arduino stream reader"""
        logger.info("DUAL TEMPERATURE continuous reader started")
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
                                self._parse_dual_temp_line(line)
                    
                    except Exception as e:
                        logger.debug(f"Dual temp read error: {e}")
                
                time.sleep(0.05)  # 50ms polling
                
            except Exception as e:
                logger.error(f"Dual temperature reader error: {e}")
                time.sleep(1)
        
        logger.info("DUAL TEMPERATURE reader stopped")
    
    def _parse_dual_temp_line(self, line):
        """ENHANCED: Parse dual temperature Arduino lines"""
        try:
            current_time = datetime.now()
            
            # 1. DUAL_TEMP format: DUAL_TEMP [TEMP1:33.45] [TEMP2:34.12] [MAX:34.12]
            dual_match = self.dual_temp_pattern.search(line)
            if dual_match:
                temp1, temp2, max_temp = dual_match.groups()
                self._update_dual_temperatures(float(temp1), float(temp2), float(max_temp))
                self.temp_updates_count += 1
                return
            
            # 2. Individual temperature extractions from ACK messages
            temp1_match = self.temp1_pattern.search(line)
            temp2_match = self.temp2_pattern.search(line)
            max_match = self.max_temp_pattern.search(line)
            
            if temp1_match and temp2_match and max_match:
                temp1, temp2, max_temp = float(temp1_match.group(1)), float(temp2_match.group(1)), float(max_match.group(1))
                self._update_dual_temperatures(temp1, temp2, max_temp)
                self.temp_updates_count += 1
                return
            
            # 3. HEARTBEAT with dual temperature
            # HB_DUAL [TEMP1:33.45] [TEMP2:34.12] [MAX:34.12]
            if "HB_DUAL" in line:
                temp1_match = self.temp1_pattern.search(line)
                temp2_match = self.temp2_pattern.search(line)
                max_match = self.max_temp_pattern.search(line)
                
                if temp1_match and temp2_match and max_match:
                    temp1, temp2, max_temp = float(temp1_match.group(1)), float(temp2_match.group(1)), float(max_match.group(1))
                    self._update_dual_temperatures(temp1, temp2, max_temp)
                    self.temp_updates_count += 1
                return
            
            # 4. Standard HEARTBEAT format
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
            
            # 5. Temperature alarm messages
            if "TEMP_ALARM:" in line:
                try:
                    temp_str = line.split("TEMP_ALARM:")[1].strip()
                    # Extract temperature value (might have additional info in parentheses)
                    temp_value = float(temp_str.split()[0])
                    
                    with state_lock:
                        temperature_data['current_temp'] = max(temperature_data['current_temp'], temp_value)
                        temperature_data['temp_alarm'] = True
                        temperature_data['buzzer_active'] = True
                        temperature_data['alarm_start_time'] = current_time
                        temperature_data['alarm_count'] += 1
                        system_state['temperature_emergency'] = True
                        temperature_data['last_temp_update'] = current_time
                    
                    logger.warning(f"TEMP_ALARM detected! Max Temperature: {temp_value}°C")
                except ValueError as e:
                    logger.debug(f"Could not parse TEMP_ALARM value: {e}")
                return
            
            # 6. Temperature safe messages
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
                    
                    logger.info(f"TEMP_SAFE detected! Max Temperature: {temp_value}°C")
                except ValueError as e:
                    logger.debug(f"Could not parse TEMP_SAFE value: {e}")
                return
            
            # 7. Sensor connection warnings
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
            
            # 8. Emergency stop messages
            if "EMERGENCY_STOP" in line.upper():
                logger.warning(f"Emergency stop detected: {line}")
                return
            
            # 9. Other system messages - debug log only
            if line and not line.startswith("ACK:") and not "PONG" in line:
                logger.debug(f"Arduino line: {line}")
                
        except Exception as e:
            logger.error(f"Dual temp line parsing error for '{line}': {e}")
    
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
                else:
                    # Try to reconnect
                    logger.info("Attempting automatic reconnection...")
                    if self.connect():
                        logger.info("Automatic reconnection successful")
                        # Restart monitoring threads if needed
                        if not self.continuous_reader_thread or not self.continuous_reader_thread.is_alive():
                            self._start_continuous_reader()
                        if not self.temp_stats_thread or not self.temp_stats_thread.is_alive():
                            self._start_temp_stats_monitor()
                        if not self.sensor_health_thread or not self.sensor_health_thread.is_alive():
                            self._start_sensor_health_monitor()
                    else:
                        time.sleep(5)
                
                time.sleep(10)
                
            except Exception as e:
                logger.error(f"Connection monitor error: {e}")
                time.sleep(5)
        
        logger.info("Connection monitor thread stopped")
    
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
                            if any(keyword in response for keyword in ["MOTOR_STARTED", "MOTOR_STOPPED", "LEV_GROUP_STARTED", 
                                                                       "THR_GROUP_STARTED", "ARMED", "RELAY_BRAKE:", 
                                                                       "PONG", "ACK:", "BRAKE_", "DISARMED", "EMERGENCY_STOP",
                                                                       "DUAL-TEMP", "TEMP_DUAL"]):
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
                self._start_continuous_reader()
                self._start_temp_stats_monitor()
                self._start_sensor_health_monitor()
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
                (self.sensor_health_thread, "SensorHealthMonitor")
            ]
            
            for thread, name in threads:
                if thread and thread.is_alive():
                    thread.join(timeout=1.0)
        
        logger.info("Arduino disconnected successfully")

# Initialize DUAL TEMPERATURE Arduino controller
logger.info("Initializing DUAL TEMPERATURE Arduino controller...")
try:
    arduino_controller = DualTempArduinoController()
except Exception as e:
    logger.error(f"Failed to initialize Arduino controller: {e}")
    arduino_controller = None

# API Routes - DUAL TEMPERATURE ENHANCED

@app.route('/api/status', methods=['GET'])
def get_status():
    """Get comprehensive system status including DUAL temperature data"""
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
                    'sensor1_temp': temperature_data['sensor1_temp'],           # NEW: Individual sensor temps
                    'sensor2_temp': temperature_data['sensor2_temp'],           # NEW: Individual sensor temps
                    'current': temperature_data['current_temp'],                # Max of both sensors
                    'alarm': temperature_data['temp_alarm'],
                    'buzzer_active': temperature_data['buzzer_active'],
                    'max_reached': temperature_data['max_temp_reached'],
                    'max_sensor1': temperature_data['max_temp_sensor1'],        # NEW: Individual max temps
                    'max_sensor2': temperature_data['max_temp_sensor2'],        # NEW: Individual max temps
                    'last_update': temperature_data['last_temp_update'].isoformat(),
                    'alarm_threshold': TEMP_ALARM_THRESHOLD,
                    'safe_threshold': TEMP_SAFE_THRESHOLD,
                    'warning_threshold': TEMP_WARNING_THRESHOLD,
                    'emergency_active': system_state['temperature_emergency'],
                    'alarm_count': temperature_data['alarm_count'],
                    'history_count': len(temperature_data['temp_history']),
                    'update_frequency': temperature_data['update_frequency'],
                    'sensor1_connected': temperature_data['sensor1_connected'], # NEW: Connection status
                    'sensor2_connected': temperature_data['sensor2_connected'], # NEW: Connection status
                    'sensor_failure_count': temperature_data['sensor_failure_count'], # NEW: Failure tracking
                    'dual_sensor_mode': system_state['dual_sensor_mode']        # NEW: Operating mode
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
                'version': '3.5-DUAL-TEMPERATURE-COMPLETE'
            })
    except Exception as e:
        logger.error(f"Status endpoint error: {e}")
        return jsonify({'error': str(e), 'connected': False}), 500

@app.route('/api/temperature', methods=['GET'])
def get_temperature_data():
    """Get detailed DUAL temperature data and history"""
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
                'current_temperature': temperature_data['current_temp'],        # Max of both sensors
                'sensor1_temperature': temperature_data['sensor1_temp'],        # Individual sensor 1
                'sensor2_temperature': temperature_data['sensor2_temp'],        # Individual sensor 2
                'temperature_difference': temp_difference,                      # NEW: Difference between sensors
                'temperature_alarm': temperature_data['temp_alarm'],
                'buzzer_active': temperature_data['buzzer_active'],
                'max_temperature_reached': temperature_data['max_temp_reached'],
                'max_temperature_sensor1': temperature_data['max_temp_sensor1'], # NEW: Individual max temps
                'max_temperature_sensor2': temperature_data['max_temp_sensor2'], # NEW: Individual max temps
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
                'sensor_status': {                                              # NEW: Individual sensor status
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
                'history': temperature_data['temp_history'][-30:],              # Last 30 readings with dual data
                'timestamp': current_time.isoformat(),
                'performance': {
                    'update_frequency_hz': temperature_data['update_frequency'],
                    'last_update_ago_seconds': last_update_age,
                    'status': 'real-time' if last_update_age < 2.0 else 'delayed',
                    'continuous_reader_alive': arduino_controller.continuous_reader_thread.is_alive() if arduino_controller and arduino_controller.continuous_reader_thread else False,
                    'sensor_health_alive': arduino_controller.sensor_health_thread.is_alive() if arduino_controller and arduino_controller.sensor_health_thread else False,
                    'optimization_level': 'dual-sensor-ultra-fast'
                }
            })
    except Exception as e:
        logger.error(f"Temperature endpoint error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/temperature/realtime', methods=['GET'])
def get_realtime_temperature():
    """Ultra-fast DUAL temperature endpoint for real-time updates"""
    try:
        with state_lock:
            current_time = datetime.now()
            last_update_age = (current_time - temperature_data['last_temp_update']).total_seconds()
            temp_diff = abs(temperature_data['sensor1_temp'] - temperature_data['sensor2_temp']) if \
                       temperature_data['sensor1_connected'] and temperature_data['sensor2_connected'] else 0
            
            return jsonify({
                'temperature': temperature_data['current_temp'],                # Max temp for safety
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
                'timestamp': current_time.isoformat(),
                'status': 'real-time' if last_update_age < 1.0 else 'delayed',
                'dual_sensor_mode': True
            })
    except Exception as e:
        logger.error(f"Realtime temperature error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/temperature/sensors', methods=['GET'])
def get_sensor_details():
    """NEW: Detailed individual sensor information"""
    try:
        with state_lock:
            current_time = datetime.now()
            
            # Sensor health stats
            sensor_health = {}
            if arduino_controller:
                sensor_health = {
                    'sensor1_updates': arduino_controller.sensor_health_stats['sensor1_updates'],
                    'sensor2_updates': arduino_controller.sensor_health_stats['sensor2_updates'],
                    'dual_updates': arduino_controller.sensor_health_stats['dual_updates'],
                    'sensor1_last_seen': arduino_controller.sensor_health_stats['sensor1_last_seen'].isoformat(),
                    'sensor2_last_seen': arduino_controller.sensor_health_stats['sensor2_last_seen'].isoformat()
                }
            
            return jsonify({
                'sensor1': {
                    'pin': 8,
                    'name': 'Primary Temperature Sensor',
                    'temperature': temperature_data['sensor1_temp'],
                    'max_temperature': temperature_data['max_temp_sensor1'],
                    'connected': temperature_data['sensor1_connected'],
                    'updates': sensor_health.get('sensor1_updates', 0)
                },
                'sensor2': {
                    'pin': 13,
                    'name': 'Secondary Temperature Sensor',
                    'temperature': temperature_data['sensor2_temp'],
                    'max_temperature': temperature_data['max_temp_sensor2'],
                    'connected': temperature_data['sensor2_connected'],
                    'updates': sensor_health.get('sensor2_updates', 0)
                },
                'comparison': {
                    'temperature_difference': abs(temperature_data['sensor1_temp'] - temperature_data['sensor2_temp']),
                    'max_for_safety': max(temperature_data['sensor1_temp'], temperature_data['sensor2_temp']),
                    'average_temperature': (temperature_data['sensor1_temp'] + temperature_data['sensor2_temp']) / 2,
                    'large_difference_warning': abs(temperature_data['sensor1_temp'] - temperature_data['sensor2_temp']) > TEMP_DIFF_WARNING
                },
                'health': sensor_health,
                'failure_count': temperature_data['sensor_failure_count'],
                'redundancy_status': {
                    'both_active': temperature_data['sensor1_connected'] and temperature_data['sensor2_connected'],
                    'single_active': (temperature_data['sensor1_connected'] or temperature_data['sensor2_connected']) and not (temperature_data['sensor1_connected'] and temperature_data['sensor2_connected']),
                    'none_active': not temperature_data['sensor1_connected'] and not temperature_data['sensor2_connected']
                },
                'timestamp': current_time.isoformat()
            })
    except Exception as e:
        logger.error(f"Sensor details error: {e}")
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
                }
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

# System Control Routes - DUAL TEMP ENHANCED
@app.route('/api/system/arm', methods=['POST'])
def arm_system():
    """Arm system - DUAL TEMPERATURE safety checks"""
    if not arduino_controller or not arduino_controller.is_connected:
        return jsonify({'status': 'error', 'message': 'Arduino not connected'}), 503
    
    # DUAL temperature safety checks
    if temperature_data['temp_alarm']:
        return jsonify({
            'status': 'error',
            'message': 'Cannot arm - temperature alarm active',
            'current_temp': temperature_data['current_temp'],
            'sensor1_temp': temperature_data['sensor1_temp'],
            'sensor2_temp': temperature_data['sensor2_temp']
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
            logger.info(f"System ARMED - Dual Temps: S1={temperature_data['sensor1_temp']}°C, S2={temperature_data['sensor2_temp']}°C, Max={temperature_data['current_temp']}°C")
            return jsonify({
                'status': 'armed',
                'message': 'System armed successfully',
                'dual_temperatures': {
                    'sensor1_temp': temperature_data['sensor1_temp'],
                    'sensor2_temp': temperature_data['sensor2_temp'],
                    'max_temp': temperature_data['current_temp'],
                    'sensor1_connected': temperature_data['sensor1_connected'],
                    'sensor2_connected': temperature_data['sensor2_connected']
                }
            })
        else:
            return jsonify({'status': 'error', 'message': f'Arduino error: {response}'}), 500
            
    except Exception as e:
        logger.error(f"Arm system error: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/system/disarm', methods=['POST'])
def disarm_system():
    """Disarm the system"""
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
                }
            })
        else:
            return jsonify({'status': 'error', 'message': f'Arduino error: {response}'}), 500
            
    except Exception as e:
        logger.error(f"Disarm system error: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

# Brake Control Routes - DUAL TEMP ENHANCED
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
        
        if success and command in response.upper():
            with state_lock:
                system_state['brake_active'] = (action == 'on')
                
                if system_state['brake_active']:
                    for i in range(1, 7):
                        motor_states[i] = False
                        individual_motor_speeds[i] = 0
                    group_speeds['levitation'] = 0
                    group_speeds['thrust'] = 0
            
            status = 'activated' if system_state['brake_active'] else 'deactivated'
            logger.info(f"Software brake {status}")
            
            return jsonify({
                'status': 'success',
                'action': action,
                'brake_active': system_state['brake_active'],
                'message': f'Software brake {status}',
                'dual_temperatures': {
                    'sensor1_temp': temperature_data['sensor1_temp'],
                    'sensor2_temp': temperature_data['sensor2_temp'],
                    'max_temp': temperature_data['current_temp']
                }
            })
        else:
            return jsonify({'status': 'error', 'message': f'Brake control failed: {response}'}), 500
        
    except Exception as e:
        logger.error(f"Software brake control error: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/relay-brake/<action>', methods=['POST'])
def control_relay_brake(action):
    """Control relay brake system with DUAL temperature checks"""
    if not arduino_controller or not arduino_controller.is_connected:
        return jsonify({'status': 'error', 'message': 'Arduino not connected'}), 503
    
    if action not in ['on', 'off']:
        return jsonify({'status': 'error', 'message': 'Invalid action. Use "on" or "off"'}), 400
    
    # DUAL temperature safety check for relay activation
    if action == 'on' and temperature_data['temp_alarm']:
        return jsonify({
            'status': 'error',
            'message': 'Cannot activate relay brake - temperature alarm active',
            'dual_temperatures': {
                'sensor1_temp': temperature_data['sensor1_temp'],
                'sensor2_temp': temperature_data['sensor2_temp'],
                'max_temp': temperature_data['current_temp'],
                'alarm_active': temperature_data['temp_alarm']
            }
        }), 400
    
    try:
        command = "RELAY_BRAKE_ON" if action == 'on' else "RELAY_BRAKE_OFF"
        success, response = arduino_controller.send_command_sync(command, timeout=3.0)
        
        if success and "RELAY_BRAKE:" in response:
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
            logger.info(f"Relay brake {status} - Dual Temps: S1={temperature_data['sensor1_temp']}°C, S2={temperature_data['sensor2_temp']}°C")
            
            return jsonify({
                'status': 'success',
                'action': action,
                'relay_brake_active': system_state['relay_brake_active'],
                'system_disarmed': not system_state['relay_brake_active'],
                'message': f'Relay brake {status}',
                'dual_temperatures': {
                    'sensor1_temp': temperature_data['sensor1_temp'],
                    'sensor2_temp': temperature_data['sensor2_temp'],
                    'max_temp': temperature_data['current_temp'],
                    'sensor1_connected': temperature_data['sensor1_connected'],
                    'sensor2_connected': temperature_data['sensor2_connected']
                },
                'arduino_response': response
            })
        else:
            return jsonify({
                'status': 'error',
                'message': f'Relay brake failed: {response}'
            }), 500
        
    except Exception as e:
        logger.error(f"Relay brake control error: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

# Emergency Stop Route - DUAL TEMP ENHANCED
@app.route('/api/emergency-stop', methods=['POST'])
def emergency_stop():
    """Emergency stop all systems with dual temperature logging"""
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
        
        logger.warning(f"EMERGENCY STOP ACTIVATED! Dual Temps: S1={temperature_data['sensor1_temp']}°C, S2={temperature_data['sensor2_temp']}°C, Max={temperature_data['current_temp']}°C")
        
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
            'timestamp': datetime.now().isoformat()
        })

# Motor Control Routes - DUAL TEMP ENHANCED
@app.route('/api/motor/<int:motor_num>/start', methods=['POST'])
def start_individual_motor(motor_num):
    """Start individual motor with DUAL temperature safety checks"""
    if not arduino_controller or not arduino_controller.is_connected:
        return jsonify({'status': 'error', 'message': 'Arduino not connected'}), 503
    
    # DUAL temperature safety checks
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
    
    # Check maximum temperature from both sensors
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
            
            logger.info(f"Motor {motor_num} ({motor_type}, Pin {pin_num}) started at {speed}% - Dual Temps: S1={temperature_data['sensor1_temp']:.1f}°C, S2={temperature_data['sensor2_temp']:.1f}°C")
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
        
        if success and "MOTOR_STOPPED" in response:
            with state_lock:
                motor_states[motor_num] = False
                individual_motor_speeds[motor_num] = 0
            
            logger.info(f"Motor {motor_num} stopped - Dual Temps: S1={temperature_data['sensor1_temp']:.1f}°C, S2={temperature_data['sensor2_temp']:.1f}°C")
            return jsonify({
                'status': 'success',
                'motor': motor_num,
                'action': 'stop',
                'speed': 0,
                'message': f'Motor {motor_num} stopped',
                'dual_temperatures': {
                    'sensor1_temp': temperature_data['sensor1_temp'],
                    'sensor2_temp': temperature_data['sensor2_temp'],
                    'max_temp': temperature_data['current_temp']
                },
                'arduino_response': response
            })
        else:
            return jsonify({
                'status': 'error',
                'message': f'Motor stop failed: {response}'
            }), 500
            
    except Exception as e:
        logger.error(f"Motor {motor_num} stop error: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/motor/<int:motor_num>/speed', methods=['POST'])
def set_individual_motor_speed(motor_num):
    """Set individual motor speed with DUAL temperature safety checks"""
    if not arduino_controller or not arduino_controller.is_connected:
        return jsonify({'status': 'error', 'message': 'Arduino not connected'}), 503
    
    if not system_state['armed']:
        return jsonify({'status': 'error', 'message': 'System not armed'}), 400
    
    if not system_state['relay_brake_active']:
        return jsonify({'status': 'error', 'message': 'Relay brake must be active to control motors'}), 400
    
    # DUAL temperature safety checks
    if temperature_data['temp_alarm']:
        return jsonify({
            'status': 'error', 
            'message': 'Cannot control motor - temperature alarm active',
            'dual_temperatures': {
                'sensor1_temp': temperature_data['sensor1_temp'],
                'sensor2_temp': temperature_data['sensor2_temp'],
                'max_temp': temperature_data['current_temp']
            }
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
        
        if success and "MOTOR_SPEED" in response:
            with state_lock:
                individual_motor_speeds[motor_num] = speed
            
            logger.info(f"Motor {motor_num} speed set to {speed}% - Dual Temps: S1={temperature_data['sensor1_temp']:.1f}°C, S2={temperature_data['sensor2_temp']:.1f}°C")
            return jsonify({
                'status': 'success',
                'motor': motor_num,
                'speed': speed,
                'message': f'Motor {motor_num} speed set to {speed}%',
                'dual_temperatures': {
                    'sensor1_temp': temperature_data['sensor1_temp'],
                    'sensor2_temp': temperature_data['sensor2_temp'],
                    'max_temp': temperature_data['current_temp']
                },
                'arduino_response': response
            })
        else:
            return jsonify({
                'status': 'error',
                'message': f'Motor speed failed: {response}'
            }), 500
            
    except ValueError:
        return jsonify({'status': 'error', 'message': 'Invalid speed value'}), 400
    except Exception as e:
        logger.error(f"Motor {motor_num} speed error: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

# Group Motor Control Routes - DUAL TEMP ENHANCED
@app.route('/api/levitation/start', methods=['POST'])
def start_levitation_group():
    """Start levitation group with DUAL temperature safety checks"""
    if not arduino_controller or not arduino_controller.is_connected:
        return jsonify({'status': 'error', 'message': 'Arduino not connected'}), 503
    
    if not system_state['armed']:
        return jsonify({'status': 'error', 'message': 'System not armed'}), 400
    
    if not system_state['relay_brake_active']:
        return jsonify({'status': 'error', 'message': 'Relay brake must be active to start motors'}), 400
    
    # DUAL temperature safety checks
    if temperature_data['temp_alarm']:
        return jsonify({
            'status': 'error', 
            'message': 'Cannot start levitation group - temperature alarm active',
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
            'message': f'Cannot start levitation group - temperature too high ({temperature_data["current_temp"]:.1f}°C)',
            'dual_temperatures': {
                'sensor1_temp': temperature_data['sensor1_temp'],
                'sensor2_temp': temperature_data['sensor2_temp'],
                'max_temp': temperature_data['current_temp'],
                'max_safe_temp': TEMP_ALARM_THRESHOLD - 3
            }
        }), 400
    
    try:
        data = request.get_json() or {}
        speed = int(data.get('speed', group_speeds['levitation'] or 50))
        
        if not 0 <= speed <= 100:
            return jsonify({'status': 'error', 'message': 'Speed must be 0-100'}), 400
        
        command = f"LEV_GROUP:START:{speed}"
        success, response = arduino_controller.send_command_sync(command, timeout=5.0)
        
        if success and "LEV_GROUP_STARTED" in response:
            with state_lock:
                group_speeds['levitation'] = speed
                for i in range(1, 5):
                    motor_states[i] = True
                    individual_motor_speeds[i] = speed
            
            logger.info(f"Levitation group (Motors 1,2,3,4) started at {speed}% - Dual Temps: S1={temperature_data['sensor1_temp']:.1f}°C, S2={temperature_data['sensor2_temp']:.1f}°C")
            return jsonify({
                'status': 'success',
                'action': 'start',
                'speed': speed,
                'motors': list(range(1, 5)),
                'pins': [2, 4, 5, 6],
                'message': 'Levitation group started',
                'group': 'levitation',
                'dual_temperatures': {
                    'sensor1_temp': temperature_data['sensor1_temp'],
                    'sensor2_temp': temperature_data['sensor2_temp'],
                    'max_temp': temperature_data['current_temp'],
                    'sensor1_connected': temperature_data['sensor1_connected'],
                    'sensor2_connected': temperature_data['sensor2_connected']
                },
                'arduino_response': response
            })
        else:
            return jsonify({
                'status': 'error',
                'message': f'Levitation start failed: {response}'
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
        
        if success and "LEV_GROUP_STOPPED" in response:
            with state_lock:
                group_speeds['levitation'] = 0
                for i in range(1, 5):
                    motor_states[i] = False
                    individual_motor_speeds[i] = 0
            
            logger.info(f"Levitation group stopped - Dual Temps: S1={temperature_data['sensor1_temp']:.1f}°C, S2={temperature_data['sensor2_temp']:.1f}°C")
            return jsonify({
                'status': 'success',
                'action': 'stop',
                'speed': 0,
                'motors': list(range(1, 5)),
                'message': 'Levitation group stopped',
                'group': 'levitation',
                'dual_temperatures': {
                    'sensor1_temp': temperature_data['sensor1_temp'],
                    'sensor2_temp': temperature_data['sensor2_temp'],
                    'max_temp': temperature_data['current_temp']
                },
                'arduino_response': response
            })
        else:
            return jsonify({
                'status': 'error',
                'message': f'Levitation stop failed: {response}'
            }), 500
            
    except Exception as e:
        logger.error(f"Levitation stop error: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/levitation/speed', methods=['POST'])
def set_levitation_speed():
    """Set levitation group speed with DUAL temperature safety checks"""
    if not arduino_controller or not arduino_controller.is_connected:
        return jsonify({'status': 'error', 'message': 'Arduino not connected'}), 503
    
    if not system_state['armed']:
        return jsonify({'status': 'error', 'message': 'System not armed'}), 400
    
    if not system_state['relay_brake_active']:
        return jsonify({'status': 'error', 'message': 'Relay brake must be active to control motors'}), 400
    
    # DUAL temperature safety checks
    if temperature_data['temp_alarm']:
        return jsonify({
            'status': 'error', 
            'message': 'Cannot control levitation group - temperature alarm active',
            'dual_temperatures': {
                'sensor1_temp': temperature_data['sensor1_temp'],
                'sensor2_temp': temperature_data['sensor2_temp'],
                'max_temp': temperature_data['current_temp']
            }
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
        
        if success and "LEV_GROUP_SPEED" in response:
            with state_lock:
                group_speeds['levitation'] = speed
                for i in range(1, 5):
                    if motor_states[i]:
                        individual_motor_speeds[i] = speed
            
            logger.info(f"Levitation group speed set to {speed}% - Dual Temps: S1={temperature_data['sensor1_temp']:.1f}°C, S2={temperature_data['sensor2_temp']:.1f}°C")
            return jsonify({
                'status': 'success',
                'speed': speed,
                'motors': list(range(1, 5)),
                'message': 'Levitation group speed updated',
                'group': 'levitation',
                'dual_temperatures': {
                    'sensor1_temp': temperature_data['sensor1_temp'],
                    'sensor2_temp': temperature_data['sensor2_temp'],
                    'max_temp': temperature_data['current_temp']
                },
                'arduino_response': response
            })
        else:
            return jsonify({
                'status': 'error',
                'message': f'Levitation speed failed: {response}'
            }), 500
            
    except ValueError:
        return jsonify({'status': 'error', 'message': 'Invalid speed value'}), 400
    except Exception as e:
        logger.error(f"Levitation speed error: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/thrust/start', methods=['POST'])
def start_thrust_group():
    """Start thrust group with DUAL temperature safety checks"""
    if not arduino_controller or not arduino_controller.is_connected:
        return jsonify({'status': 'error', 'message': 'Arduino not connected'}), 503
    
    if not system_state['armed']:
        return jsonify({'status': 'error', 'message': 'System not armed'}), 400
    
    if not system_state['relay_brake_active']:
        return jsonify({'status': 'error', 'message': 'Relay brake must be active to start motors'}), 400
    
    # DUAL temperature safety checks
    if temperature_data['temp_alarm']:
        return jsonify({
            'status': 'error', 
            'message': 'Cannot start thrust group - temperature alarm active',
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
            'message': f'Cannot start thrust group - temperature too high ({temperature_data["current_temp"]:.1f}°C)',
            'dual_temperatures': {
                'sensor1_temp': temperature_data['sensor1_temp'],
                'sensor2_temp': temperature_data['sensor2_temp'],
                'max_temp': temperature_data['current_temp'],
                'max_safe_temp': TEMP_ALARM_THRESHOLD - 3
            }
        }), 400
    
    try:
        data = request.get_json() or {}
        speed = int(data.get('speed', group_speeds['thrust'] or 50))
        
        if not 0 <= speed <= 100:
            return jsonify({'status': 'error', 'message': 'Speed must be 0-100'}), 400
        
        command = f"THR_GROUP:START:{speed}"
        success, response = arduino_controller.send_command_sync(command, timeout=5.0)
        
        if success and "THR_GROUP_STARTED" in response:
            with state_lock:
                group_speeds['thrust'] = speed
                for i in range(5, 7):
                    motor_states[i] = True
                    individual_motor_speeds[i] = speed
            
            logger.info(f"Thrust group (Motors 5,6) started at {speed}% - Dual Temps: S1={temperature_data['sensor1_temp']:.1f}°C, S2={temperature_data['sensor2_temp']:.1f}°C")
            return jsonify({
                'status': 'success',
                'action': 'start',
                'speed': speed,
                'motors': list(range(5, 7)),
                'pins': [3, 7],
                'message': 'Thrust group started',
                'group': 'thrust',
                'dual_temperatures': {
                    'sensor1_temp': temperature_data['sensor1_temp'],
                    'sensor2_temp': temperature_data['sensor2_temp'],
                    'max_temp': temperature_data['current_temp'],
                    'sensor1_connected': temperature_data['sensor1_connected'],
                    'sensor2_connected': temperature_data['sensor2_connected']
                },
                'arduino_response': response
            })
        else:
            return jsonify({
                'status': 'error',
                'message': f'Thrust start failed: {response}'
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
        
        if success and "THR_GROUP_STOPPED" in response:
            with state_lock:
                group_speeds['thrust'] = 0
                for i in range(5, 7):
                    motor_states[i] = False
                    individual_motor_speeds[i] = 0
            
            logger.info(f"Thrust group stopped - Dual Temps: S1={temperature_data['sensor1_temp']:.1f}°C, S2={temperature_data['sensor2_temp']:.1f}°C")
            return jsonify({
                'status': 'success',
                'action': 'stop',
                'speed': 0,
                'motors': list(range(5, 7)),
                'message': 'Thrust group stopped',
                'group': 'thrust',
                'dual_temperatures': {
                    'sensor1_temp': temperature_data['sensor1_temp'],
                    'sensor2_temp': temperature_data['sensor2_temp'],
                    'max_temp': temperature_data['current_temp']
                },
                'arduino_response': response
            })
        else:
            return jsonify({
                'status': 'error',
                'message': f'Thrust stop failed: {response}'
            }), 500
            
    except Exception as e:
        logger.error(f"Thrust stop error: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/thrust/speed', methods=['POST'])
def set_thrust_speed():
    """Set thrust group speed with DUAL temperature safety checks"""
    if not arduino_controller or not arduino_controller.is_connected:
        return jsonify({'status': 'error', 'message': 'Arduino not connected'}), 503
    
    if not system_state['armed']:
        return jsonify({'status': 'error', 'message': 'System not armed'}), 400
    
    if not system_state['relay_brake_active']:
        return jsonify({'status': 'error', 'message': 'Relay brake must be active to control motors'}), 400
    
    # DUAL temperature safety checks
    if temperature_data['temp_alarm']:
        return jsonify({
            'status': 'error', 
            'message': 'Cannot control thrust group - temperature alarm active',
            'dual_temperatures': {
                'sensor1_temp': temperature_data['sensor1_temp'],
                'sensor2_temp': temperature_data['sensor2_temp'],
                'max_temp': temperature_data['current_temp']
            }
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
        
        if success and "THR_GROUP_SPEED" in response:
            with state_lock:
                group_speeds['thrust'] = speed
                for i in range(5, 7):
                    if motor_states[i]:
                        individual_motor_speeds[i] = speed
            
            logger.info(f"Thrust group speed set to {speed}% - Dual Temps: S1={temperature_data['sensor1_temp']:.1f}°C, S2={temperature_data['sensor2_temp']:.1f}°C")
            return jsonify({
                'status': 'success',
                'speed': speed,
                'motors': list(range(5, 7)),
                'message': 'Thrust group speed updated',
                'group': 'thrust',
                'dual_temperatures': {
                    'sensor1_temp': temperature_data['sensor1_temp'],
                    'sensor2_temp': temperature_data['sensor2_temp'],
                    'max_temp': temperature_data['current_temp']
                },
                'arduino_response': response
            })
        else:
            return jsonify({
                'status': 'error',
                'message': f'Thrust speed failed: {response}'
            }), 500
            
    except ValueError:
        return jsonify({'status': 'error', 'message': 'Invalid speed value'}), 400
    except Exception as e:
        logger.error(f"Thrust speed error: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

# Utility Routes - DUAL TEMP ENHANCED
@app.route('/api/test-connection', methods=['GET'])
def test_connection():
    """Test Arduino connection with dual temperature info"""
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
                'dual_temperatures': {
                    'sensor1_temp': temperature_data['sensor1_temp'],
                    'sensor2_temp': temperature_data['sensor2_temp'],
                    'max_temp': temperature_data['current_temp'],
                    'sensor1_connected': temperature_data['sensor1_connected'],
                    'sensor2_connected': temperature_data['sensor2_connected']
                },
                'temperature_system': 'dual-sensor-active'
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
                'dual_temperature_monitoring': 'restarted',
                'sensor_health_monitoring': 'restarted'
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
    """Ultra-fast health check with DUAL temperature info"""
    try:
        with state_lock:
            temp_age = (datetime.now() - temperature_data['last_temp_update']).total_seconds()
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
                'performance': {
                    'continuous_reader': arduino_controller.continuous_reader_thread.is_alive() if arduino_controller and arduino_controller.continuous_reader_thread else False,
                    'temp_stats_monitor': arduino_controller.temp_stats_thread.is_alive() if arduino_controller and arduino_controller.temp_stats_thread else False,
                    'sensor_health_monitor': arduino_controller.sensor_health_thread.is_alive() if arduino_controller and arduino_controller.sensor_health_thread else False,
                    'optimization': 'dual-sensor-ultra-fast'
                },
                'version': '3.5-DUAL-TEMPERATURE',
                'port': arduino_controller.port if arduino_controller else None
            })
        
    except Exception as e:
        logger.error(f"Ping error: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

# Error Handlers - DUAL TEMP ENHANCED
@app.errorhandler(404)
def not_found(error):
    return jsonify({
        'status': 'error',
        'message': 'Endpoint not found',
        'available_endpoints': [
            'GET /api/status',
            'GET /api/temperature',
            'GET /api/temperature/realtime',
            'GET /api/temperature/sensors',
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
        ],
        'dual_sensor_features': [
            'Individual sensor temperatures',
            'Redundant safety monitoring',
            'Sensor health tracking',
            'Temperature difference warnings',
            'Automatic failover capability'
        ]
    }), 404

@app.errorhandler(500)
def internal_error(error):
    logger.error(f"Internal server error: {error}")
    return jsonify({
        'status': 'error',
        'message': 'Internal server error',
        'timestamp': datetime.now().isoformat(),
        'dual_sensor_status': {
            'sensor1_connected': temperature_data['sensor1_connected'],
            'sensor2_connected': temperature_data['sensor2_connected'],
            'current_temps': {
                'sensor1': temperature_data['sensor1_temp'],
                'sensor2': temperature_data['sensor2_temp'],
                'max': temperature_data['current_temp']
            }
        }
    }), 500

# Background monitoring - DUAL TEMP ENHANCED
def dual_temp_background_monitor():
    """DUAL TEMPERATURE background monitoring and maintenance"""
    logger.info("DUAL TEMPERATURE background monitor started")
    
    while not shutdown_event.is_set():
        try:
            # Connection monitoring
            if arduino_controller and not arduino_controller.is_connected:
                if arduino_controller.reconnect_attempts < arduino_controller.max_attempts:
                    logger.info("Auto-reconnection attempt...")
                    if arduino_controller.reconnect():
                        logger.info("Auto-reconnection successful")
            
            # DUAL temperature monitoring
            with state_lock:
                temp_age = (datetime.now() - temperature_data['last_temp_update']).total_seconds()
                
                if temp_age > 10:  # 10 seconds is too old
                    logger.warning(f"Dual temperature data is stale: {temp_age:.1f}s old")
                    
                    # Try to restart continuous reader
                    if arduino_controller and arduino_controller.is_connected:
                        if not arduino_controller.continuous_reader_thread or not arduino_controller.continuous_reader_thread.is_alive():
                            logger.info("Restarting dual temperature reader...")
                            arduino_controller._start_continuous_reader()
                        if not arduino_controller.sensor_health_thread or not arduino_controller.sensor_health_thread.is_alive():
                            logger.info("Restarting sensor health monitor...")
                            arduino_controller._start_sensor_health_monitor()
                
                # Update frequency monitoring
                if temperature_data['update_frequency'] < 0.5:  # Less than 0.5 Hz
                    logger.warning(f"Low dual temperature update frequency: {temperature_data['update_frequency']:.2f} Hz")
                
                # Sensor health check
                if not temperature_data['sensor1_connected'] and not temperature_data['sensor2_connected']:
                    if not system_state['temperature_emergency']:
                        logger.error("CRITICAL: Both temperature sensors failed!")
                        system_state['temperature_emergency'] = True
                
                # Large sensor difference warning
                if temperature_data['sensor1_connected'] and temperature_data['sensor2_connected']:
                    temp_diff = abs(temperature_data['sensor1_temp'] - temperature_data['sensor2_temp'])
                    if temp_diff > TEMP_DIFF_WARNING:
                        logger.warning(f"Large sensor difference detected: {temp_diff:.1f}°C")
            
            shutdown_event.wait(5)  # Monitor every 5 seconds
            
        except Exception as e:
            logger.error(f"Dual temperature background monitor error: {e}")
            shutdown_event.wait(5)
    
    logger.info("DUAL TEMPERATURE background monitor stopped")

# Start dual temperature background monitor
monitor_thread = threading.Thread(target=dual_temp_background_monitor, daemon=True, name="DualTempMonitor")
monitor_thread.start()

# Graceful shutdown handler - DUAL TEMP
def signal_handler(sig, frame):
    """Graceful shutdown handler"""
    logger.info("Shutdown signal received...")
    
    try:
        shutdown_event.set()
        
        if arduino_controller:
            arduino_controller.disconnect()
        
        logger.info("DUAL TEMPERATURE backend shutdown completed")
        
    except Exception as e:
        logger.error(f"Shutdown error: {e}")
    finally:
        sys.exit(0)

# Register signal handlers
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

if __name__ == '__main__':
    logger.info("=" * 80)
    logger.info("SpectraLoop Backend DUAL TEMPERATURE v3.5 - COMPLETE SYSTEM")
    logger.info("=" * 80)
    
    try:
        if arduino_controller and arduino_controller.is_connected:
            logger.info(f"Arduino Status: Connected to {arduino_controller.port}")
            logger.info("DUAL TEMPERATURE FEATURES:")
            logger.info("   🌡️ Primary sensor (Pin 8) + Secondary sensor (Pin 13)")
            logger.info("   🛡️ Redundant safety monitoring")
            logger.info("   ⚡ 100ms temperature readings from both sensors")
            logger.info("   📊 Individual sensor health tracking")
            logger.info("   🔄 Automatic sensor failover capability")
            logger.info("   ⚠️ Large temperature difference warnings")
            logger.info("   📈 Real-time performance monitoring")
            logger.info("   🚨 Enhanced safety with worst-case temperature logic")
        else:
            logger.warning("Arduino Status: Not Connected")
        
        logger.info("=" * 80)
        logger.info("Starting DUAL TEMPERATURE Flask server...")
        
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
        logger.info("DUAL TEMPERATURE server shutdown complete")
                