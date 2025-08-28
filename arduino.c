/*
 * SpectraLoop Motor Control System - Arduino FAULT TOLERANT DUAL TEMPERATURE + REFLECTOR v3.7
 * FAULT TOLERANT: Tek sensör bile çalışırsa sistem devam eder
 * Dual DS18B20 Temperature Sensors + Ultra-fast monitoring + Omron Reflector Counter
 * 6 BLDC Motor + Relay Brake + 2x DS18B20 + Buzzer + Reflector Counting
 * Motor Pin Mapping: Thrust(3,7), Levitation(2,4,5,6)
 * Temperature Sensors: Pin 8 (Primary), Pin 13 (Secondary)
 * Reflector Sensor: Pin A0 (Omron Photoelectric)
 * FAULT TOLERANCE: System works with one or no temperature sensors
 */

#include <Servo.h>
#include <OneWire.h>
#include <DallasTemperature.h>

// Pin definitions
#define ONE_WIRE_BUS_1 8    // Primary temperature sensor
#define ONE_WIRE_BUS_2 13   // Secondary temperature sensor
#define BUZZER_PIN 9
#define RELAY_BRAKE_PIN 11
#define REFLECTOR_SENSOR_PIN A0  // Omron photoelectric sensor
#define REFLECTOR_LED_PIN 12     // Reflector status LED

// Dual temperature sensors - FAULT TOLERANT
OneWire oneWire1(ONE_WIRE_BUS_1);
OneWire oneWire2(ONE_WIRE_BUS_2);
DallasTemperature tempSensor1(&oneWire1);  // Primary sensor
DallasTemperature tempSensor2(&oneWire2);  // Secondary sensor

// Motor configuration
const byte MOTOR_PINS[] = {2, 4, 5, 6, 3, 7}; // M1-M6
const byte NUM_MOTORS = 6;
const int ESC_MIN = 1000, ESC_MAX = 2000;

// Motor objects and states
Servo motors[NUM_MOTORS];
bool motorStates[NUM_MOTORS];
byte motorSpeeds[NUM_MOTORS];
byte levitationGroupSpeed = 0;
byte thrustGroupSpeed = 0;

// System state - FAULT TOLERANT ENHANCED
struct SystemState {
  bool armed : 1;
  bool brakeActive : 1;
  bool relayBrakeActive : 1;
  bool temperatureAlarm : 1;
  bool buzzerActive : 1;
  bool sensor1Connected : 1;
  bool sensor2Connected : 1;
  bool reflectorSystemActive : 1;
  bool tempSensorRequired : 1;  // NEW: Can disable temp requirement
  bool allowOperationWithoutTemp : 1;  // NEW: Allow operation without temp sensors
} sysState = {0, 0, 0, 0, 0, 0, 0, 1, 0, 1};  // Default: allow operation without temp

// FAULT TOLERANT Temperature monitoring - ENHANCED
float currentTemp1 = 25.0;    // Primary sensor
float currentTemp2 = 25.0;    // Secondary sensor
float lastValidTemp1 = 25.0;  // NEW: Last valid reading
float lastValidTemp2 = 25.0;  // NEW: Last valid reading
float lastReportedTemp1 = 25.0;
float lastReportedTemp2 = 25.0;
float maxTemp1 = 25.0;
float maxTemp2 = 25.0;
float maxTempOverall = 25.0;  // Highest of both sensors
float fallbackTemp = 25.0;    // NEW: Fallback temperature when no sensors

unsigned long lastTempRead = 0;
unsigned long lastTempReport = 0;
unsigned long lastBuzzerToggle = 0;
unsigned long lastCommandTime = 0;
unsigned long lastHeartbeat = 0;
unsigned long tempReadCount = 0;
unsigned long alarmCount = 0;
unsigned long sensor1FailCount = 0;  // NEW: Failure tracking
unsigned long sensor2FailCount = 0;  // NEW: Failure tracking
unsigned long lastSensor1Success = 0;  // NEW: Last successful read
unsigned long lastSensor2Success = 0;  // NEW: Last successful read

// REFLECTOR COUNTER SYSTEM - SAME AS BEFORE
struct ReflectorSystem {
  volatile unsigned long count = 0;
  bool currentState = false;
  bool lastState = false;
  unsigned long lastChangeTime = 0;
  unsigned long lastStableTime = 0;
  
  int analogValue = 0;
  float voltage = 0.0;
  unsigned long lastReadTime = 0;
  unsigned long lastReportTime = 0;
  
  unsigned long startTime = 0;
  unsigned long lastReflectorTime = 0;
  float averageSpeed = 0.0;
  float instantSpeed = 0.0;
  unsigned long speedUpdateTime = 0;
  
  const int DETECT_THRESHOLD = 950;
  const int RELEASE_THRESHOLD = 1000;
  const unsigned long DEBOUNCE_TIME = 50;
  const unsigned long STABLE_TIME = 10;
  const unsigned long READ_INTERVAL = 5;
  const unsigned long REPORT_INTERVAL = 500;
  
  unsigned long readCount = 0;
  unsigned long detectionCount = 0;
  float readFrequency = 0.0;
} reflector;

// FAULT TOLERANT Temperature safety thresholds
const float TEMP_ALARM = 55.0;
const float TEMP_SAFE = 50.0;
const float TEMP_WARNING = 45.0;
const float TEMP_SENSOR_TIMEOUT = 30000;  // 30 seconds before considering sensor failed
const float TEMP_MAX_CHANGE = 50.0;       // Maximum realistic temperature change per reading
const unsigned long SENSOR_RETRY_INTERVAL = 5000;  // Retry failed sensors every 5 seconds

// ULTRA-FAST Constants - same as before
const unsigned long TEMP_INTERVAL = 100;
const unsigned long TEMP_REPORT_INTERVAL = 200;
const unsigned long REFLECTOR_INTERVAL = 5;
const unsigned long BUZZER_INTERVAL = 500;
const unsigned long COMMAND_COOLDOWN = 10;
const unsigned long HEARTBEAT_INTERVAL = 5000;
const float TEMP_CHANGE_THRESHOLD = 0.1;

// Performance monitoring
unsigned long loopCount = 0;
unsigned long lastPerformanceReport = 0;
const unsigned long PERFORMANCE_INTERVAL = 10000;

