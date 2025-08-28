/*
 * SpectraLoop Frontend JavaScript FAULT TOLERANT DUAL TEMPERATURE + REFLECTOR v3.7
 * FAULT TOLERANT: Sistem 0, 1 veya 2 sıcaklık sensörü ile çalışabilir
 * Dual DS18B20 sensor monitoring + Omron reflector counting system + Enhanced fault tolerance
 * Individual sensor + reflector tracking + combined safety logic + ultra-fast updates
 * FAULT TOLERANCE: Sensör hatalarında bile Arduino-Backend-Frontend bağlantısı devam eder
 */

// Configuration - FAULT TOLERANT DUAL SENSOR + REFLECTOR OPTIMIZED
const BACKEND_URL = 'http://192.168.241.82:5001';

// System State Management - FAULT TOLERANT DUAL TEMPERATURE + REFLECTOR ENHANCED
let systemState = {
    armed: false,
    brakeActive: false,
    relayBrakeActive: false,
    connected: false,
    motorStates: {1: false, 2: false, 3: false, 4: false, 5: false, 6: false},
    individualMotorSpeeds: {1: 0, 2: 0, 3: 0, 4: 0, 5: 0, 6: 0},
    groupSpeeds: {levitation: 0, thrust: 0},
    connectionStatus: {backend: false, arduino: false},
    // FAULT TOLERANT TEMPERATURE STATE - ENHANCED
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
        sensor1_connected: false,      // Connection status
        sensor2_connected: false,      // Connection status
        sensor_failure_count: 0,      // Failure tracking
        temperature_difference: 0.0,  // Difference between sensors
        dual_sensor_mode: true,       // Operating in dual mode
        // NEW: FAULT TOLERANT fields
        temp_monitoring_required: false,     // Is temperature monitoring required?
        allow_operation_without_temp: true,  // Allow operation without temp sensors
        fault_tolerant_mode: true,           // Operating in fault tolerant mode
        last_valid_temp1: 25.0,             // Last valid sensor 1 reading
        last_valid_temp2: 25.0,             // Last valid sensor 2 reading
        sensor1_fail_count: 0,              // Individual sensor failure counts
        sensor2_fail_count: 0,              // Individual sensor failure counts
        sensor_recovery_attempts: 0         // Recovery attempts count
    },
    // REFLECTOR SYSTEM STATE - SAME AS BEFORE
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

// Application State - FAULT TOLERANT DUAL SENSOR + REFLECTOR OPTIMIZED
let appState = {
    requestCount: 0,
    errorCount: 0,
    lastRequestTime: 0,
    consecutiveErrors: 0,
    commandLog: [],
    statusUpdateInterval: null,
    temperatureUpdateInterval: null,
    realtimeTemperatureInterval: null,  // Ultra-fast realtime updates
    reflectorUpdateInterval: null,      // Ultra-fast reflector updates
    reflectorStatsInterval: null,       // Reflector statistics
    isInitialized: false,
    lastTempAlarmNotified: false,
    lastReflectorCount: 0,              // Track reflector changes
    temperatureHistory: [],
    reflectorHistory: [],               // Reflector history
    tempWarningShown: false,
    sensorDifferenceWarningShown: false,
    reflectorAnomalyWarningShown: false, // Reflector anomaly warning
    // NEW: FAULT TOLERANT flags
    temperatureBypassWarningShown: false,    // Temperature bypass warning shown
    sensorRecoveryNotificationShown: false, // Sensor recovery notification shown
    faultTolerantModeActive: true,           // Fault tolerant mode active
    lastSensorRecoveryAttempt: 0,            // Last sensor recovery attempt time
    performanceStats: {
        temperatureUpdatesCount: 0,
        reflectorUpdatesCount: 0,       // Reflector update count
        lastTempUpdateTime: 0,
        lastReflectorUpdateTime: 0,     // Last reflector update
        averageUpdateFrequency: 0,
        averageReflectorFrequency: 0,   // Average reflector frequency
        sensor1UpdatesCount: 0,
        sensor2UpdatesCount: 0,
        dualSensorUpdatesCount: 0,
        reflectorDetectionCount: 0,     // Detection events count
        // NEW: FAULT TOLERANT stats
        faultTolerantUpdatesCount: 0,   // Fault tolerant updates count
        sensorRecoverySuccessCount: 0,  // Successful sensor recoveries
        operationWithoutTempCount: 0,   // Operations without temp sensors
        temperatureBypassUsageCount: 0  // Temperature bypass usage count
    }
};

// Constants - FAULT TOLERANT DUAL SENSOR + REFLECTOR OPTIMIZED
const CONFIG = {
    REQUEST_THROTTLE: 25,
    MAX_RETRIES: 3,
    STATUS_UPDATE_INTERVAL: 1500,        // General status
    TEMPERATURE_UPDATE_INTERVAL: 800,    // Dual temp updates
    REALTIME_TEMP_INTERVAL: 400,         // Ultra-fast realtime temp
    REFLECTOR_UPDATE_INTERVAL: 300,      // Ultra-fast reflector updates
    REFLECTOR_STATS_INTERVAL: 2000,      // Reflector statistics updates
    CONNECTION_TIMEOUT: 4000,
    MAX_LOG_ENTRIES: 30,
    NOTIFICATION_TIMEOUT: 4000,
    TEMP_SAFE_THRESHOLD: 50,
    TEMP_WARNING_THRESHOLD: 45,
    TEMP_ALARM_THRESHOLD: 55,
    TEMP_DIFF_WARNING_THRESHOLD: 5.0,
    REFLECTOR_ANOMALY_THRESHOLD: 10000,  // Reflector anomaly detection
    REFLECTOR_SPEED_WARNING: 1000,       // High speed warning (rpm)
    PERFORMANCE_LOG_INTERVAL: 10000,
    // NEW: FAULT TOLERANT constants
    SENSOR_RECOVERY_INTERVAL: 30000,     // Attempt sensor recovery every 30 seconds
    FAULT_TOLERANT_RETRY_COUNT: 5,       // Retry count for fault tolerant operations
    TEMP_BYPASS_CONFIRMATION_TIMEOUT: 10000, // Temp bypass confirmation timeout
    MIN_SENSOR_UPTIME_FOR_RECOVERY: 5000 // Minimum sensor uptime before considering recovery
};

// Utility Functions - ENHANCED WITH FAULT TOLERANCE
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

    // NEW: FAULT TOLERANT utility functions
    static isSensorHealthy(sensorConnected, failCount, lastValidTemp) {
        return sensorConnected && failCount < CONFIG.FAULT_TOLERANT_RETRY_COUNT && lastValidTemp > -50;
    }

    static canOperateWithCurrentSensors(sensor1Healthy, sensor2Healthy, allowWithoutTemp) {
        return sensor1Healthy || sensor2Healthy || allowWithoutTemp;
    }

    static getSensorStatusText(sensor1Connected, sensor2Connected, tempRequired, allowWithoutTemp) {
        if (sensor1Connected && sensor2Connected) {
            return 'Çift Sensör Aktif';
        } else if (sensor1Connected || sensor2Connected) {
            return 'Tek Sensör Aktif (FAULT TOLERANT)';
        } else if (allowWithoutTemp) {
            return 'Sensörsüz Operasyon (BYPASS)';
        } else if (tempRequired) {
            return 'Sensör Gerekli (HATA)';
        } else {
            return 'Sıcaklık İzleme Devre Dışı';
        }
    }

    static getFaultTolerantStatusColor(sensor1Connected, sensor2Connected, tempRequired, allowWithoutTemp) {
        if (sensor1Connected && sensor2Connected) {
            return '#00ff88'; // Green - optimal
        } else if (sensor1Connected || sensor2Connected) {
            return '#ffc107'; // Yellow - degraded but working
        } else if (allowWithoutTemp) {
            return '#00d4ff'; // Blue - bypassed
        } else {
            return '#ff4757'; // Red - error
        }
    }
}

// NEW: REFLECTOR SYSTEM MANAGER - ENHANCED
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
    
    // Reflector control functions
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
    
    // Ultra-fast reflector updates
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
                if (!appState.faultTolerantModeActive) {
                    systemState.reflector.system_active = false;
                }
            }
        }
    }
    
    // Get reflector statistics
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

// NEW: FAULT TOLERANT TEMPERATURE MANAGER - ENHANCED
class FaultTolerantTemperatureManager {
    static updateFaultTolerantTemperatureDisplay(tempData) {
        if (!tempData) return;
        
        // Extract fault tolerant dual temperature data
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
        const sensor1Connected = tempData.sensor1_connected !== undefined ? tempData.sensor1_connected : false;
        const sensor2Connected = tempData.sensor2_connected !== undefined ? tempData.sensor2_connected : false;
        const tempDifference = Math.abs(sensor1Temp - sensor2Temp);
        
        // NEW: FAULT TOLERANT specific fields
        const tempMonitoringRequired = tempData.temp_monitoring_required !== undefined ? tempData.temp_monitoring_required : false;
        const allowOperationWithoutTemp = tempData.allow_operation_without_temp !== undefined ? tempData.allow_operation_without_temp : true;
        const faultTolerantMode = tempData.fault_tolerant_mode !== undefined ? tempData.fault_tolerant_mode : true;
        const lastValidTemp1 = tempData.last_valid_temp1 || sensor1Temp;
        const lastValidTemp2 = tempData.last_valid_temp2 || sensor2Temp;
        const sensor1FailCount = tempData.sensor1_fail_count || 0;
        const sensor2FailCount = tempData.sensor2_fail_count || 0;
        const sensorRecoveryAttempts = tempData.sensor_recovery_attempts || 0;
        
        // Update performance stats with fault tolerant tracking
        appState.performanceStats.temperatureUpdatesCount++;
        appState.performanceStats.dualSensorUpdatesCount++;
        appState.performanceStats.faultTolerantUpdatesCount++; // NEW
        
        if (sensor1Connected) appState.performanceStats.sensor1UpdatesCount++;
        if (sensor2Connected) appState.performanceStats.sensor2UpdatesCount++;
        
        // Update operational stats
        if (!tempMonitoringRequired && allowOperationWithoutTemp) {
            appState.performanceStats.operationWithoutTempCount++; // NEW
        }
        if (allowOperationWithoutTemp) {
            appState.performanceStats.temperatureBypassUsageCount++; // NEW
        }
        
        const now = Date.now();
        if (appState.performanceStats.lastTempUpdateTime > 0) {
            const timeDiff = (now - appState.performanceStats.lastTempUpdateTime) / 1000;
            appState.performanceStats.averageUpdateFrequency = 1 / timeDiff;
        }
        appState.performanceStats.lastTempUpdateTime = now;
        
        // Update all fault tolerant dual temperature displays
        this.updateFaultTolerantSensorElements(sensor1Temp, sensor2Temp, currentTemp, sensor1Connected, sensor2Connected, 
                                             tempMonitoringRequired, allowOperationWithoutTemp, faultTolerantMode);
        this.updateFaultTolerantTemperatureStatus(currentTemp, tempAlarm, emergencyActive, tempMonitoringRequired, allowOperationWithoutTemp);
        this.updateFaultTolerantTemperatureDetails(maxTemp, maxSensor1, maxSensor2, alarmCount, buzzerActive, updateFrequency, 
                                                 tempDifference, sensor1FailCount, sensor2FailCount, sensorRecoveryAttempts);
        this.updateFaultTolerantSensorConnectionStatus(sensor1Connected, sensor2Connected, lastValidTemp1, lastValidTemp2);
        this.updateFaultTolerantRedundancyStatus(sensor1Connected, sensor2Connected, tempMonitoringRequired, allowOperationWithoutTemp);
        this.updateLastUpdateTime();
        
        // Store fault tolerant dual temperature data in system state
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
            dual_sensor_mode: true,
            // NEW: FAULT TOLERANT fields
            temp_monitoring_required: tempMonitoringRequired,
            allow_operation_without_temp: allowOperationWithoutTemp,
            fault_tolerant_mode: faultTolerantMode,
            last_valid_temp1: lastValidTemp1,
            last_valid_temp2: lastValidTemp2,
            sensor1_fail_count: sensor1FailCount,
            sensor2_fail_count: sensor2FailCount,
            sensor_recovery_attempts: sensorRecoveryAttempts
        };
        
