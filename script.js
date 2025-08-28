/*
 * SpectraLoop Frontend JavaScript v3.2 - Production with Temperature Display
 * Complete Motor Control System + Temperature Safety
 * Backend IP: Update BACKEND_URL with your Raspberry Pi IP
 */

// Configuration - UPDATE WITH YOUR RASPBERRY PI IP
const BACKEND_URL = 'http://10.237.49.82:5001';

// System State Management
let systemState = {
    armed: false,
    brakeActive: false,
    relayBrakeActive: false,
    connected: false,
    motorStates: {1: false, 2: false, 3: false, 4: false, 5: false, 6: false},
    individualMotorSpeeds: {1: 0, 2: 0, 3: 0, 4: 0, 5: 0, 6: 0},
    groupSpeeds: {levitation: 0, thrust: 0},
    connectionStatus: {backend: false, arduino: false},
    temperature: {
        current: 25.0,
        alarm: false,
        buzzer_active: false,
        max_reached: 25.0,
        last_update: null,
        emergency_active: false,
        alarm_count: 0
    }
};

// Application State
let appState = {
    requestCount: 0,
    errorCount: 0,
    lastRequestTime: 0,
    consecutiveErrors: 0,
    commandLog: [],
    statusUpdateInterval: null,
    isInitialized: false,
    lastTempAlarmNotified: false,
    temperatureHistory: [],
    tempWarningShown: false
};