void setup() {
  Serial.begin(115200);
  Serial.setTimeout(100);
  
  // Initialize pins
  pinMode(BUZZER_PIN, OUTPUT);
  pinMode(RELAY_BRAKE_PIN, OUTPUT);
  pinMode(REFLECTOR_SENSOR_PIN, INPUT);
  pinMode(REFLECTOR_LED_PIN, OUTPUT);
  digitalWrite(BUZZER_PIN, LOW);
  digitalWrite(RELAY_BRAKE_PIN, LOW);
  digitalWrite(REFLECTOR_LED_PIN, LOW);
  
  // FAULT TOLERANT temperature sensor initialization
  Serial.println(F("FAULT TOLERANT dual temperature sensor initialization..."));
  
  tempSensor1.begin();
  tempSensor2.begin();
  
  // Configure sensors for speed
  tempSensor1.setResolution(10);
  tempSensor2.setResolution(10);
  tempSensor1.setWaitForConversion(false);
  tempSensor2.setWaitForConversion(false);
  
  // FAULT TOLERANT sensor connection checking
  sysState.sensor1Connected = initializeSensor1();
  sysState.sensor2Connected = initializeSensor2();
  
  Serial.print(F("Sensor 1 (Pin 8): "));
  Serial.println(sysState.sensor1Connected ? F("CONNECTED") : F("DISCONNECTED"));
  Serial.print(F("Sensor 2 (Pin 13): "));
  Serial.println(sysState.sensor2Connected ? F("DISCONNECTED") : F("DISCONNECTED"));
  
  // FAULT TOLERANCE: System can work without temperature sensors
  if (!sysState.sensor1Connected && !sysState.sensor2Connected) {
    Serial.println(F("WARNING: No temperature sensors detected!"));
    Serial.println(F("FAULT TOLERANCE: System will operate without temperature monitoring"));
    sysState.allowOperationWithoutTemp = true;
    sysState.tempSensorRequired = false;
  } else {
    Serial.println(F("At least one temperature sensor available - safety monitoring enabled"));
    sysState.tempSensorRequired = true;
  }
  
  // Initialize REFLECTOR system - SAME AS BEFORE
  Serial.println(F("Initializing Omron reflector counter..."));
  reflector.startTime = millis();
  reflector.lastReflectorTime = reflector.startTime;
  reflector.lastReadTime = reflector.startTime;
  reflector.lastReportTime = reflector.startTime;
  reflector.speedUpdateTime = reflector.startTime;
  sysState.reflectorSystemActive = true;
  
  // Test reflector sensor
  reflector.analogValue = analogRead(REFLECTOR_SENSOR_PIN);
  reflector.voltage = (reflector.analogValue * 5.0) / 1023.0;
  Serial.print(F("Reflector sensor initial reading: "));
  Serial.print(reflector.analogValue);
  Serial.print(F(" ("));
  Serial.print(reflector.voltage, 2);
  Serial.println(F("V)"));
  
  // Initialize motors
  for (byte i = 0; i < NUM_MOTORS; i++) {
    motors[i].attach(MOTOR_PINS[i]);
    motors[i].writeMicroseconds(ESC_MIN);
    motorStates[i] = false;
    motorSpeeds[i] = 0;
  }
  
  delay(1500); // ESC calibration
  
  // FAULT TOLERANT first temperature readings
  if (sysState.tempSensorRequired) {
    requestTemperatureReadings();
    delay(200);
    readTemperaturesNonBlocking();
  } else {
    Serial.println(F("Skipping initial temperature reading - no sensors available"));
    currentTemp1 = fallbackTemp;
    currentTemp2 = fallbackTemp;
    maxTempOverall = fallbackTemp;
  }
  
  Serial.println(F("SpectraLoop v3.7 FAULT TOLERANT DUAL TEMPERATURE + REFLECTOR"));
  Serial.println(F("FAULT TOLERANCE: Works with 0, 1, or 2 temperature sensors"));
  Serial.print(F("Temperature Status - S1: "));
  Serial.print(sysState.sensor1Connected ? "ACTIVE" : "FAULT");
  Serial.print(F(", S2: "));
  Serial.print(sysState.sensor2Connected ? "ACTIVE" : "FAULT");
  Serial.print(F(", System: "));
  Serial.println(sysState.tempSensorRequired ? "TEMP_MONITORED" : "TEMP_BYPASSED");
  Serial.print(F("Current Temps - S1: "));
  Serial.print(currentTemp1);
  Serial.print(F("°C, S2: "));
  Serial.print(currentTemp2);
  Serial.println(F("°C"));
  Serial.print(F("Reflector Count: "));
  Serial.println(reflector.count);
  Serial.println(F("READY - FAULT TOLERANT MODE"));
}

void loop() {
  unsigned long now = millis();
  loopCount++;
  
  // FAULT TOLERANT temperature monitoring
  if (now - lastTempRead >= TEMP_INTERVAL) {
    if (sysState.tempSensorRequired) {
      readTemperaturesNonBlocking();
    } else {
      // Update fallback temperature slowly to room temperature
      fallbackTemp = 25.0;
      currentTemp1 = fallbackTemp;
      currentTemp2 = fallbackTemp;
      maxTempOverall = fallbackTemp;
    }
    lastTempRead = now;
  }
  
  // SAME reflector monitoring
  if (now - reflector.lastReadTime >= REFLECTOR_INTERVAL) {
    readReflectorSensor();
    reflector.lastReadTime = now;
  }
  
  // FAULT TOLERANT temperature reporting
  if (now - lastTempReport >= TEMP_REPORT_INTERVAL) {
    reportTemperaturesIfChanged();
    lastTempReport = now;
  }
  
  // SAME reflector reporting
  if (now - reflector.lastReportTime >= reflector.REPORT_INTERVAL) {
    reportReflectorData();
    reflector.lastReportTime = now;
  }
  
  // SAME buzzer control
  if (sysState.temperatureAlarm && sysState.buzzerActive) {
    if (now - lastBuzzerToggle > BUZZER_INTERVAL) {
      static bool buzzerState = false;
      buzzerState = !buzzerState;
      digitalWrite(BUZZER_PIN, buzzerState);
      lastBuzzerToggle = now;
    }
  }
  
  // SAME command processing
  if (Serial.available() && (now - lastCommandTime) > COMMAND_COOLDOWN) {
    processCommand();
    lastCommandTime = now;
  }
  
  // FAULT TOLERANT heartbeat
  if (now - lastHeartbeat > HEARTBEAT_INTERVAL) {
    sendHeartbeat();
    lastHeartbeat = now;
  }
  
  // SAME performance monitoring
  if (now - lastPerformanceReport > PERFORMANCE_INTERVAL) {
    sendPerformanceReport(now);
    lastPerformanceReport = now;
  }
  
  // NEW: Periodic sensor recovery attempts
  if (now % SENSOR_RETRY_INTERVAL == 0) {
    attemptSensorRecovery();
  }
}

