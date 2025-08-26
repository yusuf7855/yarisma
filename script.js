/*
 * SpectraLoop Frontend JavaScript v3.2 - Production
 * Complete Motor Control System
 * Backend IP: Update BACKEND_URL with your Raspberry Pi IP
 */

// Configuration - UPDATE WITH YOUR RASPBERRY PI IP
const BACKEND_URL = 'http://172.20.10.3:5001';

// System State Management
let systemState = {
    armed: false,
    brakeActive: false,
    relayBrakeActive: false,
    connected: false,
    motorStates: {1: false, 2: false, 3: false, 4: false, 5: false, 6: false},
    individualMotorSpeeds: {1: 0, 2: 0, 3: 0, 4: 0, 5: 0, 6: 0},
    groupSpeeds: {levitation: 0, thrust: 0},
    connectionStatus: {backend: false, arduino: false}
};

// Application State
let appState = {
    requestCount: 0,
    errorCount: 0,
    lastRequestTime: 0,
    consecutiveErrors: 0,
    commandLog: [],
    statusUpdateInterval: null,
    isInitialized: false
};

// Constants
const CONFIG = {
    REQUEST_THROTTLE: 50,
    MAX_RETRIES: 3,
    STATUS_UPDATE_INTERVAL: 2000,
    CONNECTION_TIMEOUT: 8000,
    MAX_LOG_ENTRIES: 25,
    NOTIFICATION_TIMEOUT: 4000
};

// Utility Functions
class Utils {
    static throttle(func, delay) {
        let timeoutId;
        return (...args) => {
            clearTimeout(timeoutId);
            timeoutId = setTimeout(() => func.apply(this, args), delay);
        };
    }

    static debounce(func, delay) {
        let timeoutId;
        return (...args) => {
            clearTimeout(timeoutId);
            timeoutId = setTimeout(() => func.apply(this, args), delay);
        };
    }

    static formatTime(date) {
        return date.toLocaleTimeString('tr-TR', {
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit'
        });
    }

    static formatUptime(seconds) {
        const hours = Math.floor(seconds / 3600);
        const minutes = Math.floor((seconds % 3600) / 60);
        const secs = seconds % 60;
        
        if (hours > 0) {
            return `${hours}h ${minutes}m`;
        } else if (minutes > 0) {
            return `${minutes}m ${secs}s`;
        } else {
            return `${secs}s`;
        }
    }

    static clamp(value, min, max) {
        return Math.min(Math.max(value, min), max);
    }
}

// HTTP Request Handler
class RequestHandler {
    static async makeRequest(url, options = {}, timeout = CONFIG.CONNECTION_TIMEOUT, retries = CONFIG.MAX_RETRIES) {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), timeout);
        
        for (let attempt = 0; attempt < retries; attempt++) {
            try {
                console.log(`Making request to ${url} (attempt ${attempt + 1}/${retries})`);
                
                const response = await fetch(url, {
                    ...options,
                    signal: controller.signal,
                    headers: {
                        'Content-Type': 'application/json',
                        'Accept': 'application/json',
                        ...options.headers
                    },
                    mode: 'cors',
                    credentials: 'omit'
                });
                
                clearTimeout(timeoutId);
                
                if (!response.ok) {
                    throw new Error(`HTTP ${response.status}: ${response.statusText}`);
                }
                
                appState.requestCount++;
                appState.consecutiveErrors = 0;
                ConnectionManager.updateConnectionStatus('backend', true);
                console.log(`Request successful: ${url}`);
                return response;
                
            } catch (error) {
                console.warn(`Request failed (attempt ${attempt + 1}): ${error.message}`);
                
                if (attempt === retries - 1) {
                    clearTimeout(timeoutId);
                    appState.errorCount++;
                    appState.consecutiveErrors++;
                    ConnectionManager.updateConnectionStatus('backend', false);
                    
                    if (error.name === 'AbortError') {
                        throw new Error('Request timed out');
                    }
                    throw error;
                }
                
                await new Promise(resolve => setTimeout(resolve, 1000 * (attempt + 1)));
            }
        }
    }

    static throttleRequest(callback) {
        const now = Date.now();
        if (now - appState.lastRequestTime < CONFIG.REQUEST_THROTTLE) {
            setTimeout(() => RequestHandler.throttleRequest(callback), CONFIG.REQUEST_THROTTLE);
            return;
        }
        appState.lastRequestTime = now;
        callback();
    }
}

// Command Logger
class CommandLogger {
    static log(command, success = true, details = '') {
        const timestamp = Utils.formatTime(new Date());
        const status = success ? '✅' : '❌';
        const logEntry = {
            timestamp,
            status,
            command,
            details,
            id: Date.now()
        };
        
        appState.commandLog.unshift(logEntry);
        if (appState.commandLog.length > CONFIG.MAX_LOG_ENTRIES) {
            appState.commandLog.pop();
        }
        
        this.updateLogDisplay();
    }

    static updateLogDisplay() {
        const logElement = document.getElementById('command-log');
        if (!logElement) return;

        logElement.innerHTML = appState.commandLog
            .map(entry => 
                `<div class="log-entry">
                    ${entry.timestamp} ${entry.status} ${entry.command}
                    ${entry.details ? ` - ${entry.details}` : ''}
                </div>`
            )
            .join('');
        
        logElement.scrollTop = 0;
    }

