/*
 * SpectraLoop Motor Control System - Arduino DUAL TEMPERATURE + REFLECTOR COUNTER v3.6
 * DUAL DS18B20 Temperature Sensors + Ultra-fast monitoring + Omron Reflector Counter
 * 6 BLDC Motor + Relay Brake + 2x DS18B20 + Buzzer + Reflector Counting
 * Motor Pin Mapping: Thrust(3,7), Levitation(2,4,5,6)
 * Temperature Sensors: Pin 8 (Primary), Pin 13 (Secondary)
 * Reflector Sensor: Pin A0 (Omron Photoelectric)
 * ULTRA-FAST: 100ms temp readings + 5ms reflector readings + dual sensor monitoring
 */

#include <Servo.h>
#include <OneWire.h>
#include <DallasTemperature.h>

// Pin definitions
#define ONE_WIRE_BUS_1 8    // Primary temperature sensor
#define ONE_WIRE_BUS_2 13   // Secondary temperature sensor
#define BUZZER_PIN 9
#define RELAY_BRAKE_PIN 11
#define REFLECTOR_SENSOR_PIN A0  // NEW: Omron photoelectric sensor
#define REFLECTOR_LED_PIN 12     // NEW: Reflector status LED

// Dual temperature sensors
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

// System state (packed into bytes)
struct SystemState {
  bool armed : 1;
  bool brakeActive : 1;
  bool relayBrakeActive : 1;
  bool temperatureAlarm : 1;
  bool buzzerActive : 1;
  bool sensor1Connected : 1;
  bool sensor2Connected : 1;
  bool reflectorSystemActive : 1;  // NEW: Reflector system status
} sysState = {0};

// DUAL Temperature monitoring - ENHANCED
float currentTemp1 = 25.0;    // Primary sensor
float currentTemp2 = 25.0;    // Secondary sensor
float lastReportedTemp1 = 25.0;
float lastReportedTemp2 = 25.0;
float maxTemp1 = 25.0;
float maxTemp2 = 25.0;
float maxTempOverall = 25.0;  // Highest of both sensors

unsigned long lastTempRead = 0;
unsigned long lastTempReport = 0;
unsigned long lastBuzzerToggle = 0;
unsigned long lastCommandTime = 0;
unsigned long lastHeartbeat = 0;
unsigned long tempReadCount = 0;
unsigned long alarmCount = 0;

// REFLECTOR COUNTER SYSTEM - NEW COMPLETE SECTION
struct ReflectorSystem {
  // Counter variables
  volatile unsigned long count = 0;
  bool currentState = false;           // false = no reflector, true = reflector detected
  bool lastState = false;
  unsigned long lastChangeTime = 0;
  unsigned long lastStableTime = 0;
  
  // Measurement variables
  int analogValue = 0;
  float voltage = 0.0;
  unsigned long lastReadTime = 0;
  unsigned long lastReportTime = 0;
  
  // Statistics
  unsigned long startTime = 0;
  unsigned long lastReflectorTime = 0;
  float averageSpeed = 0.0;        // reflectors per minute
  float instantSpeed = 0.0;        // current speed
  unsigned long speedUpdateTime = 0;
  
  // Configuration
  const int DETECT_THRESHOLD = 950;     // 4.64V below = reflector detected (1023 = 5V)
  const int RELEASE_THRESHOLD = 1000;   // 4.89V above = no reflector
  const unsigned long DEBOUNCE_TIME = 50;      // 50ms debounce
  const unsigned long STABLE_TIME = 10;        // 10ms stable reading
  const unsigned long READ_INTERVAL = 5;       // 5ms reading interval
  const unsigned long REPORT_INTERVAL = 500;   // 500ms report interval
  
  // Performance tracking
  unsigned long readCount = 0;
  unsigned long detectionCount = 0;
  float readFrequency = 0.0;
} reflector;

// Temperature safety thresholds
const float TEMP_ALARM = 55.0;
const float TEMP_SAFE = 50.0;
const float TEMP_WARNING = 45.0;