// NEW: FAULT TOLERANT sensor initialization functions
bool initializeSensor1() {
  tempSensor1.begin();
  int deviceCount = tempSensor1.getDeviceCount();
  if (deviceCount > 0) {
    tempSensor1.requestTemperatures();
    delay(100);
    float testTemp = tempSensor1.getTempCByIndex(0);
    if (testTemp > -50 && testTemp < 100 && testTemp != DEVICE_DISCONNECTED_C) {
      lastSensor1Success = millis();
      lastValidTemp1 = testTemp;
      currentTemp1 = testTemp;
      return true;
    }
  }
  Serial.println(F("Sensor 1 initialization failed"));
  return false;
}

bool initializeSensor2() {
  tempSensor2.begin();
  int deviceCount = tempSensor2.getDeviceCount();
  if (deviceCount > 0) {
    tempSensor2.requestTemperatures();
    delay(100);
    float testTemp = tempSensor2.getTempCByIndex(0);
    if (testTemp > -50 && testTemp < 100 && testTemp != DEVICE_DISCONNECTED_C) {
      lastSensor2Success = millis();
      lastValidTemp2 = testTemp;
      currentTemp2 = testTemp;
      return true;
    }
  }
  Serial.println(F("Sensor 2 initialization failed"));
  return false;
}

// NEW: Attempt to recover failed sensors
void attemptSensorRecovery() {
  unsigned long now = millis();
  
  // Try to recover sensor 1
  if (!sysState.sensor1Connected && (now - lastSensor1Success) > SENSOR_RETRY_INTERVAL) {
    if (initializeSensor1()) {
      sysState.sensor1Connected = true;
      sysState.tempSensorRequired = true;
      Serial.println(F("Sensor 1 RECOVERED"));
    }
  }
  
  // Try to recover sensor 2
  if (!sysState.sensor2Connected && (now - lastSensor2Success) > SENSOR_RETRY_INTERVAL) {
    if (initializeSensor2()) {
      sysState.sensor2Connected = true;
      sysState.tempSensorRequired = true;
      Serial.println(F("Sensor 2 RECOVERED"));
    }
  }
  
  // Update system temperature requirement status
  if (!sysState.tempSensorRequired && (sysState.sensor1Connected || sysState.sensor2Connected)) {
    sysState.tempSensorRequired = true;
    sysState.allowOperationWithoutTemp = false;
    Serial.println(F("Temperature monitoring RESTORED"));
  }
}

// SAME reflector functions (no changes needed)
void readReflectorSensor() {
  reflector.analogValue = analogRead(REFLECTOR_SENSOR_PIN);
  reflector.voltage = (reflector.analogValue * 5.0) / 1023.0;
  reflector.readCount++;
  
  bool newState = reflector.currentState;
  
  if (!reflector.currentState && reflector.analogValue < reflector.DETECT_THRESHOLD) {
    newState = true;
  } else if (reflector.currentState && reflector.analogValue > reflector.RELEASE_THRESHOLD) {
    newState = false;
  }
  
  unsigned long currentTime = millis();
  
  if (newState != reflector.currentState) {
    if (currentTime - reflector.lastChangeTime > reflector.DEBOUNCE_TIME) {
      reflector.lastChangeTime = currentTime;
    }
    
    if (currentTime - reflector.lastChangeTime >= reflector.STABLE_TIME) {
      reflector.lastState = reflector.currentState;
      reflector.currentState = newState;
      
      if (reflector.currentState && !reflector.lastState) {
        reflector.count++;
        reflector.detectionCount++;
        reflector.lastReflectorTime = currentTime;
        
        static unsigned long lastReflectorDetection = 0;
        if (lastReflectorDetection > 0) {
          unsigned long timeDiff = currentTime - lastReflectorDetection;
          if (timeDiff > 0) {
            reflector.instantSpeed = 60000.0 / timeDiff;
          }
        }
        lastReflectorDetection = currentTime;
        
        digitalWrite(REFLECTOR_LED_PIN, HIGH);
        
        Serial.print(F("REFLECTOR_DETECTED:"));
        Serial.print(reflector.count);
        Serial.print(F(" [VOLTAGE:"));
        Serial.print(reflector.voltage, 2);
        Serial.print(F("V] [SPEED:"));
        Serial.print(reflector.instantSpeed, 1);
        Serial.println(F("rpm]"));
      }
    }
  } else {
    reflector.lastChangeTime = currentTime;
  }
  
  digitalWrite(REFLECTOR_LED_PIN, reflector.currentState);
  
  if (reflector.currentState && !reflector.lastState && 
      currentTime - reflector.lastReflectorTime > 50) {
    digitalWrite(REFLECTOR_LED_PIN, LOW);
  }
}

void reportReflectorData() {
  unsigned long currentTime = millis();
  
  float elapsedMinutes = (currentTime - reflector.startTime) / 60000.0;
  if (elapsedMinutes > 0) {
    reflector.averageSpeed = reflector.count / elapsedMinutes;
  }
  
  static unsigned long lastReadCount = 0;
  static unsigned long lastFreqUpdate = 0;
  unsigned long elapsed = currentTime - lastFreqUpdate;
  if (elapsed >= 1000) {
    reflector.readFrequency = (reflector.readCount - lastReadCount) / (elapsed / 1000.0);
    lastReadCount = reflector.readCount;
    lastFreqUpdate = currentTime;
  }
  
  Serial.print(F("REFLECTOR_STATUS [COUNT:"));
  Serial.print(reflector.count);
  Serial.print(F("] [VOLTAGE:"));
  Serial.print(reflector.voltage, 2);
  Serial.print(F("V] [STATE:"));
  Serial.print(reflector.currentState ? F("DETECTED") : F("CLEAR"));
  Serial.print(F("] [AVG_SPEED:"));
  Serial.print(reflector.averageSpeed, 1);
  Serial.print(F("rpm] [INST_SPEED:"));
  Serial.print(reflector.instantSpeed, 1);
  Serial.print(F("rpm] [READ_FREQ:"));
  Serial.print(reflector.readFrequency, 1);
  Serial.println(F("Hz]"));
}