    static clear() {
        appState.commandLog = [];
        this.updateLogDisplay();
    }
}

// Notification System
class NotificationManager {
    static show(message, type = 'info', duration = CONFIG.NOTIFICATION_TIMEOUT) {
        const notification = document.getElementById('notification');
        const messageElement = document.getElementById('notification-message');
        const iconElement = document.getElementById('notification-icon');
        
        if (!notification || !messageElement || !iconElement) return;

        // Set icon based on type
        const icons = {
            success: '✅',
            error: '❌',
            warning: '⚠️',
            info: 'ℹ️'
        };

        iconElement.textContent = icons[type] || icons.info;
        messageElement.textContent = message;
        
        // Remove existing classes and add new ones
        notification.className = `notification ${type} show`;
        
        // Auto hide after duration
        setTimeout(() => {
            this.hide();
        }, duration);
    }

    static hide() {
        const notification = document.getElementById('notification');
        if (notification) {
            notification.classList.remove('show');
        }
    }
}

// Connection Manager
class ConnectionManager {
    static updateConnectionStatus(type, connected) {
        systemState.connectionStatus[type] = connected;
        
        const statusElement = document.getElementById(
            type === 'backend' ? 'backend-status' : 'arduino-connection-status'
        );
        
        const textElement = document.getElementById(
            type === 'backend' ? 'backend-text' : 'arduino-text'
        );
        
        if (statusElement) {
            statusElement.className = connected ? 'connection-dot connected' : 'connection-dot';
        }
        
        if (textElement) {
            textElement.textContent = connected ? 'Bağlı' : 'Bağlantısız';
        }
        
        if (type === 'arduino') {
            const arduinoStatus = document.getElementById('arduino-status');
            if (arduinoStatus) {
                arduinoStatus.textContent = connected ? 'Bağlı' : 'Bağlantısız';
                arduinoStatus.className = connected ? 'status-value status-connected' : 'status-value status-error';
            }
        }

        // Update last update time
        if (connected) {
            const lastUpdateElement = document.getElementById('last-update');
            if (lastUpdateElement) {
                lastUpdateElement.textContent = Utils.formatTime(new Date());
            }
        }
    }

    static async testConnection() {
        try {
            NotificationManager.show('🔍 Bağlantı test ediliyor...', 'info');
            
            const response = await RequestHandler.makeRequest(`${BACKEND_URL}/api/test-connection`);
            const data = await response.json();
            
            if (data.status === 'success') {
                CommandLogger.log('Bağlantı testi başarılı', true);
                NotificationManager.show('✅ Bağlantı testi başarılı!', 'success');
                this.updateConnectionStatus('backend', true);
                this.updateConnectionStatus('arduino', true);
            } else {
                throw new Error(data.message || 'Test failed');
            }
            
        } catch (error) {
            CommandLogger.log('Bağlantı testi', false, error.message);
            NotificationManager.show(`❌ Bağlantı testi başarısız: ${error.message}`, 'error');
            this.updateConnectionStatus('backend', false);
            this.updateConnectionStatus('arduino', false);
        }
    }

    static async reconnectArduino() {
        try {
            NotificationManager.show('🔄 Arduino yeniden bağlanıyor...', 'info');
            
            const response = await RequestHandler.makeRequest(`${BACKEND_URL}/api/reconnect`, {
                method: 'POST'
            });
            
            const data = await response.json();
            
            if (data.status === 'success') {
                CommandLogger.log('Arduino yeniden bağlandı', true);
                NotificationManager.show('✅ Arduino yeniden bağlandı!', 'success');
                setTimeout(StatusManager.pollStatus, 1000);
            } else {
                throw new Error(data.message || 'Reconnection failed');
            }
            
        } catch (error) {
            CommandLogger.log('Arduino yeniden bağlanma', false, error.message);
            NotificationManager.show(`❌ Arduino yeniden bağlanamadı: ${error.message}`, 'error');
        }
    }
}

// Motor Control
class MotorController {
    static async startMotor(motorNum) {
        if (!systemState.armed) {
            NotificationManager.show('⚠️ Önce sistemi hazırlamanız gerekiyor!', 'warning');
            return;
        }

        if (!systemState.relayBrakeActive) {
            NotificationManager.show('⚠️ Röle pasif! Önce röleyi aktif yapın.', 'warning');
            return;
        }

        RequestHandler.throttleRequest(async () => {
            try {
                const speed = parseInt(document.getElementById(`motor${motorNum}-speed-input`).value) || 50;
                
                const response = await RequestHandler.makeRequest(`${BACKEND_URL}/api/motor/${motorNum}/start`, {
                    method: 'POST',
                    body: JSON.stringify({speed: speed})
                });

                if (response.ok) {
                    const data = await response.json();
                    systemState.motorStates[motorNum] = true;
                    systemState.individualMotorSpeeds[motorNum] = speed;
                    UIManager.updateMotorStatus(motorNum, true, speed);
                    UIManager.updateMotorCount();
                    CommandLogger.log(`Motor ${motorNum} başlatıldı`, true, `${speed}%`);
                    NotificationManager.show(`🎯 Motor ${motorNum} başlatıldı!`, 'success');
                }

            } catch (error) {
                CommandLogger.log(`Motor ${motorNum} başlatma`, false, error.message);
                NotificationManager.show(`❌ Motor ${motorNum} başlatılamadı: ${error.message}`, 'error');
                console.error('Motor start error:', error);
            }
        });
    }

