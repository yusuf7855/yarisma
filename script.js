/*
 * SpectraLoop Frontend JavaScript DUAL TEMPERATURE + REFLECTOR COUNTER v3.6
 * Dual DS18B20 sensor monitoring + Omron reflector counting system
 * Individual sensor + reflector tracking + combined safety logic + ultra-fast updates
 */

// Configuration - DUAL SENSOR + REFLECTOR OPTIMIZED
const BACKEND_URL = 'http://192.168.241.82:5001';

// System State Management - DUAL TEMPERATURE + REFLECTOR ENHANCED
let systemState = {
    armed: false,
    brakeActive: false,
    relayBrakeActive: false,
    connected: false,
    motorStates: {1: false, 2: false, 3: false, 4: false, 5: false, 6: false},
    individualMotorSpeeds: {1: 0, 2: 0, 3: 0, 4: 0, 5: 0, 6: 0},
    groupSpeeds: {levitation: 0, thrust: 0},
    connectionStatus: {backend: false, arduino: false},
    // DUAL TEMPERATURE STATE - ENHANCED
    temperature: {
        sensor1_temp: 25.0,           // Primary sensor (Pin 8)
        sensor2_temp: 25.0,           // Secondary sensor (Pin 13)  
        current: 25.0,                // Max of both for safety
        alarm: false,
        buzzer_active: false,
        max_reached: 25.0,
        max_sensor1: 25.0,            // Individual max temps
        max_sensor2: 25.0,            // Individual max temps
        last_update: null,
        emergency_active: false,
        alarm_count: 0,
        update_frequency: 0.0,
        sensor1_connected: true,      // Connection status
        sensor2_connected: true,      // Connection status
        sensor_failure_count: 0,     // Failure tracking
        temperature_difference: 0.0,  // Difference between sensors
        dual_sensor_mode: true       // Operating in dual mode
    },
    // NEW: REFLECTOR SYSTEM STATE
    reflector: {
        count: 0,                    // Total reflector count
        voltage: 5.0,                // Current sensor voltage
        state: false,                // Current detection state
        average_speed: 0.0,          // Average speed (reflectors/min)
        instant_speed: 0.0,          // Instantaneous speed
        last_update: null,           // Last update timestamp
        system_active: true,         // Reflector system status
        detections: 0,               // Total detection events
        read_frequency: 0.0,         // Read frequency (Hz)
        max_speed_recorded: 0.0,     // Maximum speed recorded
        session_count: 0,            // Session counter
        daily_count: 0,              // Daily counter
        total_runtime: 0.0,          // Runtime in minutes
        detection_rate: 0.0,         // Detections per minute
        connected: true,             // Connection status
        calibration_status: 'not_calibrated', // Calibration status
        performance_indicator: 'optimal'      // Performance indicator
    }
};

// Application State - DUAL SENSOR + REFLECTOR OPTIMIZED
let appState = {
    requestCount: 0,
    errorCount: 0,
    lastRequestTime: 0,
    consecutiveErrors: 0,
    commandLog: [],
    statusUpdateInterval: null,
    temperatureUpdateInterval: null,
    realtimeTemperatureInterval: null,  // Ultra-fast realtime updates
    reflectorUpdateInterval: null,      // NEW: Ultra-fast reflector updates
    reflectorStatsInterval: null,       // NEW: Reflector statistics
    isInitialized: false,
    lastTempAlarmNotified: false,
    lastReflectorCount: 0,              // NEW: Track reflector changes
    temperatureHistory: [],
    reflectorHistory: [],               // NEW: Reflector history
    tempWarningShown: false,
    sensorDifferenceWarningShown: false,
    reflectorAnomalyWarningShown: false, // NEW: Reflector anomaly warning
    performanceStats: {
        temperatureUpdatesCount: 0,
        reflectorUpdatesCount: 0,       // NEW: Reflector update count
        lastTempUpdateTime: 0,
        lastReflectorUpdateTime: 0,     // NEW: Last reflector update
        averageUpdateFrequency: 0,
        averageReflectorFrequency: 0,   // NEW: Average reflector frequency
        sensor1UpdatesCount: 0,
        sensor2UpdatesCount: 0,
        dualSensorUpdatesCount: 0,
        reflectorDetectionCount: 0      // NEW: Detection events count
    }
};

// Constants - DUAL SENSOR + REFLECTOR OPTIMIZED
const CONFIG = {
    REQUEST_THROTTLE: 25,
    MAX_RETRIES: 3,
    STATUS_UPDATE_INTERVAL: 1500,        // General status
    TEMPERATURE_UPDATE_INTERVAL: 800,    // Dual temp updates
    REALTIME_TEMP_INTERVAL: 400,         // Ultra-fast realtime temp
    REFLECTOR_UPDATE_INTERVAL: 300,      // NEW: Ultra-fast reflector updates
    REFLECTOR_STATS_INTERVAL: 2000,      // NEW: Reflector statistics updates
    CONNECTION_TIMEOUT: 4000,
    MAX_LOG_ENTRIES: 30,
    NOTIFICATION_TIMEOUT: 4000,
    TEMP_SAFE_THRESHOLD: 50,
    TEMP_WARNING_THRESHOLD: 45,
    TEMP_ALARM_THRESHOLD: 55,
    TEMP_DIFF_WARNING_THRESHOLD: 5.0,
    REFLECTOR_ANOMALY_THRESHOLD: 10000,  // NEW: Reflector anomaly detection
    REFLECTOR_SPEED_WARNING: 1000,       // NEW: High speed warning (rpm)
    PERFORMANCE_LOG_INTERVAL: 10000
};

// Utility Functions - SAME
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

    static formatNumber(value, decimals = 1) {
        return parseFloat(value).toFixed(decimals);
    }

    static calculateEfficiency(current, maximum) {
        if (maximum === 0) return 100;
        return Math.min(100, (current / maximum) * 100);
    }
}