// Constants
const CONFIG = {
    REQUEST_THROTTLE: 50,
    MAX_RETRIES: 3,
    STATUS_UPDATE_INTERVAL: 2000,
    CONNECTION_TIMEOUT: 8000,
    MAX_LOG_ENTRIES: 25,
    NOTIFICATION_TIMEOUT: 4000,
    TEMP_SAFE_THRESHOLD: 50,
    TEMP_WARNING_THRESHOLD: 45,
    TEMP_ALARM_THRESHOLD: 55
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

// Temperature Manager
class TemperatureManager {
    static updateTemperatureDisplay(tempData) {
        if (!tempData) return;
        
        const currentTemp = tempData.current || 25.0;
        const tempAlarm = tempData.alarm || false;
        const buzzerActive = tempData.buzzer_active || false;
        const maxTemp = tempData.max_reached || currentTemp;
        const alarmCount = tempData.alarm_count || 0;
        const emergencyActive = tempData.emergency_active || false;
        
        // Update main temperature reading
        const tempCurrentEl = document.getElementById('temp-current');
        const tempStatusEl = document.getElementById('temp-status-text');
        const tempSectionEl = document.getElementById('temperature-section');
        
        if (tempCurrentEl) {
            tempCurrentEl.textContent = `${currentTemp.toFixed(1)}°C`;
            tempCurrentEl.className = 'temp-current';
            
            if (tempAlarm || currentTemp >= CONFIG.TEMP_ALARM_THRESHOLD) {
                tempCurrentEl.classList.add('danger');
            } else if (currentTemp >= CONFIG.TEMP_WARNING_THRESHOLD) {
                tempCurrentEl.classList.add('warning');
            }
        }
        
        if (tempStatusEl) {
            if (tempAlarm || emergencyActive) {
                tempStatusEl.textContent = 'ALARM!';
            } else if (currentTemp >= CONFIG.TEMP_WARNING_THRESHOLD) {
                tempStatusEl.textContent = 'Uyarı';
            } else {
                tempStatusEl.textContent = 'Güvenli';
            }
        }
        
        if (tempSectionEl) {
            tempSectionEl.className = 'temperature-section';
            if (tempAlarm || emergencyActive) {
                tempSectionEl.classList.add('danger');
            } else if (currentTemp >= CONFIG.TEMP_WARNING_THRESHOLD) {
                tempSectionEl.classList.add('warning');
            }
        }
        
        // Update temperature details
        const elements = {
            'temp-max': `${maxTemp.toFixed(1)}°C`,
            'temp-alarm-count': alarmCount,
            'buzzer-status': buzzerActive ? 'Aktif' : 'Pasif',
            'detailed-temp-current': `${currentTemp.toFixed(1)}°C`,
            'detailed-temp-max': `${maxTemp.toFixed(1)}°C`,
            'detailed-alarm-count': alarmCount,
            'system-temperature': `${currentTemp.toFixed(0)}°C`
        };
        
        Object.entries(elements).forEach(([id, value]) => {
            const element = document.getElementById(id);
            if (element) element.textContent = value;
        });
        
        // Update detailed status
        const detailedStatusEl = document.getElementById('detailed-temp-status');
        if (detailedStatusEl) {
            if (tempAlarm || emergencyActive) {
                detailedStatusEl.textContent = 'ALARM';
                detailedStatusEl.style.color = '#ff4757';
            } else if (currentTemp >= CONFIG.TEMP_WARNING_THRESHOLD) {
                detailedStatusEl.textContent = 'Uyarı';
                detailedStatusEl.style.color = '#ffc107';
            } else {
                detailedStatusEl.textContent = 'Güvenli';
                detailedStatusEl.style.color = '#00ff88';
            }
        }
        
        // Update buzzer button
        const buzzerBtn = document.getElementById('buzzer-off-btn');
        if (buzzerBtn) {
            buzzerBtn.disabled = !buzzerActive;
        }
        
        // Show/hide emergency indicators
        const tempEmergencyEl = document.getElementById('temp-emergency');
        if (tempEmergencyEl) {
            tempEmergencyEl.style.display = (tempAlarm || emergencyActive) ? 'block' : 'none';
        }
        
        const emergencyWarning = document.getElementById('temperature-emergency-warning');
        const warningTempValue = document.getElementById('warning-temp-value');
        if (emergencyWarning) {
            if (tempAlarm || emergencyActive) {
                emergencyWarning.style.display = 'block';
                if (warningTempValue) {
                    warningTempValue.textContent = `${currentTemp.toFixed(1)}°C`;
                }
            } else {
                emergencyWarning.style.display = 'none';
            }
        }
        
        // Update last update time
        const lastUpdateEl = document.getElementById('temp-last-update');
        if (lastUpdateEl) {
            lastUpdateEl.textContent = Utils.formatTime(new Date());
        }
        
        // Store temperature data in system state
        systemState.temperature = {
            current: currentTemp,
            alarm: tempAlarm,
            buzzer_active: buzzerActive,
            max_reached: maxTemp,
            last_update: new Date(),
            emergency_active: emergencyActive,
            alarm_count: alarmCount
        };
        
        // Handle temperature notifications
        this.handleTemperatureNotifications(tempAlarm, emergencyActive, currentTemp);
    }
    
    static handleTemperatureNotifications(tempAlarm, emergencyActive, currentTemp) {
        // Temperature alarm notifications
        if ((tempAlarm || emergencyActive) && !appState.lastTempAlarmNotified) {
            NotificationManager.show(
                `SICAKLIK ALARMI! ${currentTemp.toFixed(1)}°C - Sistem durduruldu!`, 
                'error', 
                8000
            );
            appState.lastTempAlarmNotified = true;
        } else if (!(tempAlarm || emergencyActive) && appState.lastTempAlarmNotified) {
            NotificationManager.show(
                `Sıcaklık güvenli seviyeye döndü: ${currentTemp.toFixed(1)}°C`, 
                'success'
            );
            appState.lastTempAlarmNotified = false;
        }
        
        // Warning level notifications
        if (currentTemp >= CONFIG.TEMP_WARNING_THRESHOLD && currentTemp < CONFIG.TEMP_ALARM_THRESHOLD) {
            if (!appState.tempWarningShown) {
                NotificationManager.show(
                    `Sıcaklık uyarı seviyesinde: ${currentTemp.toFixed(1)}°C`, 
                    'warning'
                );
                appState.tempWarningShown = true;
            }
        } else {
            appState.tempWarningShown = false;
        }
    }
    
    static async turnOffBuzzer() {
        try {
            const response = await RequestHandler.makeRequest(`${BACKEND_URL}/api/temperature/buzzer/off`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' }
            });
            
            const data = await response.json();
            
            if (data.status === 'success') {
                systemState.temperature.buzzer_active = false;
                NotificationManager.show('Buzzer kapatıldı', 'success');
                CommandLogger.log('Buzzer kapatıldı', true);
            } else {
                throw new Error(data.message || 'Buzzer kapatılamadı');
            }
        } catch (error) {
            CommandLogger.log('Buzzer kapatma', false, error.message);
            NotificationManager.show(`Buzzer kapatılamadı: ${error.message}`, 'error');
        }
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

        const icons = {
            success: '✅',
            error: '❌',
            warning: '⚠️',
            info: 'ℹ️'
        };

        iconElement.textContent = icons[type] || icons.info;
        messageElement.textContent = message;
        
        notification.className = `notification ${type} show`;
        
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

        if (connected) {
            const lastUpdateElement = document.getElementById('last-update');
            if (lastUpdateElement) {
                lastUpdateElement.textContent = Utils.formatTime(new Date());
            }
        }
    }

    static async testConnection() {
        try {
            NotificationManager.show('Bağlantı test ediliyor...', 'info');
            
            const response = await RequestHandler.makeRequest(`${BACKEND_URL}/api/test-connection`);
            const data = await response.json();
            
            if (data.status === 'success') {
                CommandLogger.log('Bağlantı testi başarılı', true);
                NotificationManager.show('Bağlantı testi başarılı!', 'success');
                this.updateConnectionStatus('backend', true);
                this.updateConnectionStatus('arduino', true);
            } else {
                throw new Error(data.message || 'Test failed');
            }
            
        } catch (error) {
            CommandLogger.log('Bağlantı testi', false, error.message);
            NotificationManager.show(`Bağlantı testi başarısız: ${error.message}`, 'error');
            this.updateConnectionStatus('backend', false);
            this.updateConnectionStatus('arduino', false);
        }
    }

    static async reconnectArduino() {
        try {
            NotificationManager.show('Arduino yeniden bağlanıyor...', 'info');
            
            const response = await RequestHandler.makeRequest(`${BACKEND_URL}/api/reconnect`, {
                method: 'POST'
            });
            
            const data = await response.json();
            
            if (data.status === 'success') {
                CommandLogger.log('Arduino yeniden bağlandı', true);
                NotificationManager.show('Arduino yeniden bağlandı!', 'success');
                setTimeout(() => StatusManager.pollStatus(), 1000);
            } else {
                throw new Error(data.message || 'Reconnection failed');
            }
            
        } catch (error) {
            CommandLogger.log('Arduino yeniden bağlanma', false, error.message);
            NotificationManager.show(`Arduino yeniden bağlanamadı: ${error.message}`, 'error');
        }
    }
}