    static async stopMotor(motorNum) {
        RequestHandler.throttleRequest(async () => {
            try {
                const response = await RequestHandler.makeRequest(`${BACKEND_URL}/api/motor/${motorNum}/stop`, {
                    method: 'POST'
                });

                if (response.ok) {
                    systemState.motorStates[motorNum] = false;
                    systemState.individualMotorSpeeds[motorNum] = 0;
                    UIManager.updateMotorStatus(motorNum, false, 0);
                    UIManager.updateMotorCount();
                    CommandLogger.log(`Motor ${motorNum} durduruldu`, true);
                    NotificationManager.show(`🎯 Motor ${motorNum} durduruldu!`, 'success');
                }

            } catch (error) {
                CommandLogger.log(`Motor ${motorNum} durdurma`, false, error.message);
                NotificationManager.show(`❌ Motor ${motorNum} durdurulamadı: ${error.message}`, 'error');
                console.error('Motor stop error:', error);
            }
        });
    }

    static async setMotorSpeed(motorNum, speed) {
        if (!systemState.armed) {
            NotificationManager.show('⚠️ Sistem armed değil!', 'warning');
            return;
        }

        if (!systemState.relayBrakeActive) {
            NotificationManager.show('⚠️ Röle pasif! Önce röleyi aktif yapın.', 'warning');
            return;
        }

        speed = Utils.clamp(parseInt(speed), 0, 100);
        if (isNaN(speed)) {
            NotificationManager.show('⚠️ Geçersiz hız değeri!', 'warning');
            return;
        }

        RequestHandler.throttleRequest(async () => {
            try {
                const response = await RequestHandler.makeRequest(`${BACKEND_URL}/api/motor/${motorNum}/speed`, {
                    method: 'POST',
                    body: JSON.stringify({speed: speed})
                });

                if (response.ok) {
                    systemState.individualMotorSpeeds[motorNum] = speed;
                    UIManager.updateMotorSpeedDisplay(motorNum, speed);
                    CommandLogger.log(`Motor ${motorNum} hızı`, true, `${speed}%`);
                }

            } catch (error) {
                CommandLogger.log(`Motor ${motorNum} hız`, false, error.message);
                NotificationManager.show(`❌ Motor ${motorNum} hız ayarlanamadı`, 'error');
                console.error('Motor speed error:', error);
            }
        });
    }
}

// Group Control
class GroupController {
    static async startGroup(groupType) {
        if (!systemState.armed) {
            NotificationManager.show('⚠️ Önce sistemi hazırlamanız gerekiyor!', 'warning');
            return;
        }

        if (!systemState.relayBrakeActive) {
            NotificationManager.show('⚠️ Röle pasif! Önce röleyi aktif yapın.', 'warning');
            return;
        }

        RequestHandler.throttleRequest(async () => {
            try {
                const speed = systemState.groupSpeeds[groupType] || 50;
                
                const response = await RequestHandler.makeRequest(`${BACKEND_URL}/api/${groupType}/start`, {
                    method: 'POST',
                    body: JSON.stringify({speed: speed})
                });

                if (response.ok) {
                    const data = await response.json();
                    systemState.groupSpeeds[groupType] = speed;
                    
                    // Update motor states
                    const motorRange = groupType === 'levitation' ? [1,2,3,4] : [5,6];
                    motorRange.forEach(motorNum => {
                        systemState.motorStates[motorNum] = true;
                        systemState.individualMotorSpeeds[motorNum] = speed;
                        UIManager.updateMotorStatus(motorNum, true, speed);
                        const inputElement = document.getElementById(`motor${motorNum}-speed-input`);
                        if (inputElement) inputElement.value = speed;
                    });
                    
                    UIManager.updateGroupSpeedDisplay(groupType, speed);
                    UIManager.updateMotorCount();
                    
                    const groupName = groupType === 'levitation' ? 'Levitasyon' : 'İtki';
                    CommandLogger.log(`${groupName} grubu başlatıldı`, true, `${speed}% - M${motorRange.join(',')}`);
                    NotificationManager.show(`🚀 ${groupName} grubu başlatıldı! (M${motorRange.join(',')})`, 'success');
                }

            } catch (error) {
                CommandLogger.log(`${groupType} başlatma`, false, error.message);
                NotificationManager.show(`❌ ${groupType} grubu başlatılamadı: ${error.message}`, 'error');
                console.error('Group start error:', error);
            }
        });
    }

    static async stopGroup(groupType) {
        RequestHandler.throttleRequest(async () => {
            try {
                const response = await RequestHandler.makeRequest(`${BACKEND_URL}/api/${groupType}/stop`, {
                    method: 'POST'
                });

                if (response.ok) {
                    systemState.groupSpeeds[groupType] = 0;
                    
                    // Update motor states
                    const motorRange = groupType === 'levitation' ? [1,2,3,4] : [5,6];
                    motorRange.forEach(motorNum => {
                        systemState.motorStates[motorNum] = false;
                        systemState.individualMotorSpeeds[motorNum] = 0;
                        UIManager.updateMotorStatus(motorNum, false, 0);
                    });
                    
                    UIManager.updateGroupSpeedDisplay(groupType, 0);
                    UIManager.updateMotorCount();
                    
                    const groupName = groupType === 'levitation' ? 'Levitasyon' : 'İtki';
                    CommandLogger.log(`${groupName} grubu durduruldu`, true, `M${motorRange.join(',')}`);
                    NotificationManager.show(`🛑 ${groupName} grubu durduruldu! (M${motorRange.join(',')})`, 'success');
                }

            } catch (error) {
                CommandLogger.log(`${groupType} durdurma`, false, error.message);
                NotificationManager.show(`❌ ${groupType} grubu durdurulamadı: ${error.message}`, 'error');
                console.error('Group stop error:', error);
            }
        });
    }