        // Update global fault tolerant mode flag
        appState.faultTolerantModeActive = faultTolerantMode;
        
        // Handle fault tolerant notifications with reflector correlation
        this.handleFaultTolerantTemperatureNotifications(tempAlarm, emergencyActive, currentTemp, tempDifference, 
                                                        sensor1Connected, sensor2Connected, tempMonitoringRequired, 
                                                        allowOperationWithoutTemp, faultTolerantMode);
    }
    
    static updateFaultTolerantSensorElements(sensor1Temp, sensor2Temp, safetyTemp, sensor1Connected, sensor2Connected, 
                                           tempMonitoringRequired, allowOperationWithoutTemp, faultTolerantMode) {
        // Update individual sensor temperatures with fault tolerant styling
        const sensor1El = document.getElementById('sensor1-temp');
        const sensor2El = document.getElementById('sensor2-temp');
        const safetyTempEl = document.getElementById('safety-temp');
        
        if (sensor1El) {
            sensor1El.textContent = `${sensor1Temp.toFixed(1)}°C`;
            sensor1El.className = 'temp-current primary';
            
            // FAULT TOLERANT color coding
            if (!sensor1Connected) {
                sensor1El.classList.add('disconnected');
                if (faultTolerantMode) {
                    sensor1El.classList.add('fault-tolerant'); // NEW CSS class for fault tolerant mode
                }
            } else if (sensor1Temp >= CONFIG.TEMP_ALARM_THRESHOLD && tempMonitoringRequired) {
                sensor1El.classList.add('danger');
            } else if (sensor1Temp >= CONFIG.TEMP_WARNING_THRESHOLD && tempMonitoringRequired) {
                sensor1El.classList.add('warning');
            } else if (!tempMonitoringRequired) {
                sensor1El.classList.add('bypass'); // NEW CSS class for bypass mode
            }
        }
        
        if (sensor2El) {
            sensor2El.textContent = `${sensor2Temp.toFixed(1)}°C`;
            sensor2El.className = 'temp-current secondary';
            
            if (!sensor2Connected) {
                sensor2El.classList.add('disconnected');
                if (faultTolerantMode) {
                    sensor2El.classList.add('fault-tolerant');
                }
            } else if (sensor2Temp >= CONFIG.TEMP_ALARM_THRESHOLD && tempMonitoringRequired) {
                sensor2El.classList.add('danger');
            } else if (sensor2Temp >= CONFIG.TEMP_WARNING_THRESHOLD && tempMonitoringRequired) {
                sensor2El.classList.add('warning');
            } else if (!tempMonitoringRequired) {
                sensor2El.classList.add('bypass');
            }
        }
        
        // Update safety temperature (maximum) with fault tolerant logic
        if (safetyTempEl) {
            safetyTempEl.textContent = `${safetyTemp.toFixed(1)}°C`;
            safetyTempEl.className = 'temp-current safety';
            
            if (!tempMonitoringRequired) {
                safetyTempEl.classList.add('bypass');
            } else if (safetyTemp >= CONFIG.TEMP_ALARM_THRESHOLD) {
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
            if (!sensor1Connected && faultTolerantMode) {
                sensor1MaxEl.style.opacity = '0.6';
                sensor1MaxEl.title = 'Sensör bağlantısız - son geçerli değer';
            } else {
                sensor1MaxEl.style.opacity = '1';
                sensor1MaxEl.title = '';
            }
        }
        if (sensor2MaxEl) {
            sensor2MaxEl.textContent = `${systemState.temperature.max_sensor2.toFixed(1)}°C`;
            if (!sensor2Connected && faultTolerantMode) {
                sensor2MaxEl.style.opacity = '0.6';
                sensor2MaxEl.title = 'Sensör bağlantısız - son geçerli değer';
            } else {
                sensor2MaxEl.style.opacity = '1';
                sensor2MaxEl.title = '';
            }
        }
        
        // FAULT TOLERANT temperature section styling
        const tempSectionEl = document.getElementById('temperature-section');
        if (tempSectionEl) {
            tempSectionEl.className = 'temperature-section';
            
            if (systemState.temperature.alarm && tempMonitoringRequired) {
                tempSectionEl.classList.add('danger');
            } else if (safetyTemp >= CONFIG.TEMP_WARNING_THRESHOLD && tempMonitoringRequired) {
                tempSectionEl.classList.add('warning');
            } else if (!tempMonitoringRequired && allowOperationWithoutTemp) {
                tempSectionEl.classList.add('bypass-active'); // NEW CSS class
            } else if (faultTolerantMode && (!sensor1Connected || !sensor2Connected)) {
                tempSectionEl.classList.add('fault-tolerant-active'); // NEW CSS class
            }
        }
    }
    
    static updateFaultTolerantTemperatureDetails(maxTemp, maxSensor1, maxSensor2, alarmCount, buzzerActive, 
                                               updateFrequency, tempDifference, sensor1FailCount, sensor2FailCount, 
                                               sensorRecoveryAttempts) {
        // Batch DOM updates for better performance with fault tolerant data
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
            'temp-difference-value': `${tempDifference.toFixed(1)}°C`,
            // NEW: FAULT TOLERANT fields
            'sensor1-fail-count': sensor1FailCount,
            'sensor2-fail-count': sensor2FailCount,
            'sensor-recovery-attempts': sensorRecoveryAttempts,
            'fault-tolerant-mode-status': systemState.temperature.fault_tolerant_mode ? 'Aktif' : 'Pasif',
            'temp-monitoring-status': systemState.temperature.temp_monitoring_required ? 'Gerekli' : 'Devre Dışı',
            'temp-bypass-status': systemState.temperature.allow_operation_without_temp ? 'İzinli' : 'Yasak',
            'last-valid-temp1': `${systemState.temperature.last_valid_temp1.toFixed(1)}°C`,
            'last-valid-temp2': `${systemState.temperature.last_valid_temp2.toFixed(1)}°C`
        };
        
        Object.entries(updates).forEach(([id, value]) => {
            const element = document.getElementById(id);
            if (element && element.textContent !== value.toString()) {
                element.textContent = value;
            }
        });
        
        // Update buzzer button with fault tolerant logic
        const buzzerBtn = document.getElementById('buzzer-off-btn');
        if (buzzerBtn) {
            buzzerBtn.disabled = !buzzerActive || !systemState.temperature.temp_monitoring_required;
            if (!systemState.temperature.temp_monitoring_required) {
                buzzerBtn.title = 'Sıcaklık izleme devre dışı - buzzer kullanılmıyor';
            } else {
                buzzerBtn.title = '';
            }
        }
        
        // Show/hide temperature difference warning with fault tolerant logic
        const tempDiffWarning = document.getElementById('temp-difference-warning');
        if (tempDiffWarning) {
            const shouldShow = tempDifference > CONFIG.TEMP_DIFF_WARNING_THRESHOLD && 
                              systemState.temperature.sensor1_connected && 
                              systemState.temperature.sensor2_connected &&
                              systemState.temperature.temp_monitoring_required;
            
            const currentDisplay = tempDiffWarning.style.display;
            const targetDisplay = shouldShow ? 'block' : 'none';
            
            if (currentDisplay !== targetDisplay) {
                tempDiffWarning.style.display = targetDisplay;
            }
        }
        
        // NEW: Show/hide fault tolerant status indicators
        this.updateFaultTolerantStatusIndicators();
    }
    
    static updateFaultTolerantSensorConnectionStatus(sensor1Connected, sensor2Connected, lastValidTemp1, lastValidTemp2) {
        // Update sensor 1 connection status with fault tolerant info
        const sensor1Dot = document.getElementById('sensor1-dot');
        const sensor1StatusText = document.getElementById('sensor1-status-text');
        const sensor1StatusMini = document.getElementById('sensor1-status-mini');
        
        if (sensor1Dot) {
            sensor1Dot.className = sensor1Connected ? 'connection-dot connected' : 'connection-dot';
            if (!sensor1Connected && systemState.temperature.fault_tolerant_mode) {
                sensor1Dot.classList.add('fault-tolerant');
            }
        }
        if (sensor1StatusText) {
            if (sensor1Connected) {
                sensor1StatusText.textContent = 'Bağlı';
            } else if (systemState.temperature.fault_tolerant_mode) {
                sensor1StatusText.textContent = `Hatalı (Son: ${lastValidTemp1.toFixed(1)}°C)`;
            } else {
                sensor1StatusText.textContent = 'Bağlantısız';
            }
        }
        if (sensor1StatusMini) {
            sensor1StatusMini.textContent = '●';
            if (sensor1Connected) {
                sensor1StatusMini.style.color = '#00ff88';
            } else if (systemState.temperature.fault_tolerant_mode) {
                sensor1StatusMini.style.color = '#ffc107'; // Yellow for fault tolerant mode
            } else {
                sensor1StatusMini.style.color = '#ff4757';
            }
        }
        
        // Update sensor 2 connection status with fault tolerant info
        const sensor2Dot = document.getElementById('sensor2-dot');
        const sensor2StatusText = document.getElementById('sensor2-status-text');
        const sensor2StatusMini = document.getElementById('sensor2-status-mini');
        
        if (sensor2Dot) {
            sensor2Dot.className = sensor2Connected ? 'connection-dot connected' : 'connection-dot';
            if (!sensor2Connected && systemState.temperature.fault_tolerant_mode) {
                sensor2Dot.classList.add('fault-tolerant');
            }
        }
        if (sensor2StatusText) {
            if (sensor2Connected) {
                sensor2StatusText.textContent = 'Bağlı';
            } else if (systemState.temperature.fault_tolerant_mode) {
                sensor2StatusText.textContent = `Hatalı (Son: ${lastValidTemp2.toFixed(1)}°C)`;
            } else {
                sensor2StatusText.textContent = 'Bağlantısız';
            }
        }
        if (sensor2StatusMini) {
            sensor2StatusMini.textContent = '●';
            if (sensor2Connected) {
                sensor2StatusMini.style.color = '#00ff88';
            } else if (systemState.temperature.fault_tolerant_mode) {
                sensor2StatusMini.style.color = '#ffc107'; // Yellow for fault tolerant mode
            } else {
                sensor2StatusMini.style.color = '#ff4757';
            }
        }
    }
    
    static updateFaultTolerantRedundancyStatus(sensor1Connected, sensor2Connected, tempMonitoringRequired, allowOperationWithoutTemp) {
        let redundancyStatus, redundancyColor;
        
        // FAULT TOLERANT redundancy status logic
        if (sensor1Connected && sensor2Connected) {
            redundancyStatus = 'Çift Aktif';
            redundancyColor = '#00ff88';
        } else if (sensor1Connected || sensor2Connected) {
            redundancyStatus = 'Tek Aktif (FAULT TOLERANT)';
            redundancyColor = '#ffc107';
        } else if (allowOperationWithoutTemp && !tempMonitoringRequired) {
            redundancyStatus = 'Sensörsüz Operasyon (BYPASS)';
            redundancyColor = '#00d4ff';
        } else if (!tempMonitoringRequired) {
            redundancyStatus = 'Sıcaklık İzleme Devre Dışı';
            redundancyColor = '#aaa';
        } else {
            redundancyStatus = 'Sensör Hatası';
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
        
        // NEW: Update fault tolerant status text
        const faultTolerantStatusEl = document.getElementById('fault-tolerant-status-text');
        if (faultTolerantStatusEl) {
            faultTolerantStatusEl.textContent = Utils.getSensorStatusText(sensor1Connected, sensor2Connected, tempMonitoringRequired, allowOperationWithoutTemp);
            faultTolerantStatusEl.style.color = Utils.getFaultTolerantStatusColor(sensor1Connected, sensor2Connected, tempMonitoringRequired, allowOperationWithoutTemp);
        }
    }
    
    static updateFaultTolerantTemperatureStatus(currentTemp, tempAlarm, emergencyActive, tempMonitoringRequired, allowOperationWithoutTemp) {
        const tempStatusEl = document.getElementById('temp-status-text');
        const detailedAlarmStatusEl = document.getElementById('detailed-temp-alarm-status');
        
        let statusText, statusColor;
        
        // FAULT TOLERANT status logic
        if (!tempMonitoringRequired && allowOperationWithoutTemp) {
            statusText = 'Bypass Aktif';
            statusColor = '#00d4ff';
        } else if (tempAlarm || emergencyActive) {
            statusText = 'ALARM!';
            statusColor = '#ff4757';
        } else if (currentTemp >= CONFIG.TEMP_WARNING_THRESHOLD && tempMonitoringRequired) {
            statusText = 'Uyarı';
            statusColor = '#ffc107';
        } else if (tempMonitoringRequired) {
            statusText = 'Güvenli';
            statusColor = '#00ff88';
        } else {
            statusText = 'İzleme Devre Dışı';
            statusColor = '#aaa';
        }
        
        if (tempStatusEl && tempStatusEl.textContent !== statusText) {
            tempStatusEl.textContent = statusText;
            tempStatusEl.style.color = statusColor;
        }
        
        if (detailedAlarmStatusEl) {
            let alarmStatus;
            if (!tempMonitoringRequired) {
                alarmStatus = 'Bypass';
                statusColor = '#00d4ff';
            } else if (tempAlarm) {
                alarmStatus = 'ALARM';
                statusColor = '#ff4757';
            } else {
                alarmStatus = 'Normal';
                statusColor = '#00ff88';
            }
            
            if (detailedAlarmStatusEl.textContent !== alarmStatus) {
                detailedAlarmStatusEl.textContent = alarmStatus;
                detailedAlarmStatusEl.style.color = statusColor;
            }
        }
        
        // Emergency indicators with fault tolerant logic
        const tempEmergencyEl = document.getElementById('temp-emergency');
        if (tempEmergencyEl) {
            const shouldShow = (tempAlarm || emergencyActive) && tempMonitoringRequired;
            const currentDisplay = tempEmergencyEl.style.display;
            const targetDisplay = shouldShow ? 'block' : 'none';
            
            if (currentDisplay !== targetDisplay) {
                tempEmergencyEl.style.display = targetDisplay;
            }
        }
        
        // Enhanced fault tolerant dual temperature emergency warning with reflector data
        const emergencyWarning = document.getElementById('temperature-emergency-warning');
        if (emergencyWarning) {
            const shouldShow = (tempAlarm || emergencyActive) && tempMonitoringRequired;
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
                    
                    // NEW: Add fault tolerant info to emergency warning
                    const faultTolerantInfoEl = document.getElementById('warning-fault-tolerant-info');
                    if (faultTolerantInfoEl) {
                        const sensor1Status = systemState.temperature.sensor1_connected ? 'OK' : 'HATA';
                        const sensor2Status = systemState.temperature.sensor2_connected ? 'OK' : 'HATA';
                        faultTolerantInfoEl.textContent = `Sensör Durumu: S1=${sensor1Status}, S2=${sensor2Status}`;
                    }
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
    
    static updateFaultTolerantStatusIndicators() {
        // NEW: Update fault tolerant mode indicators throughout the interface
        const faultTolerantModeEl = document.getElementById('fault-tolerant-mode-indicator');
        if (faultTolerantModeEl) {
            faultTolerantModeEl.style.display = systemState.temperature.fault_tolerant_mode ? 'block' : 'none';
            if (systemState.temperature.fault_tolerant_mode) {
                faultTolerantModeEl.innerHTML = `
                    <span class="fault-tolerant-icon">🛡️</span>
                    <span class="fault-tolerant-text">FAULT TOLERANT</span>
                `;
            }
        }
        
        // Update temperature bypass indicator
        const tempBypassEl = document.getElementById('temp-bypass-indicator');
        if (tempBypassEl) {
            tempBypassEl.style.display = systemState.temperature.allow_operation_without_temp ? 'block' : 'none';
            if (systemState.temperature.allow_operation_without_temp) {
                tempBypassEl.innerHTML = `
                    <span class="bypass-icon">⚠️</span>
                    <span class="bypass-text">TEMP BYPASS</span>
                `;
            }
        }
        
        // Update sensor count indicator
        const sensorCountEl = document.getElementById('active-sensor-count');
        if (sensorCountEl) {
            let activeSensors = 0;
            if (systemState.temperature.sensor1_connected) activeSensors++;
            if (systemState.temperature.sensor2_connected) activeSensors++;
            
            sensorCountEl.textContent = `${activeSensors}/2 Sensör`;
            
            if (activeSensors === 2) {
                sensorCountEl.style.color = '#00ff88';
            } else if (activeSensors === 1) {
                sensorCountEl.style.color = '#ffc107';
            } else {
                sensorCountEl.style.color = systemState.temperature.allow_operation_without_temp ? '#00d4ff' : '#ff4757';
            }
        }
    }
    
    static handleFaultTolerantTemperatureNotifications(tempAlarm, emergencyActive, currentTemp, tempDifference, 
                                                     sensor1Connected, sensor2Connected, tempMonitoringRequired, 
                                                     allowOperationWithoutTemp, faultTolerantMode) {
        // Temperature alarm notifications with reflector data and fault tolerance
        if ((tempAlarm || emergencyActive) && tempMonitoringRequired && !appState.lastTempAlarmNotified) {
            const sensorStatus = `S1:${sensor1Connected ? 'OK' : 'HATA'} S2:${sensor2Connected ? 'OK' : 'HATA'}`;
            NotificationManager.show(
                `FAULT TOLERANT SICAKLIK ALARMI! Max: ${currentTemp.toFixed(1)}°C [${sensorStatus}] - Sistem durduruldu! Reflektor: ${systemState.reflector.count}`, 
                'error', 
                8000
            );
            appState.lastTempAlarmNotified = true;
        } else if (!(tempAlarm || emergencyActive) && appState.lastTempAlarmNotified) {
            const sensorStatus = `S1:${sensor1Connected ? 'OK' : 'HATA'} S2:${sensor2Connected ? 'OK' : 'HATA'}`;
            NotificationManager.show(
                `FAULT TOLERANT: Sıcaklık güvenli seviyeye döndü [${sensorStatus}], Reflektor: ${systemState.reflector.count}`, 
                'success'
            );
            appState.lastTempAlarmNotified = false;
        }
        
        // Warning level notifications with fault tolerant correlation
        if (currentTemp >= CONFIG.TEMP_WARNING_THRESHOLD && currentTemp < CONFIG.TEMP_ALARM_THRESHOLD && tempMonitoringRequired) {
            if (!appState.tempWarningShown) {
                const sensorStatus = `S1:${sensor1Connected ? 'OK' : 'HATA'} S2:${sensor2Connected ? 'OK' : 'HATA'}`;
                NotificationManager.show(
                    `FAULT TOLERANT: Sıcaklık uyarı seviyesinde: ${currentTemp.toFixed(1)}°C [${sensorStatus}] - Reflektor: ${systemState.reflector.count}`, 
                    'warning'
                );
                appState.tempWarningShown = true;
            }
        } else {
            appState.tempWarningShown = false;
        }
        
        // Sensor difference warnings with fault tolerance
        if (tempDifference > CONFIG.TEMP_DIFF_WARNING_THRESHOLD && sensor1Connected && sensor2Connected && tempMonitoringRequired) {
            if (!appState.sensorDifferenceWarningShown) {
                NotificationManager.show(
                    `FAULT TOLERANT: Büyük sensör farkı! S1:${systemState.temperature.sensor1_temp.toFixed(1)}°C S2:${systemState.temperature.sensor2_temp.toFixed(1)}°C (Fark: ${tempDifference.toFixed(1)}°C)`, 
                    'warning',
                    6000
                );
                appState.sensorDifferenceWarningShown = true;
            }
        } else {
            appState.sensorDifferenceWarningShown = false;
        }
        
        // FAULT TOLERANT: Sensor disconnection warnings
        if (!sensor1Connected && systemState.temperature.sensor1_connected) {
            NotificationManager.show('FAULT TOLERANT: Sensör 1 (Pin 8) bağlantısı kesildi - sistem devam ediyor!', 'warning');
            systemState.temperature.sensor1_connected = false;
        }
        if (!sensor2Connected && systemState.temperature.sensor2_connected) {
            NotificationManager.show('FAULT TOLERANT: Sensör 2 (Pin 13) bağlantısı kesildi - sistem devam ediyor!', 'warning');
            systemState.temperature.sensor2_connected = false;
        }
        
        // FAULT TOLERANT: Both sensors failed warning with bypass option
        if (!sensor1Connected && !sensor2Connected && (systemState.temperature.sensor1_connected || systemState.temperature.sensor2_connected)) {
            if (allowOperationWithoutTemp) {
                NotificationManager.show('FAULT TOLERANT: Her iki sıcaklık sensörü de başarısız - sıcaklık izleme bypass modu aktif!', 'warning', 10000);
            } else {
                NotificationManager.show('FAULT TOLERANT: Her iki sıcaklık sensörü de başarısız - sistem güvenli moda geçiyor!', 'error', 10000);
            }
        }
        
        // NEW: Temperature bypass notifications
        if (allowOperationWithoutTemp && !tempMonitoringRequired && !appState.temperatureBypassWarningShown) {
            NotificationManager.show(
                'FAULT TOLERANT: Sıcaklık bypass modu aktif - sistem sensör olmadan çalışabilir!', 
                'info', 
                8000
            );
            appState.temperatureBypassWarningShown = true;
            appState.performanceStats.temperatureBypassUsageCount++;
        } else if (tempMonitoringRequired && appState.temperatureBypassWarningShown) {
            appState.temperatureBypassWarningShown = false;
        }
        
        // NEW: Sensor recovery notifications
        if ((sensor1Connected && !systemState.temperature.sensor1_connected) || 
            (sensor2Connected && !systemState.temperature.sensor2_connected)) {
            if (!appState.sensorRecoveryNotificationShown) {
                const recoveredSensors = [];
                if (sensor1Connected && !systemState.temperature.sensor1_connected) recoveredSensors.push('Sensör 1');
                if (sensor2Connected && !systemState.temperature.sensor2_connected) recoveredSensors.push('Sensör 2');
                
                NotificationManager.show(
                    `FAULT TOLERANT: ${recoveredSensors.join(' ve ')} kurtarıldı! Sıcaklık izleme yeniden aktif.`, 
                    'success', 
                    6000
                );
                appState.sensorRecoveryNotificationShown = true;
                appState.performanceStats.sensorRecoverySuccessCount++;
                
                // Reset flag after some time
                setTimeout(() => {
                    appState.sensorRecoveryNotificationShown = false;
                }, 30000);
            }
        }
        
        // Store previous sensor states for next comparison
        systemState.temperature.sensor1_connected = sensor1Connected;
        systemState.temperature.sensor2_connected = sensor2Connected;
    }
    
    // NEW: Temperature bypass control functions
    static async enableTemperatureBypass() {
        try {
            const response = await RequestHandler.makeRequest(`${BACKEND_URL}/api/temperature/bypass/enable`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' }
            });
            
            const data = await response.json();
            
            if (data.status === 'success') {
                systemState.temperature.allow_operation_without_temp = true;
                systemState.temperature.temp_monitoring_required = false;
                systemState.temperature.temp_alarm = false;
                systemState.temperature.buzzer_active = false;
                
                NotificationManager.show('FAULT TOLERANT: Sıcaklık bypass modu etkinleştirildi!', 'success');
                CommandLogger.log('FAULT TOLERANT bypass etkin', true, 'Sistem artık sensör olmadan çalışabilir');
                
                // Update UI immediately
                this.updateFaultTolerantStatusIndicators();
                
                return true;
            } else {
                throw new Error(data.message || 'Bypass etkinleştirilemedi');
            }
        } catch (error) {
            CommandLogger.log('FAULT TOLERANT bypass etkinleştirme', false, error.message);
            NotificationManager.show(`Sıcaklık bypass etkinleştirilemedi: ${error.message}`, 'error');
            return false;
        }
    }
    
    static async disableTemperatureBypass() {
        try {
            const response = await RequestHandler.makeRequest(`${BACKEND_URL}/api/temperature/bypass/disable`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' }
            });
            
            const data = await response.json();
            
            if (data.status === 'success') {
                systemState.temperature.temp_monitoring_required = true;
                systemState.temperature.allow_operation_without_temp = false;
                
                NotificationManager.show('FAULT TOLERANT: Sıcaklık izleme yeniden etkinleştirildi!', 'success');
                CommandLogger.log('FAULT TOLERANT bypass devre dışı', true, 'Sıcaklık izleme yeniden aktif');
                
                // Update UI immediately
                this.updateFaultTolerantStatusIndicators();
                
                return true;
            } else if (data.status === 'warning') {
                NotificationManager.show(data.message, 'warning');
                return false;
            } else {
                throw new Error(data.message || 'Bypass devre dışı bırakılamadı');
            }
        } catch (error) {
            CommandLogger.log('FAULT TOLERANT bypass devre dışı bırakma', false, error.message);
            NotificationManager.show(`Sıcaklık bypass devre dışı bırakılamadı: ${error.message}`, 'error');
            return false;
        }
    }
    
    // Enhanced turnOffBuzzer with fault tolerance
    static async turnOffBuzzer() {
        // Check if buzzer is relevant in current mode
        if (!systemState.temperature.temp_monitoring_required) {
            NotificationManager.show('FAULT TOLERANT: Sıcaklık izleme devre dışı - buzzer gerekli değil', 'info');
            return;
        }
        
        try {
            const response = await RequestHandler.makeRequest(`${BACKEND_URL}/api/temperature/buzzer/off`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' }
            });
            
            const data = await response.json();
            
            if (data.status === 'success') {
                systemState.temperature.buzzer_active = false;
                NotificationManager.show('FAULT TOLERANT: Buzzer kapatıldı', 'success');
                CommandLogger.log('FAULT TOLERANT buzzer kapatıldı', true);
                
                // Log fault tolerant dual temperatures + reflector when buzzer turned off
                if (data.dual_temps) {
                    CommandLogger.log('Buzzer kapatıldığında FAULT TOLERANT veriler', true, 
                        `S1:${data.dual_temps.sensor1}°C S2:${data.dual_temps.sensor2}°C Max:${data.dual_temps.max}°C Bypass:${systemState.temperature.allow_operation_without_temp ? 'Aktif' : 'Pasif'} Reflektor:${data.reflector_count || systemState.reflector.count}`);
                }
            } else {
                throw new Error(data.message || 'Buzzer kapatılamadı');
            }
        } catch (error) {
            CommandLogger.log('FAULT TOLERANT buzzer kapatma', false, error.message);
            NotificationManager.show(`Buzzer kapatılamadı: ${error.message}`, 'error');
        }
    }
    
    // Ultra-fast fault tolerant dual temperature updates
    static async updateFaultTolerantTemperatureOnly() {
        try {
            const response = await RequestHandler.makeRequest(`${BACKEND_URL}/api/temperature/realtime`, {
                method: 'GET'
            }, 2000, 1);
            
            const data = await response.json();
            
            if (data.fault_tolerant_mode !== undefined && data.sensor1_temp !== undefined && data.sensor2_temp !== undefined) {
                // Ultra-fast fault tolerant dual temperature data structure with reflector
                const quickFaultTolerantTempData = {
                    sensor1_temp: data.sensor1_temp,
                    sensor2_temp: data.sensor2_temp,
                    current: data.current_temperature || Math.max(data.sensor1_temp, data.sensor2_temp),
                    alarm: data.temperature_alarm || false,
                    buzzer_active: data.buzzer_active || false,
                    update_frequency: data.update_frequency || 0,
                    sensor1_connected: data.sensor1_connected !== undefined ? data.sensor1_connected : false,
                    sensor2_connected: data.sensor2_connected !== undefined ? data.sensor2_connected : false,
                    // FAULT TOLERANT fields
                    temp_monitoring_required: data.temp_monitoring_required !== undefined ? data.temp_monitoring_required : false,
                    allow_operation_without_temp: data.allow_operation_without_temp !== undefined ? data.allow_operation_without_temp : true,
                    fault_tolerant_mode: data.fault_tolerant_mode !== undefined ? data.fault_tolerant_mode : true,
                    last_valid_temp1: data.last_valid_temp1 || data.sensor1_temp,
                    last_valid_temp2: data.last_valid_temp2 || data.sensor2_temp,
                    sensor1_fail_count: data.sensor1_fail_count || 0,
                    sensor2_fail_count: data.sensor2_fail_count || 0,
                    sensor_recovery_attempts: data.sensor_recovery_attempts || 0,
                    // Keep existing values for performance
                    max_reached: systemState.temperature.max_reached,
                    max_sensor1: Math.max(systemState.temperature.max_sensor1, data.sensor1_temp),
                    max_sensor2: Math.max(systemState.temperature.max_sensor2, data.sensor2_temp),
                    emergency_active: data.temperature_alarm || false,
                    alarm_count: systemState.temperature.alarm_count,
                    sensor_failure_count: systemState.temperature.sensor_failure_count
                };
                
                this.updateFaultTolerantTemperatureDisplay(quickFaultTolerantTempData);
                
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
            console.debug('Quick fault tolerant dual temperature + reflector update failed:', error.message);
            appState.consecutiveErrors++;
            
            if (appState.consecutiveErrors >= 3) {
                ConnectionManager.updateConnectionStatus('backend', false);
                // Don't disable reflector in fault tolerant mode
                if (!systemState.temperature.fault_tolerant_mode) {
                    systemState.reflector.system_active = false;
                }
            }
        }
    }
}

