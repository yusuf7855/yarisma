#!/usr/bin/env python3
"""
SpectraLoop Motor Control Backend - Final Production v3.1 - MPU6050 Entegrasyonu
Enhanced stability and performance
Individual + Group motor control + Relay Brake Control + MPU6050 Sensör Desteği
Motor Pin Mapping: İtki (3,7), Levitasyon (2,4,5,6)
"""

from flask import Flask, jsonify, request
from flask_cors import CORS
import serial
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

# Enhanced logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('spectraloop_mpu6050.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Thread-safe global state
motor_states = {i: False for i in range(1, 7)}
individual_motor_speeds = {i: 0 for i in range(1, 7)}
group_speeds = {'levitation': 0, 'thrust': 0}

# MPU6050 sensor data
sensor_data = {
    'accel_x': 0.0,
    'accel_y': 0.0,
    'accel_z': 0.0,
    'gyro_x': 0.0,
    'gyro_y': 0.0,
    'gyro_z': 0.0,
    'temperature': 0.0,
    'timestamp': 0,
    'last_update': None,
    'available': False
}

system_state = {
    'armed': False,
    'brake_active': False,
    'relay_brake_active': False,
    'connected': False,
    'mpu6050_available': False,
    'last_response': None,
    'errors': 0,
    'commands': 0
}

command_queue = queue.Queue(maxsize=100)
state_lock = threading.Lock()