// NEW: REFLECTOR SYSTEM MANAGER
class ReflectorManager {
    static updateReflectorDisplay(reflectorData) {
        if (!reflectorData) return;
        
        // Extract reflector data
        const count = reflectorData.count || 0;
        const voltage = reflectorData.voltage || 5.0;
        const state = reflectorData.state || false;
        const averageSpeed = reflectorData.average_speed || 0.0;
        const instantSpeed = reflectorData.instant_speed || 0.0;
        const systemActive = reflectorData.system_active !== undefined ? reflectorData.system_active : true;
        const readFrequency = reflectorData.read_frequency || 0.0;
        const detections = reflectorData.detections || 0;
        const sessionCount = reflectorData.session_count || 0;
        const dailyCount = reflectorData.daily_count || 0;
        const totalRuntime = reflectorData.total_runtime || 0.0;
        const detectionRate = reflectorData.detection_rate || 0.0;
        const maxSpeedRecorded = reflectorData.max_speed_recorded || 0.0;
        
        // Update performance stats
        appState.performanceStats.reflectorUpdatesCount++;
        const now = Date.now();
        if (appState.performanceStats.lastReflectorUpdateTime > 0) {
            const timeDiff = (now - appState.performanceStats.lastReflectorUpdateTime) / 1000;
            appState.performanceStats.averageReflectorFrequency = 1 / timeDiff;
        }
        appState.performanceStats.lastReflectorUpdateTime = now;
        
        // Update main reflector displays
        this.updateMainReflectorElements(count, voltage, state, averageSpeed, instantSpeed);
        this.updateReflectorDetails(readFrequency, detections, sessionCount, dailyCount, totalRuntime, detectionRate, maxSpeedRecorded);
        this.updateReflectorStatus(systemActive, voltage, state);
        this.updateReflectorConnectionStatus(systemActive);
        this.updateReflectorStatistics(count, averageSpeed, totalRuntime);
        this.updateReflectorCorrelation(count, averageSpeed);
        this.updateReflectorLastUpdate();
        
        // Store reflector data in system state
        systemState.reflector = {
            count: count,
            voltage: voltage,
            state: state,
            average_speed: averageSpeed,
            instant_speed: instantSpeed,
            last_update: new Date(),
            system_active: systemActive,
            detections: detections,
            read_frequency: readFrequency,
            max_speed_recorded: maxSpeedRecorded,
            session_count: sessionCount,
            daily_count: dailyCount,
            total_runtime: totalRuntime,
            detection_rate: detectionRate,
            connected: systemActive,
            calibration_status: reflectorData.calibration_status || 'not_calibrated',
            performance_indicator: this.calculatePerformanceIndicator(averageSpeed, readFrequency, detections)
        };
        
        // Handle reflector notifications and warnings
        this.handleReflectorNotifications(count, averageSpeed, systemActive, state);
        
        // Update reflector history
        this.updateReflectorHistory(count, averageSpeed, instantSpeed);
    }
    
    static updateMainReflectorElements(count, voltage, state, averageSpeed, instantSpeed) {
        // Update main count display
        const countEl = document.getElementById('reflector-count');
        if (countEl && countEl.textContent !== count.toString()) {
            countEl.textContent = count;
            
            // Add animation for count changes
            if (count > appState.lastReflectorCount) {
                countEl.style.animation = 'pulse 0.3s ease-in-out';
                setTimeout(() => {
                    countEl.style.animation = '';
                }, 300);
                appState.performanceStats.reflectorDetectionCount++;
            }
            appState.lastReflectorCount = count;
        }
        
        // Update voltage display
        const voltageEl = document.getElementById('reflector-voltage');
        if (voltageEl) {
            voltageEl.textContent = `${voltage.toFixed(2)}V`;
        }
        
        // Update detection state
        const detectionStateEl = document.getElementById('reflector-detection-state');
        if (detectionStateEl) {
            detectionStateEl.textContent = state ? 'Algılandı' : 'Temiz';
            detectionStateEl.style.color = state ? '#ff6b35' : '#00ff88';
        }
        
        // Update average speed
        const avgSpeedEl = document.getElementById('reflector-avg-speed');
        if (avgSpeedEl) {
            avgSpeedEl.textContent = averageSpeed.toFixed(1);
        }
        
        // Update instant speed
        const instSpeedEl = document.getElementById('reflector-instant-speed');
        if (instSpeedEl) {
            instSpeedEl.textContent = `${instantSpeed.toFixed(1)} ref/dk`;
        }
        
        // Update reflector system status
        const systemStatusEl = document.getElementById('reflector-system-status');
        if (systemStatusEl) {
            systemStatusEl.textContent = systemState.reflector.system_active ? 'Aktif' : 'Pasif';
            systemStatusEl.style.color = systemState.reflector.system_active ? '#00ff88' : '#ff4757';
        }
    }
    
    static updateReflectorDetails(readFrequency, detections, sessionCount, dailyCount, totalRuntime, detectionRate, maxSpeedRecorded) {
        // Update detailed values
        const updates = {
            'reflector-read-freq': `${readFrequency.toFixed(1)} Hz`,
            'reflector-session-count': sessionCount,
            'reflector-daily-count': dailyCount,
            'reflector-runtime': `${totalRuntime.toFixed(1)} dk`,
            'reflector-max-speed': `${maxSpeedRecorded.toFixed(1)} ref/dk`,
            'reflector-detection-rate': `${detectionRate.toFixed(1)}/dk`,
            'reflector-total-detections': detections
        };
        
        Object.entries(updates).forEach(([id, value]) => {
            const element = document.getElementById(id);
            if (element && element.textContent !== value.toString()) {
                element.textContent = value;
            }
        });
    }
    
    static updateReflectorStatus(systemActive, voltage, state) {
        // Update system status indicator
        const statusIndicatorEl = document.getElementById('reflector-status');
        if (statusIndicatorEl) {
            const shouldShow = systemActive && voltage > 4.0;
            statusIndicatorEl.style.display = shouldShow ? 'block' : 'none';
        }
        
        // Update reflector section styling based on status
        const reflectorSectionEl = document.getElementById('reflector-section');
        if (reflectorSectionEl) {
            reflectorSectionEl.className = 'reflector-section';
            
            if (!systemActive) {
                reflectorSectionEl.classList.add('inactive');
            } else if (voltage < 2.0) {
                reflectorSectionEl.classList.add('error');
            } else if (state) {
                reflectorSectionEl.classList.add('detecting');
            }
        }
        
        // Update performance indicator
        const performanceEl = document.getElementById('performance-indicator');
        if (performanceEl) {
            performanceEl.textContent = systemState.reflector.performance_indicator;
            const color = this.getPerformanceColor(systemState.reflector.performance_indicator);
            performanceEl.style.color = color;
        }
    }
    