// ULTRA-FAST Constants - DUAL SENSOR + REFLECTOR OPTIMIZED
const unsigned long TEMP_INTERVAL = 100;        // 100ms - read both temp sensors
const unsigned long TEMP_REPORT_INTERVAL = 200; // Report every 200ms
const unsigned long REFLECTOR_INTERVAL = 5;     // 5ms - ultra fast reflector reading
const unsigned long BUZZER_INTERVAL = 500;
const unsigned long COMMAND_COOLDOWN = 10;
const unsigned long HEARTBEAT_INTERVAL = 5000;  // 5s heartbeat
const float TEMP_CHANGE_THRESHOLD = 0.1;        // 0.1°C change threshold

// Performance monitoring
unsigned long loopCount = 0;
unsigned long lastPerformanceReport = 0;
const unsigned long PERFORMANCE_INTERVAL = 10000; // 10s performance report

void setup() {
  Serial.begin(115200);
  Serial.setTimeout(100);
  
  // Initialize pins
  pinMode(BUZZER_PIN, OUTPUT);
  pinMode(RELAY_BRAKE_PIN, OUTPUT);
  pinMode(REFLECTOR_SENSOR_PIN, INPUT);  // NEW
  pinMode(REFLECTOR_LED_PIN, OUTPUT);    // NEW
  digitalWrite(BUZZER_PIN, LOW);
  digitalWrite(RELAY_BRAKE_PIN, LOW);
  digitalWrite(REFLECTOR_LED_PIN, LOW);  // NEW
  
  // Initialize DUAL temperature sensors
  Serial.println(F("Initializing dual temperature sensors..."));
  
  tempSensor1.begin();
  tempSensor2.begin();
  
  // Configure sensors for speed
  tempSensor1.setResolution(10); // 10-bit resolution for speed
  tempSensor2.setResolution(10);
  tempSensor1.setWaitForConversion(false); // Non-blocking
  tempSensor2.setWaitForConversion(false);
  
  // Check sensor connections
  sysState.sensor1Connected = (tempSensor1.getDeviceCount() > 0);
  sysState.sensor2Connected = (tempSensor2.getDeviceCount() > 0);
  
  Serial.print(F("Sensor 1 (Pin 8): "));
  Serial.println(sysState.sensor1Connected ? F("CONNECTED") : F("DISCONNECTED"));
  Serial.print(F("Sensor 2 (Pin 13): "));
  Serial.println(sysState.sensor2Connected ? F("CONNECTED") : F("DISCONNECTED"));
  
  // Initialize REFLECTOR system - NEW
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
  
  Serial.print(F("Detection threshold: "));
  Serial.print((reflector.DETECT_THRESHOLD * 5.0) / 1023.0, 2);
  Serial.println(F("V"));
  Serial.print(F("Release threshold: "));
  Serial.print((reflector.RELEASE_THRESHOLD * 5.0) / 1023.0, 2);
  Serial.println(F("V"));
  
  // Initialize motors
  for (byte i = 0; i < NUM_MOTORS; i++) {
    motors[i].attach(MOTOR_PINS[i]);
    motors[i].writeMicroseconds(ESC_MIN);
    motorStates[i] = false;
    motorSpeeds[i] = 0;
  }
  
  delay(1500); // ESC calibration
  
  // First temperature readings
  requestTemperatureReadings();
  delay(200); // Wait for conversion
  readTemperaturesNonBlocking();
  
  Serial.println(F("SpectraLoop v3.6 DUAL TEMPERATURE + REFLECTOR COUNTER"));
  Serial.println(F("FEATURES: 2x DS18B20 sensors, Omron reflector counter, ultra-fast monitoring"));
  Serial.print(F("Initial Temps - Sensor1: "));
  Serial.print(currentTemp1);
  Serial.print(F("°C, Sensor2: "));
  Serial.print(currentTemp2);
  Serial.println(F("°C"));
  Serial.print(F("Reflector Count: "));
  Serial.println(reflector.count);
  Serial.println(F("READY"));
}

