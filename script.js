/*
 * SpectraLoop Frontend JavaScript v3.7 - REFLECTOR DATA FIXED
 * Arduino'dan gelen R:count:voltage:speed:avg_speed formatındaki reflector verilerini gösterir
 * Dual DS18B20 sensor monitoring + OMRON Reflector Counter
 */

// Configuration
const BACKEND_URL = 'http://192.168.241.82:5001';

// System State Management - REFLECTOR DATA ADDED
let systemState = {
    armed: false,
    brakeActive: false,
    relayBrakeActive: false,
    connected: false,
    motorStates: {1: false, 2: false, 3: false, 4: false, 5: false, 6: false},
    individualMotorSpeeds: {1: 0, 2: 0, 3: 0, 4: 0, 5: 0, 6: 0},
    groupSpeeds: {levitation: 0, thrust: 0},
    connectionStatus: {backend: false, arduino: false},
    
    // DUAL TEMPERATURE STATE
    temperature: {
        sensor1_temp: 25.0,
        sensor2_temp: 25.0,
        current: 25.0,
        alarm: false,
        buzzer_active: false,
        max_reached: 25.0,
        max_sensor1: 25.0,
        max_sensor2: 25.0,
        last_update: null,
        emergency_active: false,
        alarm_count: 0,
        update_frequency: 0.0,
        sensor1_connected: true,
        sensor2_connected: true,
        sensor_failure_count: 0,
        temperature_difference: 0.0,
        dual_sensor_mode: true
    },
    
    // REFLECTOR SYSTEM STATE - MAIN DATA
    reflector: {
        count: 0,                    // Toplam sayım - Arduino'dan R: formatında gelir
        voltage: 0.0,               // Sensör voltajı
        state: false,               // Algılama durumu
        average_speed: 0.0,         // Ortalama hız (ref/dk)
        instant_speed: 0.0,         // Anlık hız
        last_update: null,          // Son güncelleme zamanı
        system_active: true,        // Sistem aktif mi?
        detections: 0,              // Toplam algılama sayısı
        read_frequency: 0.0,        // Okuma frekansı (Hz)
        last_count_time: null,      // Son sayım zamanı
        performance: {
            total_runtime: 0.0,     // Toplam çalışma süresi (dakika)
            detection_rate: 0.0,    // Dakikada algılama oranı
            max_speed_recorded: 0.0 // Kaydedilen maksimum hız
        },
        statistics: {
            session_count: 0,       // Oturum sayımı
            daily_count: 0,         // Günlük sayım
            total_count: 0          // Toplam sayım
        }
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
    temperatureUpdateInterval: null,
    realtimeTemperatureInterval: null,
    reflectorUpdateInterval: null,
    isInitialized: false,
    lastTempAlarmNotified: false,
    performanceStats: {
        temperatureUpdatesCount: 0,
        reflectorUpdatesCount: 0,
        lastTempUpdateTime: 0,
        lastReflectorUpdateTime: 0,
        averageUpdateFrequency: 0
    }
};

// Constants
const CONFIG = {
    REQUEST_THROTTLE: 25,
    MAX_RETRIES: 3,
    STATUS_UPDATE_INTERVAL: 1000,        // Genel durum güncellemesi
    TEMPERATURE_UPDATE_INTERVAL: 500,    // Sıcaklık güncellemesi  
    REALTIME_TEMP_INTERVAL: 300,         // Ultra hızlı sıcaklık
    REFLECTOR_UPDATE_INTERVAL: 200,      // Ultra hızlı reflector güncelleme
    CONNECTION_TIMEOUT: 4000,
    MAX_LOG_ENTRIES: 30,
    NOTIFICATION_TIMEOUT: 4000,
    TEMP_SAFE_THRESHOLD: 50,
    TEMP_WARNING_THRESHOLD: 45,
    TEMP_ALARM_THRESHOLD: 55,
    TEMP_DIFF_WARNING_THRESHOLD: 5.0,
    PERFORMANCE_LOG_INTERVAL: 10000
};

// Utility Functions
class Utils {
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

// REFLECTOR DATA MANAGER - MAIN CLASS FOR DISPLAYING REFLECTOR DATA
class ReflectorDataManager {
    
    static updateReflectorDisplay(reflectorData) {
        if (!reflectorData) return;
        
        const now = Date.now();
        
        // Update main reflector data
        systemState.reflector.count = reflectorData.count || 0;
        systemState.reflector.voltage = reflectorData.voltage || 0.0;
        systemState.reflector.average_speed = reflectorData.average_speed || 0.0;
        systemState.reflector.instant_speed = reflectorData.instant_speed || 0.0;
        systemState.reflector.system_active = reflectorData.system_active || false;
        systemState.reflector.read_frequency = reflectorData.read_frequency || 0.0;
        systemState.reflector.last_update = new Date();
        
        // Update performance stats
        appState.performanceStats.reflectorUpdatesCount++;
        appState.performanceStats.lastReflectorUpdateTime = now;
        
        // Update all reflector UI elements
        this.updateMainReflectorDisplay();
        this.updateReflectorStatistics();
        this.updateReflectorMonitoring();
        this.updateReflectorPerformance();
        
        // Log significant count changes
        const oldCount = parseInt(document.getElementById('reflector-count')?.textContent || '0');
        if (systemState.reflector.count > oldCount) {
            const newDetections = systemState.reflector.count - oldCount;
            CommandLogger.log(`Reflector Detection`, true, `+${newDetections} (Total: ${systemState.reflector.count})`);
            console.log(`🔵 NEW REFLECTOR DETECTIONS: +${newDetections}, Total: ${systemState.reflector.count}`);
        }
    }
    
    static updateMainReflectorDisplay() {
        // Ana reflector gösterimi
        const countElement = document.getElementById('reflector-count');
        const voltageElement = document.getElementById('reflector-voltage');
        const avgSpeedElement = document.getElementById('reflector-avg-speed');
        const systemStatusElement = document.getElementById('reflector-system-status');
        const detectionStateElement = document.getElementById('reflector-detection-state');
        
        if (countElement) {
            countElement.textContent = systemState.reflector.count.toString();
            countElement.style.color = systemState.reflector.count > 0 ? '#00ff88' : '#aaa';
        }
        
        if (voltageElement) {
            voltageElement.textContent = `${systemState.reflector.voltage.toFixed(2)}V`;
            // Voltaj seviyesine göre renk
            if (systemState.reflector.voltage > 4.5) {
                voltageElement.style.color = '#00ff88'; // Yüksek voltaj - temiz
            } else if (systemState.reflector.voltage > 3.0) {
                voltageElement.style.color = '#ffc107'; // Orta voltaj - algılama
            } else {
                voltageElement.style.color = '#ff4757'; // Düşük voltaj - problem
            }
        }
        
        if (avgSpeedElement) {
            avgSpeedElement.textContent = systemState.reflector.average_speed.toFixed(1);
        }
        
        if (systemStatusElement) {
            systemStatusElement.textContent = systemState.reflector.system_active ? 'Aktif' : 'Pasif';
            systemStatusElement.style.color = systemState.reflector.system_active ? '#00ff88' : '#ff4757';
        }
        
        if (detectionStateElement) {
            const isDetecting = systemState.reflector.voltage < 4.0;
            detectionStateElement.textContent = isDetecting ? 'Algılandı' : 'Temiz';
            detectionStateElement.style.color = isDetecting ? '#ffc107' : '#00ff88';
        }
    }
    
    static updateReflectorStatistics() {
        // İstatistik gösterimi
        const elements = {
            'stats-total-count': systemState.reflector.count,
            'stats-avg-speed': `${systemState.reflector.average_speed.toFixed(1)} ref/dk`,
            'stats-runtime': Utils.formatUptime(systemState.reflector.performance.total_runtime * 60),
            'stats-efficiency': systemState.reflector.system_active ? '100%' : '0%',
            'monitor-reflector-count': systemState.reflector.count,
            'monitor-reflector-voltage': `${systemState.reflector.voltage.toFixed(2)}V`,
            'monitor-avg-speed': `${systemState.reflector.average_speed.toFixed(1)}/dk`,
            'monitor-instant-speed': `${systemState.reflector.instant_speed.toFixed(1)}/dk`,
            'monitor-read-freq': `${systemState.reflector.read_frequency.toFixed(1)} Hz`,
            'monitor-system-status': systemState.reflector.system_active ? 'Aktif' : 'Pasif',
            'monitor-session-count': systemState.reflector.statistics.session_count || systemState.reflector.count,
            'monitor-runtime': `${(systemState.reflector.performance.total_runtime || 0).toFixed(1)}dk`
        };
        
        Object.entries(elements).forEach(([id, value]) => {
            const element = document.getElementById(id);
            if (element && element.textContent !== value.toString()) {
                element.textContent = value.toString();
            }
        });
    }
    
    static updateReflectorMonitoring() {
        // Connection status
        const reflectorDot = document.getElementById('reflector-dot');
        const reflectorText = document.getElementById('reflector-connection-text');
        
        if (reflectorDot) {
            reflectorDot.className = systemState.reflector.system_active ? 'connection-dot connected' : 'connection-dot';
        }
        
        if (reflectorText) {
            reflectorText.textContent = systemState.reflector.system_active ? 'Bağlı' : 'Bağlantısız';
        }
        
        // Last update time
        const lastUpdateElement = document.getElementById('reflector-last-update');
        if (lastUpdateElement && systemState.reflector.last_update) {
            lastUpdateElement.textContent = Utils.formatTime(systemState.reflector.last_update);
        }
    }
    
    static updateReflectorPerformance() {
        // Performance indicators
        const tempSpeedRatio = document.getElementById('temp-speed-ratio');
        const systemLoadIndicator = document.getElementById('system-load-indicator');
        const performanceIndicator = document.getElementById('performance-indicator');
        
        if (tempSpeedRatio && systemState.temperature.current > 0) {
            const ratio = systemState.reflector.average_speed / systemState.temperature.current;
            tempSpeedRatio.textContent = ratio.toFixed(2);
        }
        
        if (systemLoadIndicator) {
            const isHighLoad = systemState.temperature.current > 40 && systemState.reflector.average_speed > 30;
            systemLoadIndicator.textContent = isHighLoad ? 'Yüksek' : 'Normal';
            systemLoadIndicator.style.color = isHighLoad ? '#ffc107' : '#00ff88';
        }
        
        if (performanceIndicator) {
            const isOptimal = systemState.reflector.system_active && systemState.reflector.read_frequency > 100;
            performanceIndicator.textContent = isOptimal ? 'Optimal' : 'Normal';
            performanceIndicator.style.color = isOptimal ? '#00ff88' : '#ffc107';
        }
    }
    
    // Ultra-fast reflector data fetching
    static async updateReflectorDataOnly() {
        try {
            const response = await RequestHandler.makeRequest(`${BACKEND_URL}/api/reflector/realtime`, {
                method: 'GET'
            }, 2000, 1);
            
            const data = await response.json();
            
            if (data && typeof data.count !== 'undefined') {
                this.updateReflectorDisplay(data);
                
                // Update connection status
                ConnectionManager.updateConnectionStatus('backend', true);
                appState.consecutiveErrors = 0;
                
                console.debug(`Reflector update: Count=${data.count}, Voltage=${data.voltage}V, Speed=${data.average_speed}rpm`);
            }
            
        } catch (error) {
            console.debug('Quick reflector update failed:', error.message);
            appState.consecutiveErrors++;
            
            if (appState.consecutiveErrors >= 3) {
                ConnectionManager.updateConnectionStatus('backend', false);
            }
        }
    }
}

// DUAL Temperature Manager - ENHANCED
class DualTemperatureManager {
    static updateDualTemperatureDisplay(tempData) {
        if (!tempData) return;
        
        // Extract dual temperature data
        const sensor1Temp = tempData.sensor1_temp || 25.0;
        const sensor2Temp = tempData.sensor2_temp || 25.0;
        const currentTemp = tempData.current || Math.max(sensor1Temp, sensor2Temp);
        const tempAlarm = tempData.alarm || false;
        const buzzerActive = tempData.buzzer_active || false;
        const maxTemp = tempData.max_reached || currentTemp;
        const maxSensor1 = tempData.max_sensor1 || sensor1Temp;
        const maxSensor2 = tempData.max_sensor2 || sensor2Temp;
        const alarmCount = tempData.alarm_count || 0;
        const emergencyActive = tempData.emergency_active || false;
        const updateFrequency = tempData.update_frequency || 0.0;
        const sensor1Connected = tempData.sensor1_connected !== undefined ? tempData.sensor1_connected : true;
        const sensor2Connected = tempData.sensor2_connected !== undefined ? tempData.sensor2_connected : true;
        const tempDifference = Math.abs(sensor1Temp - sensor2Temp);
        
        // Update performance stats
        appState.performanceStats.temperatureUpdatesCount++;
        
        const now = Date.now();
        if (appState.performanceStats.lastTempUpdateTime > 0) {
            const timeDiff = (now - appState.performanceStats.lastTempUpdateTime) / 1000;
            appState.performanceStats.averageUpdateFrequency = 1 / timeDiff;
        }
        appState.performanceStats.lastTempUpdateTime = now;
        
        // Update all dual temperature displays
        this.updateDualSensorElements(sensor1Temp, sensor2Temp, currentTemp, sensor1Connected, sensor2Connected);
        this.updateTemperatureStatus(currentTemp, tempAlarm, emergencyActive);
        this.updateTemperatureDetails(maxTemp, maxSensor1, maxSensor2, alarmCount, buzzerActive, updateFrequency, tempDifference);
        this.updateSensorConnectionStatus(sensor1Connected, sensor2Connected);
        this.updateRedundancyStatus(sensor1Connected, sensor2Connected);
        this.updateLastUpdateTime();
        
        // Store dual temperature data in system state
        systemState.temperature = {
            sensor1_temp: sensor1Temp,
            sensor2_temp: sensor2Temp,
            current: currentTemp,
            alarm: tempAlarm,
            buzzer_active: buzzerActive,
            max_reached: maxTemp,
            max_sensor1: maxSensor1,
            max_sensor2: maxSensor2,
            last_update: new Date(),
            emergency_active: emergencyActive,
            alarm_count: alarmCount,
            update_frequency: updateFrequency,
            sensor1_connected: sensor1Connected,
            sensor2_connected: sensor2Connected,
            sensor_failure_count: tempData.sensor_failure_count || 0,
            temperature_difference: tempDifference,
            dual_sensor_mode: true
        };
    }
    
    static updateDualSensorElements(sensor1Temp, sensor2Temp, safetyTemp, sensor1Connected, sensor2Connected) {
        // Update individual sensor temperatures
        const sensor1El = document.getElementById('sensor1-temp');
        const sensor2El = document.getElementById('sensor2-temp');
        const safetyTempEl = document.getElementById('safety-temp');
        
        if (sensor1El) {
            sensor1El.textContent = `${sensor1Temp.toFixed(1)}°C`;
            sensor1El.className = 'temp-current primary';
            
            if (!sensor1Connected) {
                sensor1El.classList.add('disconnected');
            } else if (sensor1Temp >= CONFIG.TEMP_ALARM_THRESHOLD) {
                sensor1El.classList.add('danger');
            } else if (sensor1Temp >= CONFIG.TEMP_WARNING_THRESHOLD) {
                sensor1El.classList.add('warning');
            }
        }
        
        if (sensor2El) {
            sensor2El.textContent = `${sensor2Temp.toFixed(1)}°C`;
            sensor2El.className = 'temp-current secondary';
            
            if (!sensor2Connected) {
                sensor2El.classList.add('disconnected');
            } else if (sensor2Temp >= CONFIG.TEMP_ALARM_THRESHOLD) {
                sensor2El.classList.add('danger');
            } else if (sensor2Temp >= CONFIG.TEMP_WARNING_THRESHOLD) {
                sensor2El.classList.add('warning');
            }
        }
        
        if (safetyTempEl) {
            safetyTempEl.textContent = `${safetyTemp.toFixed(1)}°C`;
            safetyTempEl.className = 'temp-current safety';
            
            if (safetyTemp >= CONFIG.TEMP_ALARM_THRESHOLD) {
                safetyTempEl.classList.add('danger');
            } else if (safetyTemp >= CONFIG.TEMP_WARNING_THRESHOLD) {
                safetyTempEl.classList.add('warning');
            }
        }
    }
    
    static updateTemperatureDetails(maxTemp, maxSensor1, maxSensor2, alarmCount, buzzerActive, updateFrequency, tempDifference) {
        const updates = {
            'temp-alarm-count': alarmCount,
            'buzzer-status': buzzerActive ? 'Aktif' : 'Pasif',
            'temp-frequency': updateFrequency ? `${updateFrequency.toFixed(1)}` : '0.0',
            'detailed-sensor1-temp': `${systemState.temperature.sensor1_temp.toFixed(1)}°C`,
            'detailed-sensor2-temp': `${systemState.temperature.sensor2_temp.toFixed(1)}°C`,
            'detailed-sensor1-max': `${maxSensor1.toFixed(1)}°C`,
            'detailed-sensor2-max': `${maxSensor2.toFixed(1)}°C`,
            'detailed-safety-temp': `${systemState.temperature.current.toFixed(1)}°C`,
            'detailed-temp-diff': `${tempDifference.toFixed(1)}°C`,
            'temp-update-frequency': updateFrequency ? `${updateFrequency.toFixed(1)} Hz` : '0 Hz',
            'temp-difference-value': `${tempDifference.toFixed(1)}°C`
        };
        
        Object.entries(updates).forEach(([id, value]) => {
            const element = document.getElementById(id);
            if (element && element.textContent !== value) {
                element.textContent = value;
            }
        });
        
        const buzzerBtn = document.getElementById('buzzer-off-btn');
        if (buzzerBtn) {
            buzzerBtn.disabled = !buzzerActive;
        }
    }
    
    static updateSensorConnectionStatus(sensor1Connected, sensor2Connected) {
        const sensor1Dot = document.getElementById('sensor1-dot');
        const sensor1StatusText = document.getElementById('sensor1-status-text');
        const sensor1StatusMini = document.getElementById('sensor1-status-mini');
        
        if (sensor1Dot) {
            sensor1Dot.className = sensor1Connected ? 'connection-dot connected' : 'connection-dot';
        }
        if (sensor1StatusText) {
            sensor1StatusText.textContent = sensor1Connected ? 'Bağlı' : 'Bağlantısız';
        }
        if (sensor1StatusMini) {
            sensor1StatusMini.textContent = '●';
            sensor1StatusMini.style.color = sensor1Connected ? '#00ff88' : '#ff4757';
        }
        
        const sensor2Dot = document.getElementById('sensor2-dot');
        const sensor2StatusText = document.getElementById('sensor2-status-text');
        const sensor2StatusMini = document.getElementById('sensor2-status-mini');
        
        if (sensor2Dot) {
            sensor2Dot.className = sensor2Connected ? 'connection-dot connected' : 'connection-dot';
        }
        if (sensor2StatusText) {
            sensor2StatusText.textContent = sensor2Connected ? 'Bağlı' : 'Bağlantısız';
        }
        if (sensor2StatusMini) {
            sensor2StatusMini.textContent = '●';
            sensor2StatusMini.style.color = sensor2Connected ? '#00ff88' : '#ff4757';
        }
    }
    
    static updateRedundancyStatus(sensor1Connected, sensor2Connected) {
        let redundancyStatus, redundancyColor;
        
        if (sensor1Connected && sensor2Connected) {
            redundancyStatus = 'Çift Aktif';
            redundancyColor = '#00ff88';
        } else if (sensor1Connected || sensor2Connected) {
            redundancyStatus = 'Tek Aktif';
            redundancyColor = '#ffc107';
        } else {
            redundancyStatus = 'Sensör Yok';
            redundancyColor = '#ff4757';
        }
        
        const redundancyElements = [
            'sensor-redundancy-status',
            'detailed-redundancy-status'
        ];
        
        redundancyElements.forEach(id => {
            const element = document.getElementById(id);
            if (element) {
                element.textContent = redundancyStatus;
                element.style.color = redundancyColor;
            }
        });
    }
    
    static updateTemperatureStatus(currentTemp, tempAlarm, emergencyActive) {
        const tempStatusEl = document.getElementById('temp-status-text');
        
        let statusText;
        if (tempAlarm || emergencyActive) {
            statusText = 'ALARM!';
        } else if (currentTemp >= CONFIG.TEMP_WARNING_THRESHOLD) {
            statusText = 'Uyarı';
        } else {
            statusText = 'Güvenli';
        }
        
        if (tempStatusEl && tempStatusEl.textContent !== statusText) {
            tempStatusEl.textContent = statusText;
        }
    }
    
    static updateLastUpdateTime() {
        const lastUpdateEl = document.getElementById('temp-last-update');
        if (lastUpdateEl) {
            lastUpdateEl.textContent = Utils.formatTime(new Date());
        }
    }
    
    // Ultra-fast dual temperature updates
    static async updateDualTemperatureOnly() {
        try {
            const response = await RequestHandler.makeRequest(`${BACKEND_URL}/api/temperature/realtime`, {
                method: 'GET'
            }, 2000, 1);
            
            const data = await response.json();
            
            if (data.dual_sensor_mode && data.sensor1_temp !== undefined && data.sensor2_temp !== undefined) {
                const quickDualTempData = {
                    sensor1_temp: data.sensor1_temp,
                    sensor2_temp: data.sensor2_temp,
                    current: data.temperature,
                    alarm: data.alarm,
                    buzzer_active: data.buzzer,
                    update_frequency: data.frequency_hz,
                    sensor1_connected: data.sensor1_connected,
                    sensor2_connected: data.sensor2_connected,
                    max_reached: systemState.temperature.max_reached,
                    max_sensor1: Math.max(systemState.temperature.max_sensor1, data.sensor1_temp),
                    max_sensor2: Math.max(systemState.temperature.max_sensor2, data.sensor2_temp),
                    emergency_active: data.alarm,
                    alarm_count: systemState.temperature.alarm_count,
                    sensor_failure_count: systemState.temperature.sensor_failure_count
                };
                
                this.updateDualTemperatureDisplay(quickDualTempData);
                
                // Also update reflector data if available
                if (data.reflector_count !== undefined) {
                    const reflectorQuickData = {
                        count: data.reflector_count,
                        voltage: data.reflector_voltage || 0,
                        average_speed: data.reflector_speed || 0,
                        system_active: data.reflector_system_active !== undefined ? data.reflector_system_active : true
                    };
                    ReflectorDataManager.updateReflectorDisplay(reflectorQuickData);
                }
                
                ConnectionManager.updateConnectionStatus('backend', true);
                appState.consecutiveErrors = 0;
            }
            
        } catch (error) {
            console.debug('Quick dual temperature update failed:', error.message);
            appState.consecutiveErrors++;
            
            if (appState.consecutiveErrors >= 3) {
                ConnectionManager.updateConnectionStatus('backend', false);
            }
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
                console.debug(`Making request to ${url} (attempt ${attempt + 1}/${retries})`);
                
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
                return response;
                
            } catch (error) {
                console.debug(`Request failed (attempt ${attempt + 1}): ${error.message}`);
                
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
                
                await new Promise(resolve => setTimeout(resolve, 400 * (attempt + 1)));
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

// Status Manager - DUAL TEMPERATURE + REFLECTOR ENHANCED
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
                
                // Update dual temperature data
                if (data.temperature) {
                    DualTemperatureManager.updateDualTemperatureDisplay(data.temperature);
                }
                
                // Update reflector data - CRITICAL: This was missing!
                if (data.reflector) {
                    console.log('📊 Reflector data received from backend:', data.reflector);
                    ReflectorDataManager.updateReflectorDisplay(data.reflector);
                }
                
                // Update motor states
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
                
                // Update group speeds
                systemState.groupSpeeds.levitation = (data.group_speeds && data.group_speeds.levitation) || 0;
                systemState.groupSpeeds.thrust = (data.group_speeds && data.group_speeds.thrust) || 0;
                UIManager.updateGroupSpeedDisplay('levitation', systemState.groupSpeeds.levitation);
                UIManager.updateGroupSpeedDisplay('thrust', systemState.groupSpeeds.thrust);
                
                // Update UI elements
                UIManager.updateMotorCount();
                UIManager.updateArmButton();
                UIManager.updateRelayBrakeStatus();
                
                // Update connection status
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
            if (appState.consecutiveErrors >= 2) {
                ConnectionManager.updateConnectionStatus('backend', false);
                ConnectionManager.updateConnectionStatus('arduino', false);
            }
            console.debug('Status poll error:', error.message);
        }
    }

    static startStatusPolling() {
        // Stop existing intervals
        if (appState.statusUpdateInterval) {
            clearInterval(appState.statusUpdateInterval);
        }
        if (appState.temperatureUpdateInterval) {
            clearInterval(appState.temperatureUpdateInterval);
        }
        if (appState.realtimeTemperatureInterval) {
            clearInterval(appState.realtimeTemperatureInterval);
        }
        if (appState.reflectorUpdateInterval) {
            clearInterval(appState.reflectorUpdateInterval);
        }
        
        // Start general status polling
        appState.statusUpdateInterval = setInterval(() => {
            this.pollStatus();
        }, CONFIG.STATUS_UPDATE_INTERVAL);
        
        // Start dual temperature polling
        appState.temperatureUpdateInterval = setInterval(() => {
            DualTemperatureManager.updateDualTemperatureOnly();
        }, CONFIG.TEMPERATURE_UPDATE_INTERVAL);
        
        // Start ultra-fast realtime temperature polling
        appState.realtimeTemperatureInterval = setInterval(() => {
            DualTemperatureManager.updateDualTemperatureOnly();
        }, CONFIG.REALTIME_TEMP_INTERVAL);
        
        // Start ultra-fast reflector polling - CRITICAL FOR REFLECTOR DATA!
        appState.reflectorUpdateInterval = setInterval(() => {
            ReflectorDataManager.updateReflectorDataOnly();
        }, CONFIG.REFLECTOR_UPDATE_INTERVAL);
        
        // Initial calls
        setTimeout(() => this.pollStatus(), 500);
        setTimeout(() => DualTemperatureManager.updateDualTemperatureOnly(), 100);
        setTimeout(() => ReflectorDataManager.updateReflectorDataOnly(), 200);
        
        console.log('🚀 Status polling started with reflector updates every', CONFIG.REFLECTOR_UPDATE_INTERVAL, 'ms');
    }

    static stopStatusPolling() {
        if (appState.statusUpdateInterval) {
            clearInterval(appState.statusUpdateInterval);
            appState.statusUpdateInterval = null;
        }
        if (appState.temperatureUpdateInterval) {
            clearInterval(appState.temperatureUpdateInterval);
            appState.temperatureUpdateInterval = null;
        }
        if (appState.realtimeTemperatureInterval) {
            clearInterval(appState.realtimeTemperatureInterval);
            appState.realtimeTemperatureInterval = null;
        }
        if (appState.reflectorUpdateInterval) {
            clearInterval(appState.reflectorUpdateInterval);
            appState.reflectorUpdateInterval = null;
        }
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
            NotificationManager.show('Dual sensör + reflector bağlantı test ediliyor...', 'info');
            
            const response = await RequestHandler.makeRequest(`${BACKEND_URL}/api/ping`);
            const data = await response.json();
            
            if (data.status === 'ok') {
                CommandLogger.log('Dual sensör + reflector bağlantı testi başarılı', true);
                
                let tempInfo = 'Sensör Yok';
                if (data.dual_temperatures) {
                    tempInfo = `S1:${data.dual_temperatures.sensor1_temp}°C S2:${data.dual_temperatures.sensor2_temp}°C Max:${data.dual_temperatures.max_temp}°C`;
                }
                
                let reflectorInfo = 'Reflector Yok';
                if (data.reflector_system) {
                    reflectorInfo = `Count:${data.reflector_system.count}, Voltage:${data.reflector_system.voltage}V, Speed:${data.reflector_system.average_speed}rpm`;
                }
                
                NotificationManager.show(`Bağlantı başarılı! ${tempInfo} | ${reflectorInfo}`, 'success');
                this.updateConnectionStatus('backend', true);
                this.updateConnectionStatus('arduino', data.arduino_connected);
            } else {
                throw new Error(data.message || 'Test failed');
            }
            
        } catch (error) {
            CommandLogger.log('Dual sensör + reflector bağlantı testi', false, error.message);
            NotificationManager.show(`Bağlantı testi başarısız: ${error.message}`, 'error');
            this.updateConnectionStatus('backend', false);
            this.updateConnectionStatus('arduino', false);
        }
    }

    static async reconnectArduino() {
        try {
            NotificationManager.show('Arduino dual sensör + reflector sistemi yeniden bağlanıyor...', 'info');
            
            const response = await RequestHandler.makeRequest(`${BACKEND_URL}/api/reconnect`, {
                method: 'POST'
            });
            
            const data = await response.json();
            
            if (data.status === 'success') {
                CommandLogger.log('Arduino dual sensör + reflector sistemi yeniden bağlandı', true);
                NotificationManager.show('Arduino dual sensör + reflector sistemi yeniden bağlandı!', 'success');
                setTimeout(() => StatusManager.pollStatus(), 1000);
                setTimeout(() => ReflectorDataManager.updateReflectorDataOnly(), 1500);
            } else {
                throw new Error(data.message || 'Reconnection failed');
            }
            
        } catch (error) {
            CommandLogger.log('Arduino dual sensör + reflector yeniden bağlanma', false, error.message);
            NotificationManager.show(`Arduino yeniden bağlanamadı: ${error.message}`, 'error');
        }
    }
}

// Motor Control
class MotorController {
    static async startMotor(motorNum) {
        if (systemState.temperature.alarm || systemState.temperature.emergency_active) {
            NotificationManager.show(`Sıcaklık alarmı nedeniyle motorlar başlatılamaz! S1:${systemState.temperature.sensor1_temp.toFixed(1)}°C S2:${systemState.temperature.sensor2_temp.toFixed(1)}°C`, 'warning');
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
                    CommandLogger.log(`Motor ${motorNum} başlatıldı`, true, 
                        `${speed}% - Reflector: ${systemState.reflector.count}`);
                    NotificationManager.show(`Motor ${motorNum} başlatıldı!`, 'success');
                    
                    // Quick updates after motor start
                    setTimeout(() => DualTemperatureManager.updateDualTemperatureOnly(), 200);
                    setTimeout(() => ReflectorDataManager.updateReflectorDataOnly(), 300);
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
            NotificationManager.show(`Sıcaklık alarmı nedeniyle motor kontrol edilemez!`, 'warning');
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

// System Controller
class SystemController {
    static async toggleArm() {
        if (!systemState.armed && (systemState.temperature.alarm || systemState.temperature.emergency_active)) {
            NotificationManager.show(`Sıcaklık alarmı nedeniyle sistem hazırlanamaz!`, 'warning');
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
                    CommandLogger.log(`Sistem ${statusText}`, true, 
                        `Reflector: ${systemState.reflector.count}, Temp: ${systemState.temperature.current.toFixed(1)}°C`);
                    NotificationManager.show(`Sistem ${statusText}!`, 'success');
                    
                    // Quick updates after system change
                    setTimeout(() => DualTemperatureManager.updateDualTemperatureOnly(), 200);
                    setTimeout(() => ReflectorDataManager.updateReflectorDataOnly(), 300);
                }

            } catch (error) {
                CommandLogger.log('Arm/Disarm', false, error.message);
                NotificationManager.show(`Sistem hatası: ${error.message}`, 'error');
                console.error('Arm/Disarm error:', error);
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

            CommandLogger.log('ACİL DURDURMA AKTİF', true, 
                `Tüm sistemler durduruldu - Reflector Final: ${systemState.reflector.count}`);
            NotificationManager.show('ACİL DURDURMA! Tüm sistemler durduruldu!', 'error', 6000);

        } catch (error) {
            CommandLogger.log('Acil durdurma', false, error.message);
            NotificationManager.show('Acil durdurma sinyali gönderilemedi!', 'warning');
            console.error('Emergency stop error:', error);
        }
    }
}

// UI Manager
class UIManager {
    static updateMotorStatus(motorNum, running, speed) {
        const statusElement = document.getElementById(`motor${motorNum}-status`);
        const speedDisplay = document.getElementById(`motor${motorNum}-speed-display`);
        
        if (statusElement) {
            const newText = running ? 'ON' : 'OFF';
            if (statusElement.textContent !== newText) {
                statusElement.textContent = newText;
                statusElement.className = running ? 'motor-status running' : 'motor-status off';
            }
        }
        
        if (speedDisplay) {
            const newSpeedText = `Hız: ${speed}%`;
            if (speedDisplay.textContent !== newSpeedText) {
                speedDisplay.textContent = newSpeedText;
            }
        }
    }

    static updateMotorSpeedDisplay(motorNum, speed) {
        const speedDisplay = document.getElementById(`motor${motorNum}-speed-display`);
        if (speedDisplay) {
            const newSpeedText = `Hız: ${speed}%`;
            if (speedDisplay.textContent !== newSpeedText) {
                speedDisplay.textContent = newSpeedText;
            }
        }
    }

    static updateGroupSpeedDisplay(groupType, speed) {
        const speedElement = document.getElementById(`${groupType}-speed`);
        const sliderElement = document.getElementById(`${groupType}-slider`);
        
        if (speedElement) {
            const newText = `${speed}%`;
            if (speedElement.textContent !== newText) {
                speedElement.textContent = newText;
            }
        }
        
        if (sliderElement && sliderElement.value != speed) {
            sliderElement.value = speed;
        }
    }

    static updateMotorCount() {
        const activeCount = Object.values(systemState.motorStates).filter(state => state).length;
        const countElement = document.getElementById('motor-count');
        const activeMotorsElement = document.getElementById('active-motors');
        
        if (countElement) {
            const newText = `${activeCount}/6`;
            if (countElement.textContent !== newText) {
                countElement.textContent = newText;
                countElement.style.color = activeCount > 0 ? '#00ff88' : '#aaa';
            }
        }
        
        if (activeMotorsElement) {
            const newText = `${activeCount}/6`;
            if (activeMotorsElement.textContent !== newText) {
                activeMotorsElement.textContent = newText;
            }
        }

        // Calculate average speeds with reflector correlation
        const levSpeeds = [1,2,3,4].map(i => systemState.individualMotorSpeeds[i]).filter(s => s > 0);
        const thrSpeeds = [5,6].map(i => systemState.individualMotorSpeeds[i]).filter(s => s > 0);
        
        const levAvg = levSpeeds.length > 0 ? Math.round(levSpeeds.reduce((a,b) => a+b, 0) / levSpeeds.length) : 0;
        const thrAvg = thrSpeeds.length > 0 ? Math.round(thrSpeeds.reduce((a,b) => a+b, 0) / thrSpeeds.length) : 0;
        
        const speedUpdates = {
            'lev-avg-speed': `${levAvg}%`,
            'thr-avg-speed': `${thrAvg}%`,
            'total-speed': `${activeCount > 0 ? Math.round((levAvg + thrAvg) / 2) : 0}%`
        };
        
        Object.entries(speedUpdates).forEach(([id, value]) => {
            const element = document.getElementById(id);
            if (element && element.textContent !== value) {
                element.textContent = value;
            }
        });

        this.updateSimulatedValues(activeCount);
    }

    static updateSimulatedValues(activeCount) {
        // Enhanced simulation with reflector correlation
        const baseRpm = activeCount * 1500;
        const tempEffect = Math.max(0, (systemState.temperature.current - 25) * 10);
        const reflectorEffect = systemState.reflector.average_speed * 2; // Reflector contribution
        const totalRpm = baseRpm + tempEffect + reflectorEffect + Math.random() * 500;
        
        const rpmElement = document.getElementById('total-rpm');
        if (rpmElement) {
            const newRpm = Math.round(totalRpm);
            if (rpmElement.textContent != newRpm) {
                rpmElement.textContent = newRpm;
            }
        }

        // Power calculation with reflector load
        const basePower = activeCount * 45;
        const tempPowerEffect = Math.max(0, (systemState.temperature.current - 25) * 2);
        const reflectorPowerEffect = systemState.reflector.system_active ? 15 : 0;
        const powerUsage = basePower + tempPowerEffect + reflectorPowerEffect + Math.random() * 20;
        
        const powerElement = document.getElementById('power-usage');
        if (powerElement) {
            const newPower = `${Math.round(powerUsage)}W`;
            if (powerElement.textContent !== newPower) {
                powerElement.textContent = newPower;
            }
        }
    }

    static updateArmButton() {
        const armButton = document.getElementById('arm-button');
        const systemStatus = document.getElementById('system-status');
        
        if (armButton) {
            if (systemState.armed) {
                if (!armButton.textContent.includes('DEVRE DIŞI')) {
                    armButton.textContent = 'SİSTEMİ DEVRE DIŞI BIRAK';
                    armButton.className = 'arm-button armed';
                }
            } else {
                if (!armButton.textContent.includes('HAZIRLA')) {
                    armButton.textContent = 'SİSTEMİ HAZIRLA';
                    armButton.className = 'arm-button';
                }
            }
        }
        
        if (systemStatus) {
            const newStatus = systemState.armed ? 'Hazır' : 'Devre Dışı';
            if (systemStatus.textContent !== newStatus) {
                systemStatus.textContent = newStatus;
                systemStatus.className = systemState.armed ? 'status-value status-armed' : 'status-value status-error';
            }
        }
    }

    static updateRelayBrakeStatus() {
        const relayStatus = document.getElementById('relay-status');
        const relayBrakeStatus = document.getElementById('relay-brake-status');
        
        const statusText = systemState.relayBrakeActive ? 'Aktif' : 'Pasif';
        const statusColor = systemState.relayBrakeActive ? '#00ff88' : '#ff0066';
        
        if (relayStatus && relayStatus.textContent !== statusText) {
            relayStatus.textContent = statusText;
            relayStatus.style.color = statusColor;
        }
        
        if (relayBrakeStatus && relayBrakeStatus.textContent !== statusText) {
            relayBrakeStatus.textContent = statusText;
            relayBrakeStatus.style.color = statusColor;
        }
    }

    static updateStatistics(stats) {
        const elements = {
            'total-commands': stats.commands || 0,
            'total-errors': stats.errors || 0,
            'uptime': Utils.formatUptime(stats.uptime_seconds || 0),
            'arduino-port': stats.port_info?.port || '--'
        };

        Object.entries(elements).forEach(([id, value]) => {
            const element = document.getElementById(id);
            if (element && element.textContent !== value) {
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
        if (loadingText && loadingText.textContent !== text) {
            loadingText.textContent = text;
        }
    }
}

// REFLECTOR FUNCTIONS - NEW
window.resetReflectorCounter = async function() {
    try {
        NotificationManager.show('Reflector sayacı sıfırlanıyor...', 'info');
        
        const response = await RequestHandler.makeRequest(`${BACKEND_URL}/api/reflector/reset`, {
            method: 'POST'
        });
        
        const data = await response.json();
        
        if (data.status === 'success') {
            // Reset local state
            systemState.reflector.count = 0;
            systemState.reflector.detections = 0;
            systemState.reflector.statistics.session_count = 0;
            
            // Update UI immediately
            ReflectorDataManager.updateReflectorDisplay(systemState.reflector);
            
            CommandLogger.log('Reflector sayacı sıfırlandı', true);
            NotificationManager.show('Reflector sayacı başarıyla sıfırlandı!', 'success');
            
            // Force update
            setTimeout(() => ReflectorDataManager.updateReflectorDataOnly(), 500);
        } else {
            throw new Error(data.message || 'Reset failed');
        }
        
    } catch (error) {
        CommandLogger.log('Reflector sayacı sıfırlama', false, error.message);
        NotificationManager.show(`Reflector sayacı sıfırlanamadı: ${error.message}`, 'error');
    }
};

window.calibrateReflectorSensor = async function() {
    NotificationManager.show('Reflector sensör kalibrasyonu henüz desteklenmiyor', 'warning');
};

window.showReflectorDetails = function() {
    NotificationManager.show('Detaylı reflector istatistikleri açılacak...', 'info');
};

window.hideReflectorDetails = function() {
    // Modal kapatma fonksiyonu
};

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
window.turnOffBuzzer = () => DualTemperatureManager.turnOffBuzzer();

// Group Controller Class
class GroupController {
    static async startGroup(groupType) {
        if (systemState.temperature.alarm || systemState.temperature.emergency_active) {
            NotificationManager.show(`Sıcaklık alarmı nedeniyle motor grubu başlatılamaz!`, 'warning');
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
                    CommandLogger.log(`${groupName} grubu başlatıldı`, true, 
                        `${speed}% - M${motorRange.join(',')} - Reflector: ${systemState.reflector.count}`);
                    NotificationManager.show(`${groupName} grubu başlatıldı! (M${motorRange.join(',')})`, 'success');
                    
                    // Quick updates after group start
                    setTimeout(() => DualTemperatureManager.updateDualTemperatureOnly(), 200);
                    setTimeout(() => ReflectorDataManager.updateReflectorDataOnly(), 300);
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
        }, 200);
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

// System Controller - Additional methods
SystemController.controlRelayBrake = async function(action) {
    if (action === 'on' && (systemState.temperature.alarm || systemState.temperature.emergency_active)) {
        NotificationManager.show(`Sıcaklık alarmı nedeniyle röle aktif yapılamaz!`, 'warning');
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
                CommandLogger.log(`Röle ${status}`, true, `Reflector: ${systemState.reflector.count}`);
                NotificationManager.show(`Röle sistem ${status}!`, systemState.relayBrakeActive ? 'success' : 'warning');
            }

        } catch (error) {
            CommandLogger.log('Röle kontrol', false, error.message);
            NotificationManager.show(`Röle kontrol hatası: ${error.message}`, 'error');
            console.error('Relay brake error:', error);
        }
    });
};

SystemController.controlBrake = async function(action) {
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
};

// Temperature Manager - Additional methods
DualTemperatureManager.turnOffBuzzer = async function() {
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
            
            // Log dual temperatures when buzzer turned off
            if (data.dual_temps) {
                CommandLogger.log('Buzzer kapatıldığında sıcaklıklar', true, 
                    `S1:${data.dual_temps.sensor1}°C S2:${data.dual_temps.sensor2}°C Max:${data.dual_temps.max}°C`);
            }
        } else {
            throw new Error(data.message || 'Buzzer kapatılamadı');
        }
    } catch (error) {
        CommandLogger.log('Buzzer kapatma', false, error.message);
        NotificationManager.show(`Buzzer kapatılamadı: ${error.message}`, 'error');
    }
};

// Application Lifecycle - DUAL TEMPERATURE + REFLECTOR ENHANCED
class Application {
    static async initialize() {
        console.log('SpectraLoop Frontend DUAL TEMPERATURE + REFLECTOR v3.7 initializing...');
        console.log('REFLECTOR FEATURES: Omron photoelectric sensor counter with ultra-fast updates');
        
        try {
            UIManager.showLoading(true);
            UIManager.setLoadingText('Dual sensör + reflector sistem başlatılıyor...');
            
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
            
            UIManager.setLoadingText('Ultra-fast dual sensör + reflector polling başlatılıyor...');
            
            StatusManager.startStatusPolling();
            
            // Start performance monitoring
            this.startPerformanceMonitoring();
            
            CommandLogger.log('DUAL SENSOR + REFLECTOR Frontend başlatıldı', true, 'Ultra-fast v3.7 + Omron Reflector Counter');
            NotificationManager.show('SpectraLoop DUAL SENSOR + REFLECTOR sistemi hazır! ⚡Reflector sayımları canlı⚡', 'success');
            
            UIManager.showLoading(false);
            appState.isInitialized = true;
            
            console.log('🚀 DUAL SENSOR + REFLECTOR Frontend initialization complete');
            console.log('📊 Reflector data will update every', CONFIG.REFLECTOR_UPDATE_INTERVAL, 'ms');
            
        } catch (error) {
            console.error('Dual sensor + reflector initialization error:', error);
            UIManager.setLoadingText('Başlatma hatası! Yeniden denenecek...');
            CommandLogger.log('Dual sensör + reflector başlatma hatası', false, error.message);
            
            setTimeout(() => {
                this.initialize();
            }, 2000);
        }
    }

    static startPerformanceMonitoring() {
        setInterval(() => {
            if (appState.performanceStats.averageUpdateFrequency > 0) {
                console.debug(`Performance: Temp ${appState.performanceStats.averageUpdateFrequency.toFixed(2)} Hz, Reflector ${appState.performanceStats.reflectorUpdatesCount} updates`);
            }
            
            // Log reflector status
            if (systemState.reflector.system_active && systemState.reflector.count > 0) {
                console.debug(`🔵 Reflector Status: Count=${systemState.reflector.count}, Speed=${systemState.reflector.average_speed.toFixed(1)}rpm, Voltage=${systemState.reflector.voltage.toFixed(2)}V`);
            }
        }, CONFIG.PERFORMANCE_LOG_INTERVAL);
    }

    static setupEventListeners() {
        document.addEventListener('visibilitychange', () => {
            if (document.visibilityState === 'visible' && appState.isInitialized) {
                setTimeout(() => {
                    StatusManager.pollStatus();
                    DualTemperatureManager.updateDualTemperatureOnly();
                    ReflectorDataManager.updateReflectorDataOnly();
                }, 200);
            }
        });

        // Keyboard shortcuts
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
                        DualTemperatureManager.turnOffBuzzer();
                        break;
                    case 'z': // NEW: Reset reflector counter
                        event.preventDefault();
                        resetReflectorCounter();
                        break;
                }
            }
        });

        // Enhanced error handling
        window.addEventListener('beforeunload', (event) => {
            if (systemState.armed || Object.values(systemState.motorStates).some(state => state)) {
                const message = 'Motorlar çalışıyor! Sayfayı kapatmak istediğinizden emin misiniz?';
                event.preventDefault();
                event.returnValue = message;
                return message;
            }
        });

        window.addEventListener('online', () => {
            NotificationManager.show('İnternet bağlantısı yeniden kuruldu - Dual sensör + reflector sistemi aktif', 'success');
            setTimeout(() => {
                StatusManager.pollStatus();
                DualTemperatureManager.updateDualTemperatureOnly();
                ReflectorDataManager.updateReflectorDataOnly();
            }, 500);
        });

        window.addEventListener('offline', () => {
            NotificationManager.show('İnternet bağlantısı kesildi - Sistem offline', 'warning', 2000);
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
    }

    static shutdown() {
        console.log('Shutting down DUAL TEMPERATURE + REFLECTOR SpectraLoop Frontend...');
        
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
            
            CommandLogger.log('DUAL SENSOR + REFLECTOR Frontend kapatıldı', true, `Final Count: ${systemState.reflector.count}`);
            console.log('DUAL SENSOR + REFLECTOR Frontend shutdown complete');
            
        } catch (error) {
            console.error('Dual sensor + reflector shutdown error:', error);
        }
    }
}