    static updateReflectorConnectionStatus(systemActive) {
        // Update connection status dot
        const connectionDotEl = document.getElementById('reflector-dot');
        const connectionTextEl = document.getElementById('reflector-connection-text');
        const connectionMiniEl = document.getElementById('reflector-connection-mini');
        
        if (connectionDotEl) {
            connectionDotEl.className = systemActive ? 'connection-dot connected' : 'connection-dot';
        }
        if (connectionTextEl) {
            connectionTextEl.textContent = systemActive ? 'Bağlı' : 'Bağlantısız';
        }
        if (connectionMiniEl) {
            connectionMiniEl.textContent = '●';
            connectionMiniEl.style.color = systemActive ? '#00ff88' : '#ff4757';
        }
        
        // Update system connection status
        systemState.reflector.connected = systemActive;
    }
    
    static updateReflectorStatistics(count, averageSpeed, totalRuntime) {
        // Update statistics displays
        const statisticsUpdates = {
            'stats-total-count': count,
            'stats-avg-speed': `${averageSpeed.toFixed(1)} ref/dk`,
            'stats-runtime': Utils.formatUptime(totalRuntime * 60),
            'stats-efficiency': `${Utils.calculateEfficiency(count, count + 10).toFixed(0)}%`
        };
        
        Object.entries(statisticsUpdates).forEach(([id, value]) => {
            const element = document.getElementById(id);
            if (element && element.textContent !== value.toString()) {
                element.textContent = value;
            }
        });
        
        // Update monitor section
        const monitorUpdates = {
            'monitor-reflector-count': count,
            'monitor-reflector-voltage': `${systemState.reflector.voltage.toFixed(2)}V`,
            'monitor-avg-speed': `${averageSpeed.toFixed(1)}/dk`,
            'monitor-instant-speed': `${systemState.reflector.instant_speed.toFixed(1)}/dk`,
            'monitor-read-freq': `${systemState.reflector.read_frequency.toFixed(1)} Hz`,
            'monitor-system-status': systemState.reflector.system_active ? 'Aktif' : 'Pasif',
            'monitor-session-count': systemState.reflector.session_count,
            'monitor-runtime': `${totalRuntime.toFixed(1)}dk`
        };
        
        Object.entries(monitorUpdates).forEach(([id, value]) => {
            const element = document.getElementById(id);
            if (element && element.textContent !== value.toString()) {
                element.textContent = value;
            }
        });
    }
    
    static updateReflectorCorrelation(count, averageSpeed) {
        // Update temperature vs reflector correlation
        const tempSpeedRatio = systemState.temperature.current > 0 ? 
            (averageSpeed / systemState.temperature.current).toFixed(1) : '0.0';
        
        const systemLoad = this.calculateSystemLoad(systemState.temperature.current, averageSpeed);
        
        const correlationUpdates = {
            'temp-speed-ratio': tempSpeedRatio,
            'system-load-indicator': systemLoad,
            'modal-temp-speed-ratio': tempSpeedRatio,
            'modal-system-load': systemLoad,
            'modal-correlation-count': count,
            'modal-correlation-speed': `${averageSpeed.toFixed(1)} ref/dk`
        };
        
        Object.entries(correlationUpdates).forEach(([id, value]) => {
            const element = document.getElementById(id);
            if (element && element.textContent !== value.toString()) {
                element.textContent = value;
            }
        });
    }
    
    static updateReflectorLastUpdate() {
        const lastUpdateEl = document.getElementById('reflector-last-update');
        if (lastUpdateEl) {
            lastUpdateEl.textContent = Utils.formatTime(new Date());
        }
    }
    
    static updateReflectorHistory(count, averageSpeed, instantSpeed) {
        // Add to reflector history (limited frequency)
        if (appState.reflectorHistory.length === 0 || 
            (Date.now() - new Date(appState.reflectorHistory[appState.reflectorHistory.length - 1].timestamp).getTime()) >= 2000) {
            
            appState.reflectorHistory.push({
                timestamp: new Date().toISOString(),
                count: count,
                average_speed: averageSpeed,
                instant_speed: instantSpeed,
                voltage: systemState.reflector.voltage
            });
            
            // Keep history limited
            if (appState.reflectorHistory.length > 200) {
                appState.reflectorHistory = appState.reflectorHistory.slice(-200);
            }
        }
    }
    
    static handleReflectorNotifications(count, averageSpeed, systemActive, state) {
        // System inactive notification
        if (!systemActive && systemState.reflector.connected) {
            NotificationManager.show('Reflektor sistemi bağlantısı kesildi!', 'warning');
            systemState.reflector.connected = false;
        } else if (systemActive && !systemState.reflector.connected) {
            NotificationManager.show('Reflektor sistemi yeniden bağlandı!', 'success');
            systemState.reflector.connected = true;
        }
        
        // High speed warning
        if (averageSpeed > CONFIG.REFLECTOR_SPEED_WARNING && !appState.reflectorAnomalyWarningShown) {
            NotificationManager.show(
                `Yüksek reflektor hızı tespit edildi: ${averageSpeed.toFixed(1)} ref/dk`, 
                'warning', 
                6000
            );
            appState.reflectorAnomalyWarningShown = true;
        } else if (averageSpeed <= CONFIG.REFLECTOR_SPEED_WARNING) {
            appState.reflectorAnomalyWarningShown = false;
        }
        
        // Count milestone notifications
        const milestones = [100, 500, 1000, 5000, 10000];
        milestones.forEach(milestone => {
            if (count === milestone && appState.lastReflectorCount < milestone) {
                NotificationManager.show(
                    `🎉 Reflektor sayacı ${milestone} sayıma ulaştı! Ortalama hız: ${averageSpeed.toFixed(1)} ref/dk`, 
                    'success', 
                    5000
                );
            }
        });
    }
    