    static setGroupSpeed(groupType, speed) {
        speed = Utils.clamp(parseInt(speed), 0, 100);
        systemState.groupSpeeds[groupType] = speed;
        UIManager.updateGroupSpeedDisplay(groupType, speed);
        
        // Debounce the actual API call
        clearTimeout(window[`${groupType}SpeedTimeout`]);
        window[`${groupType}SpeedTimeout`] = setTimeout(() => {
            this.sendGroupSpeed(groupType, speed);
        }, 300);
    }

    static adjustGroupSpeed(groupType, change) {
        const currentSpeed = systemState.groupSpeeds[groupType];
        const newSpeed = Utils.clamp(currentSpeed + change, 0, 100);
        this.setGroupSpeed(groupType, newSpeed);
        
        const sliderElement = document.getElementById(`${groupType}-slider`);
        if (sliderElement) sliderElement.value = newSpeed;
    }

    static async sendGroupSpeed(groupType, speed) {
        if (!systemState.armed || !systemState.relayBrakeActive) return;

        RequestHandler.throttleRequest(async () => {
            try {
                const response = await RequestHandler.makeRequest(`${BACKEND_URL}/api/${groupType}/speed`, {
                    method: 'POST',
                    body: JSON.stringify({speed: speed})
                });

                if (response.ok) {
                    // Update motor speeds for active motors in the group
                    const motorRange = groupType === 'levitation' ? [1,2,3,4] : [5,6];
                    motorRange.forEach(motorNum => {
                        if (systemState.motorStates[motorNum]) {
                            systemState.individualMotorSpeeds[motorNum] = speed;
                            UIManager.updateMotorSpeedDisplay(motorNum, speed);
                            const inputElement = document.getElementById(`motor${motorNum}-speed-input`);
                            if (inputElement) inputElement.value = speed;
                        }
                    });
                    
                    CommandLogger.log(`${groupType} hızı`, true, `${speed}%`);
                }

            } catch (error) {
                CommandLogger.log(`${groupType} hız`, false, error.message);
                console.error('Group speed error:', error);
            }
        });
    }
}

// System Controller
class SystemController {
    static async toggleArm() {
        RequestHandler.throttleRequest(async () => {
            try {
                const action = systemState.armed ? 'disarm' : 'arm';
                console.log(`Attempting to ${action} system`);
                
                // If arming and relay is inactive, activate relay first
                if (action === 'arm' && !systemState.relayBrakeActive) {
                    NotificationManager.show('🔧 Röle aktif hale getiriliyor, sistem hazırlanıyor...', 'info');
                    
                    const relayResponse = await RequestHandler.makeRequest(`${BACKEND_URL}/api/relay-brake/on`, {
                        method: 'POST'
                    });
                    
                    if (relayResponse.ok) {
                        systemState.relayBrakeActive = true;
                        UIManager.updateRelayBrakeStatus();
                        CommandLogger.log('Röle otomatik aktif yapıldı', true);
                        await new Promise(resolve => setTimeout(resolve, 500));
                    } else {
                        throw new Error('Röle aktif yapılamadı');
                    }
                }
                
                const response = await RequestHandler.makeRequest(`${BACKEND_URL}/api/system/${action}`, {
                    method: 'POST'
                });

                if (response.ok) {
                    const data = await response.json();
                    systemState.armed = !systemState.armed;
                    UIManager.updateArmButton();
                    
                    if (!systemState.armed) {
                        // Reset all motor states when disarming
                        Object.keys(systemState.motorStates).forEach(motorNum => {
                            systemState.motorStates[motorNum] = false;
                            systemState.individualMotorSpeeds[motorNum] = 0;
                            UIManager.updateMotorStatus(motorNum, false, 0);
                        });
                        systemState.groupSpeeds.levitation = 0;
                        systemState.groupSpeeds.thrust = 0;
                        UIManager.updateGroupSpeedDisplay('levitation', 0);
                        UIManager.updateGroupSpeedDisplay('thrust', 0);
                        UIManager.updateMotorCount();
                    }
                    
                    const statusText = action === 'arm' ? 'hazırlandı' : 'devre dışı bırakıldı';
                    CommandLogger.log(`Sistem ${statusText}`, true);
                    NotificationManager.show(`🎯 Sistem ${statusText}!`, 'success');
                }

            } catch (error) {
                CommandLogger.log('Arm/Disarm', false, error.message);
                NotificationManager.show(`❌ Sistem hatası: ${error.message}`, 'error');
                console.error('Arm/Disarm error:', error);
            }
        });
    }