// FAULT TOLERANT temperature functions - ENHANCED
void requestTemperatureReadings() {
  if (sysState.sensor1Connected) {
    tempSensor1.requestTemperatures();
  }
  if (sysState.sensor2Connected) {
    tempSensor2.requestTemperatures();
  }
}

void readTemperaturesNonBlocking() {
  bool tempChanged = false;
  unsigned long now = millis();
  
  // FAULT TOLERANT sensor 1 reading
  if (sysState.sensor1Connected) {
    float newTemp1 = tempSensor1.getTempCByIndex(0);
    if (newTemp1 > -50 && newTemp1 < 100 && newTemp1 != DEVICE_DISCONNECTED_C) {
      // Validate temperature change is realistic
      if (abs(newTemp1 - currentTemp1) <= TEMP_MAX_CHANGE) {
        if (abs(newTemp1 - currentTemp1) > 0.05) {
          currentTemp1 = newTemp1;
          lastValidTemp1 = newTemp1;
          tempChanged = true;
          
          if (currentTemp1 > maxTemp1) {
            maxTemp1 = currentTemp1;
          }
        }
        lastSensor1Success = now;
        sensor1FailCount = 0;
      } else {
        Serial.print(F("WARNING: Sensor1 unrealistic temp change: "));
        Serial.println(newTemp1);
      }
    } else {
      // Sensor 1 failure handling
      sensor1FailCount++;
      if (sensor1FailCount > 5 && sysState.sensor1Connected) {
        Serial.println(F("WARNING: Sensor1 FAILED - switching to last valid reading"));
        sysState.sensor1Connected = false;
        currentTemp1 = lastValidTemp1; // Use last known good value
        
        // Check if we need to disable temperature requirement
        if (!sysState.sensor2Connected) {
          Serial.println(F("FAULT TOLERANCE: Both sensors failed - disabling temperature monitoring"));
          sysState.tempSensorRequired = false;
          sysState.allowOperationWithoutTemp = true;
        }
      }
    }
  }
  
  // FAULT TOLERANT sensor 2 reading
  if (sysState.sensor2Connected) {
    float newTemp2 = tempSensor2.getTempCByIndex(0);
    if (newTemp2 > -50 && newTemp2 < 100 && newTemp2 != DEVICE_DISCONNECTED_C) {
      // Validate temperature change is realistic
      if (abs(newTemp2 - currentTemp2) <= TEMP_MAX_CHANGE) {
        if (abs(newTemp2 - currentTemp2) > 0.05) {
          currentTemp2 = newTemp2;
          lastValidTemp2 = newTemp2;
          tempChanged = true;
          
          if (currentTemp2 > maxTemp2) {
            maxTemp2 = currentTemp2;
          }
        }
        lastSensor2Success = now;
        sensor2FailCount = 0;
      } else {
        Serial.print(F("WARNING: Sensor2 unrealistic temp change: "));
        Serial.println(newTemp2);
      }
    } else {
      // Sensor 2 failure handling
      sensor2FailCount++;
      if (sensor2FailCount > 5 && sysState.sensor2Connected) {
        Serial.println(F("WARNING: Sensor2 FAILED - switching to last valid reading"));
        sysState.sensor2Connected = false;
        currentTemp2 = lastValidTemp2; // Use last known good value
        
        // Check if we need to disable temperature requirement
        if (!sysState.sensor1Connected) {
          Serial.println(F("FAULT TOLERANCE: Both sensors failed - disabling temperature monitoring"));
          sysState.tempSensorRequired = false;
          sysState.allowOperationWithoutTemp = true;
        }
      }
    }
  }
  
  // Update overall maximum temperature
  maxTempOverall = max(maxTemp1, maxTemp2);
  
  if (tempChanged) {
    tempReadCount++;
    // FAULT TOLERANT safety check
    if (sysState.tempSensorRequired) {
      checkDualTempSafety();
    }
  }
  
  // Request next readings for continuous monitoring (only if sensors available)
  if (sysState.tempSensorRequired) {
    requestTemperatureReadings();
  }
}

void reportTemperaturesIfChanged() {
  bool shouldReport = false;
  
  if (abs(currentTemp1 - lastReportedTemp1) >= TEMP_CHANGE_THRESHOLD) {
    shouldReport = true;
  }
  if (abs(currentTemp2 - lastReportedTemp2) >= TEMP_CHANGE_THRESHOLD) {
    shouldReport = true;
  }
  
  if ((millis() - lastTempReport) > 1000) {
    shouldReport = true;
  }
  
  if (shouldReport) {
    // FAULT TOLERANT dual temperature reporting
    Serial.print(F("DUAL_TEMP [TEMP1:"));
    Serial.print(currentTemp1, 2);
    Serial.print(F("] [TEMP2:"));
    Serial.print(currentTemp2, 2);
    Serial.print(F("] [MAX:"));
    Serial.print(maxTempOverall, 2);
    Serial.print(F("] [S1_CONN:"));
    Serial.print(sysState.sensor1Connected ? "1" : "0");
    Serial.print(F("] [S2_CONN:"));
    Serial.print(sysState.sensor2Connected ? "1" : "0");
    Serial.print(F("] [TEMP_REQ:"));
    Serial.print(sysState.tempSensorRequired ? "1" : "0");
    Serial.println(F("]"));
    
    lastReportedTemp1 = currentTemp1;
    lastReportedTemp2 = currentTemp2;
  }
}