class ProductionArduinoController:
    def __init__(self, port='/dev/ttyUSB0', baudrate=115200):
        self.port = port
        self.baudrate = baudrate
        self.connection = None
        self.is_connected = False
        self.last_command_time = 0
        self.reconnect_attempts = 0
        self.max_attempts = 3
        
        # Command processing
        self.command_queue = queue.Queue(maxsize=50)
        self.response_timeout = 1.0
        
        # Connection management
        self.connection_lock = threading.Lock()
        
        # Sensor data update thread
        self.sensor_thread = None
        self.sensor_running = False
        
        # Initialize connection safely
        try:
            self.connect()
            self._start_command_processor()
            self._start_sensor_reader()
        except KeyboardInterrupt:
            logger.info("Initialization interrupted by user")
            self.disconnect()
            raise
        except Exception as e:
            logger.error(f"Initialization error: {e}")
            self.disconnect()
            raise
    
    def find_arduino_port(self):
        """Find available Arduino port - Windows compatible"""
        import serial.tools.list_ports
        
        # Windows için port listesi
        ports = serial.tools.list_ports.comports()
        
        for port in ports:
            if 'Arduino' in port.description or 'USB Serial' in port.description:
                try:
                    test_conn = serial.Serial(port.device, self.baudrate, timeout=1)
                    test_conn.close()
                    logger.info(f"Found Arduino port: {port.device}")
                    return port.device
                except Exception:
                    continue
        
        # Fallback to common ports
        common_ports = ['COM3', 'COM4', 'COM5', 'COM6', 'COM7', 'COM8']
        for port in common_ports:
            try:
                test_conn = serial.Serial(port, self.baudrate, timeout=1)
                test_conn.close()
                logger.info(f"Found valid port: {port}")
                return port
            except Exception:
                continue
        
        logger.warning("No Arduino port found")
        return None
    
    def connect(self):
        """Connect to Arduino with enhanced reliability"""
        if self.reconnect_attempts >= self.max_attempts:
            logger.error(f"Max reconnection attempts reached")
            return False
        
        try:
            with self.connection_lock:
                # Find port if current doesn't exist
                if not os.path.exists(self.port):
                    auto_port = self.find_arduino_port()
                    if auto_port:
                        self.port = auto_port
                    else:
                        raise Exception("No Arduino port available")
                
                # Create connection
                self.connection = serial.Serial(
                    port=self.port,
                    baudrate=self.baudrate,
                    timeout=2,
                    write_timeout=1,
                    parity=serial.PARITY_NONE,
                    stopbits=serial.STOPBITS_ONE,
                    bytesize=serial.EIGHTBITS
                )
                
                logger.info(f"Serial connection opened: {self.port}")
                
                # Wait for Arduino to initialize
                time.sleep(3)
                self.connection.flushInput()
                self.connection.flushOutput()
                
                # Test connection
                if self._test_connection():
                    self.is_connected = True
                    self.reconnect_attempts = 0
                    system_state['connected'] = True
                    logger.info("Arduino connection successful")
                    
                    # Check MPU6050 availability
                    self._check_mpu6050()
                    return True
                else:
                    raise Exception("Connection test failed")
        
        except Exception as e:
            self.reconnect_attempts += 1
            logger.error(f"Connection error (attempt {self.reconnect_attempts}): {e}")
            system_state['connected'] = False
            self.is_connected = False
            if self.connection:
                try:
                    self.connection.close()
                except:
                    pass
                self.connection = None
            return False
    
    def _check_mpu6050(self):
        """Check MPU6050 sensor availability"""
        try:
            # Use shorter timeout for MPU6050 check
            success, response = self.send_command_sync("STATUS", 2.0)
            if success and response and "MPU6050:1" in response:
                system_state['mpu6050_available'] = True
                sensor_data['available'] = True
                logger.info("MPU6050 sensor available")
            else:
                system_state['mpu6050_available'] = False
                sensor_data['available'] = False
                logger.warning("MPU6050 sensor not available")
        except KeyboardInterrupt:
            logger.info("MPU6050 check interrupted by user")
            raise
        except Exception as e:
            logger.error(f"MPU6050 check error: {e}")
            system_state['mpu6050_available'] = False
            sensor_data['available'] = False
        
    
    def _test_connection(self):
        """Quick connection test"""
        try:
            for attempt in range(2):
                self.connection.write(b"PING\n")
                self.connection.flush()
                
                start_time = time.time()
                response = ""
                
                while time.time() - start_time < 2.0:
                    if self.connection.in_waiting > 0:
                        data = self.connection.read(self.connection.in_waiting)
                        response += data.decode('utf-8', errors='ignore')
                        
                        # Arduino'dan gelen herhangi bir yanıt kabul et
                        if any(keyword in response for keyword in ["PONG", "ACK", "SpectraLoop", "READY"]):
                            logger.info("Arduino responded successfully")
                            return True
                    time.sleep(0.05)
                
                time.sleep(0.5)
            
            return False
            
        except Exception as e:
            logger.error(f"Connection test error: {e}")
            return False
    
    def _start_command_processor(self):
        """Start background command processor"""
        self.processor_thread = threading.Thread(target=self._command_processor, daemon=True)
        self.processor_thread.start()
    
    def _start_sensor_reader(self):
        """Start background sensor data reader"""
        self.sensor_running = True
        self.sensor_thread = threading.Thread(target=self._sensor_reader, daemon=True)
        self.sensor_thread.start()
    
    def _sensor_reader(self):
        """Background sensor data reader"""
        while self.sensor_running:
            try:
                if self.is_connected and system_state.get('mpu6050_available', False):
                    self._read_sensor_data()
                time.sleep(0.1)  # 10Hz sensor reading
            except Exception as e:
                logger.error(f"Sensor reader error: {e}")
                time.sleep(1)
    
    def _read_sensor_data(self):
        """Read sensor data from Arduino"""
        try:
            success, response = self.send_command_sync("SENSOR_DATA", 1.0)
            if success and response:
                self._parse_sensor_response(response)
        except Exception as e:
            logger.debug(f"Sensor read error: {e}")
    
    def _parse_sensor_response(self, response):
        """Parse sensor data response from Arduino"""
        try:
            if "SENSOR_DATA_START" not in response:
                return
            
            lines = response.split('\n')
            parsed_data = {}
            
            for line in lines:
                line = line.strip()
                if ':' in line:
                    key, value = line.split(':', 1)
                    try:
                        if key in ['AccelX', 'AccelY', 'AccelZ', 'GyroX', 'GyroY', 'GyroZ', 'Temperature']:
                            parsed_data[key] = float(value)
                        elif key == 'Timestamp':
                            parsed_data[key] = int(value)
                    except ValueError:
                        continue
            
            # Update global sensor data
            with state_lock:
                if 'AccelX' in parsed_data:
                    sensor_data['accel_x'] = parsed_data['AccelX']
                if 'AccelY' in parsed_data:
                    sensor_data['accel_y'] = parsed_data['AccelY']
                if 'AccelZ' in parsed_data:
                    sensor_data['accel_z'] = parsed_data['AccelZ']
                if 'GyroX' in parsed_data:
                    sensor_data['gyro_x'] = parsed_data['GyroX']
                if 'GyroY' in parsed_data:
                    sensor_data['gyro_y'] = parsed_data['GyroY']
                if 'GyroZ' in parsed_data:
                    sensor_data['gyro_z'] = parsed_data['GyroZ']
                if 'Temperature' in parsed_data:
                    sensor_data['temperature'] = parsed_data['Temperature']
                if 'Timestamp' in parsed_data:
                    sensor_data['timestamp'] = parsed_data['Timestamp']
                
                sensor_data['last_update'] = datetime.now()
                sensor_data['available'] = True
                
        except Exception as e:
            logger.debug(f"Sensor parse error: {e}")
    
    def _command_processor(self):
        """Background command processor"""
        while True:
            try:
                if not self.command_queue.empty():
                    command_data = self.command_queue.get(timeout=1)
                    self._execute_command(command_data)
                else:
                    time.sleep(0.1)
            except queue.Empty:
                time.sleep(0.1)
            except Exception as e:
                logger.error(f"Command processor error: {e}")
                time.sleep(0.5)
    
    def send_command_async(self, command):
        """Send command asynchronously"""
        try:
            command_data = {
                'command': command,
                'timestamp': time.time()
            }
            self.command_queue.put(command_data, timeout=0.1)
            return True
        except queue.Full:
            logger.warning("Command queue full")
            return False
    
    def send_command_sync(self, command, timeout=2.0):
        """Send command synchronously"""
        if not self.is_connected or not self.connection:
            return False, "Not connected"
        
        try:
            with self.connection_lock:
                # Rate limiting
                current_time = time.time()
                if current_time - self.last_command_time < 0.05:
                    time.sleep(0.05)
                
                # Send command
                self.connection.write(f"{command}\n".encode())
                self.connection.flush()
                self.last_command_time = current_time
                
                # Read response
                start_time = time.time()
                response = ""
                
                while time.time() - start_time < timeout:
                    if self.connection.in_waiting > 0:
                        data = self.connection.read(self.connection.in_waiting)
                        response += data.decode('utf-8', errors='ignore')
                        
                        if command == "SENSOR_DATA":
                            if "SENSOR_DATA_END" in response:
                                break
                        else:
                            if '\n' in response:
                                break
                    time.sleep(0.02)
                
                # Update stats
                system_state['commands'] += 1
                system_state['last_response'] = datetime.now()
                
                return True, response.strip()
                
        except KeyboardInterrupt:
            logger.info(f"Command '{command}' interrupted by user")
            raise
        except Exception as e:
            logger.error(f"Sync command error: {e}")
            self.is_connected = False
            system_state['connected'] = False
            system_state['errors'] += 1
            return False, str(e)
    
    def _execute_command(self, command_data):
        """Execute command from queue"""
        if not self.is_connected:
            return
        
        try:
            command = command_data['command']
            success, response = self.send_command_sync(command, 1.0)
            
            if success:
                logger.debug(f"Command executed: {command}")
            else:
                logger.error(f"Command failed: {command}")
                
        except Exception as e:
            logger.error(f"Command execution error: {e}")
    
    def reconnect(self):
        """Reconnect to Arduino"""
        logger.info("Attempting reconnection...")
        self.disconnect()
        time.sleep(2)
        success = self.connect()
        if success:
            self._check_mpu6050()
        return success
    
    def disconnect(self):
        """Disconnect from Arduino"""
        logger.info("Disconnecting Arduino...")
        
        # Stop sensor thread first
        self.sensor_running = False
        if self.sensor_thread and self.sensor_thread.is_alive():
            try:
                self.sensor_thread.join(timeout=1.0)
            except Exception as e:
                logger.debug(f"Sensor thread join error: {e}")
        
        # Update system state
        self.is_connected = False
        system_state['connected'] = False
        system_state['mpu6050_available'] = False
        
        # Close serial connection safely
        if self.connection:
            try:
                # Try to acquire lock with timeout
                if self.connection_lock.acquire(timeout=2.0):
                    try:
                        self.connection.close()
                        logger.info("Serial connection closed")
                    except Exception as e:
                        logger.debug(f"Serial close error: {e}")
                    finally:
                        self.connection_lock.release()
                else:
                    logger.warning("Could not acquire connection lock for disconnect")
                    # Force close without lock
                    try:
                        self.connection.close()
                    except:
                        pass
            except Exception as e:
                logger.debug(f"Disconnect error: {e}")
            finally:
                self.connection = None
        
        logger.info("Arduino disconnected successfully")