    static async controlRelayBrake(action) {
        RequestHandler.throttleRequest(async () => {
            try {
                console.log(`Attempting relay brake ${action}`);
                
                const response = await RequestHandler.makeRequest(`${BACKEND_URL}/api/relay-brake/${action}`, {
                    method: 'POST'
                });

                if (response.ok) {
                    const data = await response.json();
                    systemState.relayBrakeActive = (action === 'on');
                    UIManager.updateRelayBrakeStatus();
                    
                    // If relay is turned off, reset all motors
                    if (!systemState.relayBrakeActive) {
                        Object.keys(systemState.motorStates).forEach(motorNum => {
                            systemState.motorStates[motorNum] = false;
                            systemState.individualMotorSpeeds[motorNum] = 0;
                            UIManager.updateMotorStatus(motorNum, false, 0);
                        });
                        systemState.groupSpeeds.levitation = 0;
                        systemState.groupSpeeds.thrust = 0;
                        UIManager.updateGroupSpeedDisplay('levitation', 0);
                        UIManager.updateGroupSpeedDisplay('thrust', 0);
                        UIManager.updateMotorCount();
                    }
                    
                    const status = systemState.relayBrakeActive ? 'aktif' : 'pasif';
                    CommandLogger.log(`Röle ${status}`, true);
                    NotificationManager.show(`🔌 Röle sistem ${status}!`, systemState.relayBrakeActive ? 'success' : 'warning');
                }

            } catch (error) {
                CommandLogger.log('Röle kontrol', false, error.message);
                NotificationManager.show(`❌ Röle kontrol hatası: ${error.message}`, 'error');
                console.error('Relay brake error:', error);
            }
        });
    }

    static async controlBrake(action) {
        RequestHandler.throttleRequest(async () => {
            try {
                console.log(`Attempting brake ${action}`);
                
                const response = await RequestHandler.makeRequest(`${BACKEND_URL}/api/brake/${action}`, {
                    method: 'POST'
                });

                if (response.ok) {
                    const data = await response.json();
                    systemState.brakeActive = (action === 'on');
                    
                    CommandLogger.log(`Software brake ${action === 'on' ? 'aktif' : 'pasif'}`, true);
                    NotificationManager.show(`🔒 Software brake ${action === 'on' ? 'aktif' : 'pasif'}!`, 'success');
                }

            } catch (error) {
                CommandLogger.log('Brake kontrol', false, error.message);
                NotificationManager.show(`❌ Brake kontrol hatası: ${error.message}`, 'error');
                console.error('Brake control error:', error);
            }
        });
    }

    static async emergencyStop() {
        try {
            // Immediate local emergency actions
            systemState.armed = false;
            systemState.relayBrakeActive = false;
            systemState.brakeActive = true;
            
            Object.keys(systemState.motorStates).forEach(motorNum => {
                systemState.motorStates[motorNum] = false;
                systemState.individualMotorSpeeds[motorNum] = 0;
                UIManager.updateMotorStatus(motorNum, false, 0);
            });
            
            systemState.groupSpeeds.levitation = 0;
            systemState.groupSpeeds.thrust = 0;
            UIManager.updateGroupSpeedDisplay('levitation', 0);
            UIManager.updateGroupSpeedDisplay('thrust', 0);
            UIManager.updateMotorCount();
            UIManager.updateArmButton();
            UIManager.updateRelayBrakeStatus();

            // Send emergency stop to backend
            const response = await RequestHandler.makeRequest(`${BACKEND_URL}/api/emergency-stop`, {
                method: 'POST'
            });

            CommandLogger.log('ACİL DURDURMA AKTİF', true, 'Tüm sistemler durduruldu');
            NotificationManager.show('🚨 ACİL DURDURMA! Tüm sistemler durduruldu!', 'error', 6000);

        } catch (error) {
            CommandLogger.log('Acil durdurma', false, error.message);
            NotificationManager.show('⚠️ Acil durdurma sinyali gönderilemedi!', 'warning');
            console.error('Emergency stop error:', error);
        }
    }
}

// Status Manager
class StatusManager {
    static async pollStatus() {
        try {
            const response = await RequestHandler.makeRequest(`${BACKEND_URL}/api/status`, {
                method: 'GET'
            }, 3000, 1);

            if (response.ok) {
                const data = await response.json();
                
                // Update system state
                systemState.armed = data.armed;
                systemState.brakeActive = data.brake_active;
                systemState.relayBrakeActive = data.relay_brake_active;
                systemState.connected = data.connected;
                
                // Update motor states
                Object.keys(data.motors).forEach(motorNum => {
                    const running = data.motors[motorNum];
                    const speed = data.individual_speeds[motorNum] || 0;
                    
                    systemState.motorStates[motorNum] = running;
                    systemState.individualMotorSpeeds[motorNum] = speed;
                    UIManager.updateMotorStatus(motorNum, running, speed);
                    
                    const inputElement = document.getElementById(`motor${motorNum}-speed-input`);
                    if (inputElement && speed > 0) {
                        inputElement.value = speed;
                    }
                });
                
                // Update group speeds
                systemState.groupSpeeds.levitation = data.group_speeds.levitation || 0;
                systemState.groupSpeeds.thrust = data.group_speeds.thrust || 0;
                UIManager.updateGroupSpeedDisplay('levitation', systemState.groupSpeeds.levitation);
                UIManager.updateGroupSpeedDisplay('thrust', systemState.groupSpeeds.thrust);
                
                // Update UI elements
                UIManager.updateMotorCount();
                UIManager.updateArmButton();
                UIManager.updateRelayBrakeStatus();
                ConnectionManager.updateConnectionStatus('backend', true);
                ConnectionManager.updateConnectionStatus('arduino', data.connected);
                
                // Update statistics
                if (data.stats) {
                    UIManager.updateStatistics(data.stats);
                }

                appState.consecutiveErrors = 0;
            } else {
                throw new Error('Status request failed');
            }

        } catch (error) {
            appState.consecutiveErrors++;
            if (appState.consecutiveErrors >= 3) {
                ConnectionManager.updateConnectionStatus('backend', false);
                ConnectionManager.updateConnectionStatus('arduino', false);
            }
            console.warn('Status poll error:', error.message);
        }
    }