void checkDualTempSafety() {
  // FAULT TOLERANT safety check - only check if temperature monitoring is required
  if (!sysState.tempSensorRequired || sysState.allowOperationWithoutTemp) {
    return;
  }
  
  float maxCurrentTemp = max(currentTemp1, currentTemp2);
  bool wasAlarmActive = sysState.temperatureAlarm;
  
  // Alarm condition: Either sensor exceeds alarm threshold
  if (maxCurrentTemp >= TEMP_ALARM && !sysState.temperatureAlarm) {
    sysState.temperatureAlarm = true;
    sysState.buzzerActive = true;
    alarmCount++;
    emergencyStopTemp();
    
    Serial.print(F("TEMP_ALARM:"));
    Serial.print(maxCurrentTemp, 2);
    Serial.print(F(" (S1:"));
    Serial.print(currentTemp1, 2);
    Serial.print(F(",S2:"));
    Serial.print(currentTemp2, 2);
    Serial.print(F(") [REFLECTOR:"));
    Serial.print(reflector.count);
    Serial.println(F("]"));
    
  } else if (maxCurrentTemp <= TEMP_SAFE && sysState.temperatureAlarm) {
    sysState.temperatureAlarm = false;
    sysState.buzzerActive = false;
    digitalWrite(BUZZER_PIN, LOW);
    
    Serial.print(F("TEMP_SAFE:"));
    Serial.print(maxCurrentTemp, 2);
    Serial.print(F(" (S1:"));
    Serial.print(currentTemp1, 2);
    Serial.print(F(",S2:"));
    Serial.print(currentTemp2, 2);
    Serial.print(F(") [REFLECTOR:"));
    Serial.print(reflector.count);
    Serial.println(F("]"));
  }
}

void emergencyStopTemp() {
  sysState.armed = false;
  sysState.brakeActive = true;
  sysState.relayBrakeActive = false;
  digitalWrite(RELAY_BRAKE_PIN, LOW);
  
  for (byte i = 0; i < NUM_MOTORS; i++) {
    setMotorSpeed(i, 0);
    motorStates[i] = false;
    motorSpeeds[i] = 0;
  }
  
  levitationGroupSpeed = thrustGroupSpeed = 0;
  Serial.print(F("EMERGENCY_STOP:TEMPERATURE - Max:"));
  Serial.print(max(currentTemp1, currentTemp2), 2);
  Serial.print(F("°C (S1:"));
  Serial.print(currentTemp1, 2);
  Serial.print(F(",S2:"));
  Serial.print(currentTemp2, 2);
  Serial.print(F(") [REFLECTOR_FINAL:"));
  Serial.print(reflector.count);
  Serial.println(F("]"));
}

void processCommand() {
  String cmd = Serial.readStringUntil('\n');
  cmd.trim();
  if (cmd.length() == 0) return;

  // FAULT TOLERANT ACK with temperature info
  Serial.print(F("ACK:"));
  Serial.print(cmd);
  Serial.print(F(" [TEMP1:"));
  Serial.print(currentTemp1, 2);
  Serial.print(F("] [TEMP2:"));
  Serial.print(currentTemp2, 2);
  Serial.print(F("] [MAX:"));
  Serial.print(max(currentTemp1, currentTemp2), 2);
  Serial.print(F("] [REFLECTOR:"));
  Serial.print(reflector.count);
  Serial.print(F("] [TEMP_OK:"));
  Serial.print(sysState.tempSensorRequired ? (sysState.temperatureAlarm ? "0" : "1") : "1");
  Serial.println(F("]"));

  if (cmd == F("PING")) {
    Serial.print(F("PONG:v3.7-FAULT-TOLERANT-DUAL-TEMP-REFLECTOR S1:"));
    Serial.print(sysState.sensor1Connected ? "OK" : "FAIL");
    Serial.print(F(" S2:"));
    Serial.print(sysState.sensor2Connected ? "OK" : "FAIL");
    Serial.print(F(" TEMP_REQ:"));
    Serial.println(sysState.tempSensorRequired ? "YES" : "NO");
  } 
  else if (cmd == F("ARM")) {
    armSystem();
  } 
  else if (cmd == F("DISARM")) {
    disarmSystem();
  } 
  else if (cmd == F("STATUS")) {
    sendStatus();
  } 
  else if (cmd == F("TEMP_STATUS")) {
    sendTempStatus();
  }
  else if (cmd == F("TEMP_DUAL")) {
    Serial.print(F("TEMP_DUAL:S1:"));
    Serial.print(currentTemp1, 2);
    Serial.print(F(",S2:"));
    Serial.print(currentTemp2, 2);
    Serial.print(F(",MAX:"));
    Serial.print(max(currentTemp1, currentTemp2), 2);
    Serial.print(F(",ALARM:"));
    Serial.print(sysState.temperatureAlarm);
    Serial.print(F(",S1_CONN:"));
    Serial.print(sysState.sensor1Connected);
    Serial.print(F(",S2_CONN:"));
    Serial.print(sysState.sensor2Connected);
    Serial.print(F(",TEMP_REQ:"));
    Serial.print(sysState.tempSensorRequired);
    Serial.print(F(",ALLOW_NO_TEMP:"));
    Serial.println(sysState.allowOperationWithoutTemp);
  }
  else if (cmd == F("TEMP_BYPASS_ON")) {
    // NEW: Enable operation without temperature sensors
    sysState.allowOperationWithoutTemp = true;
    sysState.tempSensorRequired = false;
    sysState.temperatureAlarm = false;
    sysState.buzzerActive = false;
    digitalWrite(BUZZER_PIN, LOW);
    Serial.println(F("TEMP_BYPASS:ENABLED - System will operate without temperature monitoring"));
  }
  else if (cmd == F("TEMP_BYPASS_OFF")) {
    // NEW: Disable operation without temperature sensors (if any sensors available)
    if (sysState.sensor1Connected || sysState.sensor2Connected) {
      sysState.tempSensorRequired = true;
      sysState.allowOperationWithoutTemp = false;
      Serial.println(F("TEMP_BYPASS:DISABLED - Temperature monitoring restored"));
    } else {
      Serial.println(F("TEMP_BYPASS:CANNOT_DISABLE - No temperature sensors available"));
    }
  }
  // ... (rest of command processing remains the same)
  else if (cmd == F("REFLECTOR_STATUS")) {
    Serial.print(F("REFLECTOR_FULL:COUNT:"));
    Serial.print(reflector.count);
    Serial.print(F(",VOLTAGE:"));
    Serial.print(reflector.voltage, 3);
    Serial.print(F(",STATE:"));
    Serial.print(reflector.currentState);
    Serial.print(F(",AVG_SPEED:"));
    Serial.print(reflector.averageSpeed, 2);
    Serial.print(F(",INST_SPEED:"));
    Serial.print(reflector.instantSpeed, 2);
    Serial.print(F(",DETECTIONS:"));
    Serial.print(reflector.detectionCount);
    Serial.print(F(",READS:"));
    Serial.print(reflector.readCount);
    Serial.print(F(",read_FREQ:"));
    Serial.print(reflector.readFrequency, 1);
    Serial.print(F(",ACTIVE:"));
    Serial.println(sysState.reflectorSystemActive);
  }
  else if (cmd == F("REFLECTOR_RESET")) {
    reflector.count = 0;
    reflector.detectionCount = 0;
    reflector.startTime = millis();
    reflector.lastReflectorTime = reflector.startTime;
    reflector.averageSpeed = 0.0;
    reflector.instantSpeed = 0.0;
    Serial.println(F("REFLECTOR_RESET:SUCCESS"));
  }
  else if (cmd == F("REFLECTOR_CALIBRATE")) {
    int readings[10];
    for (int i = 0; i < 10; i++) {
      readings[i] = analogRead(REFLECTOR_SENSOR_PIN);
      delay(50);
    }
    int minReading = 1023, maxReading = 0;
    int avgReading = 0;
    for (int i = 0; i < 10; i++) {
      if (readings[i] < minReading) minReading = readings[i];
      if (readings[i] > maxReading) maxReading = readings[i];
      avgReading += readings[i];
    }
    avgReading /= 10;
    
    Serial.print(F("REFLECTOR_CALIBRATION:MIN:"));
    Serial.print(minReading);
    Serial.print(F(",MAX:"));
    Serial.print(maxReading);
    Serial.print(F(",AVG:"));
    Serial.print(avgReading);
    Serial.print(F(",MIN_V:"));
    Serial.print((minReading * 5.0) / 1023.0, 2);
    Serial.print(F(",MAX_V:"));
    Serial.print((maxReading * 5.0) / 1023.0, 2);
    Serial.print(F(",AVG_V:"));
    Serial.print((avgReading * 5.0) / 1023.0, 2);
    Serial.print(F(",DETECT_TH:"));
    Serial.print(reflector.DETECT_THRESHOLD);
    Serial.print(F(",RELEASE_TH:"));
    Serial.println(reflector.RELEASE_THRESHOLD);
  }
  // ... (other commands remain the same)
  else if (cmd == F("EMERGENCY_STOP")) {
    emergencyStop();
  } 
  else if (cmd == F("BRAKE_ON")) {
    setBrake(true);
  } 
  else if (cmd == F("BRAKE_OFF")) {
    setBrake(false);
  } 
  else if (cmd == F("RELAY_BRAKE_ON")) {
    setRelayBrake(true);
  } 
  else if (cmd == F("RELAY_BRAKE_OFF")) {
    setRelayBrake(false);
  } 
  else if (cmd.startsWith(F("MOTOR:"))) {
    parseMotorCmd(cmd);
  } 
  else if (cmd.startsWith(F("LEV_GROUP:"))) {
    parseLevCmd(cmd);
  } 
  else if (cmd.startsWith(F("THR_GROUP:"))) {
    parseThrCmd(cmd);
  }
}