// Motor Control
class MotorController {
    static async startMotor(motorNum) {
        if (systemState.temperature.alarm || systemState.temperature.emergency_active) {
            NotificationManager.show('Sıcaklık alarmı nedeniyle motorlar başlatılamaz!', 'warning');
            return;
        }
        
        if (!systemState.armed) {
            NotificationManager.show('Önce sistemi hazırlamanız gerekiyor!', 'warning');
            return;
        }

        if (!systemState.relayBrakeActive) {
            NotificationManager.show('Röle pasif! Önce röleyi aktif yapın.', 'warning');
            return;
        }

        RequestHandler.throttleRequest(async () => {
            try {
                const speedInput = document.getElementById(`motor${motorNum}-speed-input`);
                const speed = speedInput ? parseInt(speedInput.value) || 50 : 50;
                
                const response = await RequestHandler.makeRequest(`${BACKEND_URL}/api/motor/${motorNum}/start`, {
                    method: 'POST',
                    body: JSON.stringify({speed: speed})
                });

                if (response.ok) {
                    systemState.motorStates[motorNum] = true;
                    systemState.individualMotorSpeeds[motorNum] = speed;
                    UIManager.updateMotorStatus(motorNum, true, speed);
                    UIManager.updateMotorCount();
                    CommandLogger.log(`Motor ${motorNum} başlatıldı`, true, `${speed}% - Temp: ${systemState.temperature.current.toFixed(1)}°C`);
                    NotificationManager.show(`Motor ${motorNum} başlatıldı!`, 'success');
                }

            } catch (error) {
                CommandLogger.log(`Motor ${motorNum} başlatma`, false, error.message);
                NotificationManager.show(`Motor ${motorNum} başlatılamadı: ${error.message}`, 'error');
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
                    NotificationManager.show(`Motor ${motorNum} durduruldu!`, 'success');
                }

            } catch (error) {
                CommandLogger.log(`Motor ${motorNum} durdurma`, false, error.message);
                NotificationManager.show(`Motor ${motorNum} durdurulamadı: ${error.message}`, 'error');
                console.error('Motor stop error:', error);
            }
        });
    }

    static async setMotorSpeed(motorNum, speed) {
        if (systemState.temperature.alarm || systemState.temperature.emergency_active) {
            NotificationManager.show('Sıcaklık alarmı nedeniyle motor kontrol edilemez!', 'warning');
            return;
        }
        
        if (!systemState.armed) {
            NotificationManager.show('Sistem armed değil!', 'warning');
            return;
        }

        if (!systemState.relayBrakeActive) {
            NotificationManager.show('Röle pasif! Önce röleyi aktif yapın.', 'warning');
            return;
        }

        speed = Utils.clamp(parseInt(speed), 0, 100);
        if (isNaN(speed)) {
            NotificationManager.show('Geçersiz hız değeri!', 'warning');
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
                NotificationManager.show(`Motor ${motorNum} hız ayarlanamadı`, 'error');
                console.error('Motor speed error:', error);
            }
        });
    }
}