// HTTP Request Handler - ENHANCED WITH FAULT TOLERANCE
class RequestHandler {
    static async makeRequest(url, options = {}, timeout = CONFIG.CONNECTION_TIMEOUT, retries = CONFIG.MAX_RETRIES) {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), timeout);
        
        for (let attempt = 0; attempt < retries; attempt++) {
            try {
                console.debug(`Making FAULT TOLERANT request to ${url} (attempt ${attempt + 1}/${retries})`);
                
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
                console.debug(`FAULT TOLERANT request failed (attempt ${attempt + 1}): ${error.message}`);
                
                if (attempt === retries - 1) {
                    clearTimeout(timeoutId);
                    appState.errorCount++;
                    appState.consecutiveErrors++;
                    
                    // In fault tolerant mode, don't immediately mark backend as disconnected
                    if (!appState.faultTolerantModeActive || appState.consecutiveErrors >= CONFIG.FAULT_TOLERANT_RETRY_COUNT) {
                        ConnectionManager.updateConnectionStatus('backend', false);
                    }
                    
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

// Enhanced Status Manager with FAULT TOLERANT support
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
                
                // FAULT TOLERANT dual temperature data handling
                if (data.temperature) {
                    FaultTolerantTemperatureManager.updateFaultTolerantTemperatureDisplay(data.temperature);
                }
                
                // Reflector data handling - same as before
                if (data.reflector) {
                    ReflectorManager.updateReflectorDisplay(data.reflector);
                }
                
                // Update global fault tolerant flags
                if (data.stats && data.stats.fault_tolerant_mode !== undefined) {
                    appState.faultTolerantModeActive = data.stats.fault_tolerant_mode;
                }
                
                // Motor states - same as before
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
                if (!appState.faultTolerantModeActive || appState.consecutiveErrors >= CONFIG.FAULT_TOLERANT_RETRY_COUNT) {
                    ConnectionManager.updateConnectionStatus('backend', false);
                    ConnectionManager.updateConnectionStatus('arduino', false);
                    
                    // In fault tolerant mode, don't immediately disable reflector
                    if (!appState.faultTolerantModeActive && systemState.reflector) {
                        systemState.reflector.system_active = false;
                        systemState.reflector.connected = false;
                        ReflectorManager.updateReflectorConnectionStatus(false);
                    }
                }
            }
            console.debug('FAULT TOLERANT status poll error:', error.message);
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
        
        // Start fault tolerant dual temperature polling
        appState.temperatureUpdateInterval = setInterval(() => {
            FaultTolerantTemperatureManager.updateFaultTolerantTemperatureOnly();
        }, CONFIG.TEMPERATURE_UPDATE_INTERVAL);
        
        // Start ultra-fast realtime fault tolerant temperature polling
        appState.realtimeTemperatureInterval = setInterval(() => {
            FaultTolerantTemperatureManager.updateFaultTolerantTemperatureOnly();
        }, CONFIG.REALTIME_TEMP_INTERVAL);
        
        // Start ultra-fast reflector polling
        appState.reflectorUpdateInterval = setInterval(() => {
            ReflectorManager.updateReflectorOnly();
        }, CONFIG.REFLECTOR_UPDATE_INTERVAL);
        
        // Start reflector statistics polling
        appState.reflectorStatsInterval = setInterval(() => {
            ReflectorManager.getReflectorStatistics();
        }, CONFIG.REFLECTOR_STATS_INTERVAL);
        
        // Initial calls
        setTimeout(() => this.pollStatus(), 500);
        setTimeout(() => FaultTolerantTemperatureManager.updateFaultTolerantTemperatureOnly(), 100);
        setTimeout(() => ReflectorManager.updateReflectorOnly(), 200);
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

// Enhanced Command Logger with FAULT TOLERANT support
class CommandLogger {
    static log(command, success = true, details = '') {
        const timestamp = Utils.formatTime(new Date());
        const status = success ? '✅' : '❌';
        
        // Enhanced logging with fault tolerant and reflector data for important commands
        let enhancedDetails = details;
        if (success && (command.includes('Motor') || command.includes('Grup') || command.includes('ARM') || command.includes('EMERGENCY'))) {
            const faultTolerantInfo = appState.faultTolerantModeActive ? '[FT]' : '';
            const sensorInfo = systemState.temperature.temp_monitoring_required ? '[TEMP]' : '[BYPASS]';
            enhancedDetails = `${details} ${faultTolerantInfo}${sensorInfo} [Reflektor: ${systemState.reflector.count}]`;
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

// Notification System - ENHANCED FOR FAULT TOLERANT
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
        
        // Add fault tolerant styling if in fault tolerant mode
        if (appState.faultTolerantModeActive) {
            notification.classList.add('fault-tolerant-notification');
        }
        
        setTimeout(() => {
            this.hide();
        }, duration);
    }

    static hide() {
        const notification = document.getElementById('notification');
        if (notification) {
            notification.classList.remove('show');
            notification.classList.remove('fault-tolerant-notification');
        }
    }
}

// Enhanced Connection Manager with FAULT TOLERANT support
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
            
            // Add fault tolerant styling if in fault tolerant mode
            if (appState.faultTolerantModeActive && !connected) {
                statusElement.classList.add('fault-tolerant');
            }
        }
        
        if (textElement) {
            if (connected) {
                textElement.textContent = 'Bağlı';
                if (appState.faultTolerantModeActive) {
                    textElement.textContent += ' (FAULT TOLERANT)';
                }
            } else {
                textElement.textContent = appState.faultTolerantModeActive ? 'Bağlantısız (FT Modu)' : 'Bağlantısız';
            }
        }
        
        if (type === 'arduino') {
            const arduinoStatus = document.getElementById('arduino-status');
            if (arduinoStatus) {
                if (connected) {
                    arduinoStatus.textContent = appState.faultTolerantModeActive ? 'Bağlı (FAULT TOLERANT)' : 'Bağlı';
                    arduinoStatus.className = 'status-value status-connected';
                } else {
                    arduinoStatus.textContent = appState.faultTolerantModeActive ? 'Bağlantısız (FT Modu)' : 'Bağlantısız';
                    arduinoStatus.className = 'status-value status-error';
                }
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
            NotificationManager.show('FAULT TOLERANT dual sensör + reflektor bağlantı test ediliyor...', 'info');
            
            const response = await RequestHandler.makeRequest(`${BACKEND_URL}/api/ping`);
            const data = await response.json();
            
            if (data.status === 'ok') {
                CommandLogger.log('FAULT TOLERANT dual sensör + reflektor bağlantı testi başarılı', true);
                
                let tempInfo = 'N/A';
                let reflectorInfo = 'N/A';
                let faultTolerantInfo = '';
                
                if (data.dual_temperatures) {
                    const temps = data.dual_temperatures;
                    tempInfo = `S1:${temps.sensor1_temp}°C S2:${temps.sensor2_temp}°C Max:${temps.max_temp}°C`;
                    const sensorStatus = `S1:${temps.sensor1_connected ? 'OK' : 'HATA'} S2:${temps.sensor2_connected ? 'OK' : 'HATA'}`;
                    const tempMode = temps.temp_monitoring_required ? 'MONITORED' : 'BYPASS';
                    faultTolerantInfo = `[${sensorStatus}] [${tempMode}] [FT:${temps.fault_tolerant_mode ? 'ON' : 'OFF'}]`;
                }
                
                if (data.reflector_system) {
                    reflectorInfo = `Sayım:${data.reflector_system.count} Hız:${data.reflector_system.average_speed.toFixed(1)}rpm`;
                }
                
                NotificationManager.show(
                    `FAULT TOLERANT dual sensör + reflektor bağlantı testi başarılı! Sıcaklık: ${tempInfo} ${faultTolerantInfo}, Reflektor: ${reflectorInfo}`, 
                    'success', 
                    8000
                );
                this.updateConnectionStatus('backend', true);
                this.updateConnectionStatus('arduino', data.arduino_connected);
            } else {
                throw new Error(data.message || 'Test failed');
            }
            
        } catch (error) {
            CommandLogger.log('FAULT TOLERANT dual sensör + reflektor bağlantı testi', false, error.message);
            NotificationManager.show(`Bağlantı testi başarısız: ${error.message}`, 'error');
            this.updateConnectionStatus('backend', false);
            this.updateConnectionStatus('arduino', false);
        }
    }

    static async reconnectArduino() {
        try {
            NotificationManager.show('FAULT TOLERANT Arduino dual sensör + reflektor sistemi yeniden bağlanıyor...', 'info');
            
            const response = await RequestHandler.makeRequest(`${BACKEND_URL}/api/reconnect`, {
                method: 'POST'
            });
            
            const data = await response.json();
            
            if (data.status === 'success') {
                CommandLogger.log('FAULT TOLERANT Arduino dual sensör + reflektor sistemi yeniden bağlandı', true);
                NotificationManager.show('FAULT TOLERANT Arduino dual sensör + reflektor sistemi yeniden bağlandı!', 'success');
                setTimeout(() => StatusManager.pollStatus(), 1000);
            } else {
                throw new Error(data.message || 'Reconnection failed');
            }
            
        } catch (error) {
            CommandLogger.log('FAULT TOLERANT Arduino dual sensör + reflektor yeniden bağlanma', false, error.message);
            NotificationManager.show(`Arduino yeniden bağlanamadı: ${error.message}`, 'error');
        }
    }
}

// Enhanced Motor Controller with FAULT TOLERANT temperature checks
class MotorController {
    static async startMotor(motorNum) {
        // FAULT TOLERANT temperature safety check
        if (systemState.temperature.temp_monitoring_required && 
            (systemState.temperature.alarm || systemState.temperature.emergency_active)) {
            const sensorStatus = `S1:${systemState.temperature.sensor1_connected ? 'OK' : 'HATA'} S2:${systemState.temperature.sensor2_connected ? 'OK' : 'HATA'}`;
            NotificationManager.show(`FAULT TOLERANT: Sıcaklık alarmı nedeniyle motorlar başlatılamaz! [${sensorStatus}]`, 'warning');
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
                    
                    // FAULT TOLERANT logging with sensor status
                    const sensorStatus = `S1:${systemState.temperature.sensor1_connected ? 'OK' : 'HATA'} S2:${systemState.temperature.sensor2_connected ? 'OK' : 'HATA'}`;
                    const tempMode = systemState.temperature.temp_monitoring_required ? 'MONITORED' : 'BYPASS';
                    CommandLogger.log(`FAULT TOLERANT Motor ${motorNum} başlatıldı`, true, 
                        `${speed}% - [${sensorStatus}] [${tempMode}] - Reflektor:${systemState.reflector.count}`);
                    NotificationManager.show(`Motor ${motorNum} başlatıldı!`, 'success');
                    
                    // Quick fault tolerant dual temperature + reflector check after motor start
                    setTimeout(() => FaultTolerantTemperatureManager.updateFaultTolerantTemperatureOnly(), 200);
                    setTimeout(() => ReflectorManager.updateReflectorOnly(), 200);
                }

            } catch (error) {
                CommandLogger.log(`FAULT TOLERANT Motor ${motorNum} başlatma`, false, error.message);
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
                    CommandLogger.log(`FAULT TOLERANT Motor ${motorNum} durduruldu`, true, `Reflektor:${systemState.reflector.count}`);
                    NotificationManager.show(`Motor ${motorNum} durduruldu!`, 'success');
                }

            } catch (error) {
                CommandLogger.log(`FAULT TOLERANT Motor ${motorNum} durdurma`, false, error.message);
                NotificationManager.show(`Motor ${motorNum} durdurulamadı: ${error.message}`, 'error');
                console.error('Motor stop error:', error);
            }
        });
    }

    static async setMotorSpeed(motorNum, speed) {
        // FAULT TOLERANT temperature safety check
        if (systemState.temperature.temp_monitoring_required && 
            (systemState.temperature.alarm || systemState.temperature.emergency_active)) {
            const sensorStatus = `S1:${systemState.temperature.sensor1_connected ? 'OK' : 'HATA'} S2:${systemState.temperature.sensor2_connected ? 'OK' : 'HATA'}`;
            NotificationManager.show(`FAULT TOLERANT: Sıcaklık alarmı nedeniyle motor kontrol edilemez! [${sensorStatus}]`, 'warning');
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
                    CommandLogger.log(`FAULT TOLERANT Motor ${motorNum} hızı`, true, `${speed}% - Reflektor:${systemState.reflector.count}`);
                }

            } catch (error) {
                CommandLogger.log(`FAULT TOLERANT Motor ${motorNum} hız`, false, error.message);
                NotificationManager.show(`Motor ${motorNum} hız ayarlanamadı`, 'error');
                console.error('Motor speed error:', error);
            }
        });
    }
}