    static calculatePerformanceIndicator(averageSpeed, readFrequency, detections) {
        if (readFrequency < 10 || detections === 0) return 'düşük';
        if (readFrequency > 100 && averageSpeed > 10) return 'optimal';
        if (readFrequency > 50 && averageSpeed > 5) return 'iyi';
        return 'normal';
    }
    
    static getPerformanceColor(indicator) {
        const colors = {
            'optimal': '#00ff88',
            'iyi': '#00d4ff',
            'normal': '#ffc107',
            'düşük': '#ff4757'
        };
        return colors[indicator] || '#aaa';
    }
    
    static calculateSystemLoad(temperature, reflectorSpeed) {
        if (temperature > 45 && reflectorSpeed > 50) return 'Yüksek';
        if (temperature > 35 || reflectorSpeed > 30) return 'Orta';
        return 'Normal';
    }
    
    // NEW: Reflector control functions
    static async resetReflectorCounter() {
        try {
            const response = await RequestHandler.makeRequest(`${BACKEND_URL}/api/reflector/reset`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' }
            });
            
            const data = await response.json();
            
            if (data.status === 'success') {
                systemState.reflector.count = 0;
                systemState.reflector.session_count = 0;
                appState.lastReflectorCount = 0;
                appState.reflectorHistory = [];
                
                NotificationManager.show('Reflektor sayacı başarıyla sıfırlandı', 'success');
                CommandLogger.log('Reflektor sayacı sıfırlandı', true);
                
                // Update displays immediately
                this.updateMainReflectorElements(0, systemState.reflector.voltage, 
                    systemState.reflector.state, 0, 0);
                
            } else {
                throw new Error(data.message || 'Sayaç sıfırlanamadı');
            }
        } catch (error) {
            CommandLogger.log('Reflektor sayaç sıfırlama', false, error.message);
            NotificationManager.show(`Reflektor sayacı sıfırlanamadı: ${error.message}`, 'error');
        }
    }
    
    static async calibrateReflectorSensor() {
        try {
            NotificationManager.show('Reflektor sensörü kalibre ediliyor...', 'info');
            
            const response = await RequestHandler.makeRequest(`${BACKEND_URL}/api/reflector/calibrate`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' }
            });
            
            const data = await response.json();
            
            if (data.status === 'success') {
                systemState.reflector.calibration_status = 'calibrated';
                
                NotificationManager.show('Reflektor sensörü başarıyla kalibre edildi', 'success');
                CommandLogger.log('Reflektor sensörü kalibre edildi', true);
                
                // Log calibration data if available
                if (data.calibration_data) {
                    const calData = data.calibration_data;
                    CommandLogger.log('Kalibrasyon verileri', true, 
                        `Min: ${calData.min_voltage}V, Max: ${calData.max_voltage}V, Avg: ${calData.avg_voltage}V`);
                }
                
            } else {
                throw new Error(data.message || 'Kalibrasyon başarısız');
            }
        } catch (error) {
            CommandLogger.log('Reflektor kalibrasyon', false, error.message);
            NotificationManager.show(`Reflektor kalibrasyonu başarısız: ${error.message}`, 'error');
        }
    }
    
    // NEW: Ultra-fast reflector updates
    static async updateReflectorOnly() {
        try {
            const response = await RequestHandler.makeRequest(`${BACKEND_URL}/api/reflector/realtime`, {
                method: 'GET'
            }, 2000, 1);
            
            const data = await response.json();
            
            if (data.count !== undefined) {
                // Ultra-fast reflector data structure
                const quickReflectorData = {
                    count: data.count,
                    voltage: data.voltage,
                    state: data.state,
                    average_speed: data.average_speed,
                    instant_speed: data.instant_speed,
                    read_frequency: data.read_frequency,
                    system_active: data.system_active,
                    // Keep existing values for performance
                    detections: systemState.reflector.detections,
                    session_count: data.count, // Session count is current count
                    daily_count: data.count,   // Daily count is current count
                    total_runtime: systemState.reflector.total_runtime,
                    detection_rate: systemState.reflector.detection_rate,
                    max_speed_recorded: Math.max(systemState.reflector.max_speed_recorded, data.instant_speed)
                };
                
                this.updateReflectorDisplay(quickReflectorData);
                
                // Update connection status
                ConnectionManager.updateConnectionStatus('backend', true);
                appState.consecutiveErrors = 0;
            }
            
        } catch (error) {
            console.debug('Quick reflector update failed:', error.message);
            appState.consecutiveErrors++;
            
            if (appState.consecutiveErrors >= 3) {
                ConnectionManager.updateConnectionStatus('backend', false);
                systemState.reflector.system_active = false;
            }
        }
    }
    
    // NEW: Get reflector statistics
    static async getReflectorStatistics() {
        try {
            const response = await RequestHandler.makeRequest(`${BACKEND_URL}/api/reflector/statistics`, {
                method: 'GET'
            });
            
            const data = await response.json();
            
            if (data.session && data.performance) {
                // Update comprehensive statistics
                systemState.reflector.total_runtime = data.session.duration_hours * 60;
                systemState.reflector.detection_rate = data.session.average_rate;
                systemState.reflector.max_speed_recorded = data.performance.max_speed_recorded;
                
                // Update statistics displays
                this.updateReflectorStatistics(
                    data.session.count,
                    data.performance.recent_average_speed || systemState.reflector.average_speed,
                    systemState.reflector.total_runtime
                );
                
                // Update efficiency indicator
                const efficiencyEl = document.getElementById('stats-efficiency');
                if (efficiencyEl && data.performance.detection_efficiency !== undefined) {
                    efficiencyEl.textContent = `${data.performance.detection_efficiency.toFixed(0)}%`;
                }
            }
            
        } catch (error) {
            console.debug('Reflector statistics update failed:', error.message);
        }
    }
}