void loop() {
  unsigned long now = millis();
  loopCount++;
  
  // ULTRA-FAST Dual temperature monitoring
  if (now - lastTempRead >= TEMP_INTERVAL) {
    readTemperaturesNonBlocking();
    lastTempRead = now;
  }
  
  // ULTRA-FAST Reflector monitoring - NEW
  if (now - reflector.lastReadTime >= REFLECTOR_INTERVAL) {
    readReflectorSensor();
    reflector.lastReadTime = now;
  }
  
  // Temperature reporting - both sensors
  if (now - lastTempReport >= TEMP_REPORT_INTERVAL) {
    reportTemperaturesIfChanged();
    lastTempReport = now;
  }
  
  // Reflector reporting - NEW
  if (now - reflector.lastReportTime >= reflector.REPORT_INTERVAL) {
    reportReflectorData();
    reflector.lastReportTime = now;
  }
  
  // Buzzer control
  if (sysState.temperatureAlarm && sysState.buzzerActive) {
    if (now - lastBuzzerToggle > BUZZER_INTERVAL) {
      static bool buzzerState = false;
      buzzerState = !buzzerState;
      digitalWrite(BUZZER_PIN, buzzerState);
      lastBuzzerToggle = now;
    }
  }
  
  // Command processing
  if (Serial.available() && (now - lastCommandTime) > COMMAND_COOLDOWN) {
    processCommand();
    lastCommandTime = now;
  }
  
  // Heartbeat with dual temperatures + reflector data
  if (now - lastHeartbeat > HEARTBEAT_INTERVAL) {
    sendHeartbeat();
    lastHeartbeat = now;
  }
  
  // Performance monitoring
  if (now - lastPerformanceReport > PERFORMANCE_INTERVAL) {
    sendPerformanceReport(now);
    lastPerformanceReport = now;
  }
}