// Enhanced Group Controller with FAULT TOLERANT temperature checks
class GroupController {
    static async startGroup(groupType) {
        // FAULT TOLERANT temperature safety check
        if (systemState.temperature.temp_monitoring_required && 
            (systemState.temperature.alarm || systemState.temperature.emergency_active)) {
            const sensorStatus = `S1:${systemState.temperature.sensor1_connected ? 'OK' : 'HATA'} S2:${systemState.temperature.sensor2_connected ? 'OK' : 'HATA'}`;
            NotificationManager.show(`FAULT TOLERANT: Sıcaklık alarmı nedeniyle motor grubu başlatılamaz! [${sensorStatus}]`, 'warning');
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
                    
                    // FAULT TOLERANT logging with sensor status
                    const groupName = groupType === 'levitation' ? 'Levitasyon' : 'İtki';
                    const sensorStatus = `S1:${systemState.temperature.sensor1_connected ? 'OK' : 'HATA'} S2:${systemState.temperature.sensor2_connected ? 'OK' : 'HATA'}`;
                    const tempMode = systemState.temperature.temp_monitoring_required ? 'MONITORED' : 'BYPASS';
                    CommandLogger.log(`FAULT TOLERANT ${groupName} grubu başlatıldı`, true, 
                        `${speed}% - M${motorRange.join(',')} - [${sensorStatus}] [${tempMode}] - Reflektor:${systemState.reflector.count}`);
                    NotificationManager.show(`${groupName} grubu başlatıldı! (M${motorRange.join(',')})`, 'success');
                    
                    // Quick fault tolerant dual temperature + reflector check after group start
                    setTimeout(() => FaultTolerantTemperatureManager.updateFaultTolerantTemperatureOnly(), 200);
                    setTimeout(() => ReflectorManager.updateReflectorOnly(), 200);
                }

            } catch (error) {
                CommandLogger.log(`FAULT TOLERANT ${groupType} başlatma`, false, error.message);
                NotificationManager.show(`${groupType} grubu başlatılamadı: ${error.message}`, 'error');
                console.error('Group start error:', error);
            }
        });
    }

    // Rest of GroupController methods remain similar but with FAULT TOLERANT enhancements
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
                    CommandLogger.log(`FAULT TOLERANT ${groupName} grubu durduruldu`, true, `M${motorRange.join(',')} - Reflektor:${systemState.reflector.count}`);
                    NotificationManager.show(`${groupName} grubu durduruldu! (M${motorRange.join(',')})`, 'success');
                }

            } catch (error) {
                CommandLogger.log(`FAULT TOLERANT ${groupType} durdurma`, false, error.message);
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
        // FAULT TOLERANT temperature safety check
        if (systemState.temperature.temp_monitoring_required && 
            (systemState.temperature.alarm || systemState.temperature.emergency_active)) return;
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
                    
                    CommandLogger.log(`FAULT TOLERANT ${groupType} hızı`, true, `${speed}% - Reflektor:${systemState.reflector.count}`);
                }

            } catch (error) {
                CommandLogger.log(`FAULT TOLERANT ${groupType} hız`, false, error.message);
                console.error('Group speed error:', error);
            }
        });
    }
}