// DUAL Temperature Manager - ENHANCED WITH REFLECTOR CORRELATION
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
        appState.performanceStats.dualSensorUpdatesCount++;
        if (sensor1Connected) appState.performanceStats.sensor1UpdatesCount++;
        if (sensor2Connected) appState.performanceStats.sensor2UpdatesCount++;
        
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
        
        // Handle notifications with reflector correlation
        this.handleDualTemperatureNotifications(tempAlarm, emergencyActive, currentTemp, tempDifference, sensor1Connected, sensor2Connected);
    }
    
    static updateDualSensorElements(sensor1Temp, sensor2Temp, safetyTemp, sensor1Connected, sensor2Connected) {
        // Update individual sensor temperatures
        const sensor1El = document.getElementById('sensor1-temp');
        const sensor2El = document.getElementById('sensor2-temp');
        const safetyTempEl = document.getElementById('safety-temp');
        
        if (sensor1El) {
            sensor1El.textContent = `${sensor1Temp.toFixed(1)}°C`;
            sensor1El.className = 'temp-current primary';
            
            // Color coding based on temperature and connection
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
        
        // Update safety temperature (maximum)
        if (safetyTempEl) {
            safetyTempEl.textContent = `${safetyTemp.toFixed(1)}°C`;
            safetyTempEl.className = 'temp-current safety';
            
            if (safetyTemp >= CONFIG.TEMP_ALARM_THRESHOLD) {
                safetyTempEl.classList.add('danger');
            } else if (safetyTemp >= CONFIG.TEMP_WARNING_THRESHOLD) {
                safetyTempEl.classList.add('warning');
            }
        }
        
        // Update individual sensor max temperatures
        const sensor1MaxEl = document.getElementById('sensor1-max');
        const sensor2MaxEl = document.getElementById('sensor2-max');
        
        if (sensor1MaxEl) {
            sensor1MaxEl.textContent = `${systemState.temperature.max_sensor1.toFixed(1)}°C`;
        }
        if (sensor2MaxEl) {
            sensor2MaxEl.textContent = `${systemState.temperature.max_sensor2.toFixed(1)}°C`;
        }
        
        // Temperature section styling
        const tempSectionEl = document.getElementById('temperature-section');
        if (tempSectionEl) {
            tempSectionEl.className = 'temperature-section';
            if (systemState.temperature.alarm || systemState.temperature.emergency_active) {
                tempSectionEl.classList.add('danger');
            } else if (safetyTemp >= CONFIG.TEMP_WARNING_THRESHOLD) {
                tempSectionEl.classList.add('warning');
            }
        }
    }
    
    static updateTemperatureDetails(maxTemp, maxSensor1, maxSensor2, alarmCount, buzzerActive, updateFrequency, tempDifference) {
        // Batch DOM updates for better performance
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
        
        // Update buzzer button
        const buzzerBtn = document.getElementById('buzzer-off-btn');
        if (buzzerBtn) {
            buzzerBtn.disabled = !buzzerActive;
        }
        
        // Show/hide temperature difference warning
        const tempDiffWarning = document.getElementById('temp-difference-warning');
        if (tempDiffWarning) {
            const shouldShow = tempDifference > CONFIG.TEMP_DIFF_WARNING_THRESHOLD && 
                              systemState.temperature.sensor1_connected && 
                              systemState.temperature.sensor2_connected;
            
            const currentDisplay = tempDiffWarning.style.display;
            const targetDisplay = shouldShow ? 'block' : 'none';
            
            if (currentDisplay !== targetDisplay) {
                tempDiffWarning.style.display = targetDisplay;
            }
        }
    }
    
    static updateSensorConnectionStatus(sensor1Connected, sensor2Connected) {
        // Update sensor 1 connection status
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
        
        // Update sensor 2 connection status
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
            'detailed-redundancy-status',
            'modal-redundancy'
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
        const detailedAlarmStatusEl = document.getElementById('detailed-temp-alarm-status');
        
        let statusText, statusColor;
        
        if (tempAlarm || emergencyActive) {
            statusText = 'ALARM!';
            statusColor = '#ff4757';
        } else if (currentTemp >= CONFIG.TEMP_WARNING_THRESHOLD) {
            statusText = 'Uyarı';
            statusColor = '#ffc107';
        } else {
            statusText = 'Güvenli';
            statusColor = '#00ff88';
        }
        
        if (tempStatusEl && tempStatusEl.textContent !== statusText) {
            tempStatusEl.textContent = statusText;
        }
        
        if (detailedAlarmStatusEl) {
            const alarmStatus = tempAlarm ? 'ALARM' : 'Normal';
            if (detailedAlarmStatusEl.textContent !== alarmStatus) {
                detailedAlarmStatusEl.textContent = alarmStatus;
                detailedAlarmStatusEl.style.color = tempAlarm ? '#ff4757' : '#00ff88';
            }
        }
        
        // Emergency indicators
        const tempEmergencyEl = document.getElementById('temp-emergency');
        if (tempEmergencyEl) {
            const shouldShow = tempAlarm || emergencyActive;
            const currentDisplay = tempEmergencyEl.style.display;
            const targetDisplay = shouldShow ? 'block' : 'none';
            
            if (currentDisplay !== targetDisplay) {
                tempEmergencyEl.style.display = targetDisplay;
            }
        }
        
        // Enhanced dual temperature emergency warning with reflector data
        const emergencyWarning = document.getElementById('temperature-emergency-warning');
        if (emergencyWarning) {
            const shouldShow = tempAlarm || emergencyActive;
            const currentDisplay = emergencyWarning.style.display;
            const targetDisplay = shouldShow ? 'block' : 'none';
            
            if (currentDisplay !== targetDisplay) {
                emergencyWarning.style.display = targetDisplay;
                
                if (shouldShow) {
                    // Update dual sensor emergency values
                    const temp1ValueEl = document.getElementById('warning-temp1-value');
                    const temp2ValueEl = document.getElementById('warning-temp2-value');
                    const tempMaxValueEl = document.getElementById('warning-temp-max-value');
                    const reflectorCountEl = document.getElementById('warning-reflector-count');
                    
                    if (temp1ValueEl) temp1ValueEl.textContent = `${systemState.temperature.sensor1_temp.toFixed(1)}°C`;
                    if (temp2ValueEl) temp2ValueEl.textContent = `${systemState.temperature.sensor2_temp.toFixed(1)}°C`;
                    if (tempMaxValueEl) tempMaxValueEl.textContent = `${currentTemp.toFixed(1)}°C`;
                    if (reflectorCountEl) reflectorCountEl.textContent = systemState.reflector.count;
                }
            }
        }
    }
    
    static updateLastUpdateTime() {
        const lastUpdateEl = document.getElementById('temp-last-update');
        if (lastUpdateEl) {
            lastUpdateEl.textContent = Utils.formatTime(new Date());
        }
    }
    
    static handleDualTemperatureNotifications(tempAlarm, emergencyActive, currentTemp, tempDifference, sensor1Connected, sensor2Connected) {
        // Temperature alarm notifications with reflector data
        if ((tempAlarm || emergencyActive) && !appState.lastTempAlarmNotified) {
            NotificationManager.show(
                `ÇIFT SENSÖR SICAKLIK ALARMI! Max: ${currentTemp.toFixed(1)}°C - Sistem durduruldu! Reflektor sayımı: ${systemState.reflector.count}`, 
                'error', 
                8000
            );
            appState.lastTempAlarmNotified = true;
        } else if (!(tempAlarm || emergencyActive) && appState.lastTempAlarmNotified) {
            NotificationManager.show(
                `Sıcaklık güvenli seviyeye döndü: S1:${systemState.temperature.sensor1_temp.toFixed(1)}°C S2:${systemState.temperature.sensor2_temp.toFixed(1)}°C, Reflektor: ${systemState.reflector.count}`, 
                'success'
            );
            appState.lastTempAlarmNotified = false;
        }
        
        // Warning level notifications with reflector correlation
        if (currentTemp >= CONFIG.TEMP_WARNING_THRESHOLD && currentTemp < CONFIG.TEMP_ALARM_THRESHOLD) {
            if (!appState.tempWarningShown) {
                NotificationManager.show(
                    `Sıcaklık uyarı seviyesinde: Max ${currentTemp.toFixed(1)}°C (S1:${systemState.temperature.sensor1_temp.toFixed(1)}°C S2:${systemState.temperature.sensor2_temp.toFixed(1)}°C) - Reflektor: ${systemState.reflector.count}`, 
                    'warning'
                );
                appState.tempWarningShown = true;
            }
        } else {
            appState.tempWarningShown = false;
        }
        
        // Sensor difference warnings
        if (tempDifference > CONFIG.TEMP_DIFF_WARNING_THRESHOLD && sensor1Connected && sensor2Connected) {
            if (!appState.sensorDifferenceWarningShown) {
                NotificationManager.show(
                    `Büyük sensör farkı! S1:${systemState.temperature.sensor1_temp.toFixed(1)}°C S2:${systemState.temperature.sensor2_temp.toFixed(1)}°C (Fark: ${tempDifference.toFixed(1)}°C)`, 
                    'warning',
                    6000
                );
                appState.sensorDifferenceWarningShown = true;
            }
        } else {
            appState.sensorDifferenceWarningShown = false;
        }
        
        // Sensor disconnection warnings
        if (!sensor1Connected && systemState.temperature.sensor1_connected) {
            NotificationManager.show('Sensör 1 (Pin 8) bağlantısı kesildi!', 'warning');
        }
        if (!sensor2Connected && systemState.temperature.sensor2_connected) {
            NotificationManager.show('Sensör 2 (Pin 13) bağlantısı kesildi!', 'warning');
        }
        
        // Both sensors failed warning
        if (!sensor1Connected && !sensor2Connected && (systemState.temperature.sensor1_connected || systemState.temperature.sensor2_connected)) {
            NotificationManager.show('KRITIK: Her iki sıcaklık sensörü de bağlantısız!', 'error', 10000);
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
                
                // Log dual temperatures + reflector when buzzer turned off
                if (data.dual_temps) {
                    CommandLogger.log('Buzzer kapatıldığında veriler', true, 
                        `S1:${data.dual_temps.sensor1}°C S2:${data.dual_temps.sensor2}°C Max:${data.dual_temps.max}°C Reflektor:${data.reflector_count || systemState.reflector.count}`);
                }
            } else {
                throw new Error(data.message || 'Buzzer kapatılamadı');
            }
        } catch (error) {
            CommandLogger.log('Buzzer kapatma', false, error.message);
            NotificationManager.show(`Buzzer kapatılamadı: ${error.message}`, 'error');
        }
    }
    
    // Ultra-fast dual temperature updates (same as before)
    static async updateDualTemperatureOnly() {
        try {
            const response = await RequestHandler.makeRequest(`${BACKEND_URL}/api/temperature/realtime`, {
                method: 'GET'
            }, 2000, 1);
            
            const data = await response.json();
            
            if (data.dual_sensor_mode && data.sensor1_temp !== undefined && data.sensor2_temp !== undefined) {
                // Ultra-fast dual temperature data structure with reflector
                const quickDualTempData = {
                    sensor1_temp: data.sensor1_temp,
                    sensor2_temp: data.sensor2_temp,
                    current: data.temperature,
                    alarm: data.alarm,
                    buzzer_active: data.buzzer,
                    update_frequency: data.frequency_hz,
                    sensor1_connected: data.sensor1_connected,
                    sensor2_connected: data.sensor2_connected,
                    // Keep existing values
                    max_reached: systemState.temperature.max_reached,
                    max_sensor1: Math.max(systemState.temperature.max_sensor1, data.sensor1_temp),
                    max_sensor2: Math.max(systemState.temperature.max_sensor2, data.sensor2_temp),
                    emergency_active: data.alarm,
                    alarm_count: systemState.temperature.alarm_count,
                    sensor_failure_count: systemState.temperature.sensor_failure_count
                };
                
                this.updateDualTemperatureDisplay(quickDualTempData);
                
                // Also update reflector data if included
                if (data.reflector_count !== undefined) {
                    const quickReflectorData = {
                        count: data.reflector_count,
                        voltage: data.reflector_voltage || systemState.reflector.voltage,
                        average_speed: data.reflector_speed || systemState.reflector.average_speed,
                        system_active: data.reflector_system_active !== undefined ? data.reflector_system_active : systemState.reflector.system_active,
                        // Keep other existing values
                        state: systemState.reflector.state,
                        instant_speed: systemState.reflector.instant_speed,
                        read_frequency: systemState.reflector.read_frequency,
                        detections: systemState.reflector.detections,
                        session_count: systemState.reflector.session_count,
                        daily_count: systemState.reflector.daily_count,
                        total_runtime: systemState.reflector.total_runtime,
                        detection_rate: systemState.reflector.detection_rate,
                        max_speed_recorded: systemState.reflector.max_speed_recorded
                    };
                    
                    ReflectorManager.updateReflectorDisplay(quickReflectorData);
                }
                
                // Update connection status
                ConnectionManager.updateConnectionStatus('backend', true);
                appState.consecutiveErrors = 0;
            }
            
        } catch (error) {
            console.debug('Quick dual temperature + reflector update failed:', error.message);
            appState.consecutiveErrors++;
            
            if (appState.consecutiveErrors >= 3) {
                ConnectionManager.updateConnectionStatus('backend', false);
            }
        }
    }
}