// Initialize application
document.addEventListener('DOMContentLoaded', () => {
    Application.initialize();
});

window.addEventListener('beforeunload', () => {
    Application.shutdown();
});

// Debug mode - ENHANCED WITH REFLECTOR
if (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1') {
    window.spectraDebugDualTempReflector = {
        systemState,
        appState,
        performanceStats: appState.performanceStats,
        dualTempState: systemState.temperature,
        reflectorState: systemState.reflector,
        CONFIG,
        CommandLogger,
        NotificationManager,
        ConnectionManager,
        DualTemperatureManager,
        ReflectorDataManager,
        MotorController,
        GroupController,
        SystemController,
        StatusManager,
        UIManager,
        Application
    };
    
    console.log('DUAL TEMPERATURE + REFLECTOR Debug mode enabled. Use window.spectraDebugDualTempReflector to access internals.');
    console.log('Reflector data: systemState.reflector');
    console.log('Force reflector update: ReflectorDataManager.updateReflectorDataOnly()');
}

// Console info - ENHANCED WITH REFLECTOR
console.log(`
SpectraLoop Frontend DUAL TEMPERATURE + REFLECTOR v3.7 - FIXED

🌡️ DUAL SENSOR FEATURES:
   ⚡ Primary DS18B20 sensor (Pin 8)
   ⚡ Secondary DS18B20 sensor (Pin 13)
   ⚡ 300ms ultra-fast realtime updates
   ⚡ 500ms comprehensive dual updates
   ⚡ Individual sensor health monitoring
   ⚡ Redundant safety logic (worst-case)
   ⚡ Temperature difference warnings
   ⚡ Automatic sensor failover

📏 REFLECTOR COUNTER FEATURES:
   🔵 Omron photoelectric sensor (Pin A0)
   🔵 200ms ultra-fast reflector updates
   🔵 Real-time count display
   🔵 Voltage monitoring
   🔵 Speed calculations (ref/min)
   🔵 Performance statistics
   🔵 Session and daily tracking
   🔵 Arduino R: format parsing

🔧 OPTIMIZATION FEATURES:
   ⚡ 1000ms general status polling
   ⚡ Optimized DOM updates
   ⚡ Dual sensor + reflector performance tracking
   ⚡ Enhanced connection monitoring
   ⚡ Smart request throttling (25ms)

⌨️ Keyboard shortcuts:
   Ctrl+Space: Emergency Stop
   Ctrl+A: Arm/Disarm System  
   Ctrl+T: Test Connection
   Ctrl+R: Toggle Relay
   Ctrl+L: Clear Command Log
   Ctrl+B: Turn Off Buzzer
   Ctrl+Z: Reset Reflector Counter (NEW)

📊 REFLECTOR DATA FLOW:
   Arduino → R:count:voltage:speed:avg_speed
   Backend → /api/reflector/realtime
   Frontend → ReflectorDataManager updates
   
⚡ NOW WITH LIVE REFLECTOR COUNTING! ⚡
`);

if (window.location.protocol === 'file:') {
    console.warn('Running from file:// protocol. For best results, serve from a web server.');
}