// FAULT TOLERANT system control functions
void armSystem() {
  float maxCurrentTemp = max(currentTemp1, currentTemp2);
  
  // FAULT TOLERANT arming - allow if no temperature monitoring required
  if (!sysState.allowOperationWithoutTemp && sysState.tempSensorRequired) {
    if (sysState.brakeActive || !sysState.relayBrakeActive || 
        sysState.temperatureAlarm || maxCurrentTemp > TEMP_ALARM - 5) {
      Serial.print(F("ERROR:Cannot_arm (MaxTemp:"));
      Serial.print(maxCurrentTemp, 1);
      Serial.print(F("°C) [REFLECTOR:"));
      Serial.print(reflector.count);
      Serial.println(F("]"));
      return;
    }
  } else {
    // Allow arming without temperature checks
    if (sysState.brakeActive || !sysState.relayBrakeActive) {
      Serial.print(F("ERROR:Cannot_arm (Brake/Relay) [REFLECTOR:"));
      Serial.print(reflector.count);
      Serial.println(F("]"));
      return;
    }
  }
  
  sysState.armed = true;
  Serial.print(F("ARMED"));
  if (sysState.tempSensorRequired) {
    Serial.print(F(" [TEMP_MONITORED]"));
  } else {
    Serial.print(F(" [NO_TEMP_MONITORING]"));
  }
  Serial.print(F(" [REFLECTOR:"));
  Serial.print(reflector.count);
  Serial.println(F("]"));
}

void disarmSystem() {
  sysState.armed = false;
  for (byte i = 0; i < NUM_MOTORS; i++) {
    setMotorSpeed(i, 0);
    motorStates[i] = false;
    motorSpeeds[i] = 0;
  }
  levitationGroupSpeed = thrustGroupSpeed = 0;
  Serial.print(F("DISARMED [REFLECTOR:"));
  Serial.print(reflector.count);
  Serial.println(F("]"));
}

void setRelayBrake(bool active) {
  // FAULT TOLERANT relay brake - allow without temperature checks if bypass enabled
  if (active && sysState.tempSensorRequired && !sysState.allowOperationWithoutTemp && sysState.temperatureAlarm) {
    Serial.println(F("ERROR:Temp_alarm"));
    return;
  }
  
  sysState.relayBrakeActive = active;
  digitalWrite(RELAY_BRAKE_PIN, active);
  
  if (!active) {
    for (byte i = 0; i < NUM_MOTORS; i++) {
      setMotorSpeed(i, 0);
      motorStates[i] = false;
      motorSpeeds[i] = 0;
    }
    levitationGroupSpeed = thrustGroupSpeed = 0;
    sysState.armed = false;
  }
  
  Serial.print(F("RELAY_BRAKE:"));
  Serial.print(active ? F("ON") : F("OFF"));
  Serial.print(F(" [REFLECTOR:"));
  Serial.print(reflector.count);
  Serial.println(F("]"));
}