    static startStatusPolling() {
        if (appState.statusUpdateInterval) {
            clearInterval(appState.statusUpdateInterval);
        }
        
        appState.statusUpdateInterval = setInterval(() => {
            this.pollStatus();
        }, CONFIG.STATUS_UPDATE_INTERVAL);
        
        // Initial status check
        setTimeout(() => this.pollStatus(), 1000);
    }

    static stopStatusPolling() {
        if (appState.statusUpdateInterval) {
            clearInterval(appState.statusUpdateInterval);
            appState.statusUpdateInterval = null;
        }
    }
}

// UI Manager
class UIManager {
    static updateMotorStatus(motorNum, running, speed) {
        const statusElement = document.getElementById(`motor${motorNum}-status`);
        const speedDisplay = document.getElementById(`motor${motorNum}-speed-display`);
        
        if (statusElement) {
            statusElement.textContent = running ? 'ON' : 'OFF';
            statusElement.className = running ? 'motor-status running' : 'motor-status off';
        }
        
        if (speedDisplay) {
            speedDisplay.textContent = `Hız: ${speed}%`;
        }
    }

    static updateMotorSpeedDisplay(motorNum, speed) {
        const speedDisplay = document.getElementById(`motor${motorNum}-speed-display`);
        if (speedDisplay) {
            speedDisplay.textContent = `Hız: ${speed}%`;
        }
    }

    static updateGroupSpeedDisplay(groupType, speed) {
        const speedElement = document.getElementById(`${groupType}-speed`);
        const sliderElement = document.getElementById(`${groupType}-slider`);
        
        if (speedElement) {
            speedElement.textContent = `${speed}%`;
        }
        
        if (sliderElement) {
            sliderElement.value = speed;
        }
    }

    static updateMotorCount() {
        const activeCount = Object.values(systemState.motorStates).filter(state => state).length;
        const countElement = document.getElementById('motor-count');
        const activeMotorsElement = document.getElementById('active-motors');
        
        if (countElement) {
            countElement.textContent = `${activeCount}/6`;
            countElement.style.color = activeCount > 0 ? '#00ff88' : '#aaa';
        }
        
        if (activeMotorsElement) {
            activeMotorsElement.textContent = `${activeCount}/6`;
        }

        // Update average speeds
        const levSpeeds = [1,2,3,4].map(i => systemState.individualMotorSpeeds[i]).filter(s => s > 0);
        const thrSpeeds = [5,6].map(i => systemState.individualMotorSpeeds[i]).filter(s => s > 0);
        
        const levAvg = levSpeeds.length > 0 ? Math.round(levSpeeds.reduce((a,b) => a+b, 0) / levSpeeds.length) : 0;
        const thrAvg = thrSpeeds.length > 0 ? Math.round(thrSpeeds.reduce((a,b) => a+b, 0) / thrSpeeds.length) : 0;
        
        const levAvgElement = document.getElementById('lev-avg-speed');
        const thrAvgElement = document.getElementById('thr-avg-speed');
        const totalSpeedElement = document.getElementById('total-speed');
        
        if (levAvgElement) levAvgElement.textContent = `${levAvg}%`;
        if (thrAvgElement) thrAvgElement.textContent = `${thrAvg}%`;
        if (totalSpeedElement) {
            const totalAvg = activeCount > 0 ? Math.round((levAvg + thrAvg) / 2) : 0;
            totalSpeedElement.textContent = `${totalAvg}%`;
        }

        // Update simulated values
        this.updateSimulatedValues(activeCount);
    }

    static updateSimulatedValues(activeCount) {
        // Update total RPM (simulated)
        const totalRpm = activeCount * 1500 + Math.random() * 500;
        const rpmElement = document.getElementById('total-rpm');
        if (rpmElement) {
            rpmElement.textContent = Math.round(totalRpm);
        }

        // Update power usage (simulated)
        const powerUsage = activeCount * 45 + Math.random() * 20;
        const powerElement = document.getElementById('power-usage');
        if (powerElement) {
            powerElement.textContent = `${Math.round(powerUsage)}W`;
        }

        // Update system temperature (simulated)
        const baseTemp = 25 + (activeCount * 2) + (Math.random() * 5 - 2.5);
        const tempElement = document.getElementById('system-temperature');
        if (tempElement) {
            tempElement.textContent = `${Math.round(baseTemp)}°C`;
        }
    }

    static updateArmButton() {
        const armButton = document.getElementById('arm-button');
        const systemStatus = document.getElementById('system-status');
        
        if (armButton) {
            if (systemState.armed) {
                armButton.textContent = '🔒 SİSTEMİ DEVRE DIŞI BIRAK';
                armButton.className = 'arm-button armed';
            } else {
                armButton.textContent = '🔧 SİSTEMİ HAZIRLA';
                armButton.className = 'arm-button';
            }
        }
        
        if (systemStatus) {
            systemStatus.textContent = systemState.armed ? 'Hazır' : 'Devre Dışı';
            systemStatus.className = systemState.armed ? 'status-value status-armed' : 'status-value status-error';
        }
    }

