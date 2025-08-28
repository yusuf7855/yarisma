/*
 * SpectraLoop Motor Control System - Arduino Final v3.3
 * Optimized for Arduino Uno - Temperature + Buzzer Safety
 * 6 BLDC Motor + Relay Brake + DS18B20 + Buzzer
 * Motor Pin Mapping: Thrust(3,7), Levitation(2,4,5,6)
 */

#include <Servo.h>
#include <OneWire.h>
#include <DallasTemperature.h>

// Pin definitions
#define ONE_WIRE_BUS 8
#define BUZZER_PIN 9
#define RELAY_BRAKE_PIN 11

// Temperature sensor
OneWire oneWire(ONE_WIRE_BUS);
DallasTemperature tempSensor(&oneWire);

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
  byte reserved : 3;
} sysState = {0};

// Temperature and timing
float currentTemp = 25.0;
unsigned long lastTempRead = 0;
unsigned long lastBuzzerToggle = 0;
unsigned long lastCommandTime = 0;
unsigned long lastHeartbeat = 0;

// Constants
const float TEMP_ALARM = 55.0;
const float TEMP_SAFE = 50.0;
const unsigned long TEMP_INTERVAL = 2000;
const unsigned long BUZZER_INTERVAL = 500;
const unsigned long COMMAND_COOLDOWN = 25;
const unsigned long HEARTBEAT_INTERVAL = 30000;

void setup() {
  Serial.begin(115200);
  Serial.setTimeout(500);
  
  // Initialize pins
  pinMode(BUZZER_PIN, OUTPUT);
  pinMode(RELAY_BRAKE_PIN, OUTPUT);
  digitalWrite(BUZZER_PIN, LOW);
  digitalWrite(RELAY_BRAKE_PIN, LOW);
  
  // Initialize temperature sensor
  tempSensor.begin();
  
  // Initialize motors
  for (byte i = 0; i < NUM_MOTORS; i++) {
    motors[i].attach(MOTOR_PINS[i]);
    motors[i].writeMicroseconds(ESC_MIN);
    motorStates[i] = false;
    motorSpeeds[i] = 0;
  }
  
  delay(2000); // ESC calibration
  
  // First temperature reading
  readTemperature();
  
  Serial.println(F("SpectraLoop v3.3 - Temperature Safety"));
  Serial.println(F("READY"));
}

void loop() {
  unsigned long now = millis();
  
  // Temperature monitoring
  if (now - lastTempRead > TEMP_INTERVAL) {
    readTemperature();
    checkTempSafety();
    lastTempRead = now;
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
  
  // Heartbeat
  if (now - lastHeartbeat > HEARTBEAT_INTERVAL) {
    sendHeartbeat();
    lastHeartbeat = now;
  }
}

void readTemperature() {
  tempSensor.requestTemperatures();
  float newTemp = tempSensor.getTempCByIndex(0);
  if (newTemp > -50 && newTemp < 100) {
    currentTemp = newTemp;
  }
}

void checkTempSafety() {
  if (currentTemp >= TEMP_ALARM && !sysState.temperatureAlarm) {
    sysState.temperatureAlarm = true;
    sysState.buzzerActive = true;
    emergencyStopTemp();
    Serial.print(F("TEMP_ALARM:"));
    Serial.println(currentTemp);
  } else if (currentTemp <= TEMP_SAFE && sysState.temperatureAlarm) {
    sysState.temperatureAlarm = false;
    sysState.buzzerActive = false;
    digitalWrite(BUZZER_PIN, LOW);
    Serial.print(F("TEMP_SAFE:"));
    Serial.println(currentTemp);
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
  Serial.println(F("EMERGENCY_STOP:TEMPERATURE"));
}

void processCommand() {
  String cmd = Serial.readStringUntil('\n');
  cmd.trim();
  if (cmd.length() == 0) return;

  // Her komut için ACK ve mevcut sıcaklık değerini yazdır
  Serial.print(F("ACK:"));
  Serial.print(cmd);
  Serial.print(F(" [TEMP:"));
  Serial.print(currentTemp);
  Serial.println(F("]"));

  if (cmd == F("PING")) {
    Serial.println(F("PONG:v3.3"));
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
  else if (cmd == F("TEMP_DEBUG")) {
    // Yeni debug komutu
    Serial.println(F("=== TEMPERATURE DEBUG ==="));
    Serial.print(F("Raw Temperature: "));
    Serial.println(currentTemp);
    Serial.print(F("Sensor Status: "));
    float testTemp = tempSensor.getTempCByIndex(0);
    Serial.println(testTemp);
    Serial.print(F("Temperature Alarm: "));
    Serial.println(sysState.temperatureAlarm);
    Serial.print(F("Buzzer Active: "));
    Serial.println(sysState.buzzerActive);
    Serial.print(F("Last Read Time: "));
    Serial.println(lastTempRead);
    Serial.println(F("=== DEBUG END ==="));
  } 
  else if (cmd == F("BUZZER_OFF")) {
    if (!sysState.temperatureAlarm) {
      sysState.buzzerActive = false;
      digitalWrite(BUZZER_PIN, LOW);
      Serial.println(F("BUZZER_OFF"));
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
  if (sysState.brakeActive || !sysState.relayBrakeActive || 
      sysState.temperatureAlarm || currentTemp > TEMP_ALARM - 5) {
    Serial.println(F("ERROR:Cannot_arm"));
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
  if (!sysState.armed || sysState.brakeActive || !sysState.relayBrakeActive || 
      sysState.temperatureAlarm || currentTemp > TEMP_ALARM - 3) {
    Serial.println(F("ERROR:Cannot_start"));
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
  Serial.print(F("Temperature:"));
  Serial.println(currentTemp);
  Serial.print(F("TempAlarm:"));
  Serial.println(sysState.temperatureAlarm);
  Serial.print(F("BuzzerActive:"));
  Serial.println(sysState.buzzerActive);
}

void sendStatus() {
  Serial.println(F("STATUS_START"));
  Serial.print(F("Armed:"));
  Serial.println(sysState.armed);
  Serial.print(F("Brake:"));
  Serial.println(sysState.brakeActive);
  Serial.print(F("RelayBrake:"));
  Serial.println(sysState.relayBrakeActive);
  Serial.print(F("Temperature:"));
  Serial.println(currentTemp);
  Serial.print(F("TempAlarm:"));
  Serial.println(sysState.temperatureAlarm);
  Serial.print(F("BuzzerActive:"));
  Serial.println(sysState.buzzerActive);
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
  Serial.print(F("HEARTBEAT:"));
  Serial.print(millis() / 1000);
  Serial.print(',');
  Serial.print(sysState.armed);
  Serial.print(',');
  Serial.print(sysState.brakeActive);
  Serial.print(',');
  Serial.print(sysState.relayBrakeActive);
  Serial.print(',');
  Serial.print(currentTemp);
  Serial.print(',');
  Serial.print(sysState.temperatureAlarm);
  
  byte activeCount = 0;
  for (byte i = 0; i < NUM_MOTORS; i++) {
    if (motorStates[i]) activeCount++;
  }
  Serial.print(',');
  Serial.println(activeCount);
}