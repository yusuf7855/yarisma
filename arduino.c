/*
 * SpectraLoop Motor Control System - Arduino DUAL TEMPERATURE v3.5
 * DUAL DS18B20 Temperature Sensors + Ultra-fast monitoring
 * 6 BLDC Motor + Relay Brake + 2x DS18B20 + Buzzer
 * Motor Pin Mapping: Thrust(3,7), Levitation(2,4,5,6)
 * Temperature Sensors: Pin 8 (Primary), Pin 13 (Secondary)
 * ULTRA-FAST: 100ms readings, dual sensor monitoring, safety redundancy
 */

#include <Servo.h>
#include <OneWire.h>
#include <DallasTemperature.h>

// Pin definitions
#define ONE_WIRE_BUS_1 8    // Primary temperature sensor
#define ONE_WIRE_BUS_2 13   // Secondary temperature sensor
#define BUZZER_PIN 9
#define RELAY_BRAKE_PIN 11

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
  byte reserved : 1;
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

// Temperature safety thresholds
const float TEMP_ALARM = 55.0;
const float TEMP_SAFE = 50.0;
const float TEMP_WARNING = 45.0;

// ULTRA-FAST Constants - DUAL SENSOR OPTIMIZED
const unsigned long TEMP_INTERVAL = 100;        // 100ms - read both sensors
const unsigned long TEMP_REPORT_INTERVAL = 200; // Report every 200ms
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
  digitalWrite(BUZZER_PIN, LOW);
  digitalWrite(RELAY_BRAKE_PIN, LOW);
  
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
  
  Serial.println(F("SpectraLoop v3.5 DUAL TEMPERATURE - Ultra-fast Monitoring"));
  Serial.println(F("FEATURES: 2x DS18B20 sensors, redundant safety, 100ms monitoring"));
  Serial.print(F("Initial Temps - Sensor1: "));
  Serial.print(currentTemp1);
  Serial.print(F("°C, Sensor2: "));
  Serial.print(currentTemp2);
  Serial.println(F("°C"));
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
  
  // Temperature reporting - both sensors
  if (now - lastTempReport >= TEMP_REPORT_INTERVAL) {
    reportTemperaturesIfChanged();
    lastTempReport = now;
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
  
  // Heartbeat with dual temperatures
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
    
    // Immediate alarm reports
    Serial.print(F("TEMP_ALARM:"));
    Serial.print(maxCurrentTemp, 2);
    Serial.print(F(" (S1:"));
    Serial.print(currentTemp1, 2);
    Serial.print(F(",S2:"));
    Serial.print(currentTemp2, 2);
    Serial.println(F(")"));
    
    // Also send in ACK format for immediate parsing
    Serial.print(F("ALARM_ACTIVE [TEMP:"));
    Serial.print(maxCurrentTemp, 2);
    Serial.println(F("]"));
    
  } else if (maxCurrentTemp <= TEMP_SAFE && sysState.temperatureAlarm) {
    // Safe condition: BOTH sensors below safe threshold
    sysState.temperatureAlarm = false;
    sysState.buzzerActive = false;
    digitalWrite(BUZZER_PIN, LOW);
    
    // Immediate safe reports
    Serial.print(F("TEMP_SAFE:"));
    Serial.print(maxCurrentTemp, 2);
    Serial.print(F(" (S1:"));
    Serial.print(currentTemp1, 2);
    Serial.print(F(",S2:"));
    Serial.print(currentTemp2, 2);
    Serial.println(F(")"));
    
    // Also send in ACK format
    Serial.print(F("TEMP_NORMAL [TEMP:"));
    Serial.print(maxCurrentTemp, 2);
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
  Serial.println(F(")"));
}