// HTTP Request Handler - SAME (optimized)
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
                
                systemState.armed = data.armed;
                systemState.brakeActive = data.brake_active;
                systemState.relayBrakeActive = data.relay_brake_active;
                systemState.connected = data.connected;
                
                // Dual temperature data handling
                if (data.temperature) {
                    DualTemperatureManager.updateDualTemperatureDisplay(data.temperature);
                }
                
                // NEW: Reflector data handling
                if (data.reflector) {
                    ReflectorManager.updateReflectorDisplay(data.reflector);
                }
                
                // Motor states - SAME
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
            if (appState.consecutiveErrors >= 2) {
                ConnectionManager.updateConnectionStatus('backend', false);
                ConnectionManager.updateConnectionStatus('arduino', false);
                
                // Also mark reflector as inactive
                if (systemState.reflector) {
                    systemState.reflector.system_active = false;
                    systemState.reflector.connected = false;
                    ReflectorManager.updateReflectorConnectionStatus(false);
                }
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
        if (appState.reflectorStatsInterval) {
            clearInterval(appState.reflectorStatsInterval);
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
        
        // NEW: Start ultra-fast reflector polling
        appState.reflectorUpdateInterval = setInterval(() => {
            ReflectorManager.updateReflectorOnly();
        }, CONFIG.REFLECTOR_UPDATE_INTERVAL);
        
        // NEW: Start reflector statistics polling
        appState.reflectorStatsInterval = setInterval(() => {
            ReflectorManager.getReflectorStatistics();
        }, CONFIG.REFLECTOR_STATS_INTERVAL);
        
        // Initial calls
        setTimeout(() => this.pollStatus(), 500);
        setTimeout(() => DualTemperatureManager.updateDualTemperatureOnly(), 100);
        setTimeout(() => ReflectorManager.updateReflectorOnly(), 200); // NEW
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
        if (appState.reflectorStatsInterval) {
            clearInterval(appState.reflectorStatsInterval);
            appState.reflectorStatsInterval = null;
        }
    }
}