    static updateRelayBrakeStatus() {
        const relayStatus = document.getElementById('relay-status');
        const relayBrakeStatus = document.getElementById('relay-brake-status');
        
        if (relayStatus) {
            relayStatus.textContent = systemState.relayBrakeActive ? 'Aktif' : 'Pasif';
            relayStatus.style.color = systemState.relayBrakeActive ? '#00ff88' : '#ff0066';
        }
        
        if (relayBrakeStatus) {
            relayBrakeStatus.textContent = systemState.relayBrakeActive ? 'Aktif' : 'Pasif';
            relayBrakeStatus.style.color = systemState.relayBrakeActive ? '#00ff88' : '#ff0066';
        }
    }

    static updateStatistics(stats) {
        const elements = {
            'total-commands': stats.commands || 0,
            'total-errors': stats.errors || 0,
            'uptime': Utils.formatUptime(stats.uptime_seconds || 0),
            'arduino-port': stats.reconnect_attempts !== undefined ? `USB${stats.reconnect_attempts}` : '--'
        };

        Object.entries(elements).forEach(([id, value]) => {
            const element = document.getElementById(id);
            if (element) {
                element.textContent = value;
            }
        });
    }

    static showLoading(show = true) {
        const overlay = document.getElementById('loading-overlay');
        if (overlay) {
            overlay.classList.toggle('hidden', !show);
        }
    }

    static setLoadingText(text) {
        const loadingText = document.querySelector('.loading-text');
        if (loadingText) {
            loadingText.textContent = text;
        }
    }
}

// Event Handlers - Global Functions (called from HTML)
window.toggleArm = () => SystemController.toggleArm();
window.startMotor = (motorNum) => MotorController.startMotor(motorNum);
window.stopMotor = (motorNum) => MotorController.stopMotor(motorNum);
window.setMotorSpeed = (motorNum, speed) => MotorController.setMotorSpeed(motorNum, speed);
window.startGroup = (groupType) => GroupController.startGroup(groupType);
window.stopGroup = (groupType) => GroupController.stopGroup(groupType);
window.setGroupSpeed = (groupType, speed) => GroupController.setGroupSpeed(groupType, speed);
window.adjustGroupSpeed = (groupType, change) => GroupController.adjustGroupSpeed(groupType, change);
window.controlRelayBrake = (action) => SystemController.controlRelayBrake(action);
window.controlBrake = (action) => SystemController.controlBrake(action);
window.emergencyStop = () => SystemController.emergencyStop();
window.testConnection = () => ConnectionManager.testConnection();
window.reconnectArduino = () => ConnectionManager.reconnectArduino();
window.closeNotification = () => NotificationManager.hide();

// Application Lifecycle
class Application {
    static async initialize() {
        console.log('🚀 SpectraLoop Frontend v3.2 - Production initializing...');
        console.log('✅ Motor Groups: Levitation(1,2,3,4) Thrust(5,6)');
        
        try {
            UIManager.showLoading(true);
            UIManager.setLoadingText('Sistem başlatılıyor...');
            
            // Initialize UI state
            UIManager.updateArmButton();
            UIManager.updateRelayBrakeStatus();
            UIManager.updateMotorCount();
            
            // Setup event listeners
            this.setupEventListeners();
            
            UIManager.setLoadingText('Backend bağlantısı test ediliyor...');
            
            // Test initial connection
            try {
                await ConnectionManager.testConnection();
            } catch (error) {
                console.warn('Initial connection test failed:', error.message);
            }
            
            UIManager.setLoadingText('Status polling başlatılıyor...');
            
            // Start status polling
            StatusManager.startStatusPolling();
            
            // Log initialization
            CommandLogger.log('Frontend başlatıldı', true, 'Production v3.2');
            NotificationManager.show('🎯 SpectraLoop sistemi hazır! Motor grupları: Lev(1,2,3,4) Thr(5,6)', 'success');
            
            UIManager.showLoading(false);
            appState.isInitialized = true;
            
            console.log('✅ Frontend initialization complete');
            
        } catch (error) {
            console.error('Initialization error:', error);
            UIManager.setLoadingText('Başlatma hatası! Yeniden denenecek...');
            CommandLogger.log('Başlatma hatası', false, error.message);
            
            // Retry initialization after delay
            setTimeout(() => {
                this.initialize();
            }, 3000);
        }
    }