# Initialize Arduino controller
arduino_controller = ProductionArduinoController()

# API Routes
@app.route('/api/status', methods=['GET'])
def get_status():
    """Get system status including sensor data"""
    try:
        with state_lock:
            return jsonify({
                'connected': arduino_controller.is_connected,
                'armed': system_state['armed'],
                'motors': motor_states.copy(),
                'individual_speeds': individual_motor_speeds.copy(),
                'group_speeds': group_speeds.copy(),
                'brake_active': system_state['brake_active'],
                'relay_brake_active': system_state['relay_brake_active'],
                'mpu6050_available': system_state['mpu6050_available'],
                'sensor_data': sensor_data.copy() if sensor_data['available'] else None,
                'stats': {
                    'commands': system_state['commands'],
                    'errors': system_state['errors'],
                    'last_response': system_state['last_response'].isoformat() if system_state['last_response'] else None,
                    'reconnect_attempts': arduino_controller.reconnect_attempts
                },
                'timestamp': datetime.now().isoformat()
            })
    except Exception as e:
        logger.error(f"Status error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/sensor-data', methods=['GET'])
def get_sensor_data():
    """Get current MPU6050 sensor data"""
    try:
        # If MPU6050 not available, return mock data instead of 404
        if not system_state.get('mpu6050_available', False):
            logger.warning("MPU6050 not available, returning mock data")
            return jsonify({
                'available': False,
                'acceleration': {
                    'x': 0.0,
                    'y': 0.0,
                    'z': 1.0  # Gravity
                },
                'gyroscope': {
                    'x': 0.0,
                    'y': 0.0,
                    'z': 0.0
                },
                'temperature': 25.0,
                'timestamp': int(time.time() * 1000),
                'last_update': datetime.now().isoformat(),
                'message': 'MPU6050 sensor not available - mock data'
            })
        
        # Try to get fresh sensor data
        success, response = arduino_controller.send_command_sync("SENSOR_DATA", 3.0)
        
        if success and response:
            parsed_data = parse_sensor_response(response)
            if parsed_data:
                with state_lock:
                    sensor_data.update(parsed_data)
                    sensor_data['last_update'] = datetime.now()
                    sensor_data['available'] = True
        
        # Return current sensor data
        with state_lock:
            data = sensor_data.copy()
            
        return jsonify({
            'available': data.get('available', False),
            'acceleration': {
                'x': data.get('accel_x', 0.0),
                'y': data.get('accel_y', 0.0),
                'z': data.get('accel_z', 1.0)
            },
            'gyroscope': {
                'x': data.get('gyro_x', 0.0),
                'y': data.get('gyro_y', 0.0),
                'z': data.get('gyro_z', 0.0)
            },
            'temperature': data.get('temperature', 25.0),
            'timestamp': data.get('timestamp', int(time.time() * 1000)),
            'last_update': data.get('last_update').isoformat() if data.get('last_update') else datetime.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"Sensor data error: {e}")
        # Return mock data on error instead of error response
        return jsonify({
            'available': False,
            'acceleration': {'x': 0.0, 'y': 0.0, 'z': 1.0},
            'gyroscope': {'x': 0.0, 'y': 0.0, 'z': 0.0},
            'temperature': 25.0,
            'timestamp': int(time.time() * 1000),
            'last_update': datetime.now().isoformat(),
            'error': str(e)
        })

def parse_sensor_response(response):
    """Parse sensor data response from Arduino"""
    try:
        if "SENSOR_DATA_START" not in response:
            return None
        
        lines = response.split('\n')
        parsed_data = {}
        
        for line in lines:
            line = line.strip()
            if ':' in line:
                key, value = line.split(':', 1)
                try:
                    if key in ['AccelX', 'AccelY', 'AccelZ']:
                        parsed_data[f"accel_{key[-1].lower()}"] = float(value)
                    elif key in ['GyroX', 'GyroY', 'GyroZ']:
                        parsed_data[f"gyro_{key[-1].lower()}"] = float(value)
                    elif key == 'Temperature':
                        parsed_data['temperature'] = float(value)
                    elif key == 'Timestamp':
                        parsed_data['timestamp'] = int(value)
                except ValueError:
                    continue
        
        return parsed_data if parsed_data else None
        
    except Exception as e:
        logger.debug(f"Sensor parse error: {e}")
        return None
@app.route('/api/sensor-data/raw', methods=['GET'])
def get_raw_sensor_data():
    """Get raw sensor data directly from Arduino"""
    try:
        if not system_state['mpu6050_available']:
            return jsonify({
                'error': 'MPU6050 sensor not available',
                'available': False
            }), 404
        
        success, response = arduino_controller.send_command_sync("SENSOR_DATA", 3.0)
        
        if success and response:
            return jsonify({
                'success': True,
                'raw_response': response,
                'timestamp': datetime.now().isoformat()
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Failed to get sensor data from Arduino'
            }), 500
            
    except Exception as e:
        logger.error(f"Raw sensor data error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/system/arm', methods=['POST'])
def arm_system():
    """Arm the system - relay must be active"""
    if not system_state['relay_brake_active']:
        return jsonify({
            'status': 'error', 
            'message': 'Cannot arm while relay brake is inactive'
        }), 400
    
    try:
        # Clear any pending data first
        if arduino_controller.connection:
            arduino_controller.connection.flushInput()
            arduino_controller.connection.flushOutput()
        
        # Send ARM command with increased timeout
        success, response = arduino_controller.send_command_sync("ARM", 8.0)
        
        if success and response:
            # Clean the response
            response_lines = [line.strip() for line in response.split('\n') if line.strip()]
            
            # Look for ARMED response in any line
            for line in response_lines:
                line_upper = line.upper().strip()
                
                if line_upper == "ARMED":
                    with state_lock:
                        system_state['armed'] = True
                    logger.info("System ARMED successfully")
                    return jsonify({
                        'status': 'armed',
                        'message': 'System armed successfully',
                        'response': line
                    })
                
                # Check for error conditions
                elif "ERROR:" in line_upper:
                    if "RELAY_INACTIVE" in line_upper or "CANNOT_ARM_RELAY" in line_upper:
                        return jsonify({
                            'status': 'error',
                            'message': 'Cannot arm - relay brake inactive'
                        }), 400
                    elif "BRAKE_ACTIVE" in line_upper or "CANNOT_ARM_BRAKE" in line_upper:
                        return jsonify({
                            'status': 'error',
                            'message': 'Cannot arm - software brake active'
                        }), 400
            
            # If no ARMED found but got response, log for debugging
            logger.error(f"Unexpected ARM response: '{response}'")
            
            # Try reconnection once
            logger.warning("ARM response unclear, attempting reconnection")
            if arduino_controller.reconnect():
                success, response = arduino_controller.send_command_sync("ARM", 5.0)
                if success and "ARMED" in response.upper():
                    with state_lock:
                        system_state['armed'] = True
                    return jsonify({
                        'status': 'armed',
                        'message': 'System armed successfully after reconnection',
                        'response': response
                    })
            
            return jsonify({
                'status': 'error',
                'message': f'Unexpected Arduino response: {response}',
                'debug_response': response
            }), 500
        
        else:
            return jsonify({
                'status': 'error',
                'message': 'Arduino communication failed'
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
    try:
        success, response = arduino_controller.send_command_sync("DISARM", 3.0)
        
        if success and "DISARMED" in response.upper():
            with state_lock:
                system_state['armed'] = False
                # Reset all motor states
                for i in range(1, 7):
                    motor_states[i] = False
                    individual_motor_speeds[i] = 0
                group_speeds['levitation'] = 0
                group_speeds['thrust'] = 0
            
            logger.info("System DISARMED")
            return jsonify({
                'status': 'disarmed',
                'message': 'System disarmed successfully',
                'response': response
            })
        else:
            if not success and arduino_controller.reconnect():
                return disarm_system()
            return jsonify({'status': 'error', 'message': 'Arduino did not respond'}), 500
            
    except Exception as e:
        logger.error(f"Disarm error: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

# Individual Motor Control (Motor 5,6 on pins 3,7 - Thrust)
@app.route('/api/motor/<int:motor_num>/start', methods=['POST'])
def start_individual_motor(motor_num):
    """Start individual motor - röle aktif olmalı"""
    if not system_state['armed']:
        return jsonify({'status': 'error', 'message': 'System not armed'}), 400
    
    if not system_state['relay_brake_active']:
        return jsonify({'status': 'error', 'message': 'Relay brake must be active to start motors'}), 400
    
    if motor_num not in range(1, 7):
        return jsonify({'status': 'error', 'message': 'Invalid motor number'}), 400
    
    try:
        data = request.get_json() or {}
        speed = int(data.get('speed', 50))
        
        if speed < 0 or speed > 100:
            return jsonify({'status': 'error', 'message': 'Speed must be 0-100'}), 400
        
        command = f"MOTOR:{motor_num}:START:{speed}"
        success = arduino_controller.send_command_async(command)
        
        if success:
            with state_lock:
                motor_states[motor_num] = True
                individual_motor_speeds[motor_num] = speed
            
            motor_type = "Thrust" if motor_num in [5, 6] else "Levitation"
            pin_num = 3 if motor_num == 5 else (7 if motor_num == 6 else "N/A")
            
            logger.info(f"Motor {motor_num} ({motor_type}, Pin {pin_num}) started at {speed}%")
            return jsonify({
                'status': 'success',
                'motor': motor_num,
                'action': 'start',
                'speed': speed,
                'type': motor_type,
                'pin': pin_num,
                'message': f'Motor {motor_num} started'
            })
        else:
            return jsonify({'status': 'error', 'message': 'Command queue full'}), 500
            
    except Exception as e:
        logger.error(f"Motor {motor_num} start error: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/motor/<int:motor_num>/stop', methods=['POST'])
def stop_individual_motor(motor_num):
    """Stop individual motor"""
    if motor_num not in range(1, 7):
        return jsonify({'status': 'error', 'message': 'Invalid motor number'}), 400
    
    try:
        command = f"MOTOR:{motor_num}:STOP"
        success = arduino_controller.send_command_async(command)
        
        if success:
            with state_lock:
                motor_states[motor_num] = False
                individual_motor_speeds[motor_num] = 0
            
            logger.info(f"Motor {motor_num} stopped")
            return jsonify({
                'status': 'success',
                'motor': motor_num,
                'action': 'stop',
                'speed': 0,
                'message': f'Motor {motor_num} stopped'
            })
        else:
            return jsonify({'status': 'error', 'message': 'Command queue full'}), 500
            
    except Exception as e:
        logger.error(f"Motor {motor_num} stop error: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/motor/<int:motor_num>/speed', methods=['POST'])
def set_individual_motor_speed(motor_num):
    """Set individual motor speed - röle aktif olmalı"""
    if not system_state['armed']:
        return jsonify({'status': 'error', 'message': 'System not armed'}), 400
    
    if not system_state['relay_brake_active']:
        return jsonify({'status': 'error', 'message': 'Relay brake must be active to control motors'}), 400
    
    if motor_num not in range(1, 7):
        return jsonify({'status': 'error', 'message': 'Invalid motor number'}), 400
    
    try:
        data = request.get_json()
        speed = int(data.get('speed', 0))
        
        if speed < 0 or speed > 100:
            return jsonify({'status': 'error', 'message': 'Speed must be 0-100'}), 400
        
        command = f"MOTOR:{motor_num}:SPEED:{speed}"
        success = arduino_controller.send_command_async(command)
        
        if success:
            with state_lock:
                individual_motor_speeds[motor_num] = speed
            
            logger.info(f"Motor {motor_num} speed set to {speed}%")
            return jsonify({
                'status': 'success',
                'motor': motor_num,
                'speed': speed,
                'message': f'Motor {motor_num} speed updated'
            })
        else:
            return jsonify({'status': 'error', 'message': 'Command queue full'}), 500
            
    except Exception as e:
        logger.error(f"Motor {motor_num} speed error: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

# Group Motor Control
@app.route('/api/levitation/start', methods=['POST'])
def start_levitation_group():
    """Start levitation group (Motors 1,2,3,4)"""
    if not system_state['armed']:
        return jsonify({'status': 'error', 'message': 'System not armed'}), 400
    
    if not system_state['relay_brake_active']:
        return jsonify({'status': 'error', 'message': 'Relay brake must be active to start motors'}), 400
    
    try:
        data = request.get_json() or {}
        speed = int(data.get('speed', group_speeds['levitation'] or 50))
        
        if speed < 0 or speed > 100:
            return jsonify({'status': 'error', 'message': 'Speed must be 0-100'}), 400
        
        command = f"LEV_GROUP:START:{speed}"
        success = arduino_controller.send_command_async(command)
        
        if success:
            with state_lock:
                group_speeds['levitation'] = speed
                for i in range(1, 5):
                    motor_states[i] = True
                    individual_motor_speeds[i] = speed
            
            logger.info(f"Levitation group (Motors 1,2,3,4) started at {speed}%")
            return jsonify({
                'status': 'success',
                'action': 'start',
                'speed': speed,
                'motors': list(range(1, 5)),
                'pins': [2, 4, 5, 6],
                'message': 'Levitation group started'
            })
        else:
            return jsonify({'status': 'error', 'message': 'Command queue full'}), 500
            
    except Exception as e:
        logger.error(f"Levitation start error: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/levitation/stop', methods=['POST'])
def stop_levitation_group():
    """Stop levitation group"""
    try:
        command = "LEV_GROUP:STOP"
        success = arduino_controller.send_command_async(command)
        
        if success:
            with state_lock:
                group_speeds['levitation'] = 0
                for i in range(1, 5):
                    motor_states[i] = False
                    individual_motor_speeds[i] = 0
            
            logger.info("Levitation group stopped")
            return jsonify({
                'status': 'success',
                'action': 'stop',
                'speed': 0,
                'motors': list(range(1, 5)),
                'message': 'Levitation group stopped'
            })
        else:
            return jsonify({'status': 'error', 'message': 'Command queue full'}), 500
            
    except Exception as e:
        logger.error(f"Levitation stop error: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/levitation/speed', methods=['POST'])
def set_levitation_speed():
    """Set levitation group speed"""
    if not system_state['armed']:
        return jsonify({'status': 'error', 'message': 'System not armed'}), 400
    
    if not system_state['relay_brake_active']:
        return jsonify({'status': 'error', 'message': 'Relay brake must be active to control motors'}), 400
    
    try:
        data = request.get_json()
        speed = int(data.get('speed', 0))
        
        if speed < 0 or speed > 100:
            return jsonify({'status': 'error', 'message': 'Speed must be 0-100'}), 400
        
        command = f"LEV_GROUP:SPEED:{speed}"
        success = arduino_controller.send_command_async(command)
        
        if success:
            with state_lock:
                group_speeds['levitation'] = speed
                for i in range(1, 5):
                    if motor_states[i]:
                        individual_motor_speeds[i] = speed
            
            logger.info(f"Levitation group speed set to {speed}%")
            return jsonify({
                'status': 'success',
                'speed': speed,
                'motors': list(range(1, 5)),
                'message': 'Levitation group speed updated'
            })
        else:
            return jsonify({'status': 'error', 'message': 'Command queue full'}), 500
            
    except Exception as e:
        logger.error(f"Levitation speed error: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/thrust/start', methods=['POST'])
def start_thrust_group():
    """Start thrust group (Motors 5,6 on pins 3,7)"""
    if not system_state['armed']:
        return jsonify({'status': 'error', 'message': 'System not armed'}), 400
    
    if not system_state['relay_brake_active']:
        return jsonify({'status': 'error', 'message': 'Relay brake must be active to start motors'}), 400
    
    try:
        data = request.get_json() or {}
        speed = int(data.get('speed', group_speeds['thrust'] or 50))
        
        if speed < 0 or speed > 100:
            return jsonify({'status': 'error', 'message': 'Speed must be 0-100'}), 400
        
        command = f"THR_GROUP:START:{speed}"
        success = arduino_controller.send_command_async(command)
        
        if success:
            with state_lock:
                group_speeds['thrust'] = speed
                for i in range(5, 7):
                    motor_states[i] = True
                    individual_motor_speeds[i] = speed
            
            logger.info(f"Thrust group (Motors 5,6 on pins 3,7) started at {speed}%")
            return jsonify({
                'status': 'success',
                'action': 'start',
                'speed': speed,
                'motors': list(range(5, 7)),
                'pins': [3, 7],
                'message': 'Thrust group started'
            })
        else:
            return jsonify({'status': 'error', 'message': 'Command queue full'}), 500
            
    except Exception as e:
        logger.error(f"Thrust start error: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/thrust/stop', methods=['POST'])
def stop_thrust_group():
    """Stop thrust group"""
    try:
        command = "THR_GROUP:STOP"
        success = arduino_controller.send_command_async(command)
        
        if success:
            with state_lock:
                group_speeds['thrust'] = 0
                for i in range(5, 7):
                    motor_states[i] = False
                    individual_motor_speeds[i] = 0
            
            logger.info("Thrust group stopped")
            return jsonify({
                'status': 'success',
                'action': 'stop',
                'speed': 0,
                'motors': list(range(5, 7)),
                'message': 'Thrust group stopped'
            })
        else:
            return jsonify({'status': 'error', 'message': 'Command queue full'}), 500
            
    except Exception as e:
        logger.error(f"Thrust stop error: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/thrust/speed', methods=['POST'])
def set_thrust_speed():
    """Set thrust group speed"""
    if not system_state['armed']:
        return jsonify({'status': 'error', 'message': 'System not armed'}), 400
    
    if not system_state['relay_brake_active']:
        return jsonify({'status': 'error', 'message': 'Relay brake must be active to control motors'}), 400
    
    try:
        data = request.get_json()
        speed = int(data.get('speed', 0))
        
        if speed < 0 or speed > 100:
            return jsonify({'status': 'error', 'message': 'Speed must be 0-100'}), 400
        
        command = f"THR_GROUP:SPEED:{speed}"
        success = arduino_controller.send_command_async(command)
        
        if success:
            with state_lock:
                group_speeds['thrust'] = speed
                for i in range(5, 7):
                    if motor_states[i]:
                        individual_motor_speeds[i] = speed
            
            logger.info(f"Thrust group speed set to {speed}%")
            return jsonify({
                'status': 'success',
                'speed': speed,
                'motors': list(range(5, 7)),
                'message': 'Thrust group speed updated'
            })
        else:
            return jsonify({'status': 'error', 'message': 'Command queue full'}), 500
            
    except Exception as e:
        logger.error(f"Thrust speed error: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/brake/<action>', methods=['POST'])
def control_brake(action):
    """Control software brake system"""
    if action not in ['on', 'off']:
        return jsonify({'status': 'error', 'message': 'Invalid action'}), 400
    
    try:
        command = "BRAKE_ON" if action == 'on' else "BRAKE_OFF"
        success, response = arduino_controller.send_command_sync(command, 3.0)
        
        if success:
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
                'response': response
            })
        else:
            return jsonify({'status': 'error', 'message': 'Arduino did not respond'}), 500
            
    except Exception as e:
        logger.error(f"Software brake control error: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/relay-brake/<action>', methods=['POST'])
def control_relay_brake(action):
    """Control relay brake system"""
    if action not in ['on', 'off']:
        return jsonify({'status': 'error', 'message': 'Invalid action'}), 400
    
    try:
        command = "RELAY_BRAKE_ON" if action == 'on' else "RELAY_BRAKE_OFF"
        success, response = arduino_controller.send_command_sync(command, 3.0)
        
        if success:
            with state_lock:
                system_state['relay_brake_active'] = (action == 'on')
                
                if not system_state['relay_brake_active']:
                    for i in range(1, 7):
                        motor_states[i] = False
                        individual_motor_speeds[i] = 0
                    group_speeds['levitation'] = 0
                    group_speeds['thrust'] = 0
            
            status = 'activated' if system_state['relay_brake_active'] else 'deactivated'
            logger.info(f"Relay brake {status}")
            
            return jsonify({
                'status': 'success',
                'action': action,
                'relay_brake_active': system_state['relay_brake_active'],
                'message': f'Relay brake {status}',
                'response': response
            })
        else:
            return jsonify({'status': 'error', 'message': 'Arduino did not respond'}), 500
            
    except Exception as e:
        logger.error(f"Relay brake control error: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/emergency-stop', methods=['POST'])
def emergency_stop():
    """Emergency stop all systems"""
    try:
        # Immediate local emergency actions
        with state_lock:
            system_state['armed'] = False
            system_state['brake_active'] = True
            system_state['relay_brake_active'] = False
            for i in range(1, 7):
                motor_states[i] = False
                individual_motor_speeds[i] = 0
            group_speeds['levitation'] = 0
            group_speeds['thrust'] = 0
        
        # Send emergency stop to Arduino (async)
        arduino_controller.send_command_async("EMERGENCY_STOP")
        
        logger.warning("EMERGENCY STOP ACTIVATED! All systems stopped!")
        
        return jsonify({
            'status': 'emergency_stop',
            'message': 'Emergency stop activated! All systems stopped and relay brake deactivated.',
            'all_stopped': True,
            'system_disarmed': True,
            'brake_activated': True,
            'relay_brake_activated': False
        })
            
    except Exception as e:
        logger.error(f"Emergency stop error: {e}")
        return jsonify({
            'status': 'emergency_stop',
            'message': 'Emergency stop activated with error',
            'error': str(e)
        })

@app.route('/api/test-connection', methods=['GET'])
def test_connection():
    """Test Arduino connection"""
    if arduino_controller._test_connection():
        return jsonify({
            'status': 'success',
            'message': 'Arduino connection successful',
            'port': arduino_controller.port,
            'attempts': arduino_controller.reconnect_attempts
        })
    else:
        return jsonify({
            'status': 'error',
            'message': 'Arduino connection failed',
            'port': arduino_controller.port,
            'attempts': arduino_controller.reconnect_attempts
        }), 500

@app.route('/api/reconnect', methods=['POST'])
def reconnect_arduino():
    """Reconnect to Arduino"""
    if arduino_controller.reconnect():
        return jsonify({
            'status': 'success',
            'message': 'Arduino reconnected successfully',
            'port': arduino_controller.port,
            'mpu6050_available': system_state['mpu6050_available']
        })
    else:
        return jsonify({
            'status': 'error',
            'message': 'Arduino reconnection failed'
        }), 500

@app.route('/api/ping', methods=['GET'])
def ping():
    """Health check endpoint"""
    active_motors = sum(1 for state in motor_states.values() if state)
    
    return jsonify({
        'status': 'ok',
        'timestamp': datetime.now().isoformat(),
        'arduino_connected': arduino_controller.is_connected,
        'system_armed': system_state['armed'],
        'brake_active': system_state['brake_active'],
        'relay_brake_active': system_state['relay_brake_active'],
        'mpu6050_available': system_state['mpu6050_available'],
        'active_motors': active_motors,
        'motor_pins': {
            'thrust': [3, 7],  # Motors 5,6
            'levitation': [2, 4, 5, 6]  # Motors 1,2,3,4
        },
        'version': '3.1-final-mpu6050-integrated'
    })

# Background monitoring
def background_monitor():
    """Background monitoring thread"""
    while True:
        try:
            if not arduino_controller.is_connected:
                logger.warning("Arduino connection lost")
                time.sleep(5)
                if arduino_controller.reconnect():
                    logger.info("Arduino reconnected")
            
            time.sleep(30)
            
        except Exception as e:
            logger.error(f"Monitor error: {e}")
            time.sleep(30)

# Start background monitor
monitor_thread = threading.Thread(target=background_monitor, daemon=True)
monitor_thread.start()

def signal_handler(sig, frame):
    """Graceful shutdown"""
    logger.info("Shutting down server...")
    
    try:
        # Stop background threads
        if 'monitor_thread' in globals() and monitor_thread.is_alive():
            logger.info("Stopping background monitor...")
        
        # Emergency stop if system is armed
        if system_state.get('armed', False):
            logger.info("System is armed - performing emergency stop...")
            try:
                emergency_stop()
            except Exception as e:
                logger.error(f"Emergency stop error: {e}")
        
        # Disconnect Arduino safely
        logger.info("Disconnecting Arduino...")
        arduino_controller.disconnect()
        
        logger.info("Graceful shutdown completed")
        
    except Exception as e:
        logger.error(f"Shutdown error: {e}")
    finally:
        # Force exit after cleanup
        sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)

if __name__ == '__main__':
    logger.info("SpectraLoop Backend Final v3.1 - MPU6050 Integrated starting...")
    
    try:
        # Check if Arduino controller initialized successfully
        if arduino_controller.is_connected:
            logger.info(f"Arduino port: {arduino_controller.port}")
            logger.info("Motor Pin Mapping:")
            logger.info("   Thrust Motors: M5->Pin3, M6->Pin7")
            logger.info("   Levitation Motors: M1->Pin2, M2->Pin4, M3->Pin5, M4->Pin6")
            logger.info("MPU6050 Sensor:")
            logger.info("   SDA->A4, SCL->A5, INT->Pin9")
        else:
            logger.warning("Arduino not connected - continuing without hardware")
        
        logger.info(f"Server: http://0.0.0.0:5001")
        logger.info("API Endpoints:")
        logger.info("   GET  /api/status")
        logger.info("   GET  /api/sensor-data (MPU6050)")
        logger.info("   GET  /api/sensor-data/raw (MPU6050 raw)")
        logger.info("   POST /api/system/arm|disarm")
        logger.info("   POST /api/motor/<num>/start|stop|speed")
        logger.info("   POST /api/levitation/start|stop|speed (M1,2,3,4)")
        logger.info("   POST /api/thrust/start|stop|speed (M5,6)")
        logger.info("   POST /api/brake/on|off (software brake)")
        logger.info("   POST /api/relay-brake/on|off (relay brake)")
        logger.info("   POST /api/emergency-stop")
        logger.info("   GET  /api/ping|test-connection")
        logger.info("   POST /api/reconnect")
        
        app.run(host='0.0.0.0', port=5001, debug=False, threaded=True)
        
    except KeyboardInterrupt:
        logger.info("Received interrupt signal - shutting down gracefully...")
        signal_handler(None, None)
    except Exception as e:
        logger.error(f"Server error: {e}")
        signal_handler(None, None)
    finally:
        logger.info("Cleaning up resources...")
        arduino_controller.disconnect()
        logger.info("Shutdown complete")