void processCommand() {
  String cmd = Serial.readStringUntil('\n');
  cmd.trim();
  if (cmd.length() == 0) return;

  // Send ACK with DUAL temperature info
  Serial.print(F("ACK:"));
  Serial.print(cmd);
  Serial.print(F(" [TEMP1:"));
  Serial.print(currentTemp1, 2);
  Serial.print(F("] [TEMP2:"));
  Serial.print(currentTemp2, 2);
  Serial.print(F("] [MAX:"));
  Serial.print(max(currentTemp1, currentTemp2), 2);
  Serial.println(F("]"));

  if (cmd == F("PING")) {
    Serial.println(F("PONG:v3.5-DUAL-TEMP"));
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
    // NEW: Detailed dual temperature status
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
  else if (cmd == F("TEMP_REALTIME")) {
    // Ultra-fast dual temperature response
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
    Serial.println(tempReadCount);
  }
  else if (cmd == F("TEMP_DEBUG")) {
    Serial.println(F("=== DUAL TEMPERATURE DEBUG ==="));
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
    Serial.print(F("Read Interval: "));
    Serial.print(TEMP_INTERVAL);
    Serial.println(F("ms"));
    Serial.print(F("Safety Decision Based On: "));
    Serial.print(max(currentTemp1, currentTemp2), 2);
    Serial.println(F("°C (highest sensor)"));
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
    Serial.println(F("°C)"));
    return;
  }
  
  // Check if at least one sensor is connected
  if (!sysState.sensor1Connected && !sysState.sensor2Connected) {
    Serial.println(F("ERROR:No_temperature_sensors"));
    return;
  }
  
  sysState.armed = true;
  Serial.println(F("ARMED"));
}

void disarmSystem() {
  sysState.armed = false;
  for (byte i = 0; i < NUM_MOTORS; i++) {
    setMotorSpeed(i, 0);
    motorStates[i] = false;
    motorSpeeds[i] = 0;
  }
  levitationGroupSpeed = thrustGroupSpeed = 0;
  Serial.println(F("DISARMED"));
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
  Serial.println(active ? F("ON") : F("OFF"));
}

// Motor control functions - SAME as before but with dual temp safety
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
    Serial.println(speed);
    
    // Immediate dual temperature check after motor start
    Serial.print(F("POST_START [TEMP1:"));
    Serial.print(currentTemp1, 2);
    Serial.print(F("] [TEMP2:"));
    Serial.print(currentTemp2, 2);
    Serial.println(F("]"));
    
  } else if (action == F("STOP")) {
    motorStates[idx] = false;
    motorSpeeds[idx] = 0;
    setMotorSpeed(idx, 0);
    
    Serial.print(F("MOTOR_STOPPED:"));
    Serial.println(motorNum);
    
  } else if (action == F("SPEED") && colon3 > 0) {
    byte speed = cmd.substring(colon3 + 1).toInt();
    if (speed > 100) speed = 100;
    
    motorSpeeds[idx] = speed;
    if (motorStates[idx]) setMotorSpeed(idx, speed);
    
    Serial.print(F("MOTOR_SPEED:"));
    Serial.print(motorNum);
    Serial.print(':');
    Serial.println(speed);
  }
}

// Group control functions - similar pattern with dual temp monitoring
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
    Serial.println(speed);
    
    // Dual temperature report after group start
    Serial.print(F("LEV_START [TEMP1:"));
    Serial.print(currentTemp1, 2);
    Serial.print(F("] [TEMP2:"));
    Serial.print(currentTemp2, 2);
    Serial.println(F("]"));
    
  } else if (action == F("STOP")) {
    for (byte i = 0; i < 4; i++) {
      motorStates[i] = false;
      motorSpeeds[i] = 0;
      setMotorSpeed(i, 0);
    }
    levitationGroupSpeed = 0;
    Serial.println(F("LEV_GROUP_STOPPED"));
    
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
    Serial.println(speed);
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
    Serial.println(speed);
    
    // Dual temperature report after thrust start
    Serial.print(F("THR_START [TEMP1:"));
    Serial.print(currentTemp1, 2);
    Serial.print(F("] [TEMP2:"));
    Serial.print(currentTemp2, 2);
    Serial.println(F("]"));
    
  } else if (action == F("STOP")) {
    for (byte i = 4; i < 6; i++) {
      motorStates[i] = false;
      motorSpeeds[i] = 0;
      setMotorSpeed(i, 0);
    }
    thrustGroupSpeed = 0;
    Serial.println(F("THR_GROUP_STOPPED"));
    
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
    Serial.println(speed);
  }
}

bool canStartMotors() {
  float maxCurrentTemp = max(currentTemp1, currentTemp2);
  
  if (!sysState.armed || sysState.brakeActive || !sysState.relayBrakeActive || 
      sysState.temperatureAlarm || maxCurrentTemp > TEMP_ALARM - 3) {
    Serial.print(F("ERROR:Cannot_start (MaxTemp:"));
    Serial.print(maxCurrentTemp, 1);
    Serial.println(F("°C)"));
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
  Serial.println(active ? F("BRAKE_ON") : F("BRAKE_OFF"));
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
  Serial.println(F("EMERGENCY_STOP"));
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
  
  // Enhanced heartbeat with dual temperature info
  Serial.print(F("HB_DUAL [TEMP1:"));
  Serial.print(currentTemp1, 2);
  Serial.print(F("] [TEMP2:"));
  Serial.print(currentTemp2, 2);
  Serial.print(F("] [MAX:"));
  Serial.print(maxCurrentTemp, 2);
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