// Enhanced System Controller with FAULT TOLERANT temperature checks
class SystemController {
    static async toggleArm() {
        // FAULT TOLERANT arming check
        if (!systemState.armed) {
            // Check if we can arm based on fault tolerant temperature status
            if (systemState.temperature.temp_monitoring_required && 
                (systemState.temperature.alarm || systemState.temperature.emergency_active)) {
                const sensorStatus = `S1:${systemState.temperature.sensor1_connected ? 'OK' : 'HATA'} S2:${systemState.temperature.sensor2_connected ? 'OK' : 'HATA'}`;
                NotificationManager.show(`FAULT TOLERANT: Sıcaklık alarmı nedeniyle sistem hazırlanamaz! [${sensorStatus}]`, 'warning');
                return;
            }
            
            // FAULT TOLERANT: Allow arming even without sensors if bypass is enabled
            if (systemState.temperature.temp_monitoring_required && 
                !systemState.temperature.sensor1_connected && !systemState.temperature.sensor2_connected &&
                !systemState.temperature.allow_operation_without_temp) {
                NotificationManager.show('FAULT TOLERANT: Hiç sıcaklık sensörü bağlı değil! Bypass modunu etkinleştirin veya sensörleri kontrol edin.', 'warning');
                return;
            }
        }
        
        RequestHandler.throttleRequest(async () => {
            try {
                const action = systemState.armed ? 'disarm' : 'arm';
                console.log(`Attempting to ${action} system with FAULT TOLERANT mode`);
                
                if (action === 'arm' && !systemState.relayBrakeActive) {
                    NotificationManager.show('Röle aktif hale getiriliyor, sistem hazırlanıyor...', 'info');
                    
                    const relayResponse = await RequestHandler.makeRequest(`${BACKEND_URL}/api/relay-brake/on`, {
                        method: 'POST'
                    });
                    
                    if (relayResponse.ok) {
                        systemState.relayBrakeActive = true;
                        UIManager.updateRelayBrakeStatus();
                        CommandLogger.log('FAULT TOLERANT Röle otomatik aktif yapıldı', true, `Reflektor:${systemState.reflector.count}`);
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
                    
                    // FAULT TOLERANT logging with sensor status
                    const statusText = action === 'arm' ? 'hazırlandı' : 'devre dışı bırakıldı';
                    const sensorStatus = `S1:${systemState.temperature.sensor1_connected ? 'OK' : 'HATA'} S2:${systemState.temperature.sensor2_connected ? 'OK' : 'HATA'}`;
                    const tempMode = systemState.temperature.temp_monitoring_required ? 'MONITORED' : 'BYPASS';
                    CommandLogger.log(`FAULT TOLERANT Sistem ${statusText}`, true, 
                        `[${sensorStatus}] [${tempMode}] - Reflektor:${systemState.reflector.count}`);
                    NotificationManager.show(`Sistem ${statusText}!`, 'success');
                    
                    // Quick fault tolerant dual temperature + reflector check after system change
                    setTimeout(() => FaultTolerantTemperatureManager.updateFaultTolerantTemperatureOnly(), 200);
                    setTimeout(() => ReflectorManager.updateReflectorOnly(), 200);
                }

            } catch (error) {
                CommandLogger.log('FAULT TOLERANT Arm/Disarm', false, error.message);
                NotificationManager.show(`Sistem hatası: ${error.message}`, 'error');
                console.error('Arm/Disarm error:', error);
            }
        });
    }

    static async controlRelayBrake(action) {
        // FAULT TOLERANT relay brake control
        if (action === 'on' && systemState.temperature.temp_monitoring_required && 
            (systemState.temperature.alarm || systemState.temperature.emergency_active)) {
            const sensorStatus = `S1:${systemState.temperature.sensor1_connected ? 'OK' : 'HATA'} S2:${systemState.temperature.sensor2_connected ? 'OK' : 'HATA'}`;
            NotificationManager.show(`FAULT TOLERANT: Sıcaklık alarmı nedeniyle röle aktif yapılamaz! [${sensorStatus}]`, 'warning');
            return;
        }
        
        RequestHandler.throttleRequest(async () => {
            try {
                console.log(`Attempting relay brake ${action} with FAULT TOLERANT mode`);
                
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
                    const sensorStatus = `S1:${systemState.temperature.sensor1_connected ? 'OK' : 'HATA'} S2:${systemState.temperature.sensor2_connected ? 'OK' : 'HATA'}`;
                    const tempMode = systemState.temperature.temp_monitoring_required ? 'MONITORED' : 'BYPASS';
                    CommandLogger.log(`FAULT TOLERANT Röle ${status}`, true, 
                        `[${sensorStatus}] [${tempMode}] - Reflektor:${systemState.reflector.count}`);
                    NotificationManager.show(`Röle sistem ${status}!`, systemState.relayBrakeActive ? 'success' : 'warning');
                }

            } catch (error) {
                CommandLogger.log('FAULT TOLERANT Röle kontrol', false, error.message);
                NotificationManager.show(`Röle kontrol hatası: ${error.message}`, 'error');
                console.error('Relay brake error:', error);
            }
        });
    }