// Command Logger - ENHANCED WITH REFLECTOR DATA
class CommandLogger {
    static log(command, success = true, details = '') {
        const timestamp = Utils.formatTime(new Date());
        const status = success ? '✅' : '❌';
        
        // Enhanced logging with reflector data for important commands
        let enhancedDetails = details;
        if (success && (command.includes('Motor') || command.includes('Grup') || command.includes('ARM') || command.includes('EMERGENCY'))) {
            enhancedDetails = `${details} [Reflektor: ${systemState.reflector.count}]`;
        }
        
        const logEntry = {
            timestamp,
            status,
            command,
            details: enhancedDetails,
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

// Notification System - SAME
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

// Connection Manager - ENHANCED for dual temperature + reflector
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
            NotificationManager.show('Dual sensör + reflektor bağlantı test ediliyor...', 'info');
            
            const response = await RequestHandler.makeRequest(`${BACKEND_URL}/api/ping`);
            const data = await response.json();
            
            if (data.status === 'ok') {
                CommandLogger.log('Dual sensör + reflektor bağlantı testi başarılı', true);
                
                let tempInfo = 'N/A';
                let reflectorInfo = 'N/A';
                
                if (data.dual_temperatures) {
                    tempInfo = `S1:${data.dual_temperatures.sensor1_temp}°C S2:${data.dual_temperatures.sensor2_temp}°C Max:${data.dual_temperatures.max_temp}°C`;
                }
                
                if (data.reflector_system) {
                    reflectorInfo = `Sayım:${data.reflector_system.count} Hız:${data.reflector_system.average_speed.toFixed(1)}rpm`;
                }
                
                NotificationManager.show(`Dual sensör + reflektor bağlantı testi başarılı! Sıcaklık: ${tempInfo}, Reflektor: ${reflectorInfo}`, 'success');
                this.updateConnectionStatus('backend', true);
                this.updateConnectionStatus('arduino', data.arduino_connected);
            } else {
                throw new Error(data.message || 'Test failed');
            }
            
        } catch (error) {
            CommandLogger.log('Dual sensör + reflektor bağlantı testi', false, error.message);
            NotificationManager.show(`Bağlantı testi başarısız: ${error.message}`, 'error');
            this.updateConnectionStatus('backend', false);
            this.updateConnectionStatus('arduino', false);
        }
    }

    static async reconnectArduino() {
        try {
            NotificationManager.show('Arduino dual sensör + reflektor sistemi yeniden bağlanıyor...', 'info');
            
            const response = await RequestHandler.makeRequest(`${BACKEND_URL}/api/reconnect`, {
                method: 'POST'
            });
            
            const data = await response.json();
            
            if (data.status === 'success') {
                CommandLogger.log('Arduino dual sensör + reflektor sistemi yeniden bağlandı', true);
                NotificationManager.show('Arduino dual sensör + reflektor sistemi yeniden bağlandı!', 'success');
                setTimeout(() => StatusManager.pollStatus(), 1000);
            } else {
                throw new Error(data.message || 'Reconnection failed');
            }
            
        } catch (error) {
            CommandLogger.log('Arduino dual sensör + reflektor yeniden bağlanma', false, error.message);
            NotificationManager.show(`Arduino yeniden bağlanamadı: ${error.message}`, 'error');
        }
    }
}

