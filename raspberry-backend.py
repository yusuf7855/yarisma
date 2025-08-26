#!/usr/bin/env python3
"""
SpectraLoop Motor Control Backend - Complete Production v3.2
Enhanced stability and performance - MPU6050 Removed
Individual + Group motor control + Relay Brake Control
Motor Pin Mapping: İtki (3,7), Levitasyon (2,4,5,6)
Complete and error-free implementation
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

system_state = {
    'armed': False,
    'brake_active': False,
    'relay_brake_active': False,
    'connected': False,
    'last_response': None,
    'errors': 0,
    'commands': 0,
    'uptime': datetime.now()
}

# Thread synchronization
state_lock = threading.Lock()
shutdown_event = threading.Event()

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
        self.response_timeout = 2.0
        
        # Connection management
        self.connection_lock = threading.Lock()
        
        # Background threads
        self.processor_thread = None
        self.monitor_thread = None
        
        # Initialize connection safely
        try:
            if self.port:
                self.connect()
                self._start_command_processor()
                self._start_connection_monitor()
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
                        # Skip wildcard patterns for now
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
                    # Try to find a new port
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
                    logger.info("Arduino connection successful")
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
                        time.sleep(10)  # Wait before next attempt
                
                time.sleep(15)  # Monitor interval
                
            except Exception as e:
                logger.error(f"Connection monitor error: {e}")
                time.sleep(10)
        
        logger.info("Connection monitor thread stopped")
    
    def send_command_async(self, command):
        """Send command asynchronously via queue"""
        try:
            if shutdown_event.is_set():
                return False
            
            command_data = {
                'command': command,
                'timestamp': time.time(),
                'attempts': 0
            }
            self.command_queue.put(command_data, timeout=0.5)
            logger.debug(f"Command queued: {command}")
            return True
            
        except queue.Full:
            logger.warning(f"Command queue full, dropping: {command}")
            return False
        except Exception as e:
            logger.error(f"Async command error: {e}")
            return False
    
    def send_command_sync(self, command, timeout=3.0):
        """Send command synchronously with timeout"""
        if not self.is_connected or not self.connection or shutdown_event.is_set():
            return False, "Not connected"
        
        try:
            with self.connection_lock:
                # Rate limiting
                current_time = time.time()
                time_since_last = current_time - self.last_command_time
                if time_since_last < 0.05:  # 50ms minimum interval
                    time.sleep(0.05 - time_since_last)
                
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
                            
                            # Check if we have a complete response
                            if '\n' in response or len(response) > 100:
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
                    logger.debug(f"Command '{command}' response: '{response[:100]}...' ({len(response)} chars)")
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
                    # Retry the command
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
        
        # Stop connection temporarily
        old_connected = self.is_connected
        self.is_connected = False
        
        try:
            # Disconnect cleanly
            self.disconnect(keep_threads=True)
            time.sleep(2)
            
            # Reset attempts counter for manual reconnect
            self.reconnect_attempts = 0
            
            # Try to find port again
            new_port = self.find_arduino_port()
            if new_port:
                self.port = new_port
                logger.info(f"Using port for reconnection: {self.port}")
            
            # Attempt connection
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
        
        # Update connection state immediately
        self.is_connected = False
        system_state['connected'] = False
        
        # Close serial connection safely
        if self.connection:
            try:
                # Try to acquire lock with timeout
                acquired = self.connection_lock.acquire(timeout=3.0)
                try:
                    if acquired:
                        self.connection.close()
                        logger.info("Serial connection closed successfully")
                    else:
                        # Force close if we can't acquire lock
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
        
        # Stop threads if requested
        if not keep_threads:
            logger.info("Stopping background threads...")
            shutdown_event.set()
            
            # Wait for threads to finish
            if self.processor_thread and self.processor_thread.is_alive():
                self.processor_thread.join(timeout=2.0)
            
            if self.monitor_thread and self.monitor_thread.is_alive():
                self.monitor_thread.join(timeout=2.0)
        
        logger.info("Arduino disconnected successfully")

# Initialize Arduino controller
logger.info("Initializing Arduino controller...")
try:
    arduino_controller = ProductionArduinoController()
except Exception as e:
    logger.error(f"Failed to initialize Arduino controller: {e}")
    arduino_controller = None

# API Routes
@app.route('/api/status', methods=['GET'])
def get_status():
    """Get comprehensive system status"""
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
                'version': '3.2-production-complete'
            })
    except Exception as e:
        logger.error(f"Status endpoint error: {e}")
        return jsonify({'error': str(e), 'connected': False}), 500

@app.route('/api/system/arm', methods=['POST'])
def arm_system():
    """Arm the system - relay must be active"""
    if not arduino_controller or not arduino_controller.is_connected:
        return jsonify({
            'status': 'error',
            'message': 'Arduino not connected'
        }), 503
    
    if not system_state['relay_brake_active']:
        return jsonify({
            'status': 'error', 
            'message': 'Cannot arm while relay brake is inactive'
        }), 400
    
    try:
        # Clear input/output buffers
        if arduino_controller.connection:
            arduino_controller.connection.flushInput()
            arduino_controller.connection.flushOutput()
        
        # Send ARM command
        success, response = arduino_controller.send_command_sync("ARM", timeout=5.0)
        
        if success and response:
            # Parse response lines
            response_lines = [line.strip() for line in response.split('\n') if line.strip()]
            
            for line in response_lines:
                line_upper = line.upper()
                
                if "ARMED" in line_upper and "ERROR" not in line_upper:
                    with state_lock:
                        system_state['armed'] = True
                    logger.info("System ARMED successfully")
                    return jsonify({
                        'status': 'armed',
                        'message': 'System armed successfully',
                        'response': line
                    })
                
                # Check for specific error conditions
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
                    else:
                        return jsonify({
                            'status': 'error',
                            'message': f'Arduino error: {line}'
                        }), 400
            
            # No clear ARMED response found
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
                # Reset all motor states
                for i in range(1, 7):
                    motor_states[i] = False
                    individual_motor_speeds[i] = 0
                group_speeds['levitation'] = 0
                group_speeds['thrust'] = 0
            
            logger.info("System DISARMED successfully")
            return jsonify({
                'status': 'disarmed',
                'message': 'System disarmed successfully',
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

# Individual Motor Control Routes
@app.route('/api/motor/<int:motor_num>/start', methods=['POST'])
def start_individual_motor(motor_num):
    """Start individual motor"""
    if not arduino_controller or not arduino_controller.is_connected:
        return jsonify({'status': 'error', 'message': 'Arduino not connected'}), 503
    
    if not system_state['armed']:
        return jsonify({'status': 'error', 'message': 'System not armed'}), 400
    
    if not system_state['relay_brake_active']:
        return jsonify({'status': 'error', 'message': 'Relay brake must be active to start motors'}), 400
    
    if motor_num not in range(1, 7):
        return jsonify({'status': 'error', 'message': 'Invalid motor number (1-6)'}), 400
    
    try:
        data = request.get_json() or {}
        speed = int(data.get('speed', 50))
        
        if not 0 <= speed <= 100:
            return jsonify({'status': 'error', 'message': 'Speed must be 0-100'}), 400
        
        command = f"MOTOR:{motor_num}:START:{speed}"
        success = arduino_controller.send_command_async(command)
        
        if success:
            with state_lock:
                motor_states[motor_num] = True
                individual_motor_speeds[motor_num] = speed
            
            motor_type = "Thrust" if motor_num in [5, 6] else "Levitation"
            pin_mapping = {1: 2, 2: 4, 3: 5, 4: 6, 5: 3, 6: 7}
            pin_num = pin_mapping.get(motor_num, "Unknown")
            
            logger.info(f"Motor {motor_num} ({motor_type}, Pin {pin_num}) started at {speed}%")
            return jsonify({
                'status': 'success',
                'motor': motor_num,
                'action': 'start',
                'speed': speed,
                'type': motor_type,
                'pin': pin_num,
                'message': f'Motor {motor_num} started at {speed}%'
            })
        else:
            return jsonify({'status': 'error', 'message': 'Command queue full or error'}), 500
            
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
            return jsonify({'status': 'error', 'message': 'Command queue full or error'}), 500
            
    except Exception as e:
        logger.error(f"Motor {motor_num} stop error: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/motor/<int:motor_num>/speed', methods=['POST'])
def set_individual_motor_speed(motor_num):
    """Set individual motor speed"""
    if not arduino_controller or not arduino_controller.is_connected:
        return jsonify({'status': 'error', 'message': 'Arduino not connected'}), 503
    
    if not system_state['armed']:
        return jsonify({'status': 'error', 'message': 'System not armed'}), 400
    
    if not system_state['relay_brake_active']:
        return jsonify({'status': 'error', 'message': 'Relay brake must be active to control motors'}), 400
    
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
        success = arduino_controller.send_command_async(command)
        
        if success:
            with state_lock:
                individual_motor_speeds[motor_num] = speed
            
            logger.info(f"Motor {motor_num} speed set to {speed}%")
            return jsonify({
                'status': 'success',
                'motor': motor_num,
                'speed': speed,
                'message': f'Motor {motor_num} speed set to {speed}%'
            })
        else:
            return jsonify({'status': 'error', 'message': 'Command queue full or error'}), 500
            
    except ValueError:
        return jsonify({'status': 'error', 'message': 'Invalid speed value'}), 400
    except Exception as e:
        logger.error(f"Motor {motor_num} speed error: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

# Group Motor Control Routes
@app.route('/api/levitation/start', methods=['POST'])
def start_levitation_group():
    """Start levitation group (Motors 1,2,3,4)"""
    if not arduino_controller or not arduino_controller.is_connected:
        return jsonify({'status': 'error', 'message': 'Arduino not connected'}), 503
    
    if not system_state['armed']:
        return jsonify({'status': 'error', 'message': 'System not armed'}), 400
    
    if not system_state['relay_brake_active']:
        return jsonify({'status': 'error', 'message': 'Relay brake must be active to start motors'}), 400
    
    try:
        data = request.get_json() or {}
        speed = int(data.get('speed', group_speeds['levitation'] or 50))
        
        if not 0 <= speed <= 100:
            return jsonify({'status': 'error', 'message': 'Speed must be 0-100'}), 400
        
        command = f"LEV_GROUP:START:{speed}"
        success = arduino_controller.send_command_async(command)
        
        if success:
            with state_lock:
                group_speeds['levitation'] = speed
                for i in range(1, 5):  # Motors 1,2,3,4
                    motor_states[i] = True
                    individual_motor_speeds[i] = speed
            
            logger.info(f"Levitation group (Motors 1,2,3,4) started at {speed}%")
            return jsonify({
                'status': 'success',
                'action': 'start',
                'speed': speed,
                'motors': list(range(1, 5)),
                'pins': [2, 4, 5, 6],
                'message': 'Levitation group started',
                'group': 'levitation'
            })
        else:
            return jsonify({'status': 'error', 'message': 'Command queue full or error'}), 500
            
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
        success = arduino_controller.send_command_async(command)
        
        if success:
            with state_lock:
                group_speeds['levitation'] = 0
                for i in range(1, 5):  # Motors 1,2,3,4
                    motor_states[i] = False
                    individual_motor_speeds[i] = 0
            
            logger.info("Levitation group stopped")
            return jsonify({
                'status': 'success',
                'action': 'stop',
                'speed': 0,
                'motors': list(range(1, 5)),
                'message': 'Levitation group stopped',
                'group': 'levitation'
            })
        else:
            return jsonify({'status': 'error', 'message': 'Command queue full or error'}), 500
            
    except Exception as e:
        logger.error(f"Levitation stop error: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/levitation/speed', methods=['POST'])
def set_levitation_speed():
    """Set levitation group speed"""
    if not arduino_controller or not arduino_controller.is_connected:
        return jsonify({'status': 'error', 'message': 'Arduino not connected'}), 503
    
    if not system_state['armed']:
        return jsonify({'status': 'error', 'message': 'System not armed'}), 400
    
    if not system_state['relay_brake_active']:
        return jsonify({'status': 'error', 'message': 'Relay brake must be active to control motors'}), 400
    
    try:
        data = request.get_json()
        if not data or 'speed' not in data:
            return jsonify({'status': 'error', 'message': 'Speed parameter required'}), 400
        
        speed = int(data.get('speed'))
        
        if not 0 <= speed <= 100:
            return jsonify({'status': 'error', 'message': 'Speed must be 0-100'}), 400
        
        command = f"LEV_GROUP:SPEED:{speed}"
        success = arduino_controller.send_command_async(command)
        
        if success:
            with state_lock:
                group_speeds['levitation'] = speed
                for i in range(1, 5):  # Motors 1,2,3,4
                    if motor_states[i]:
                        individual_motor_speeds[i] = speed
            
            logger.info(f"Levitation group speed set to {speed}%")
            return jsonify({
                'status': 'success',
                'speed': speed,
                'motors': list(range(1, 5)),
                'message': 'Levitation group speed updated',
                'group': 'levitation'
            })
        else:
            return jsonify({'status': 'error', 'message': 'Command queue full or error'}), 500
            
    except ValueError:
        return jsonify({'status': 'error', 'message': 'Invalid speed value'}), 400
    except Exception as e:
        logger.error(f"Levitation speed error: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/thrust/start', methods=['POST'])
def start_thrust_group():
    """Start thrust group (Motors 5,6 on pins 3,7)"""
    if not arduino_controller or not arduino_controller.is_connected:
        return jsonify({'status': 'error', 'message': 'Arduino not connected'}), 503
    
    if not system_state['armed']:
        return jsonify({'status': 'error', 'message': 'System not armed'}), 400
    
    if not system_state['relay_brake_active']:
        return jsonify({'status': 'error', 'message': 'Relay brake must be active to start motors'}), 400
    
    try:
        data = request.get_json() or {}
        speed = int(data.get('speed', group_speeds['thrust'] or 50))
        
        if not 0 <= speed <= 100:
            return jsonify({'status': 'error', 'message': 'Speed must be 0-100'}), 400
        
        command = f"THR_GROUP:START:{speed}"
        success = arduino_controller.send_command_async(command)
        
        if success:
            with state_lock:
                group_speeds['thrust'] = speed
                for i in range(5, 7):  # Motors 5,6
                    motor_states[i] = True
                    individual_motor_speeds[i] = speed
            
            logger.info(f"Thrust group (Motors 5,6 on pins 3,7) started at {speed}%")
            return jsonify({
                'status': 'success',
                'action': 'start',
                'speed': speed,
                'motors': list(range(5, 7)),
                'pins': [3, 7],
                'message': 'Thrust group started',
                'group': 'thrust'
            })
        else:
            return jsonify({'status': 'error', 'message': 'Command queue full or error'}), 500
            
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
        success = arduino_controller.send_command_async(command)
        
        if success:
            with state_lock:
                group_speeds['thrust'] = 0
                for i in range(5, 7):  # Motors 5,6
                    motor_states[i] = False
                    individual_motor_speeds[i] = 0
            
            logger.info("Thrust group stopped")
            return jsonify({
                'status': 'success',
                'action': 'stop',
                'speed': 0,
                'motors': list(range(5, 7)),
                'message': 'Thrust group stopped',
                'group': 'thrust'
            })
        else:
            return jsonify({'status': 'error', 'message': 'Command queue full or error'}), 500
            
    except Exception as e:
        logger.error(f"Thrust stop error: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/thrust/speed', methods=['POST'])
def set_thrust_speed():
    """Set thrust group speed"""
    if not arduino_controller or not arduino_controller.is_connected:
        return jsonify({'status': 'error', 'message': 'Arduino not connected'}), 503
    
    if not system_state['armed']:
        return jsonify({'status': 'error', 'message': 'System not armed'}), 400
    
    if not system_state['relay_brake_active']:
        return jsonify({'status': 'error', 'message': 'Relay brake must be active to control motors'}), 400
    
    try:
        data = request.get_json()
        if not data or 'speed' not in data:
            return jsonify({'status': 'error', 'message': 'Speed parameter required'}), 400
        
        speed = int(data.get('speed'))
        
        if not 0 <= speed <= 100:
            return jsonify({'status': 'error', 'message': 'Speed must be 0-100'}), 400
        
        command = f"THR_GROUP:SPEED:{speed}"
        success = arduino_controller.send_command_async(command)
        
        if success:
            with state_lock:
                group_speeds['thrust'] = speed
                for i in range(5, 7):  # Motors 5,6
                    if motor_states[i]:
                        individual_motor_speeds[i] = speed
            
            logger.info(f"Thrust group speed set to {speed}%")
            return jsonify({
                'status': 'success',
                'speed': speed,
                'motors': list(range(5, 7)),
                'message': 'Thrust group speed updated',
                'group': 'thrust'
            })
        else:
            return jsonify({'status': 'error', 'message': 'Command queue full or error'}), 500
            
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
        
        if success:
            with state_lock:
                system_state['brake_active'] = (action == 'on')
                
                if system_state['brake_active']:
                    # Software brake ON - stop all motors
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
                'response': response.strip()
            })
        else:
            return jsonify({
                'status': 'error', 
                'message': f'Arduino did not respond properly: {response}'
            }), 500
            
    except Exception as e:
        logger.error(f"Software brake control error: {e}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@app.route('/api/relay-brake/<action>', methods=['POST'])
def control_relay_brake(action):
    """Control relay brake system"""
    if not arduino_controller or not arduino_controller.is_connected:
        return jsonify({'status': 'error', 'message': 'Arduino not connected'}), 503
    
    if action not in ['on', 'off']:
        return jsonify({'status': 'error', 'message': 'Invalid action. Use "on" or "off"'}), 400
    
    try:
        command = "RELAY_BRAKE_ON" if action == 'on' else "RELAY_BRAKE_OFF"
        success, response = arduino_controller.send_command_sync(command, timeout=3.0)
        
        if success:
            with state_lock:
                system_state['relay_brake_active'] = (action == 'on')
                
                if not system_state['relay_brake_active']:
                    # Relay brake OFF - stop all motors and disarm system
                    system_state['armed'] = False
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
                'system_disarmed': not system_state['relay_brake_active'],
                'message': f'Relay brake {status}',
                'response': response.strip()
            })
        else:
            return jsonify({
                'status': 'error', 
                'message': f'Arduino did not respond properly: {response}'
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
            for i in range(1, 7):
                motor_states[i] = False
                individual_motor_speeds[i] = 0
            group_speeds['levitation'] = 0
            group_speeds['thrust'] = 0
        
        # Send emergency stop to Arduino if connected
        if arduino_controller and arduino_controller.is_connected:
            try:
                arduino_controller.send_command_async("EMERGENCY_STOP")
            except Exception as e:
                logger.warning(f"Could not send emergency stop to Arduino: {e}")
        
        logger.warning("EMERGENCY STOP ACTIVATED! All systems stopped!")
        
        return jsonify({
            'status': 'emergency_stop',
            'message': 'Emergency stop activated! All systems stopped and relay brake deactivated.',
            'all_stopped': True,
            'system_disarmed': True,
            'brake_activated': True,
            'relay_brake_activated': False,
            'timestamp': datetime.now().isoformat()
        })
            
    except Exception as e:
        logger.error(f"Emergency stop error: {e}")
        return jsonify({
            'status': 'emergency_stop',
            'message': 'Emergency stop activated with error',
            'error': str(e),
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
                'attempts': arduino_controller.reconnect_attempts
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
                'baudrate': arduino_controller.baudrate
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
            'motor_pins': {
                'thrust': [3, 7],        # Motors 5,6
                'levitation': [2, 4, 5, 6]  # Motors 1,2,3,4
            },
            'version': '3.2-production-complete',
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
            'GET /api/ping',
            'GET /api/test-connection',
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
            
            # Clean up command queue if it gets too full
            if arduino_controller and arduino_controller.command_queue.qsize() > 50:
                logger.warning("Command queue getting full, clearing old commands")
                try:
                    while arduino_controller.command_queue.qsize() > 25:
                        arduino_controller.command_queue.get_nowait()
                        arduino_controller.command_queue.task_done()
                except queue.Empty:
                    pass
            
            shutdown_event.wait(30)  # Wait 30 seconds or until shutdown
            
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
        # Set shutdown event
        shutdown_event.set()
        
        # Emergency stop if system is armed
        if system_state.get('armed', False):
            logger.info("System is armed - performing emergency stop...")
            try:
                emergency_stop()
            except Exception as e:
                logger.error(f"Emergency stop during shutdown error: {e}")
        
        # Disconnect Arduino safely
        if arduino_controller:
            logger.info("Disconnecting Arduino...")
            arduino_controller.disconnect()
        
        # Wait for background threads to finish
        logger.info("Waiting for background threads to finish...")
        if monitor_thread.is_alive():
            monitor_thread.join(timeout=5.0)
        
        logger.info("Graceful shutdown completed")
        
    except Exception as e:
        logger.error(f"Shutdown error: {e}")
    finally:
        # Force exit
        sys.exit(0)

# Register signal handlers
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

if __name__ == '__main__':
    logger.info("=" * 60)
    logger.info("SpectraLoop Backend Final v3.2 - Production Complete")
    logger.info("=" * 60)
    
    try:
        # System information
        if arduino_controller and arduino_controller.is_connected:
            logger.info(f"Arduino Status: Connected")
            logger.info(f"Arduino Port: {arduino_controller.port}")
            logger.info(f"Arduino Baudrate: {arduino_controller.baudrate}")
        else:
            logger.warning("Arduino Status: Not Connected")
        
        logger.info("Motor Pin Mapping:")
        logger.info("   Thrust Motors: M5->Pin3, M6->Pin7")
        logger.info("   Levitation Motors: M1->Pin2, M2->Pin4, M3->Pin5, M4->Pin6")
        logger.info("   Relay Brake: Pin8")
        
        logger.info("Server Configuration:")
        logger.info("   Host: 0.0.0.0")
        logger.info("   Port: 5001")
        logger.info("   Debug: False")
        logger.info("   Threaded: True")
        
        logger.info("Available API Endpoints:")
        logger.info("   GET  /api/status - System status")
        logger.info("   GET  /api/ping - Health check")
        logger.info("   GET  /api/test-connection - Test Arduino connection")
        logger.info("   POST /api/system/arm - Arm system")
        logger.info("   POST /api/system/disarm - Disarm system")
        logger.info("   POST /api/motor/<num>/start - Start motor")
        logger.info("   POST /api/motor/<num>/stop - Stop motor")
        logger.info("   POST /api/motor/<num>/speed - Set motor speed")
        logger.info("   POST /api/levitation/start - Start levitation group (M1,2,3,4)")
        logger.info("   POST /api/levitation/stop - Stop levitation group")
        logger.info("   POST /api/levitation/speed - Set levitation group speed")
        logger.info("   POST /api/thrust/start - Start thrust group (M5,6)")
        logger.info("   POST /api/thrust/stop - Stop thrust group")
        logger.info("   POST /api/thrust/speed - Set thrust group speed")
        logger.info("   POST /api/brake/on|off - Software brake control")
        logger.info("   POST /api/relay-brake/on|off - Relay brake control")
        logger.info("   POST /api/emergency-stop - Emergency stop all systems")
        logger.info("   POST /api/reconnect - Reconnect Arduino")
        
        logger.info("=" * 60)
        logger.info("Starting Flask server...")
        
        # Start Flask application
        app.run(
            host='0.0.0.0', 
            port=5001, 
            debug=False, 
            threaded=True,
            use_reloader=False  # Prevent double initialization
        )
        
    except KeyboardInterrupt:
        logger.info("Received interrupt signal - shutting down gracefully...")
        signal_handler(signal.SIGINT, None)
    except Exception as e:
        logger.error(f"Server startup error: {e}")
        signal_handler(signal.SIGTERM, None)
    finally:
        logger.info("Server shutdown complete")