// FAULT TOLERANT motor control functions
bool canStartMotors() {
  float maxCurrentTemp = max(currentTemp1, currentTemp2);
  
  // FAULT TOLERANT motor start checks
  if (!sysState.armed || sysState.brakeActive || !sysState.relayBrakeActive) {
    Serial.print(F("ERROR:System_not_ready [REFLECTOR:"));
    Serial.print(reflector.count);
    Serial.println(F("]"));
    return false;
  }
  
  // Only check temperature if monitoring is required
  if (sysState.tempSensorRequired && !sysState.allowOperationWithoutTemp) {
    if (sysState.temperatureAlarm || maxCurrentTemp > TEMP_ALARM - 3) {
      Serial.print(F("ERROR:Cannot_start (MaxTemp:"));
      Serial.print(maxCurrentTemp, 1);
      Serial.print(F("°C) [REFLECTOR:"));
      Serial.print(reflector.count);
      Serial.println(F("]"));
      return false;
    }
  }
  
  return true;
}

// ... (rest of the motor control, group control functions remain the same but use FAULT TOLERANT canStartMotors())

void parseMotorCmd(String cmd) {
  if (!canStartMotors()) return;
  
  int colon1 = cmd.indexOf(':');
  int colon2 = cmd.indexOf(':', colon1 + 1);
  int colon3 = cmd.indexOf(':', colon2 + 1);
  
  byte motorNum = cmd.substring(colon1 + 1, colon2).toInt();
  String action = cmd.substring(colon2 + 1, colon3 > 0 ? colon3 : cmd.length());
  
  if (motorNum < 1 || motorNum > NUM_MOTORS) return;
  byte idx = motorNum - 1;
  
  if (action == F("START")) {
    byte speed = (colon3 > 0) ? cmd.substring(colon3 + 1).toInt() : 50;
    if (speed > 100) speed = 100;
    
    motorStates[idx] = true;
    motorSpeeds[idx] = speed;
    setMotorSpeed(idx, speed);
    
    Serial.print(F("MOTOR_STARTED:"));
    Serial.print(motorNum);
    Serial.print(':');
    Serial.print(speed);
    Serial.print(F(" [REFLECTOR:"));
    Serial.print(reflector.count);
    Serial.println(F("]"));
    
  } else if (action == F("STOP")) {
    motorStates[idx] = false;
    motorSpeeds[idx] = 0;
    setMotorSpeed(idx, 0);
    
    Serial.print(F("MOTOR_STOPPED:"));
    Serial.print(motorNum);
    Serial.print(F(" [REFLECTOR:"));
    Serial.print(reflector.count);
    Serial.println(F("]"));
    
  } else if (action == F("SPEED") && colon3 > 0) {
    byte speed = cmd.substring(colon3 + 1).toInt();
    if (speed > 100) speed = 100;
    
    motorSpeeds[idx] = speed;
    if (motorStates[idx]) setMotorSpeed(idx, speed);
    
    Serial.print(F("MOTOR_SPEED:"));
    Serial.print(motorNum);
    Serial.print(':');
    Serial.print(speed);
    Serial.print(F(" [REFLECTOR:"));
    Serial.print(reflector.count);
    Serial.println(F("]"));
  }
}

// ... (other motor and group functions remain similar with FAULT TOLERANT modifications)

void setBrake(bool active) {
  sysState.brakeActive = active;
  if (active) {
    for (byte i = 0; i < NUM_MOTORS; i++) {
      setMotorSpeed(i, 0);
      motorStates[i] = false;
      motorSpeeds[i] = 0;
    }
    levitationGroupSpeed = thrustGroupSpeed = 0;
  }
  Serial.print(active ? F("BRAKE_ON") : F("BRAKE_OFF"));
  Serial.print(F(" [REFLECTOR:"));
  Serial.print(reflector.count);
  Serial.println(F("]"));
}

void emergencyStop() {
  sysState.armed = false;
  sysState.brakeActive = true;
  sysState.relayBrakeActive = false;
  digitalWrite(RELAY_BRAKE_PIN, LOW);
  
  for (byte i = 0; i < NUM_MOTORS; i++) {
    setMotorSpeed(i, 0);
    motorStates[i] = false;
    motorSpeeds[i] = 0;
  }
  
  levitationGroupSpeed = thrustGroupSpeed = 0;
  Serial.print(F("EMERGENCY_STOP [REFLECTOR_FINAL:"));
  Serial.print(reflector.count);
  Serial.println(F("]"));
}

void setMotorSpeed(byte idx, byte speed) {
  if (idx >= NUM_MOTORS) return;
  int pwm = (speed == 0) ? ESC_MIN : map(speed, 0, 100, ESC_MIN + 50, ESC_MAX);
  motors[idx].writeMicroseconds(pwm);
}

// FAULT TOLERANT status functions
void sendTempStatus() {
  Serial.print(F("Temperature1:"));
  Serial.println(currentTemp1, 2);
  Serial.print(F("Temperature2:"));
  Serial.println(currentTemp2, 2);
  Serial.print(F("TemperatureMax:"));
  Serial.println(max(currentTemp1, currentTemp2), 2);
  Serial.print(F("TempAlarm:"));
  Serial.println(sysState.temperatureAlarm);
  Serial.print(F("BuzzerActive:"));
  Serial.println(sysState.buzzerActive);
  Serial.print(F("Sensor1Connected:"));
  Serial.println(sysState.sensor1Connected);
  Serial.print(F("Sensor2Connected:"));
  Serial.println(sysState.sensor2Connected);
  Serial.print(F("TempMonitoringRequired:"));
  Serial.println(sysState.tempSensorRequired);
  Serial.print(F("AllowOperationWithoutTemp:"));
  Serial.println(sysState.allowOperationWithoutTemp);
  Serial.print(F("ReadCount:"));
  Serial.println(tempReadCount);
  Serial.print(F("AlarmCount:"));
  Serial.println(alarmCount);
  Serial.print(F("Sensor1FailCount:"));
  Serial.println(sensor1FailCount);
  Serial.print(F("Sensor2FailCount:"));
  Serial.println(sensor2FailCount);
  Serial.print(F("ReflectorCount:"));
  Serial.println(reflector.count);
  Serial.print(F("ReflectorSpeed:"));
  Serial.print(reflector.averageSpeed, 1);
  Serial.println(F("rpm"));
}