// NEW REFLECTOR SYSTEM FUNCTIONS
void readReflectorSensor() {
  // Ultra-fast sensor reading
  reflector.analogValue = analogRead(REFLECTOR_SENSOR_PIN);
  reflector.voltage = (reflector.analogValue * 5.0) / 1023.0;
  reflector.readCount++;
  
  // State determination with hysteresis
  bool newState = reflector.currentState;
  
  if (!reflector.currentState && reflector.analogValue < reflector.DETECT_THRESHOLD) {
    // Reflector detected (voltage dropped)
    newState = true;
  } else if (reflector.currentState && reflector.analogValue > reflector.RELEASE_THRESHOLD) {
    // Reflector lost (voltage increased)
    newState = false;
  }
  
  unsigned long currentTime = millis();
  
  // State change control with debouncing
  if (newState != reflector.currentState) {
    // Record first change time
    if (currentTime - reflector.lastChangeTime > reflector.DEBOUNCE_TIME) {
      reflector.lastChangeTime = currentTime;
    }
    
    // Check if stable for required time
    if (currentTime - reflector.lastChangeTime >= reflector.STABLE_TIME) {
      // State change accepted
      reflector.lastState = reflector.currentState;
      reflector.currentState = newState;
      
      // Reflector detected -> increment counter
      if (reflector.currentState && !reflector.lastState) {
        reflector.count++;
        reflector.detectionCount++;
        reflector.lastReflectorTime = currentTime;
        
        // Calculate instant speed (time between reflectors)
        static unsigned long lastReflectorDetection = 0;
        if (lastReflectorDetection > 0) {
          unsigned long timeDiff = currentTime - lastReflectorDetection;
          if (timeDiff > 0) {
            reflector.instantSpeed = 60000.0 / timeDiff; // reflectors per minute
          }
        }
        lastReflectorDetection = currentTime;
        
        // Brief LED flash for detection feedback
        digitalWrite(REFLECTOR_LED_PIN, HIGH);
        
        // Send immediate detection report
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
    // No state change, reset change time
    reflector.lastChangeTime = currentTime;
  }
  
  // LED status (on when reflector present)
  digitalWrite(REFLECTOR_LED_PIN, reflector.currentState);
  
  // Brief LED flash turn off after detection
  if (reflector.currentState && !reflector.lastState && 
      currentTime - reflector.lastReflectorTime > 50) {
    digitalWrite(REFLECTOR_LED_PIN, LOW);
  }
}

void reportReflectorData() {
  unsigned long currentTime = millis();
  
  // Calculate average speed
  float elapsedMinutes = (currentTime - reflector.startTime) / 60000.0;
  if (elapsedMinutes > 0) {
    reflector.averageSpeed = reflector.count / elapsedMinutes;
  }
  
  // Calculate read frequency
  static unsigned long lastReadCount = 0;
  static unsigned long lastFreqUpdate = 0;
  unsigned long elapsed = currentTime - lastFreqUpdate;
  if (elapsed >= 1000) { // Update frequency every second
    reflector.readFrequency = (reflector.readCount - lastReadCount) / (elapsed / 1000.0);
    lastReadCount = reflector.readCount;
    lastFreqUpdate = currentTime;
  }
  
  // Send comprehensive reflector report
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

void requestTemperatureReadings() {
  // Request from both sensors simultaneously
  if (sysState.sensor1Connected) {
    tempSensor1.requestTemperatures();
  }
  if (sysState.sensor2Connected) {
    tempSensor2.requestTemperatures();
  }
}

void readTemperaturesNonBlocking() {
  bool tempChanged = false;
  
  // Read primary sensor (Pin 8)
  if (sysState.sensor1Connected) {
    float newTemp1 = tempSensor1.getTempCByIndex(0);
    if (newTemp1 > -50 && newTemp1 < 100 && newTemp1 != DEVICE_DISCONNECTED_C) {
      if (abs(newTemp1 - currentTemp1) > 0.05) { // 0.05°C sensitivity
        currentTemp1 = newTemp1;
        tempChanged = true;
        
        // Update max temperature
        if (currentTemp1 > maxTemp1) {
          maxTemp1 = currentTemp1;
        }
      }
    } else {
      // Sensor 1 disconnected
      if (sysState.sensor1Connected) {
        Serial.println(F("WARNING:Sensor1_disconnected"));
        sysState.sensor1Connected = false;
      }
    }
  }
  
  // Read secondary sensor (Pin 13)
  if (sysState.sensor2Connected) {
    float newTemp2 = tempSensor2.getTempCByIndex(0);
    if (newTemp2 > -50 && newTemp2 < 100 && newTemp2 != DEVICE_DISCONNECTED_C) {
      if (abs(newTemp2 - currentTemp2) > 0.05) { // 0.05°C sensitivity
        currentTemp2 = newTemp2;
        tempChanged = true;
        
        // Update max temperature
        if (currentTemp2 > maxTemp2) {
          maxTemp2 = currentTemp2;
        }
      }
    } else {
      // Sensor 2 disconnected
      if (sysState.sensor2Connected) {
        Serial.println(F("WARNING:Sensor2_disconnected"));
        sysState.sensor2Connected = false;
      }
    }
  }
  
  // Update overall maximum temperature
  maxTempOverall = max(maxTemp1, maxTemp2);
  
  if (tempChanged) {
    tempReadCount++;
    // Check safety immediately after reading
    checkDualTempSafety();
  }
  
  // Request next readings for continuous monitoring
  requestTemperatureReadings();
}

void reportTemperaturesIfChanged() {
  // Report if either sensor changed significantly
  bool shouldReport = false;
  
  if (abs(currentTemp1 - lastReportedTemp1) >= TEMP_CHANGE_THRESHOLD) {
    shouldReport = true;
  }
  if (abs(currentTemp2 - lastReportedTemp2) >= TEMP_CHANGE_THRESHOLD) {
    shouldReport = true;
  }
  
  // Always report every 1 second regardless
  if ((millis() - lastTempReport) > 1000) {
    shouldReport = true;
  }
  
  if (shouldReport) {
    // Send dual temperature in format backend expects
    Serial.print(F("DUAL_TEMP [TEMP1:"));
    Serial.print(currentTemp1, 2);
    Serial.print(F("] [TEMP2:"));
    Serial.print(currentTemp2, 2);
    Serial.print(F("] [MAX:"));
    Serial.print(maxTempOverall, 2);
    Serial.println(F("]"));
    
    lastReportedTemp1 = currentTemp1;
    lastReportedTemp2 = currentTemp2;
  }
}

void checkDualTempSafety() {
  // Use the HIGHER temperature for safety decisions (worst-case scenario)
  float maxCurrentTemp = max(currentTemp1, currentTemp2);
  bool wasAlarmActive = sysState.temperatureAlarm;
  
  // Alarm condition: Either sensor exceeds alarm threshold
  if (maxCurrentTemp >= TEMP_ALARM && !sysState.temperatureAlarm) {
    sysState.temperatureAlarm = true;
    sysState.buzzerActive = true;
    alarmCount++;
    emergencyStopTemp();
    
    // Immediate alarm reports with reflector data
    Serial.print(F("TEMP_ALARM:"));
    Serial.print(maxCurrentTemp, 2);
    Serial.print(F(" (S1:"));
    Serial.print(currentTemp1, 2);
    Serial.print(F(",S2:"));
    Serial.print(currentTemp2, 2);
    Serial.print(F(") [REFLECTOR:"));
    Serial.print(reflector.count);
    Serial.println(F("]"));
    
    // Also send in ACK format for immediate parsing
    Serial.print(F("ALARM_ACTIVE [TEMP:"));
    Serial.print(maxCurrentTemp, 2);
    Serial.print(F("] [REFLECTOR:"));
    Serial.print(reflector.count);
    Serial.println(F("]"));
    
  } else if (maxCurrentTemp <= TEMP_SAFE && sysState.temperatureAlarm) {
    // Safe condition: BOTH sensors below safe threshold
    sysState.temperatureAlarm = false;
    sysState.buzzerActive = false;
    digitalWrite(BUZZER_PIN, LOW);
    
    // Immediate safe reports with reflector data
    Serial.print(F("TEMP_SAFE:"));
    Serial.print(maxCurrentTemp, 2);
    Serial.print(F(" (S1:"));
    Serial.print(currentTemp1, 2);
    Serial.print(F(",S2:"));
    Serial.print(currentTemp2, 2);
    Serial.print(F(") [REFLECTOR:"));
    Serial.print(reflector.count);
    Serial.println(F("]"));
    
    // Also send in ACK format
    Serial.print(F("TEMP_NORMAL [TEMP:"));
    Serial.print(maxCurrentTemp, 2);
    Serial.print(F("] [REFLECTOR:"));
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

  // Send ACK with DUAL temperature + reflector info
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
  Serial.println(F("]"));

  if (cmd == F("PING")) {
    Serial.println(F("PONG:v3.6-DUAL-TEMP-REFLECTOR"));
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
    // Detailed dual temperature status
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
    Serial.println(sysState.sensor2Connected);
  }
  else if (cmd == F("REFLECTOR_STATUS")) {
    // NEW: Detailed reflector status
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
    Serial.print(F(",READ_FREQ:"));
    Serial.print(reflector.readFrequency, 1);
    Serial.print(F(",ACTIVE:"));
    Serial.println(sysState.reflectorSystemActive);
  }
  else if (cmd == F("REFLECTOR_RESET")) {
    // NEW: Reset reflector counter
    reflector.count = 0;
    reflector.detectionCount = 0;
    reflector.startTime = millis();
    reflector.lastReflectorTime = reflector.startTime;
    reflector.averageSpeed = 0.0;
    reflector.instantSpeed = 0.0;
    Serial.println(F("REFLECTOR_RESET:SUCCESS"));
  }
  else if (cmd == F("REFLECTOR_CALIBRATE")) {
    // NEW: Reflector sensor calibration
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
  else if (cmd == F("TEMP_REALTIME")) {
    // Ultra-fast dual temperature + reflector response
    Serial.print(F("REALTIME_DUAL:"));
    Serial.print(currentTemp1, 2);
    Serial.print(F(","));
    Serial.print(currentTemp2, 2);
    Serial.print(F(","));
    Serial.print(max(currentTemp1, currentTemp2), 2);
    Serial.print(F(","));
    Serial.print(sysState.temperatureAlarm);
    Serial.print(F(","));
    Serial.print(sysState.buzzerActive);
    Serial.print(F(","));
    Serial.print(tempReadCount);
    Serial.print(F(","));
    Serial.print(reflector.count);
    Serial.print(F(","));
    Serial.print(reflector.averageSpeed, 1);
    Serial.print(F(","));
    Serial.println(reflector.instantSpeed, 1);
  }
  else if (cmd == F("TEMP_DEBUG")) {
    Serial.println(F("=== DUAL TEMPERATURE + REFLECTOR DEBUG ==="));
    Serial.print(F("Sensor 1 (Pin 8): "));
    Serial.print(currentTemp1, 3);
    Serial.print(F("°C ["));
    Serial.print(sysState.sensor1Connected ? F("CONNECTED") : F("DISCONNECTED"));
    Serial.print(F("] Max: "));
    Serial.print(maxTemp1, 3);
    Serial.println(F("°C"));
    
    Serial.print(F("Sensor 2 (Pin 13): "));
    Serial.print(currentTemp2, 3);
    Serial.print(F("°C ["));
    Serial.print(sysState.sensor2Connected ? F("CONNECTED") : F("DISCONNECTED"));
    Serial.print(F("] Max: "));
    Serial.print(maxTemp2, 3);
    Serial.println(F("°C"));
    
    Serial.print(F("Overall Max: "));
    Serial.print(maxTempOverall, 3);
    Serial.println(F("°C"));
    Serial.print(F("Temperature Alarm: "));
    Serial.println(sysState.temperatureAlarm);
    Serial.print(F("Buzzer Active: "));
    Serial.println(sysState.buzzerActive);
    Serial.print(F("Alarm Count: "));
    Serial.println(alarmCount);
    Serial.print(F("Read Count: "));
    Serial.println(tempReadCount);
    
    // NEW: Reflector debug info
    Serial.println(F("--- REFLECTOR SYSTEM ---"));
    Serial.print(F("Count: "));
    Serial.println(reflector.count);
    Serial.print(F("Voltage: "));
    Serial.print(reflector.voltage, 3);
    Serial.println(F("V"));
    Serial.print(F("State: "));
    Serial.println(reflector.currentState ? F("DETECTED") : F("CLEAR"));
    Serial.print(F("Avg Speed: "));
    Serial.print(reflector.averageSpeed, 2);
    Serial.println(F(" ref/min"));
    Serial.print(F("Inst Speed: "));
    Serial.print(reflector.instantSpeed, 2);
    Serial.println(F(" ref/min"));
    Serial.print(F("Detections: "));
    Serial.println(reflector.detectionCount);
    Serial.print(F("Read Freq: "));
    Serial.print(reflector.readFrequency, 1);
    Serial.println(F(" Hz"));
    Serial.print(F("System Active: "));
    Serial.println(sysState.reflectorSystemActive);
    Serial.println(F("=== DEBUG END ==="));
  } 
  else if (cmd == F("BUZZER_OFF")) {
    if (!sysState.temperatureAlarm) {
      sysState.buzzerActive = false;
      digitalWrite(BUZZER_PIN, LOW);
      Serial.println(F("BUZZER_OFF"));
    } else {
      Serial.println(F("ERROR:Cannot_turn_off_buzzer_during_alarm"));
    }
  } 
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

void armSystem() {
  float maxCurrentTemp = max(currentTemp1, currentTemp2);
  
  if (sysState.brakeActive || !sysState.relayBrakeActive || 
      sysState.temperatureAlarm || maxCurrentTemp > TEMP_ALARM - 5) {
    Serial.print(F("ERROR:Cannot_arm (MaxTemp:"));
    Serial.print(maxCurrentTemp, 1);
    Serial.print(F("°C) [REFLECTOR:"));
    Serial.print(reflector.count);
    Serial.println(F("]"));
    return;
  }
  
  // Check if at least one sensor is connected
  if (!sysState.sensor1Connected && !sysState.sensor2Connected) {
    Serial.println(F("ERROR:No_temperature_sensors"));
    return;
  }
  
  sysState.armed = true;
  Serial.print(F("ARMED [REFLECTOR:"));
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
  if (active && sysState.temperatureAlarm) {
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

// Motor control functions - ENHANCED with dual temp + reflector safety
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
    
    // Immediate dual temperature + reflector check after motor start
    Serial.print(F("POST_START [TEMP1:"));
    Serial.print(currentTemp1, 2);
    Serial.print(F("] [TEMP2:"));
    Serial.print(currentTemp2, 2);
    Serial.print(F("] [REFLECTOR:"));
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

// Group control functions - similar pattern with dual temp + reflector monitoring
void parseLevCmd(String cmd) {
  if (!canStartMotors()) return;
  
  int colon1 = cmd.indexOf(':');
  int colon2 = cmd.indexOf(':', colon1 + 1);
  
  String action = cmd.substring(colon1 + 1, colon2 > 0 ? colon2 : cmd.length());
  
  if (action == F("START")) {
    byte speed = (colon2 > 0) ? cmd.substring(colon2 + 1).toInt() : 50;
    if (speed > 100) speed = 100;
    
    levitationGroupSpeed = speed;
    for (byte i = 0; i < 4; i++) {
      motorStates[i] = true;
      motorSpeeds[i] = speed;
      setMotorSpeed(i, speed);
    }
    
    Serial.print(F("LEV_GROUP_STARTED:"));
    Serial.print(speed);
    Serial.print(F(" [REFLECTOR:"));
    Serial.print(reflector.count);
    Serial.println(F("]"));
    
    // Dual temperature + reflector report after group start
    Serial.print(F("LEV_START [TEMP1:"));
    Serial.print(currentTemp1, 2);
    Serial.print(F("] [TEMP2:"));
    Serial.print(currentTemp2, 2);
    Serial.print(F("] [REFLECTOR:"));
    Serial.print(reflector.count);
    Serial.println(F("]"));
    
  } else if (action == F("STOP")) {
    for (byte i = 0; i < 4; i++) {
      motorStates[i] = false;
      motorSpeeds[i] = 0;
      setMotorSpeed(i, 0);
    }
    levitationGroupSpeed = 0;
    Serial.print(F("LEV_GROUP_STOPPED [REFLECTOR:"));
    Serial.print(reflector.count);
    Serial.println(F("]"));
    
  } else if (action == F("SPEED") && colon2 > 0) {
    byte speed = cmd.substring(colon2 + 1).toInt();
    if (speed > 100) speed = 100;
    
    levitationGroupSpeed = speed;
    for (byte i = 0; i < 4; i++) {
      if (motorStates[i]) {
        motorSpeeds[i] = speed;
        setMotorSpeed(i, speed);
      }
    }
    
    Serial.print(F("LEV_GROUP_SPEED:"));
    Serial.print(speed);
    Serial.print(F(" [REFLECTOR:"));
    Serial.print(reflector.count);
    Serial.println(F("]"));
  }
}

void parseThrCmd(String cmd) {
  if (!canStartMotors()) return;
  
  int colon1 = cmd.indexOf(':');
  int colon2 = cmd.indexOf(':', colon1 + 1);
  
  String action = cmd.substring(colon1 + 1, colon2 > 0 ? colon2 : cmd.length());
  
  if (action == F("START")) {
    byte speed = (colon2 > 0) ? cmd.substring(colon2 + 1).toInt() : 50;
    if (speed > 100) speed = 100;
    
    thrustGroupSpeed = speed;
    for (byte i = 4; i < 6; i++) {
      motorStates[i] = true;
      motorSpeeds[i] = speed;
      setMotorSpeed(i, speed);
    }
    
    Serial.print(F("THR_GROUP_STARTED:"));
    Serial.print(speed);
    Serial.print(F(" [REFLECTOR:"));
    Serial.print(reflector.count);
    Serial.println(F("]"));
    
    // Dual temperature + reflector report after thrust start
    Serial.print(F("THR_START [TEMP1:"));
    Serial.print(currentTemp1, 2);
    Serial.print(F("] [TEMP2:"));
    Serial.print(currentTemp2, 2);
    Serial.print(F("] [REFLECTOR:"));
    Serial.print(reflector.count);
    Serial.println(F("]"));
    
  } else if (action == F("STOP")) {
    for (byte i = 4; i < 6; i++) {
      motorStates[i] = false;
      motorSpeeds[i] = 0;
      setMotorSpeed(i, 0);
    }
    thrustGroupSpeed = 0;
    Serial.print(F("THR_GROUP_STOPPED [REFLECTOR:"));
    Serial.print(reflector.count);
    Serial.println(F("]"));
    
  } else if (action == F("SPEED") && colon2 > 0) {
    byte speed = cmd.substring(colon2 + 1).toInt();
    if (speed > 100) speed = 100;
    
    thrustGroupSpeed = speed;
    for (byte i = 4; i < 6; i++) {
      if (motorStates[i]) {
        motorSpeeds[i] = speed;
        setMotorSpeed(i, speed);
      }
    }
    
    Serial.print(F("THR_GROUP_SPEED:"));
    Serial.print(speed);
    Serial.print(F(" [REFLECTOR:"));
    Serial.print(reflector.count);
    Serial.println(F("]"));
  }
}

bool canStartMotors() {
  float maxCurrentTemp = max(currentTemp1, currentTemp2);
  
  if (!sysState.armed || sysState.brakeActive || !sysState.relayBrakeActive || 
      sysState.temperatureAlarm || maxCurrentTemp > TEMP_ALARM - 3) {
    Serial.print(F("ERROR:Cannot_start (MaxTemp:"));
    Serial.print(maxCurrentTemp, 1);
    Serial.print(F("°C) [REFLECTOR:"));
    Serial.print(reflector.count);
    Serial.println(F("]"));
    return false;
  }
  
  // Require at least one sensor working
  if (!sysState.sensor1Connected && !sysState.sensor2Connected) {
    Serial.println(F("ERROR:No_temperature_sensors"));
    return false;
  }
  
  return true;
}

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
  Serial.print(F("ReadCount:"));
  Serial.println(tempReadCount);
  Serial.print(F("AlarmCount:"));
  Serial.println(alarmCount);
  Serial.print(F("ReadFrequency:"));
  Serial.print(1000.0 / TEMP_INTERVAL, 1);
  Serial.println(F("Hz"));
  // NEW: Reflector status in temperature status
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
  Serial.print(F("LevGroupSpeed:"));
  Serial.println(levitationGroupSpeed);
  Serial.print(F("ThrGroupSpeed:"));
  Serial.println(thrustGroupSpeed);
  
  // NEW: Reflector system status
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
  
  // Standard heartbeat format
  Serial.print(F("HEARTBEAT:"));
  Serial.print(millis() / 1000);
  Serial.print(',');
  Serial.print(sysState.armed);
  Serial.print(',');
  Serial.print(sysState.brakeActive);
  Serial.print(',');
  Serial.print(sysState.relayBrakeActive);
  Serial.print(',');
  Serial.print(maxCurrentTemp, 2);  // Use max temperature for safety
  Serial.print(',');
  Serial.print(sysState.temperatureAlarm);
  
  byte activeCount = 0;
  for (byte i = 0; i < NUM_MOTORS; i++) {
    if (motorStates[i]) activeCount++;
  }
  Serial.print(',');
  Serial.println(activeCount);
  
  // Enhanced heartbeat with dual temperature + reflector info
  Serial.print(F("HB_DUAL [TEMP1:"));
  Serial.print(currentTemp1, 2);
  Serial.print(F("] [TEMP2:"));
  Serial.print(currentTemp2, 2);
  Serial.print(F("] [MAX:"));
  Serial.print(maxCurrentTemp, 2);
  Serial.print(F("] [REFLECTOR:"));
  Serial.print(reflector.count);
  Serial.print(F("] [REF_SPEED:"));
  Serial.print(reflector.averageSpeed, 1);
  Serial.println(F("]"));
}

void sendPerformanceReport(unsigned long now) {
  float loopsPerSecond = (float)loopCount * 1000.0 / PERFORMANCE_INTERVAL;
  float tempReadsPerSecond = (float)tempReadCount * 1000.0 / PERFORMANCE_INTERVAL;
  
  Serial.print(F("PERFORMANCE:"));
  Serial.print(loopsPerSecond, 1);
  Serial.print(F("Hz,TempReads:"));
  Serial.print(tempReadsPerSecond, 1);
  Serial.print(F("Hz,DualSensors:"));
  Serial.print(sysState.sensor1Connected ? 'Y' : 'N');
  Serial.print(sysState.sensor2Connected ? 'Y' : 'N');
  Serial.print(F(",ReflectorReads:"));
  Serial.print(reflector.readFrequency, 1);
  Serial.print(F("Hz,ReflectorCount:"));
  Serial.print(reflector.count);
  Serial.print(F(",FreeRAM:"));
  Serial.println(getFreeMemory());
  
  // Reset counters
  loopCount = 0;
  tempReadCount = 0;
}

int getFreeMemory() {
  extern int __heap_start, *__brkval;
  int v;
  return (int) &v - (__brkval == 0 ? (int) &__heap_start : (int) __brkval);
}