    static async controlBrake(action) {
        RequestHandler.throttleRequest(async () => {
            try {
                console.log(`Attempting brake ${action} with FAULT TOLERANT mode`);
                
                const response = await RequestHandler.makeRequest(`${BACKEND_URL}/api/brake/${action}`, {
                    method: 'POST'
                });

                if (response.ok) {
                    systemState.brakeActive = (action === 'on');
                    
                    CommandLogger.log(`FAULT TOLERANT Software brake ${action === 'on' ? 'aktif' : 'pasif'}`, true, `Reflektor:${systemState.reflector.count}`);
                    NotificationManager.show(`Software brake ${action === 'on' ? 'aktif' : 'pasif'}!`, 'success');
                }

            } catch (error) {
                CommandLogger.log('FAULT TOLERANT Brake kontrol', false, error.message);
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

            // FAULT TOLERANT emergency stop logging with sensor status
            const sensorStatus = `S1:${systemState.temperature.sensor1_connected ? 'OK' : 'HATA'} S2:${systemState.temperature.sensor2_connected ? 'OK' : 'HATA'}`;
            const tempMode = systemState.temperature.temp_monitoring_required ? 'MONITORED' : 'BYPASS';
            CommandLogger.log('FAULT TOLERANT ACİL DURDURMA AKTİF', true, 
                `Tüm sistemler durduruldu - [${sensorStatus}] [${tempMode}] - Final Reflektor:${systemState.reflector.count}`);
            NotificationManager.show(`FAULT TOLERANT ACİL DURDURMA! Tüm sistemler durduruldu! Final reflektor sayımı: ${systemState.reflector.count}`, 'error', 6000);

        } catch (error) {
            CommandLogger.log('FAULT TOLERANT Acil durdurma', false, error.message);
            NotificationManager.show('Acil durdurma sinyali gönderilemedi!', 'warning');
            console.error('Emergency stop error:', error);
        }
    }
}

// UI Manager - ENHANCED WITH FAULT TOLERANT FEATURES
class UIManager {
    static updateMotorStatus(motorNum, running, speed) {
        const statusElement = document.getElementById(`motor${motorNum}-status`);
        const speedDisplayElement = document.getElementById(`motor${motorNum}-speed-display`);
        
        if (statusElement) {
            statusElement.textContent = running ? 'ON' : 'OFF';
            statusElement.className = running ? 'motor-status running' : 'motor-status off';
        }
        
        if (speedDisplayElement) {
            speedDisplayElement.textContent = `Hız: ${speed}%`;
        }
    }
    
    static updateMotorSpeedDisplay(motorNum, speed) {
        const speedDisplayElement = document.getElementById(`motor${motorNum}-speed-display`);
        if (speedDisplayElement) {
            speedDisplayElement.textContent = `Hız: ${speed}%`;
        }
    }
    
    static updateGroupSpeedDisplay(groupType, speed) {
        const sliderElement = document.getElementById(`${groupType}-slider`);
        const valueElement = document.getElementById(`${groupType}-speed`);
        
        if (sliderElement) {
            sliderElement.value = speed;
        }
        
        if (valueElement) {
            valueElement.textContent = `${speed}%`;
        }
    }
    
    static updateMotorCount() {
        const activeCount = Object.values(systemState.motorStates).filter(state => state).length;
        const motorCountElement = document.getElementById('motor-count');
        const activeMotorsElement = document.getElementById('active-motors');
        
        if (motorCountElement) {
            motorCountElement.textContent = `${activeCount}/6`;
        }
        
        if (activeMotorsElement) {
            activeMotorsElement.textContent = `${activeCount}/6`;
        }
    }
    
    static updateArmButton() {
        const armButton = document.getElementById('arm-button');
        if (armButton) {
            if (systemState.armed) {
                armButton.textContent = '🔓 SİSTEMİ DEVRE DIŞI BIRAK';
                armButton.className = 'arm-button armed';
            } else {
                armButton.textContent = '🔧 SİSTEMİ HAZIRLA';
                armButton.className = 'arm-button';
            }
        }
    }
    
    static updateRelayBrakeStatus() {
        const relayStatusElement = document.getElementById('relay-status');
        const relayBrakeStatusElement = document.getElementById('relay-brake-status');
        
        const status = systemState.relayBrakeActive ? 'Aktif' : 'Pasif';
        const color = systemState.relayBrakeActive ? '#00ff88' : '#ff4757';
        
        if (relayStatusElement) {
            relayStatusElement.textContent = status;
            relayStatusElement.style.color = color;
        }
        
        if (relayBrakeStatusElement) {
            relayBrakeStatusElement.textContent = status;
            relayBrakeStatusElement.style.color = color;
        }
    }
    
    static updateStatistics(stats) {
        const updates = {
            'total-commands': stats.commands || 0,
            'total-errors': stats.errors || 0,
            'uptime': Utils.formatUptime(stats.uptime_seconds || 0),
            'arduino-port': stats.port_info?.port || '--'
        };
        
        Object.entries(updates).forEach(([id, value]) => {
            const element = document.getElementById(id);
            if (element) {
                element.textContent = value;
            }
        });
    }
}

// NEW: FAULT TOLERANT control functions (for HTML button calls)
async function toggleTemperatureBypass() {
    const currentBypassStatus = systemState.temperature.allow_operation_without_temp;
    
    if (currentBypassStatus) {
        // Currently in bypass mode, try to disable it
        const success = await FaultTolerantTemperatureManager.disableTemperatureBypass();
        if (success) {
            // Update button text and styling
            const bypassBtn = document.getElementById('temp-bypass-btn');
            if (bypassBtn) {
                bypassBtn.textContent = '🌡️ SICAKLIK BYPASS AKTİF';
                bypassBtn.classList.remove('bypass-disabled');
                bypassBtn.classList.add('bypass-enabled');
            }
        }
    } else {
        // Currently in monitoring mode, enable bypass
        const success = await FaultTolerantTemperatureManager.enableTemperatureBypass();
        if (success) {
            // Update button text and styling
            const bypassBtn = document.getElementById('temp-bypass-btn');
            if (bypassBtn) {
                bypassBtn.textContent = '⚠️ SICAKLIK BYPASS PASİF';
                bypassBtn.classList.remove('bypass-enabled');
                bypassBtn.classList.add('bypass-disabled');
            }
        }
    }
}

async function turnOffBuzzer() {
    await FaultTolerantTemperatureManager.turnOffBuzzer();
}

async function showSensorDetails() {
    const modal = document.getElementById('sensor-detail-modal');
    if (modal) {
        // Update modal with fault tolerant sensor details
        const updates = {
            'modal-sensor1-temp': `${systemState.temperature.sensor1_temp.toFixed(1)}°C`,
            'modal-sensor2-temp': `${systemState.temperature.sensor2_temp.toFixed(1)}°C`,
            'modal-sensor1-max': `${systemState.temperature.max_sensor1.toFixed(1)}°C`,
            'modal-sensor2-max': `${systemState.temperature.max_sensor2.toFixed(1)}°C`,
            'modal-sensor1-connection': systemState.temperature.sensor1_connected ? 'Bağlı' : 'Bağlantısız',
            'modal-sensor2-connection': systemState.temperature.sensor2_connected ? 'Bağlı' : 'Bağlantısız',
            'modal-safety-temp': `${systemState.temperature.current.toFixed(1)}°C`,
            'modal-temp-diff': `${systemState.temperature.temperature_difference.toFixed(1)}°C`,
            'modal-temp-update-freq': `${systemState.temperature.update_frequency.toFixed(1)} Hz`,
            'modal-redundancy': Utils.getSensorStatusText(
                systemState.temperature.sensor1_connected, 
                systemState.temperature.sensor2_connected, 
                systemState.temperature.temp_monitoring_required, 
                systemState.temperature.allow_operation_without_temp
            ),
            // NEW: FAULT TOLERANT modal fields
            'modal-fault-tolerant-mode': systemState.temperature.fault_tolerant_mode ? 'Aktif' : 'Pasif',
            'modal-temp-monitoring-required': systemState.temperature.temp_monitoring_required ? 'Gerekli' : 'Devre Dışı',
            'modal-temp-bypass-allowed': systemState.temperature.allow_operation_without_temp ? 'İzinli' : 'Yasak',
            'modal-sensor1-fail-count': systemState.temperature.sensor1_fail_count,
            'modal-sensor2-fail-count': systemState.temperature.sensor2_fail_count,
            'modal-last-valid-temp1': `${systemState.temperature.last_valid_temp1.toFixed(1)}°C`,
            'modal-last-valid-temp2': `${systemState.temperature.last_valid_temp2.toFixed(1)}°C`,
            'modal-sensor-recovery-attempts': systemState.temperature.sensor_recovery_attempts
        };
        
        Object.entries(updates).forEach(([id, value]) => {
            const element = document.getElementById(id);
            if (element) {
                element.textContent = value;
            }
        });
        
        // Update correlation data
        const correlationUpdates = {
            'modal-correlation-count': systemState.reflector.count,
            'modal-correlation-speed': `${systemState.reflector.average_speed.toFixed(1)} ref/dk`,
            'modal-temp-speed-ratio': systemState.temperature.current > 0 ? 
                (systemState.reflector.average_speed / systemState.temperature.current).toFixed(1) : '0.0',
            'modal-system-load': ReflectorManager.calculateSystemLoad(systemState.temperature.current, systemState.reflector.average_speed)
        };
        
        Object.entries(correlationUpdates).forEach(([id, value]) => {
            const element = document.getElementById(id);
            if (element) {
                element.textContent = value;
            }
        });
        
        modal.style.display = 'block';
    }
}

async function hideSensorDetails() {
    const modal = document.getElementById('sensor-detail-modal');
    if (modal) {
        modal.style.display = 'none';
    }
}

// Keep all existing functions (startMotor, stopMotor, setMotorSpeed, etc.) - they will use the enhanced classes above
// These functions serve as the interface between HTML onclick handlers and the enhanced classes

async function startMotor(motorNum) {
    await MotorController.startMotor(motorNum);
}

async function stopMotor(motorNum) {
    await MotorController.stopMotor(motorNum);
}

async function setMotorSpeed(motorNum, speed) {
    await MotorController.setMotorSpeed(motorNum, speed);
}

async function startGroup(groupType) {
    await GroupController.startGroup(groupType);
}

async function stopGroup(groupType) {
    await GroupController.stopGroup(groupType);
}

function setGroupSpeed(groupType, speed) {
    GroupController.setGroupSpeed(groupType, speed);
}

function adjustGroupSpeed(groupType, change) {
    GroupController.adjustGroupSpeed(groupType, change);
}

async function toggleArm() {
    await SystemController.toggleArm();
}

async function controlRelayBrake(action) {
    await SystemController.controlRelayBrake(action);
}

async function controlBrake(action) {
    await SystemController.controlBrake(action);
}

async function emergencyStop() {
    await SystemController.emergencyStop();
}

async function testConnection() {
    await ConnectionManager.testConnection();
}

async function reconnectArduino() {
    await ConnectionManager.reconnectArduino();
}

// Keep all existing ReflectorManager functions
async function resetReflectorCounter() {
    await ReflectorManager.resetReflectorCounter();
}

async function calibrateReflectorSensor() {
    await ReflectorManager.calibrateReflectorSensor();
}

async function showReflectorDetails() {
    // Existing function - will work with enhanced ReflectorManager
    const modal = document.getElementById('reflector-detail-modal');
    if (modal) {
        // Update modal with current reflector data
        const updates = {
            'modal-reflector-count': systemState.reflector.count,
            'modal-reflector-voltage': `${systemState.reflector.voltage.toFixed(2)}V`,
            'modal-detection-state': systemState.reflector.state ? 'Algılandı' : 'Temiz',
            'modal-avg-speed': `${systemState.reflector.average_speed.toFixed(1)} ref/dk`,
            'modal-instant-speed': `${systemState.reflector.instant_speed.toFixed(1)} ref/dk`,
            'modal-max-speed': `${systemState.reflector.max_speed_recorded.toFixed(1)} ref/dk`,
            'modal-session-count': systemState.reflector.session_count,
            'modal-daily-count': systemState.reflector.daily_count,
            'modal-runtime': `${systemState.reflector.total_runtime.toFixed(1)} dakika`,
            'modal-detection-rate': `${systemState.reflector.detection_rate.toFixed(1)}/dk`,
            'modal-read-freq': `${systemState.reflector.read_frequency.toFixed(1)} Hz`,
            'modal-system-active': systemState.reflector.system_active ? 'Aktif' : 'Pasif'
        };
        
        Object.entries(updates).forEach(([id, value]) => {
            const element = document.getElementById(id);
            if (element) {
                element.textContent = value;
            }
        });
        
        modal.style.display = 'block';
    }
}

async function hideReflectorDetails() {
    const modal = document.getElementById('reflector-detail-modal');
    if (modal) {
        modal.style.display = 'none';
    }
}

function closeNotification() {
    NotificationManager.hide();
}

function toggleSpeedChart() {
    // Placeholder for speed chart toggle functionality
    NotificationManager.show('Hız grafiği özelliği yakında eklenecek!', 'info');
}

// Enhanced initialization with FAULT TOLERANT support
document.addEventListener('DOMContentLoaded', function() {
    console.log('SpectraLoop FAULT TOLERANT v3.7 initializing...');
    
    // Hide loading overlay
    const loadingOverlay = document.getElementById('loading-overlay');
    if (loadingOverlay) {
        setTimeout(() => {
            loadingOverlay.style.display = 'none';
        }, 1500);
    }
    
    // Initialize command logger
    CommandLogger.log('FAULT TOLERANT DUAL sensör + reflektor sistemi başlatılıyor...', true);
    
    // Start status polling with fault tolerant support
    setTimeout(() => {
        StatusManager.startStatusPolling();
        appState.isInitialized = true;
    }, 2000);
    
    // Initialize fault tolerant UI elements
    const faultTolerantModeIndicator = document.createElement('div');
    faultTolerantModeIndicator.id = 'fault-tolerant-mode-indicator';
    faultTolerantModeIndicator.className = 'fault-tolerant-mode-indicator';
    faultTolerantModeIndicator.style.display = 'none';
    
    const tempBypassIndicator = document.createElement('div');
    tempBypassIndicator.id = 'temp-bypass-indicator';
    tempBypassIndicator.className = 'temp-bypass-indicator';
    tempBypassIndicator.style.display = 'none';
    
    // Add indicators to header or appropriate location
    const header = document.querySelector('.header');
    if (header) {
        header.appendChild(faultTolerantModeIndicator);
        header.appendChild(tempBypassIndicator);
    }
    
    // Initialize fault tolerant CSS classes (if not already in CSS file)
    const faultTolerantStyles = document.createElement('style');
    faultTolerantStyles.textContent = `
        .fault-tolerant { 
            opacity: 0.7; 
            border-color: #ffc107 !important; 
        }
        .fault-tolerant-active { 
            border-color: rgba(255, 193, 7, 0.5) !important; 
            background: rgba(255, 193, 7, 0.1) !important; 
        }
        .bypass-active { 
            border-color: rgba(0, 212, 255, 0.5) !important; 
            background: rgba(0, 212, 255, 0.1) !important; 
        }
        .bypass { 
            color: #00d4ff !important; 
        }
        .fault-tolerant-mode-indicator { 
            display: inline-block; 
            background: rgba(255, 193, 7, 0.2);
            padding: 8px 15px;
            border-radius: 20px;
            font-size: 0.85rem;
            color: #ffc107;
            font-weight: bold;
            margin: 0 10px;
            border: 1px solid rgba(255, 193, 7, 0.3);
        }
        .temp-bypass-indicator {
            display: inline-block;
            background: rgba(0, 212, 255, 0.2);  
            padding: 8px 15px;
            border-radius: 20px;
            font-size: 0.85rem;
            color: #00d4ff;
            font-weight: bold;
            margin: 0 10px;
            border: 1px solid rgba(0, 212, 255, 0.3);
        }
        .fault-tolerant-notification {
            border-left-color: #ffc107 !important;
        }
        .bypass-enabled {
            background: linear-gradient(45deg, #00d4ff, #0099cc) !important;
        }
        .bypass-disabled {
            background: linear-gradient(45deg, #ff4757, #cc3647) !important;
        }
        .connection-dot.fault-tolerant {
            animation: fault-tolerant-pulse 2s infinite;
        }
        @keyframes fault-tolerant-pulse {
            0%, 100% { opacity: 1; background: #ffc107; }
            50% { opacity: 0.6; background: #ff8800; }
        }
        .temp-current.fault-tolerant::after {
            content: ' (FT)';
            font-size: 0.7em;
            color: #ffc107;
        }
        .temp-current.bypass::after {
            content: ' (BYPASS)';
            font-size: 0.7em;
            color: #00d4ff;
        }
    `;
    document.head.appendChild(faultTolerantStyles);
    
    console.log('SpectraLoop FAULT TOLERANT v3.7 initialized successfully!');
    console.log('Features: Dual temperature sensors with fault tolerance, Omron reflector counter, Arduino-Backend-Frontend connection resilience');
});

// Global error handler for unhandled promise rejections
window.addEventListener('unhandledrejection', function(event) {
    console.error('Unhandled promise rejection:', event.reason);
    CommandLogger.log('FAULT TOLERANT System hatası', false, event.reason?.message || 'Bilinmeyen hata');
    
    // In fault tolerant mode, try to continue operation
    if (appState.faultTolerantModeActive) {
        console.log('FAULT TOLERANT: Attempting to continue operation despite error');
        NotificationManager.show('FAULT TOLERANT: Sistem hatası tespit edildi ancak çalışmaya devam ediyor', 'warning', 5000);
    }
    
    event.preventDefault();
});

// Enhanced window beforeunload handler
window.addEventListener('beforeunload', function() {
    console.log('SpectraLoop FAULT TOLERANT shutting down...');
    StatusManager.stopStatusPolling();
    
    // Log final fault tolerant statistics
    const sensorStatus = `S1:${systemState.temperature.sensor1_connected ? 'OK' : 'HATA'} S2:${systemState.temperature.sensor2_connected ? 'OK' : 'HATA'}`;
    const tempMode = systemState.temperature.temp_monitoring_required ? 'MONITORED' : 'BYPASS';
    const ftMode = appState.faultTolerantModeActive ? 'FT_ACTIVE' : 'FT_INACTIVE';
    
    console.log(`FAULT TOLERANT Final Status - [${sensorStatus}] [${tempMode}] [${ftMode}] - Reflektor: ${systemState.reflector.count}`);
    console.log(`FAULT TOLERANT Final Stats - Temp Updates: ${appState.performanceStats.faultTolerantUpdatesCount}, Sensor Recoveries: ${appState.performanceStats.sensorRecoverySuccessCount}, Bypass Usage: ${appState.performanceStats.temperatureBypassUsageCount}`);
});

// NEW: Periodic fault tolerant health check
setInterval(function() {
    if (appState.isInitialized && appState.faultTolerantModeActive) {
        // Check if system is still responsive
        const now = Date.now();
        const lastUpdate = appState.performanceStats.lastTempUpdateTime;
        
        if (lastUpdate > 0 && (now - lastUpdate) > 30000) { // 30 seconds without update
            console.warn('FAULT TOLERANT: System may be unresponsive, attempting recovery...');
            
            // Try to restart status polling
            try {
                StatusManager.stopStatusPolling();
                setTimeout(() => {
                    StatusManager.startStatusPolling();
                    CommandLogger.log('FAULT TOLERANT system recovery attempted', true);
                }, 1000);
            } catch (error) {
                console.error('FAULT TOLERANT recovery failed:', error);
                CommandLogger.log('FAULT TOLERANT system recovery failed', false, error.message);
            }
        }
    }
}, 60000); // Check every minute

// NEW: FAULT TOLERANT mode status indicator updater
setInterval(function() {
    if (appState.isInitialized) {
        // Update fault tolerant mode indicators
        FaultTolerantTemperatureManager.updateFaultTolerantStatusIndicators();
        
        // Update system status text to include fault tolerant info
        const systemStatusEl = document.getElementById('system-status');
        if (systemStatusEl) {
            let statusText = systemState.armed ? 'Hazır' : 'Beklemede';
            
            if (appState.faultTolerantModeActive) {
                statusText += ' (FAULT TOLERANT)';
            }
            
            if (!systemState.temperature.temp_monitoring_required) {
                statusText += ' (TEMP BYPASS)';
            }
            
            systemStatusEl.textContent = statusText;
        }
    }
}, 5000); // Update every 5 seconds

console.log('SpectraLoop FAULT TOLERANT v3.7 Script loaded successfully!');
console.log('🛡️ FAULT TOLERANT Features Active:');
console.log('   - Dual temperature sensor fault tolerance (0, 1, or 2 sensors)');
console.log('   - Automatic sensor recovery attempts');
console.log('   - Temperature monitoring bypass capability');
console.log('   - Arduino-Backend-Frontend connection resilience');
console.log('   - Enhanced error handling and system recovery');
console.log('   - Ultra-fast reflector counting with fault tolerance');
console.log('   - Comprehensive system health monitoring');
console.log('   - Operation continuity even with sensor failures');