// Group Control
class GroupController {
    static async startGroup(groupType) {
        if (systemState.temperature.alarm || systemState.temperature.emergency_active) {
            NotificationManager.show('Sıcaklık alarmı nedeniyle motor grubu başlatılamaz!', 'warning');
            return;
        }
        
        if (!systemState.armed) {
            NotificationManager.show('Önce sistemi hazırlamanız gerekiyor!', 'warning');
            return;
        }

        if (!systemState.relayBrakeActive) {
            NotificationManager.show('Röle pasif! Önce röleyi aktif yapın.', 'warning');
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
                    systemState.groupSpeeds[groupType] = speed;
                    
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
                    CommandLogger.log(`${groupName} grubu başlatıldı`, true, `${speed}% - M${motorRange.join(',')} - Temp: ${systemState.temperature.current.toFixed(1)}°C`);
                    NotificationManager.show(`${groupName} grubu başlatıldı! (M${motorRange.join(',')})`, 'success');
                }

            } catch (error) {
                CommandLogger.log(`${groupType} başlatma`, false, error.message);
                NotificationManager.show(`${groupType} grubu başlatılamadı: ${error.message}`, 'error');
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
                    NotificationManager.show(`${groupName} grubu durduruldu! (M${motorRange.join(',')})`, 'success');
                }

            } catch (error) {
                CommandLogger.log(`${groupType} durdurma`, false, error.message);
                NotificationManager.show(`${groupType} grubu durdurulamadı: ${error.message}`, 'error');
                console.error('Group stop error:', error);
            }
        });
    }

    static setGroupSpeed(groupType, speed) {
        speed = Utils.clamp(parseInt(speed), 0, 100);
        systemState.groupSpeeds[groupType] = speed;
        UIManager.updateGroupSpeedDisplay(groupType, speed);
        
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
        if (systemState.temperature.alarm || systemState.temperature.emergency_active) return;
        if (!systemState.armed || !systemState.relayBrakeActive) return;

        RequestHandler.throttleRequest(async () => {
            try {
                const response = await RequestHandler.makeRequest(`${BACKEND_URL}/api/${groupType}/speed`, {
                    method: 'POST',
                    body: JSON.stringify({speed: speed})
                });

                if (response.ok) {
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
        if (!systemState.armed && (systemState.temperature.alarm || systemState.temperature.emergency_active)) {
            NotificationManager.show('Sıcaklık alarmı nedeniyle sistem hazırlanamaz!', 'warning');
            return;
        }
        
        RequestHandler.throttleRequest(async () => {
            try {
                const action = systemState.armed ? 'disarm' : 'arm';
                console.log(`Attempting to ${action} system`);
                
                if (action === 'arm' && !systemState.relayBrakeActive) {
                    NotificationManager.show('Röle aktif hale getiriliyor, sistem hazırlanıyor...', 'info');
                    
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
                    systemState.armed = !systemState.armed;
                    UIManager.updateArmButton();
                    
                    if (!systemState.armed) {
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
                    CommandLogger.log(`Sistem ${statusText}`, true, `Temp: ${systemState.temperature.current.toFixed(1)}°C`);
                    NotificationManager.show(`Sistem ${statusText}!`, 'success');
                }

            } catch (error) {
                CommandLogger.log('Arm/Disarm', false, error.message);
                NotificationManager.show(`Sistem hatası: ${error.message}`, 'error');
                console.error('Arm/Disarm error:', error);
            }
        });
    }

    static async controlRelayBrake(action) {
        if (action === 'on' && (systemState.temperature.alarm || systemState.temperature.emergency_active)) {
            NotificationManager.show('Sıcaklık alarmı nedeniyle röle aktif yapılamaz!', 'warning');
            return;
        }
        
        RequestHandler.throttleRequest(async () => {
            try {
                console.log(`Attempting relay brake ${action}`);
                
                const response = await RequestHandler.makeRequest(`${BACKEND_URL}/api/relay-brake/${action}`, {
                    method: 'POST'
                });

                if (response.ok) {
                    systemState.relayBrakeActive = (action === 'on');
                    UIManager.updateRelayBrakeStatus();
                    
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
                    CommandLogger.log(`Röle ${status}`, true, `Temp: ${systemState.temperature.current.toFixed(1)}°C`);
                    NotificationManager.show(`Röle sistem ${status}!`, systemState.relayBrakeActive ? 'success' : 'warning');
                }

            } catch (error) {
                CommandLogger.log('Röle kontrol', false, error.message);
                NotificationManager.show(`Röle kontrol hatası: ${error.message}`, 'error');
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
                    systemState.brakeActive = (action === 'on');
                    
                    CommandLogger.log(`Software brake ${action === 'on' ? 'aktif' : 'pasif'}`, true);
                    NotificationManager.show(`Software brake ${action === 'on' ? 'aktif' : 'pasif'}!`, 'success');
                }

            } catch (error) {
                CommandLogger.log('Brake kontrol', false, error.message);
                NotificationManager.show(`Brake kontrol hatası: ${error.message}`, 'error');
                console.error('Brake control error:', error);
            }
        });
    }

    static async emergencyStop() {
        try {
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

            const response = await RequestHandler.makeRequest(`${BACKEND_URL}/api/emergency-stop`, {
                method: 'POST'
            });

            CommandLogger.log('ACİL DURDURMA AKTİF', true, `Tüm sistemler durduruldu - Temp: ${systemState.temperature.current.toFixed(1)}°C`);
            NotificationManager.show('ACİL DURDURMA! Tüm sistemler durduruldu!', 'error', 6000);

        } catch (error) {
            CommandLogger.log('Acil durdurma', false, error.message);
            NotificationManager.show('Acil durdurma sinyali gönderilemedi!', 'warning');
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
                
                systemState.armed = data.armed;
                systemState.brakeActive = data.brake_active;
                systemState.relayBrakeActive = data.relay_brake_active;
                systemState.connected = data.connected;
                
                if (data.temperature) {
                    TemperatureManager.updateTemperatureDisplay(data.temperature);
                }
                
                Object.keys(data.motors || {}).forEach(motorNum => {
                    const running = data.motors[motorNum];
                    const speed = (data.individual_speeds && data.individual_speeds[motorNum]) || 0;
                    
                    systemState.motorStates[motorNum] = running;
                    systemState.individualMotorSpeeds[motorNum] = speed;
                    UIManager.updateMotorStatus(motorNum, running, speed);
                    
                    const inputElement = document.getElementById(`motor${motorNum}-speed-input`);
                    if (inputElement && speed > 0) {
                        inputElement.value = speed;
                    }
                });
                
                systemState.groupSpeeds.levitation = (data.group_speeds && data.group_speeds.levitation) || 0;
                systemState.groupSpeeds.thrust = (data.group_speeds && data.group_speeds.thrust) || 0;
                UIManager.updateGroupSpeedDisplay('levitation', systemState.groupSpeeds.levitation);
                UIManager.updateGroupSpeedDisplay('thrust', systemState.groupSpeeds.thrust);
                
                UIManager.updateMotorCount();
                UIManager.updateArmButton();
                UIManager.updateRelayBrakeStatus();
                ConnectionManager.updateConnectionStatus('backend', true);
                ConnectionManager.updateConnectionStatus('arduino', data.connected);
                
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

        this.updateSimulatedValues(activeCount);
    }

    static updateSimulatedValues(activeCount) {
        const baseRpm = activeCount * 1500;
        const tempEffect = Math.max(0, (systemState.temperature.current - 25) * 10);
        const totalRpm = baseRpm + tempEffect + Math.random() * 500;
        const rpmElement = document.getElementById('total-rpm');
        if (rpmElement) {
            rpmElement.textContent = Math.round(totalRpm);
        }

        const basePower = activeCount * 45;
        const tempPowerEffect = Math.max(0, (systemState.temperature.current - 25) * 2);
        const powerUsage = basePower + tempPowerEffect + Math.random() * 20;
        const powerElement = document.getElementById('power-usage');
        if (powerElement) {
            powerElement.textContent = `${Math.round(powerUsage)}W`;
        }
    }

    static updateArmButton() {
        const armButton = document.getElementById('arm-button');
        const systemStatus = document.getElementById('system-status');
        
        if (armButton) {
            if (systemState.armed) {
                armButton.textContent = 'SİSTEMİ DEVRE DIŞI BIRAK';
                armButton.className = 'arm-button armed';
            } else {
                armButton.textContent = 'SİSTEMİ HAZIRLA';
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

// Global Functions
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
window.turnOffBuzzer = () => TemperatureManager.turnOffBuzzer();

// Application Lifecycle
class Application {
    static async initialize() {
        console.log('SpectraLoop Frontend v3.2 - Production with Temperature Safety initializing...');
        console.log('Motor Groups: Levitation(1,2,3,4) Thrust(5,6)');
        console.log('Temperature monitoring: DS18B20 on Pin8, Buzzer on Pin9');
        
        try {
            UIManager.showLoading(true);
            UIManager.setLoadingText('Sistem başlatılıyor...');
            
            UIManager.updateArmButton();
            UIManager.updateRelayBrakeStatus();
            UIManager.updateMotorCount();
            
            this.setupEventListeners();
            
            UIManager.setLoadingText('Backend bağlantısı test ediliyor...');
            
            try {
                await ConnectionManager.testConnection();
            } catch (error) {
                console.warn('Initial connection test failed:', error.message);
            }
            
            UIManager.setLoadingText('Status polling başlatılıyor...');
            
            StatusManager.startStatusPolling();
            
            CommandLogger.log('Frontend başlatıldı', true, 'Production v3.2 + Temperature Safety');
            NotificationManager.show('SpectraLoop sistemi hazır! Sıcaklık güvenlik sistemi aktif', 'success');
            
            UIManager.showLoading(false);
            appState.isInitialized = true;
            
            console.log('Frontend initialization complete with temperature monitoring');
            
        } catch (error) {
            console.error('Initialization error:', error);
            UIManager.setLoadingText('Başlatma hatası! Yeniden denenecek...');
            CommandLogger.log('Başlatma hatası', false, error.message);
            
            setTimeout(() => {
                this.initialize();
            }, 3000);
        }
    }

    static setupEventListeners() {
        document.addEventListener('visibilitychange', () => {
            if (document.visibilityState === 'visible' && appState.isInitialized) {
                setTimeout(() => StatusManager.pollStatus(), 500);
            }
        });

        document.addEventListener('keydown', (event) => {
            if (event.ctrlKey) {
                switch(event.key) {
                    case ' ':
                        event.preventDefault();
                        SystemController.emergencyStop();
                        break;
                    case 'a':
                        event.preventDefault();
                        SystemController.toggleArm();
                        break;
                    case 't':
                        event.preventDefault();
                        ConnectionManager.testConnection();
                        break;
                    case 'r':
                        event.preventDefault();
                        SystemController.controlRelayBrake(systemState.relayBrakeActive ? 'off' : 'on');
                        break;
                    case 'l':
                        event.preventDefault();
                        CommandLogger.clear();
                        break;
                    case 'b':
                        event.preventDefault();
                        TemperatureManager.turnOffBuzzer();
                        break;
                }
            }
        });

        window.addEventListener('beforeunload', (event) => {
            if (systemState.armed || Object.values(systemState.motorStates).some(state => state)) {
                const message = 'Motorlar çalışıyor! Sayfayı kapatmak istediğinizden emin misiniz?';
                event.preventDefault();
                event.returnValue = message;
                return message;
            }
        });

        window.addEventListener('online', () => {
            NotificationManager.show('İnternet bağlantısı yeniden kuruldu', 'success');
            setTimeout(() => StatusManager.pollStatus(), 1000);
        });

        window.addEventListener('offline', () => {
            NotificationManager.show('İnternet bağlantısı kesildi', 'warning', 2000);
            ConnectionManager.updateConnectionStatus('backend', false);
        });

        window.addEventListener('error', (event) => {
            console.error('Global error:', event.error);
            CommandLogger.log('JavaScript Hatası', false, event.error.message);
        });

        window.addEventListener('unhandledrejection', (event) => {
            console.error('Unhandled promise rejection:', event.reason);
            CommandLogger.log('Promise Hatası', false, event.reason.message || 'Unknown error');
        });

        this.setupResponsiveHandlers();
    }

    static setupResponsiveHandlers() {
        const mediaQuery = window.matchMedia('(max-width: 900px)');
        
        const handleScreenChange = (e) => {
            if (e.matches) {
                console.log('Switched to mobile layout');
            } else {
                console.log('Switched to desktop layout');
            }
        };

        mediaQuery.addListener(handleScreenChange);
        handleScreenChange(mediaQuery);
    }

    static shutdown() {
        console.log('Shutting down SpectraLoop Frontend...');
        
        try {
            StatusManager.stopStatusPolling();
            
            if (systemState.armed || Object.values(systemState.motorStates).some(state => state)) {
                SystemController.emergencyStop();
            }
            
            Object.keys(window).forEach(key => {
                if (key.includes('Timeout')) {
                    clearTimeout(window[key]);
                }
            });
            
            CommandLogger.log('Frontend kapatıldı', true, 'Güvenli kapatma');
            console.log('Frontend shutdown complete');
            
        } catch (error) {
            console.error('Shutdown error:', error);
        }
    }
}

// Performance monitoring
class PerformanceMonitor {
    static startMonitoring() {
        setInterval(() => {
            if (performance.memory) {
                const memUsage = performance.memory.usedJSHeapSize / 1024 / 1024;
                if (memUsage > 100) {
                    console.warn(`High memory usage: ${memUsage.toFixed(2)} MB`);
                }
            }
        }, 30000);

        const originalFetch = window.fetch;
        window.fetch = async (...args) => {
            const start = performance.now();
            try {
                const response = await originalFetch(...args);
                const duration = performance.now() - start;
                
                if (duration > 5000) {
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

// Initialize application
document.addEventListener('DOMContentLoaded', () => {
    Application.initialize();
    PerformanceMonitor.startMonitoring();
});

window.addEventListener('beforeunload', () => {
    Application.shutdown();
});

// Debug mode
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
        Application,
        TemperatureManager
    };
    
    console.log('Debug mode enabled. Use window.spectraDebug to access internals.');
}

// Console info
console.log(`
SpectraLoop Frontend v3.2 - Production with Temperature Safety
Keyboard shortcuts:
   Ctrl+Space: Emergency Stop
   Ctrl+A: Arm/Disarm System  
   Ctrl+T: Test Connection
   Ctrl+R: Toggle Relay
   Ctrl+L: Clear Command Log
   Ctrl+B: Turn Off Buzzer

MOTOR GROUPS:
   Levitation: Motors 1,2,3,4 (Pins 2,4,5,6)
   Thrust: Motors 5,6 (Pins 3,7)

TEMPERATURE SAFETY:
   Sensor: DS18B20 on Pin 8
   Buzzer: Pin 9 (Alarm notification)
   Relay Brake: Pin 11 (Safety cutoff)
   Thresholds: Safe <50°C, Warning 50-55°C, Alarm ≥55°C

FEATURES:
   Individual Motor Control
   Group Motor Control
   Software Brake Control  
   Relay Brake Control
   Arduino Reconnect Function
   Emergency Stop System
   Real-time Status Updates
   Command Logging
   Performance Monitoring
   Temperature Safety System
   Automatic Emergency Stop on Overheat
   Visual Temperature Alerts
   Buzzer Control
`);

if (window.location.protocol === 'file:') {
    console.warn('Running from file:// protocol. For best results, serve from a web server.');
}