// Motor Control - ENHANCED with dual temperature + reflector checks
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
                        `${speed}% - S1:${systemState.temperature.sensor1_temp.toFixed(1)}°C S2:${systemState.temperature.sensor2_temp.toFixed(1)}°C - Reflektor:${systemState.reflector.count}`);
                    NotificationManager.show(`Motor ${motorNum} başlatıldı!`, 'success');
                    
                    // Quick dual temperature + reflector check after motor start
                    setTimeout(() => DualTemperatureManager.updateDualTemperatureOnly(), 200);
                    setTimeout(() => ReflectorManager.updateReflectorOnly(), 200);
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
                    CommandLogger.log(`Motor ${motorNum} durduruldu`, true, `Reflektor:${systemState.reflector.count}`);
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
            NotificationManager.show(`Sıcaklık alarmı nedeniyle motor kontrol edilemez! S1:${systemState.temperature.sensor1_temp.toFixed(1)}°C S2:${systemState.temperature.sensor2_temp.toFixed(1)}°C`, 'warning');
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
                    CommandLogger.log(`Motor ${motorNum} hızı`, true, `${speed}% - Reflektor:${systemState.reflector.count}`);
                }

            } catch (error) {
                CommandLogger.log(`Motor ${motorNum} hız`, false, error.message);
                NotificationManager.show(`Motor ${motorNum} hız ayarlanamadı`, 'error');
                console.error('Motor speed error:', error);
            }
        });
    }
}

// Group Controller - ENHANCED with dual temperature + reflector logging
class GroupController {
    static async startGroup(groupType) {
        if (systemState.temperature.alarm || systemState.temperature.emergency_active) {
            NotificationManager.show(`Sıcaklık alarmı nedeniyle motor grubu başlatılamaz! S1:${systemState.temperature.sensor1_temp.toFixed(1)}°C S2:${systemState.temperature.sensor2_temp.toFixed(1)}°C`, 'warning');
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
                        `${speed}% - M${motorRange.join(',')} - S1:${systemState.temperature.sensor1_temp.toFixed(1)}°C S2:${systemState.temperature.sensor2_temp.toFixed(1)}°C - Reflektor:${systemState.reflector.count}`);
                    NotificationManager.show(`${groupName} grubu başlatıldı! (M${motorRange.join(',')})`, 'success');
                    
                    // Quick dual temperature + reflector check after group start
                    setTimeout(() => DualTemperatureManager.updateDualTemperatureOnly(), 200);
                    setTimeout(() => ReflectorManager.updateReflectorOnly(), 200);
                }

            } catch (error) {
                CommandLogger.log(`${groupType} başlatma`, false, error.message);
                NotificationManager.show(`${groupType} grubu başlatılamadı: ${error.message}`, 'error');
                console.error('Group start error:', error);
            }
        });
    }

    // Keep other GroupController methods same but with dual temp + reflector enhancements
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
                    CommandLogger.log(`${groupName} grubu durduruldu`, true, `M${motorRange.join(',')} - Reflektor:${systemState.reflector.count}`);
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
                    
                    CommandLogger.log(`${groupType} hızı`, true, `${speed}% - Reflektor:${systemState.reflector.count}`);
                }

            } catch (error) {
                CommandLogger.log(`${groupType} hız`, false, error.message);
                console.error('Group speed error:', error);
            }
        });
    }
}

// System Controller - ENHANCED with dual temperature + reflector checks
class SystemController {
    static async toggleArm() {
        if (!systemState.armed && (systemState.temperature.alarm || systemState.temperature.emergency_active)) {
            NotificationManager.show(`Sıcaklık alarmı nedeniyle sistem hazırlanamaz! S1:${systemState.temperature.sensor1_temp.toFixed(1)}°C S2:${systemState.temperature.sensor2_temp.toFixed(1)}°C`, 'warning');
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
                        CommandLogger.log('Röle otomatik aktif yapıldı', true, `Reflektor:${systemState.reflector.count}`);
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
                        `S1:${systemState.temperature.sensor1_temp.toFixed(1)}°C S2:${systemState.temperature.sensor2_temp.toFixed(1)}°C - Reflektor:${systemState.reflector.count}`);
                    NotificationManager.show(`Sistem ${statusText}!`, 'success');
                    
                    // Quick dual temperature + reflector check after system change
                    setTimeout(() => DualTemperatureManager.updateDualTemperatureOnly(), 200);
                    setTimeout(() => ReflectorManager.updateReflectorOnly(), 200);
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
            NotificationManager.show(`Sıcaklık alarmı nedeniyle röle aktif yapılamaz! S1:${systemState.temperature.sensor1_temp.toFixed(1)}°C S2:${systemState.temperature.sensor2_temp.toFixed(1)}°C`, 'warning');
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
                    CommandLogger.log(`Röle ${status}`, true, 
                        `S1:${systemState.temperature.sensor1_temp.toFixed(1)}°C S2:${systemState.temperature.sensor2_temp.toFixed(1)}°C - Reflektor:${systemState.reflector.count}`);
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
                    
                    CommandLogger.log(`Software brake ${action === 'on' ? 'aktif' : 'pasif'}`, true, `Reflektor:${systemState.reflector.count}`);
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

            CommandLogger.log('ACİL DURDURMA AKTİF', true, 
                `Tüm sistemler durduruldu - S1:${systemState.temperature.sensor1_temp.toFixed(1)}°C S2:${systemState.temperature.sensor2_temp.toFixed(1)}°C - Final Reflektor:${systemState.reflector.count}`);
            NotificationManager.show(`ACİL DURDURMA! Tüm sistemler durduruldu! Final reflektor sayımı: ${systemState.reflector.count}`, 'error', 6000);

        } catch (error) {
            CommandLogger.log('Acil durdurma', false, error.message);
            NotificationManager.show('Acil durdurma sinyali gönderilemedi!', 'warning');
            console.error('Emergency stop error:', error);
        }
    }
}