    static setupEventListeners() {
        // Page visibility change handler
        document.addEventListener('visibilitychange', () => {
            if (document.visibilityState === 'visible' && appState.isInitialized) {
                setTimeout(() => StatusManager.pollStatus(), 500);
            }
        });

        // Keyboard shortcuts
        document.addEventListener('keydown', (event) => {
            if (event.ctrlKey) {
                switch(event.key) {
                    case ' ': // Ctrl+Space for emergency stop
                        event.preventDefault();
                        SystemController.emergencyStop();
                        break;
                    case 'a': // Ctrl+A for arm/disarm
                        event.preventDefault();
                        SystemController.toggleArm();
                        break;
                    case 't': // Ctrl+T for connection test
                        event.preventDefault();
                        ConnectionManager.testConnection();
                        break;
                    case 'r': // Ctrl+R for relay toggle
                        event.preventDefault();
                        SystemController.controlRelayBrake(systemState.relayBrakeActive ? 'off' : 'on');
                        break;
                    case 'l': // Ctrl+L for clear log
                        event.preventDefault();
                        CommandLogger.clear();
                        break;
                }
            }
        });

        // Prevent page refresh with unsaved state
        window.addEventListener('beforeunload', (event) => {
            if (systemState.armed || Object.values(systemState.motorStates).some(state => state)) {
                const message = 'Motorlar çalışıyor! Sayfayı kapatmak istediğinizden emin misiniz?';
                event.preventDefault();
                event.returnValue = message;
                return message;
            }
        });

        // Handle network status changes
        window.addEventListener('online', () => {
            NotificationManager.show('🌐 İnternet bağlantısı yeniden kuruldu', 'success');
            setTimeout(() => StatusManager.pollStatus(), 1000);
        });

        window.addEventListener('offline', () => {
            NotificationManager.show('🌐 İnternet bağlantısı kesildi', 'warning', 2000);
            ConnectionManager.updateConnectionStatus('backend', false);
        });

        // Handle errors
        window.addEventListener('error', (event) => {
            console.error('Global error:', event.error);
            CommandLogger.log('JavaScript Hatası', false, event.error.message);
        });

        window.addEventListener('unhandledrejection', (event) => {
            console.error('Unhandled promise rejection:', event.reason);
            CommandLogger.log('Promise Hatası', false, event.reason.message || 'Unknown error');
        });

        // Setup responsive handlers
        this.setupResponsiveHandlers();
    }

    static setupResponsiveHandlers() {
        // Handle screen size changes
        const mediaQuery = window.matchMedia('(max-width: 900px)');
        
        const handleScreenChange = (e) => {
            if (e.matches) {
                // Mobile layout adjustments
                console.log('Switched to mobile layout');
            } else {
                // Desktop layout
                console.log('Switched to desktop layout');
            }
        };

        mediaQuery.addListener(handleScreenChange);
        handleScreenChange(mediaQuery); // Initial check
    }

    static shutdown() {
        console.log('🛑 Shutting down SpectraLoop Frontend...');
        
        try {
            // Stop status polling
            StatusManager.stopStatusPolling();
            
            // Emergency stop if needed
            if (systemState.armed || Object.values(systemState.motorStates).some(state => state)) {
                SystemController.emergencyStop();
            }
            
            // Clear timeouts
            Object.keys(window).forEach(key => {
                if (key.includes('Timeout')) {
                    clearTimeout(window[key]);
                }
            });
            
            CommandLogger.log('Frontend kapatıldı', true, 'Güvenli kapatma');
            console.log('✅ Frontend shutdown complete');
            
        } catch (error) {
            console.error('Shutdown error:', error);
        }
    }
}

// Performance monitoring
class PerformanceMonitor {
    static startMonitoring() {
        // Monitor memory usage
        setInterval(() => {
            if (performance.memory) {
                const memUsage = performance.memory.usedJSHeapSize / 1024 / 1024;
                if (memUsage > 100) { // Over 100MB
                    console.warn(`High memory usage: ${memUsage.toFixed(2)} MB`);
                }
            }
        }, 30000);

        // Monitor request performance
        const originalFetch = window.fetch;
        window.fetch = async (...args) => {
            const start = performance.now();
            try {
                const response = await originalFetch(...args);
                const duration = performance.now() - start;
                
                if (duration > 5000) { // Over 5 seconds
                    console.warn(`Slow request: ${args[0]} took ${duration.toFixed(2)}ms`);
                }
                
                return response;
            } catch (error) {
                const duration = performance.now() - start;
                console.error(`Failed request: ${args[0]} failed after ${duration.toFixed(2)}ms`);
                throw error;
            }
        };
    }
}

// Start the application when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    Application.initialize();
    PerformanceMonitor.startMonitoring();
});

// Handle page unload
window.addEventListener('beforeunload', () => {
    Application.shutdown();
});

// Debug helpers (only in development)
if (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1') {
    window.spectraDebug = {
        systemState,
        appState,
        CommandLogger,
        NotificationManager,
        ConnectionManager,
        MotorController,
        GroupController,
        SystemController,
        StatusManager,
        UIManager,
        Application
    };
    
    console.log('🐛 Debug mode enabled. Use window.spectraDebug to access internals.');
}

// Console welcome message
console.log(`
🎛️ SpectraLoop Frontend v3.2 - Production
🔧 Keyboard shortcuts:
   Ctrl+Space: Emergency Stop
   Ctrl+A: Arm/Disarm System  
   Ctrl+T: Test Connection
   Ctrl+R: Toggle Relay
   Ctrl+L: Clear Command Log

🔧 MOTOR GROUPS:
   Levitation: Motors 1,2,3,4 (Pins 2,4,5,6)
   Thrust: Motors 5,6 (Pins 3,7)

🎯 FEATURES:
   ✅ Individual Motor Control
   ✅ Group Motor Control
   ✅ Software Brake Control  
   ✅ Relay Brake Control
   ✅ Arduino Reconnect Function
   ✅ Emergency Stop System
   ✅ Real-time Status Updates
   ✅ Command Logging
   ✅ Performance Monitoring
`);

// Production warning
if (window.location.protocol === 'file:') {
    console.warn('⚠️ Running from file:// protocol. For best results, serve from a web server.');
}