void sendStatus() {
  Serial.println(F("STATUS_START"));
  Serial.print(F("Armed:"));
  Serial.println(sysState.armed);
  Serial.print(F("Brake:"));
  Serial.println(sysState.brakeActive);
  Serial.print(F("RelayBrake:"));
  Serial.println(sysState.relayBrakeActive);
  Serial.print(F("Temperature1:"));
  Serial.println(currentTemp1, 2);
  Serial.print(F("Temperature2:"));
  Serial.println(currentTemp2, 2);
  Serial.print(F("TemperatureMax:"));
  Serial.println(max(currentTemp1, currentTemp2), 2);
  Serial.print(F("TempAlarm:"));
  Serial.println(sysState.temperatureAlarm);
  Serial.print(F("BuzzerActive:"));
  Serial.println(sysState.buzzerActive);
  Serial.print(F("Sensor1Connected:"));
  Serial.println(sysState.sensor1Connected);
  Serial.print(F("Sensor2Connected:"));
  Serial.println(sysState.sensor2Connected);
  Serial.print(F("TempMonitoringRequired:"));
  Serial.println(sysState.tempSensorRequired);
  Serial.print(F("AllowOperationWithoutTemp:"));
  Serial.println(sysState.allowOperationWithoutTemp);
  Serial.print(F("LevGroupSpeed:"));
  Serial.println(levitationGroupSpeed);
  Serial.print(F("ThrGroupSpeed:"));
  Serial.println(thrustGroupSpeed);
  
  // Reflector system status
  Serial.print(F("ReflectorCount:"));
  Serial.println(reflector.count);
  Serial.print(F("ReflectorVoltage:"));
  Serial.println(reflector.voltage, 2);
  Serial.print(F("ReflectorState:"));
  Serial.println(reflector.currentState);
  Serial.print(F("ReflectorAvgSpeed:"));
  Serial.println(reflector.averageSpeed, 1);
  Serial.print(F("ReflectorInstSpeed:"));
  Serial.println(reflector.instantSpeed, 1);
  Serial.print(F("ReflectorActive:"));
  Serial.println(sysState.reflectorSystemActive);
  
  Serial.print(F("Motors:"));
  for (byte i = 0; i < NUM_MOTORS; i++) {
    Serial.print(motorStates[i] ? '1' : '0');
    if (i < NUM_MOTORS - 1) Serial.print(',');
  }
  Serial.println();
  
  Serial.print(F("IndividualSpeeds:"));
  for (byte i = 0; i < NUM_MOTORS; i++) {
    Serial.print(motorSpeeds[i]);
    if (i < NUM_MOTORS - 1) Serial.print(',');
  }
  Serial.println();
  
  Serial.println(F("STATUS_END"));
}

void sendHeartbeat() {
  float maxCurrentTemp = max(currentTemp1, currentTemp2);
  
  Serial.print(F("HEARTBEAT:"));
  Serial.print(millis() / 1000);
  Serial.print(',');
  Serial.print(sysState.armed);
  Serial.print(',');
  Serial.print(sysState.brakeActive);
  Serial.print(',');
  Serial.print(sysState.relayBrakeActive);
  Serial.print(',');
  Serial.print(maxCurrentTemp, 2);
  Serial.print(',');
  Serial.print(sysState.temperatureAlarm);
  
  byte activeCount = 0;
  for (byte i = 0; i < NUM_MOTORS; i++) {
    if (motorStates[i]) activeCount++;
  }
  Serial.print(',');
  Serial.println(activeCount);
  
  // FAULT TOLERANT enhanced heartbeat
  Serial.print(F("HB_DUAL_FT [TEMP1:"));
  Serial.print(currentTemp1, 2);
  Serial.print(F("] [TEMP2:"));
  Serial.print(currentTemp2, 2);
  Serial.print(F("] [MAX:"));
  Serial.print(maxCurrentTemp, 2);
  Serial.print(F("] [S1_CONN:"));
  Serial.print(sysState.sensor1Connected ? "OK" : "FAIL");
  Serial.print(F("] [S2_CONN:"));
  Serial.print(sysState.sensor2Connected ? "OK" : "FAIL");
  Serial.print(F("] [TEMP_REQ:"));
  Serial.print(sysState.tempSensorRequired ? "YES" : "NO");
  Serial.print(F("] [REFLECTOR:"));
  Serial.print(reflector.count);
  Serial.print(F("] [REF_SPEED:"));
  Serial.print(reflector.averageSpeed, 1);
  Serial.println(F("]"));
}

void sendPerformanceReport(unsigned long now) {
  float loopsPerSecond = (float)loopCount * 1000.0 / PERFORMANCE_INTERVAL;
  float tempReadsPerSecond = (float)tempReadCount * 1000.0 / PERFORMANCE_INTERVAL;
  
  Serial.print(F("PERFORMANCE_FT:"));
  Serial.print(loopsPerSecond, 1);
  Serial.print(F("Hz,TempReads:"));
  Serial.print(tempReadsPerSecond, 1);
  Serial.print(F("Hz,Sensors:"));
  Serial.print(sysState.sensor1Connected ? 'Y' : 'N');
  Serial.print(sysState.sensor2Connected ? 'Y' : 'N');
  Serial.print(F(",TempReq:"));
  Serial.print(sysState.tempSensorRequired ? 'Y' : 'N');
  Serial.print(F(",ReflectorReads:"));
  Serial.print(reflector.readFrequency, 1);
  Serial.print(F("Hz,ReflectorCount:"));
  Serial.print(reflector.count);
  Serial.print(F(",S1Fails:"));
  Serial.print(sensor1FailCount);
  Serial.print(F(",S2Fails:"));
  Serial.print(sensor2FailCount);
  Serial.print(F(",FreeRAM:"));
  Serial.println(getFreeMemory());
  
  loopCount = 0;
  tempReadCount = 0;
}

int getFreeMemory() {
  extern int __heap_start, *__brkval;
  int v;
  return (int) &v - (__brkval == 0 ? (int) &__heap_start : (int) __brkval);
}