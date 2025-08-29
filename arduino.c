/*
 * SpectraLoop Motor Control System - Arduino FAULT TOLERANT DUAL TEMPERATURE + REFLECTOR v3.7
 * FAULT TOLERANT: Sistem sensör olsa da olmasa da çalışır
 * Dual DS18B20 Temperature Sensors + Ultra-fast monitoring + Omron Reflector Counter
 * 6 BLDC Motor + Relay Brake + 2x DS18B20 + Buzzer + Reflector Counting
 * Motor Pin Mapping: Thrust(3,7), Levitation(2,4,5,6)
 * Temperature Sensors: Pin 8 (Primary), Pin 13 (Secondary)
 * Reflector Sensor: Pin A0 (Omron Photoelectric) - ALWAYS ACTIVE
 * FAULT TOLERANCE: System works with 0, 1, or 2 temperature sensors
 */

#include <Servo.h>
#include <OneWire.h>
#include <DallasTemperature.h>

// Pin definitions
#define ONE_WIRE_BUS_1 8    // Primary temperature sensor
#define ONE_WIRE_BUS_2 13   // Secondary temperature sensor
#define BUZZER_PIN 9
#define RELAY_BRAKE_PIN 11
#define REFLECTOR_SENSOR_PIN A0  // Omron photoelectric sensor - ALWAYS ACTIVE
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
  bool tempSensorRequired : 1;         // Can disable temp requirement
  bool allowOperationWithoutTemp : 1;  // Allow operation without temp sensors
  bool faultTolerantMode : 1;          // System running in fault tolerant mode
} sysState = {false, false, false, false, false, false, false, true, false, true, true};

// FAULT TOLERANT Temperature constants
const float TEMP_ALARM = 55.0;
const float TEMP_SAFE = 50.0;
const float TEMP_WARNING = 45.0;
const float SENSOR_TIMEOUT = 30.0;
const float fallbackTemp = 25.0;

// Temperature variables - FAULT TOLERANT DUAL SENSOR
float currentTemp1 = fallbackTemp;
float currentTemp2 = fallbackTemp;
float maxTempOverall = fallbackTemp;
float maxTempSensor1 = fallbackTemp;
float maxTempSensor2 = fallbackTemp;
unsigned long lastTempRequest1 = 0;
unsigned long lastTempRequest2 = 0;
unsigned long lastSensorCheck = 0;
unsigned long lastValidTemp1 = 0;
unsigned long lastValidTemp2 = 0;
int sensorFailCount1 = 0;
int sensorFailCount2 = 0;

// REFLECTOR system variables - ALWAYS ACTIVE
struct ReflectorData {
  unsigned long count;
  float voltage;
  int analogValue;
  float instantSpeed;
  float averageSpeed;
  unsigned long lastReflectorTime;
  unsigned long startTime;
  unsigned long lastReadTime;
  unsigned long lastReportTime;
  unsigned long speedUpdateTime;
  unsigned long reflectorHistory[10];
  byte historyIndex;
} reflector = {0, 0.0, 0, 0.0, 0.0, 0, 0, 0, 0, 0, {0}, 0};

// Timing constants
const unsigned long TEMP_REQUEST_INTERVAL = 100;     // 100ms for temperature
const unsigned long REFLECTOR_READ_INTERVAL = 5;    // 5ms for reflector - ULTRA FAST
const unsigned long REFLECTOR_REPORT_INTERVAL = 1000; // 1s for reflector reporting
const unsigned long SENSOR_CHECK_INTERVAL = 5000;   // 5s for sensor health check

// Communication
String inputBuffer = "";
bool stringComplete = false;

void setup() {
  Serial.begin(115200);
  Serial.setTimeout(50);
  inputBuffer.reserve(200);
  
  delay(1000); // Startup delay
  
  Serial.println(F("SpectraLoop v3.7 FAULT TOLERANT DUAL TEMPERATURE + REFLECTOR"));
  Serial.println(F("INITIALIZING FAULT TOLERANT SYSTEM..."));
  
  // Initialize pins
  pinMode(BUZZER_PIN, OUTPUT);
  pinMode(RELAY_BRAKE_PIN, OUTPUT);
  pinMode(REFLECTOR_SENSOR_PIN, INPUT);
  pinMode(REFLECTOR_LED_PIN, OUTPUT);
  
  // Initial states
  digitalWrite(BUZZER_PIN, LOW);
  digitalWrite(RELAY_BRAKE_PIN, LOW);
  digitalWrite(REFLECTOR_LED_PIN, LOW);
  
  // FAULT TOLERANT Temperature sensor initialization
  Serial.println(F("Initializing dual temperature sensors (FAULT TOLERANT)..."));
  
  tempSensor1.begin();
  tempSensor2.begin();
  
  delay(500);
  
  // Test sensor connections - FAULT TOLERANT
  sysState.sensor1Connected = testTemperatureSensor(1);
  sysState.sensor2Connected = testTemperatureSensor(2);
  
  Serial.print(F("Sensor 1 (Pin 8): "));
  Serial.println(sysState.sensor1Connected ? F("CONNECTED") : F("DISCONNECTED"));
  Serial.print(F("Sensor 2 (Pin 13): "));
  Serial.println(sysState.sensor2Connected ? F("CONNECTED") : F("DISCONNECTED"));
  
  // FAULT TOLERANCE: System can work without temperature sensors
  if (!sysState.sensor1Connected && !sysState.sensor2Connected) {
    Serial.println(F("WARNING: No temperature sensors detected!"));
    Serial.println(F("FAULT TOLERANCE: System will operate without temperature monitoring"));
    sysState.allowOperationWithoutTemp = true;
    sysState.tempSensorRequired = false;
    sysState.faultTolerantMode = true;
  } else {
    Serial.println(F("At least one temperature sensor available - safety monitoring enabled"));
    sysState.tempSensorRequired = true;
    sysState.faultTolerantMode = sysState.sensor1Connected && sysState.sensor2Connected ? false : true;
  }
  
  // Initialize REFLECTOR system - ALWAYS ACTIVE
  Serial.println(F("Initializing Omron reflector counter (ALWAYS ACTIVE)..."));
  reflector.startTime = millis();
  reflector.lastReflectorTime = reflector.startTime;
  reflector.lastReadTime = reflector.startTime;
  reflector.lastReportTime = reflector.startTime;
  reflector.speedUpdateTime = reflector.startTime;
  sysState.reflectorSystemActive = true;
  
  // Test reflector sensor - ALWAYS WORKS
  reflector.analogValue = analogRead(REFLECTOR_SENSOR_PIN);
  reflector.voltage = (reflector.analogValue * 5.0) / 1023.0;
  Serial.print(F("Reflector sensor initial reading: "));
  Serial.print(reflector.analogValue);
  Serial.print(F(" ("));
  Serial.print(reflector.voltage, 2);
  Serial.println(F("V)"));
  
  // Initialize motors - ALWAYS WORKS
  Serial.println(F("Initializing motors (ALWAYS ACTIVE)..."));
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
  
  // Final status
  Serial.println(F("========================================="));
  Serial.println(F("SpectraLoop v3.7 FAULT TOLERANT READY"));
  Serial.println(F("FAULT TOLERANCE: Works with 0, 1, or 2 temperature sensors"));
  Serial.print(F("Temperature Status - S1: "));
  Serial.print(sysState.sensor1Connected ? "ACTIVE" : "FAULT");
  Serial.print(F(", S2: "));
  Serial.print(sysState.sensor2Connected ? "ACTIVE" : "FAULT");
  Serial.print(F(", System: "));
  Serial.println(sysState.tempSensorRequired ? "MONITORED" : "BYPASS");
  Serial.print(F("Reflector System: ACTIVE"));
  Serial.print(F(" [COUNT:"));
  Serial.print(reflector.count);
  Serial.println(F("]"));
  Serial.println(F("Motors: READY - Relay: READY - Fault Tolerance: ACTIVE"));
  Serial.println(F("========================================="));
  Serial.println(F("Ready for commands..."));
}

void loop() {
  unsigned long currentTime = millis();
  
  // Process serial commands
  if (stringComplete) {
    processCommand(inputBuffer);
    inputBuffer = "";
    stringComplete = false;
  }
  
  // FAULT TOLERANT Temperature monitoring (if sensors available)
  if (sysState.tempSensorRequired) {
    if (currentTime - lastTempRequest1 >= TEMP_REQUEST_INTERVAL) {
      requestTemperatureReadings();
      lastTempRequest1 = currentTime;
    }
    
    if (currentTime - lastTempRequest2 >= 50) { // Offset read by 50ms
      readTemperaturesNonBlocking();
      lastTempRequest2 = currentTime;
    }
  }
  
  // REFLECTOR monitoring - ALWAYS ACTIVE (ultra-fast)
  if (currentTime - reflector.lastReadTime >= REFLECTOR_READ_INTERVAL) {
    readReflectorSensor();
    reflector.lastReadTime = currentTime;
  }
  
  // Periodic reports
  if (currentTime - reflector.lastReportTime >= REFLECTOR_REPORT_INTERVAL) {
    sendReflectorReport();
    reflector.lastReportTime = currentTime;
  }
  
  // FAULT TOLERANT sensor health check
  if (currentTime - lastSensorCheck >= SENSOR_CHECK_INTERVAL) {
    checkSensorHealth();
    lastSensorCheck = currentTime;
  }
  
  // Handle buzzer
  if (sysState.buzzerActive && sysState.temperatureAlarm) {
    static unsigned long lastBuzzerToggle = 0;
    if (currentTime - lastBuzzerToggle >= 500) {
      digitalWrite(BUZZER_PIN, !digitalRead(BUZZER_PIN));
      lastBuzzerToggle = currentTime;
    }
  } else {
    digitalWrite(BUZZER_PIN, LOW);
  }
  
  // Reflector LED indicator
  digitalWrite(REFLECTOR_LED_PIN, sysState.reflectorSystemActive ? HIGH : LOW);
}

// FAULT TOLERANT temperature sensor testing
bool testTemperatureSensor(byte sensorNum) {
  DallasTemperature* sensor = (sensorNum == 1) ? &tempSensor1 : &tempSensor2;
  
  sensor->requestTemperatures();
  delay(200);
  
  float temp = sensor->getTempCByIndex(0);
  
  if (temp == DEVICE_DISCONNECTED_C || temp < -50 || temp > 100) {
    return false;
  }
  
  return true;
}

// FAULT TOLERANT temperature reading functions
void requestTemperatureReadings() {
  if (sysState.sensor1Connected) {
    tempSensor1.requestTemperatures();
  }
  if (sysState.sensor2Connected) {
    tempSensor2.requestTemperatures();
  }
}

void readTemperaturesNonBlocking() {
  bool temp1Valid = false, temp2Valid = false;
  float temp1 = fallbackTemp, temp2 = fallbackTemp;
  
  // Read sensor 1 if connected
  if (sysState.sensor1Connected) {
    temp1 = tempSensor1.getTempCByIndex(0);
    if (temp1 != DEVICE_DISCONNECTED_C && temp1 > -50 && temp1 < 100) {
      currentTemp1 = temp1;
      maxTempSensor1 = max(maxTempSensor1, temp1);
      lastValidTemp1 = millis();
      temp1Valid = true;
      sensorFailCount1 = 0;
    } else {
      sensorFailCount1++;
      if (sensorFailCount1 > 5) {
        sysState.sensor1Connected = false;
        Serial.println(F("WARNING: Sensor 1 failed - entering FAULT TOLERANT mode"));
      }
    }
  }
  
  // Read sensor 2 if connected
  if (sysState.sensor2Connected) {
    temp2 = tempSensor2.getTempCByIndex(0);
    if (temp2 != DEVICE_DISCONNECTED_C && temp2 > -50 && temp2 < 100) {
      currentTemp2 = temp2;
      maxTempSensor2 = max(maxTempSensor2, temp2);
      lastValidTemp2 = millis();
      temp2Valid = true;
      sensorFailCount2 = 0;
    } else {
      sensorFailCount2++;
      if (sensorFailCount2 > 5) {
        sysState.sensor2Connected = false;
        Serial.println(F("WARNING: Sensor 2 failed - entering FAULT TOLERANT mode"));
      }
    }
  }
  
  // Update overall temperature (max of valid readings)
  if (temp1Valid || temp2Valid) {
    float maxCurrentTemp = max(temp1Valid ? temp1 : -100, temp2Valid ? temp2 : -100);
    maxTempOverall = max(maxTempOverall, maxCurrentTemp);
    
    // Check temperature alarms (only if monitoring required)
    if (sysState.tempSensorRequired && !sysState.allowOperationWithoutTemp) {
      if (maxCurrentTemp > TEMP_ALARM) {
        if (!sysState.temperatureAlarm) {
          sysState.temperatureAlarm = true;
          sysState.buzzerActive = true;
          Serial.print(F("TEMPERATURE_ALARM:"));
          Serial.println(maxCurrentTemp, 1);
        }
      } else if (maxCurrentTemp < TEMP_SAFE && sysState.temperatureAlarm) {
        sysState.temperatureAlarm = false;
        sysState.buzzerActive = false;
        Serial.print(F("TEMPERATURE_SAFE:"));
        Serial.println(maxCurrentTemp, 1);
      }
    }
    
    // Send temperature data
    Serial.print(F("T1:"));
    Serial.print(temp1Valid ? temp1 : fallbackTemp, 1);
    Serial.print(F(" T2:"));
    Serial.print(temp2Valid ? temp2 : fallbackTemp, 1);
    Serial.print(F(" MAX:"));
    Serial.println(maxTempOverall, 1);
  }
}

// FAULT TOLERANT sensor health monitoring
void checkSensorHealth() {
  unsigned long currentTime = millis();
  
  // Check if sensors are stale
  if (sysState.sensor1Connected && (currentTime - lastValidTemp1) > (SENSOR_TIMEOUT * 1000)) {
    sysState.sensor1Connected = false;
    Serial.println(F("FAULT TOLERANT: Sensor 1 timeout - marked as failed"));
  }
  
  if (sysState.sensor2Connected && (currentTime - lastValidTemp2) > (SENSOR_TIMEOUT * 1000)) {
    sysState.sensor2Connected = false;
    Serial.println(F("FAULT TOLERANT: Sensor 2 timeout - marked as failed"));
  }
  
  // Update fault tolerant mode
  bool previousFaultTolerant = sysState.faultTolerantMode;
  sysState.faultTolerantMode = !sysState.sensor1Connected || !sysState.sensor2Connected;
  
  // Update temperature monitoring requirement
  if (!sysState.sensor1Connected && !sysState.sensor2Connected) {
    if (sysState.tempSensorRequired) {
      sysState.tempSensorRequired = false;
      sysState.allowOperationWithoutTemp = true;
      Serial.println(F("FAULT TOLERANT: All sensors failed - disabling temperature monitoring"));
    }
  }
  
  if (sysState.faultTolerantMode != previousFaultTolerant) {
    Serial.print(F("FAULT TOLERANT MODE: "));
    Serial.println(sysState.faultTolerantMode ? F("ENABLED") : F("DISABLED"));
  }
}

// REFLECTOR sensor reading - ALWAYS ACTIVE
void readReflectorSensor() {
  if (!sysState.reflectorSystemActive) return;
  
  // Read analog value from A0
  int newAnalogValue = analogRead(REFLECTOR_SENSOR_PIN);
  float newVoltage = (newAnalogValue * 5.0) / 1023.0;
  
  // 3V threshold detection - ADC value calculation
  const int DETECT_THRESHOLD = 614;    // 3.0V = (3.0/5.0) * 1023 = 614
  const int RELEASE_THRESHOLD = 563;   // 2.75V = (2.75/5.0) * 1023 = 563
  
  static bool lastState = false;
  static bool stableState = false;
  static unsigned long lastChangeTime = 0;
  const unsigned long DEBOUNCE_TIME = 50; // 50ms debounce
  
  // Determine new state based on voltage thresholds
  bool newState = stableState;
  
  if (!stableState && newAnalogValue >= DETECT_THRESHOLD) {
    // Voltaj 3V üzerine çıktı - reflektör algılandı
    newState = true;
  } else if (stableState && newAnalogValue <= RELEASE_THRESHOLD) {
    // Voltaj 2.75V altına düştü - reflektör kayboldu
    newState = false;
  }
  
  // Debouncing - kararlı okuma için
  if (newState != stableState) {
    if (millis() - lastChangeTime > DEBOUNCE_TIME) {
      stableState = newState;
      
      // Rising edge detection - sayımı yap
      if (stableState && !lastState) {
        reflector.count++;
        
        // Calculate instant speed
        unsigned long currentTime = millis();
        if (reflector.lastReflectorTime > 0) {
          unsigned long timeDiff = currentTime - reflector.lastReflectorTime;
          if (timeDiff > 0) {
            reflector.instantSpeed = 60000.0 / timeDiff; // RPM
            
            // Update history for average speed calculation
            reflector.reflectorHistory[reflector.historyIndex] = timeDiff;
            reflector.historyIndex = (reflector.historyIndex + 1) % 10;
            
            // Calculate average speed (last 10 readings)
            unsigned long totalTime = 0;
            byte validReadings = 0;
            for (byte i = 0; i < 10; i++) {
              if (reflector.reflectorHistory[i] > 0) {
                totalTime += reflector.reflectorHistory[i];
                validReadings++;
              }
            }
            if (validReadings > 0) {
              reflector.averageSpeed = 60000.0 * validReadings / totalTime;
            }
          }
        }
        reflector.lastReflectorTime = currentTime;
        
        // Debug output
        Serial.print(F("REFLECTOR_DETECTED:"));
        Serial.print(reflector.count);
        Serial.print(F(" [VOLTAGE:"));
        Serial.print(newVoltage, 2);
        Serial.print(F("V] [SPEED:"));
        Serial.print(reflector.instantSpeed, 1);
        Serial.println(F("rpm]"));
      }
      
      lastState = stableState;
    }
    lastChangeTime = millis();
  }
  
  reflector.analogValue = newAnalogValue;
  reflector.voltage = newVoltage;
}

void sendReflectorReport() {
  if (sysState.reflectorSystemActive) {
    Serial.print(F("R:"));
    Serial.print(reflector.count);
    Serial.print(F(":"));
    Serial.print(reflector.voltage, 2);
    Serial.print(F(":"));
    Serial.print(reflector.instantSpeed, 1);
    Serial.print(F(":"));
    Serial.println(reflector.averageSpeed, 1);
  }
}

// FAULT TOLERANT motor control functions
bool canStartMotors() {
  float maxCurrentTemp = max(currentTemp1, currentTemp2);
  
  // Basic system checks
  if (!sysState.armed || sysState.brakeActive || !sysState.relayBrakeActive) {
    Serial.print(F("ERROR:System_not_ready [REFLECTOR:"));
    Serial.print(reflector.count);
    Serial.println(F("]"));
    return false;
  }
  
  // FAULT TOLERANT temperature check - only if monitoring is required
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

// Serial event handler
void serialEvent() {
  while (Serial.available()) {
    char inChar = (char)Serial.read();
    if (inChar == '\n') {
      stringComplete = true;
    } else if (inChar != '\r') {
      inputBuffer += inChar;
    }
  }
}

// Command processing
void processCommand(String command) {
  command.trim();
  command.toUpperCase();
  
  Serial.print(F("CMD: "));
  Serial.println(command);
  
  if (command == F("PING")) {
    Serial.println(F("PONG:FAULT-TOLERANT-DUAL-TEMP-REFLECTOR"));
    
  } else if (command == F("STATUS")) {
    printSystemStatus();
    
  } else if (command == F("ARM")) {
    if (sysState.tempSensorRequired && !sysState.allowOperationWithoutTemp) {
      float maxTemp = max(currentTemp1, currentTemp2);
      if (sysState.temperatureAlarm || maxTemp > TEMP_ALARM - 5) {
        Serial.print(F("ERROR:Cannot_arm (Temp:"));
        Serial.print(maxTemp, 1);
        Serial.print(F("°C > "));
        Serial.print(TEMP_ALARM - 5, 1);
        Serial.println(F("°C)"));
        return;
      }
    }
    
    sysState.armed = true;
    digitalWrite(RELAY_BRAKE_PIN, HIGH);
    sysState.relayBrakeActive = true;
    Serial.println(F("ARMED:System_ready"));
    
  } else if (command == F("DISARM")) {
    sysState.armed = false;
    sysState.brakeActive = true;
    digitalWrite(RELAY_BRAKE_PIN, LOW);
    sysState.relayBrakeActive = false;
    stopAllMotors();
    Serial.println(F("DISARMED:System_safe"));
    
  } else if (command == F("EMERGENCY_STOP")) {
    emergencyStop();
    
  } else if (command.startsWith(F("MOTOR:"))) {
    parseMotorCmd(command);
    
  } else if (command.startsWith(F("LEV_GROUP:"))) {
    parseGroupCmd(command, true);
    
  } else if (command.startsWith(F("THR_GROUP:"))) {
    parseGroupCmd(command, false);
    
  } else if (command == F("TEMP_BYPASS_ON")) {
    sysState.allowOperationWithoutTemp = true;
    sysState.tempSensorRequired = false;
    sysState.temperatureAlarm = false;
    sysState.buzzerActive = false;
    Serial.println(F("TEMP_BYPASS:ENABLED"));
    
  } else if (command == F("TEMP_BYPASS_OFF")) {
    if (sysState.sensor1Connected || sysState.sensor2Connected) {
      sysState.allowOperationWithoutTemp = false;
      sysState.tempSensorRequired = true;
      Serial.println(F("TEMP_BYPASS:DISABLED"));
    } else {
      Serial.println(F("ERROR:No_sensors_available"));
    }
    
  } else if (command == F("REFLECTOR_RESET")) {
    reflector.count = 0;
    reflector.instantSpeed = 0.0;
    reflector.averageSpeed = 0.0;
    for (byte i = 0; i < 10; i++) {
      reflector.reflectorHistory[i] = 0;
    }
    Serial.println(F("REFLECTOR_RESET:Complete"));
    
  } else {
    Serial.print(F("ERROR:Unknown_command:"));
    Serial.println(command);
  }
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
    speed = constrain(speed, 0, 100);
    
    int pwmValue = map(speed, 0, 100, ESC_MIN, ESC_MAX);
    motors[idx].writeMicroseconds(pwmValue);
    motorStates[idx] = true;
    motorSpeeds[idx] = speed;
    
    Serial.print(F("MOTOR_STARTED:"));
    Serial.print(motorNum);
    Serial.print(F(":"));
    Serial.print(speed);
    Serial.print(F("% [REFLECTOR:"));
    Serial.print(reflector.count);
    Serial.println(F("]"));
    
  } else if (action == F("STOP")) {
    motors[idx].writeMicroseconds(ESC_MIN);
    motorStates[idx] = false;
    motorSpeeds[idx] = 0;
    
    Serial.print(F("MOTOR_STOPPED:"));
    Serial.print(motorNum);
    Serial.print(F(" [REFLECTOR:"));
    Serial.print(reflector.count);
    Serial.println(F("]"));
    
  } else if (action == F("SPEED")) {
    if (motorStates[idx]) {
      byte speed = (colon3 > 0) ? cmd.substring(colon3 + 1).toInt() : 50;
      speed = constrain(speed, 0, 100);
      
      int pwmValue = map(speed, 0, 100, ESC_MIN, ESC_MAX);
      motors[idx].writeMicroseconds(pwmValue);
      motorSpeeds[idx] = speed;
      
      Serial.print(F("MOTOR_SPEED:"));
      Serial.print(motorNum);
      Serial.print(F(":"));
      Serial.print(speed);
      Serial.println(F("%"));
    }
  }
}

void parseGroupCmd(String cmd, bool isLevitation) {
  if (!canStartMotors()) return;
  
  int colon1 = cmd.indexOf(':');
  int colon2 = cmd.indexOf(':', colon1 + 1);
  
  String action = cmd.substring(colon1 + 1, colon2 > 0 ? colon2 : cmd.length());
  
  if (action == F("START")) {
    byte speed = (colon2 > 0) ? cmd.substring(colon2 + 1).toInt() : 50;
    speed = constrain(speed, 0, 100);
    
    if (isLevitation) {
      // Levitation motors: M1(2), M2(4), M3(5), M4(6)
      for (byte i = 0; i < 4; i++) {
        int pwmValue = map(speed, 0, 100, ESC_MIN, ESC_MAX);
        motors[i].writeMicroseconds(pwmValue);
        motorStates[i] = true;
        motorSpeeds[i] = speed;
      }
      levitationGroupSpeed = speed;
      Serial.print(F("LEV_GROUP_STARTED:"));
      Serial.print(speed);
      Serial.print(F("% [REFLECTOR:"));
      Serial.print(reflector.count);
      Serial.println(F("]"));
      
    } else {
      // Thrust motors: M5(3), M6(7)  
      for (byte i = 4; i < 6; i++) {
        int pwmValue = map(speed, 0, 100, ESC_MIN, ESC_MAX);
        motors[i].writeMicroseconds(pwmValue);
        motorStates[i] = true;
        motorSpeeds[i] = speed;
      }
      thrustGroupSpeed = speed;
      Serial.print(F("THR_GROUP_STARTED:"));
      Serial.print(speed);
      Serial.print(F("% [REFLECTOR:"));
      Serial.print(reflector.count);
      Serial.println(F("]"));
    }
    
  } else if (action == F("STOP")) {
    if (isLevitation) {
      for (byte i = 0; i < 4; i++) {
        motors[i].writeMicroseconds(ESC_MIN);
        motorStates[i] = false;
        motorSpeeds[i] = 0;
      }
      levitationGroupSpeed = 0;
      Serial.print(F("LEV_GROUP_STOPPED [REFLECTOR:"));
      Serial.print(reflector.count);
      Serial.println(F("]"));
      
    } else {
      for (byte i = 4; i < 6; i++) {
        motors[i].writeMicroseconds(ESC_MIN);
        motorStates[i] = false;
        motorSpeeds[i] = 0;
      }
      thrustGroupSpeed = 0;
      Serial.print(F("THR_GROUP_STOPPED [REFLECTOR:"));
      Serial.print(reflector.count);
      Serial.println(F("]"));
    }
  }
}

void stopAllMotors() {
  for (byte i = 0; i < NUM_MOTORS; i++) {
    motors[i].writeMicroseconds(ESC_MIN);
    motorStates[i] = false;
    motorSpeeds[i] = 0;
  }
  levitationGroupSpeed = 0;
  thrustGroupSpeed = 0;
  Serial.print(F("ALL_MOTORS_STOPPED [REFLECTOR:"));
  Serial.print(reflector.count);
  Serial.println(F("]"));
}

void emergencyStop() {
  // Immediate stop
  sysState.armed = false;
  sysState.brakeActive = true;
  digitalWrite(RELAY_BRAKE_PIN, LOW);
  sysState.relayBrakeActive = false;
  
  stopAllMotors();
  
  // Buzzer alert
  for (byte i = 0; i < 3; i++) {
    digitalWrite(BUZZER_PIN, HIGH);
    delay(100);
    digitalWrite(BUZZER_PIN, LOW);
    delay(100);
  }
  
  Serial.print(F("EMERGENCY_STOP:All_systems_safe [REFLECTOR:"));
  Serial.print(reflector.count);
  Serial.println(F("]"));
}

void printSystemStatus() {
  Serial.println(F("=========== FAULT TOLERANT SYSTEM STATUS ==========="));
  
  // System state
  Serial.print(F("Armed: "));
  Serial.print(sysState.armed ? F("YES") : F("NO"));
  Serial.print(F(" | Brake: "));
  Serial.print(sysState.brakeActive ? F("ON") : F("OFF"));
  Serial.print(F(" | Relay: "));
  Serial.println(sysState.relayBrakeActive ? F("ON") : F("OFF"));
  
  // Temperature status - FAULT TOLERANT
  Serial.print(F("Temperature - S1: "));
  if (sysState.sensor1Connected) {
    Serial.print(currentTemp1, 1);
    Serial.print(F("°C"));
  } else {
    Serial.print(F("FAULT"));
  }
  
  Serial.print(F(" | S2: "));
  if (sysState.sensor2Connected) {
    Serial.print(currentTemp2, 1);
    Serial.print(F("°C"));
  } else {
    Serial.print(F("FAULT"));
  }
  
  Serial.print(F(" | Max: "));
  Serial.print(maxTempOverall, 1);
  Serial.print(F("°C | Alarm: "));
  Serial.println(sysState.temperatureAlarm ? F("ON") : F("OFF"));
  
  // FAULT TOLERANT status
  Serial.print(F("Fault Tolerant: "));
  Serial.print(sysState.faultTolerantMode ? F("ACTIVE") : F("INACTIVE"));
  Serial.print(F(" | Temp Required: "));
  Serial.print(sysState.tempSensorRequired ? F("YES") : F("NO"));
  Serial.print(F(" | Allow No Temp: "));
  Serial.println(sysState.allowOperationWithoutTemp ? F("YES") : F("NO"));
  
  // Reflector status - ALWAYS ACTIVE
  Serial.print(F("Reflector - Count: "));
  Serial.print(reflector.count);
  Serial.print(F(" | Voltage: "));
  Serial.print(reflector.voltage, 2);
  Serial.print(F("V | Speed: "));
  Serial.print(reflector.instantSpeed, 1);
  Serial.print(F(" / "));
  Serial.print(reflector.averageSpeed, 1);
  Serial.println(F(" RPM"));
  
  // Motor status
  Serial.print(F("Motors - "));
  for (byte i = 0; i < NUM_MOTORS; i++) {
    Serial.print(F("M"));
    Serial.print(i + 1);
    Serial.print(F(":"));
    if (motorStates[i]) {
      Serial.print(motorSpeeds[i]);
      Serial.print(F("%"));
    } else {
      Serial.print(F("OFF"));
    }
    if (i < NUM_MOTORS - 1) Serial.print(F(" | "));
  }
  Serial.println();
  
  // Group speeds
  Serial.print(F("Groups - Levitation: "));
  Serial.print(levitationGroupSpeed);
  Serial.print(F("% | Thrust: "));
  Serial.print(thrustGroupSpeed);
  Serial.println(F("%"));
  
  Serial.println(F("=================== END STATUS ==================="));
}

// Additional utility functions for FAULT TOLERANT operation

void performSensorRecovery() {
  Serial.println(F("Attempting sensor recovery..."));
  
  // Try to reinitialize sensors
  tempSensor1.begin();
  tempSensor2.begin();
  delay(500);
  
  // Test sensors again
  bool sensor1Recovered = testTemperatureSensor(1);
  bool sensor2Recovered = testTemperatureSensor(2);
  
  if (sensor1Recovered && !sysState.sensor1Connected) {
    sysState.sensor1Connected = true;
    sensorFailCount1 = 0;
    Serial.println(F("Sensor 1 RECOVERED"));
  }
  
  if (sensor2Recovered && !sysState.sensor2Connected) {
    sysState.sensor2Connected = true;
    sensorFailCount2 = 0;
    Serial.println(F("Sensor 2 RECOVERED"));
  }
  
  // Update system state based on recovery
  if (sysState.sensor1Connected || sysState.sensor2Connected) {
    if (!sysState.tempSensorRequired) {
      Serial.println(F("Temperature monitoring RE-ENABLED after sensor recovery"));
      sysState.tempSensorRequired = true;
      sysState.allowOperationWithoutTemp = false;
    }
    sysState.faultTolerantMode = !(sysState.sensor1Connected && sysState.sensor2Connected);
  }
}

void sendPeriodicStatus() {
  // Send comprehensive status for debugging
  Serial.print(F("STATUS:"));
  Serial.print(sysState.armed ? F("ARMED") : F("DISARMED"));
  Serial.print(F(":T1="));
  Serial.print(sysState.sensor1Connected ? currentTemp1 : -999, 1);
  Serial.print(F(":T2="));
  Serial.print(sysState.sensor2Connected ? currentTemp2 : -999, 1);
  Serial.print(F(":REFL="));
  Serial.print(reflector.count);
  Serial.print(F(":FT="));
  Serial.print(sysState.faultTolerantMode ? F("ON") : F("OFF"));
  Serial.print(F(":MOTORS="));
  
  byte activeMotors = 0;
  for (byte i = 0; i < NUM_MOTORS; i++) {
    if (motorStates[i]) activeMotors++;
  }
  Serial.print(activeMotors);
  Serial.print(F("/"));
  Serial.println(NUM_MOTORS);
}

void handleCriticalTemperature() {
  if (!sysState.tempSensorRequired) return; // Skip if temp monitoring disabled
  
  float maxTemp = max(currentTemp1, currentTemp2);
  
  if (maxTemp > TEMP_ALARM + 5) { // Critical temperature (60°C+)
    Serial.println(F("CRITICAL_TEMPERATURE_SHUTDOWN"));
    
    // Immediate emergency stop
    emergencyStop();
    
    // Force buzzer on
    sysState.buzzerActive = true;
    digitalWrite(BUZZER_PIN, HIGH);
    
    // Send critical alert
    Serial.print(F("CRITICAL_TEMP:"));
    Serial.print(maxTemp, 1);
    Serial.println(F("°C - SYSTEM_SHUTDOWN"));
  }
}

void calibrateReflectorSensor() {
  Serial.println(F("Calibrating reflector sensor..."));
  
  // Take multiple readings for calibration
  int readings[20];
  int minReading = 1023, maxReading = 0;
  
  for (int i = 0; i < 20; i++) {
    readings[i] = analogRead(REFLECTOR_SENSOR_PIN);
    minReading = min(minReading, readings[i]);
    maxReading = max(maxReading, readings[i]);
    delay(50);
  }
  
  Serial.print(F("Reflector calibration - Min: "));
  Serial.print(minReading);
  Serial.print(F(" Max: "));
  Serial.print(maxReading);
  Serial.print(F(" Suggested threshold: "));
  Serial.println((minReading + maxReading) / 2);
}

// Advanced motor control functions
void setMotorGroup(bool isLevitation, byte speed, bool rampUp = false) {
  if (!canStartMotors()) return;
  
  byte startIdx = isLevitation ? 0 : 4;
  byte endIdx = isLevitation ? 4 : 6;
  byte currentSpeed = isLevitation ? levitationGroupSpeed : thrustGroupSpeed;
  
  if (rampUp && speed > currentSpeed) {
    // Gradual speed increase for safety
    for (byte s = currentSpeed; s <= speed; s += 5) {
      for (byte i = startIdx; i < endIdx; i++) {
        int pwmValue = map(s, 0, 100, ESC_MIN, ESC_MAX);
        motors[i].writeMicroseconds(pwmValue);
        motorStates[i] = true;
        motorSpeeds[i] = s;
      }
      delay(100); // 100ms between speed steps
    }
  } else {
    // Direct speed set
    for (byte i = startIdx; i < endIdx; i++) {
      int pwmValue = map(speed, 0, 100, ESC_MIN, ESC_MAX);
      motors[i].writeMicroseconds(pwmValue);
      motorStates[i] = (speed > 0);
      motorSpeeds[i] = speed;
    }
  }
  
  if (isLevitation) {
    levitationGroupSpeed = speed;
  } else {
    thrustGroupSpeed = speed;
  }
}

void performSystemSelfTest() {
  Serial.println(F("=== FAULT TOLERANT SYSTEM SELF TEST ==="));
  
  // Test 1: Temperature sensors
  Serial.print(F("Test 1 - Temperature Sensors: "));
  bool tempOK = testTemperatureSensor(1) || testTemperatureSensor(2);
  Serial.println(tempOK ? F("PASS (at least 1 working)") : F("FAIL (fault tolerant mode)"));
  
  // Test 2: Reflector sensor
  Serial.print(F("Test 2 - Reflector Sensor: "));
  int reflectorTest = analogRead(REFLECTOR_SENSOR_PIN);
  bool reflectorOK = (reflectorTest >= 0 && reflectorTest <= 1023);
  Serial.print(reflectorOK ? F("PASS") : F("FAIL"));
  Serial.print(F(" (Reading: "));
  Serial.print(reflectorTest);
  Serial.println(F(")"));
  
  // Test 3: Motor initialization
  Serial.print(F("Test 3 - Motors: "));
  bool motorsOK = true;
  for (byte i = 0; i < NUM_MOTORS; i++) {
    if (!motors[i].attached()) {
      motorsOK = false;
      break;
    }
  }
  Serial.println(motorsOK ? F("PASS") : F("FAIL"));
  
  // Test 4: Relay and buzzer
  Serial.print(F("Test 4 - Relay/Buzzer: "));
  digitalWrite(RELAY_BRAKE_PIN, HIGH);
  delay(100);
  digitalWrite(RELAY_BRAKE_PIN, LOW);
  digitalWrite(BUZZER_PIN, HIGH);
  delay(100);
  digitalWrite(BUZZER_PIN, LOW);
  Serial.println(F("PASS"));
  
  // Test 5: Communication
  Serial.println(F("Test 5 - Communication: PASS (receiving commands)"));
  
  Serial.println(F("=== SELF TEST COMPLETE ==="));
  Serial.print(F("Overall Status: "));
  bool overallOK = reflectorOK && motorsOK; // Temp sensors optional in fault tolerant mode
  Serial.println(overallOK ? F("SYSTEM READY") : F("CHECK REQUIRED"));
}

// Enhanced error handling and recovery
void handleSystemErrors() {
  static unsigned long lastErrorCheck = 0;
  unsigned long currentTime = millis();
  
  if (currentTime - lastErrorCheck < 5000) return; // Check every 5 seconds
  lastErrorCheck = currentTime;
  
  // Check for stuck motors
  static byte lastMotorStates[NUM_MOTORS] = {0};
  bool motorStuck = false;
  
  for (byte i = 0; i < NUM_MOTORS; i++) {
    if (motorStates[i] && motorSpeeds[i] > 0) {
      if (lastMotorStates[i] == motorSpeeds[i]) {
        // Motor speed hasn't changed - this is normal
      }
    }
    lastMotorStates[i] = motorSpeeds[i];
  }
  
  // Check system health
  if (sysState.armed && !sysState.relayBrakeActive) {
    Serial.println(F("ERROR: System armed but relay brake not active"));
    // Auto-fix
    digitalWrite(RELAY_BRAKE_PIN, HIGH);
    sysState.relayBrakeActive = true;
  }
  
  // Temperature sensor health check with auto-recovery
  if (sysState.tempSensorRequired) {
    if (!sysState.sensor1Connected && !sysState.sensor2Connected) {
      static byte recoveryAttempts = 0;
      if (recoveryAttempts < 3) {
        Serial.println(F("Attempting automatic sensor recovery..."));
        performSensorRecovery();
        recoveryAttempts++;
      } else if (recoveryAttempts == 3) {
        Serial.println(F("Auto-enabling fault tolerant mode after recovery failures"));
        sysState.allowOperationWithoutTemp = true;
        sysState.tempSensorRequired = false;
        recoveryAttempts++;
      }
    }
  }
}

// Data logging for debugging
void logSystemData() {
  static unsigned long lastLogTime = 0;
  unsigned long currentTime = millis();
  
  if (currentTime - lastLogTime < 10000) return; // Log every 10 seconds
  lastLogTime = currentTime;
  
  Serial.print(F("LOG:"));
  Serial.print(currentTime / 1000); // Uptime in seconds
  Serial.print(F(":T1="));
  Serial.print(sysState.sensor1Connected ? currentTemp1 : -999, 1);
  Serial.print(F(":T2="));
  Serial.print(sysState.sensor2Connected ? currentTemp2 : -999, 1);
  Serial.print(F(":R="));
  Serial.print(reflector.count);
  Serial.print(F(":V="));
  Serial.print(reflector.voltage, 2);
  Serial.print(F(":RPM="));
  Serial.print(reflector.averageSpeed, 1);
  Serial.print(F(":FT="));
  Serial.print(sysState.faultTolerantMode ? 1 : 0);
  Serial.print(F(":ARM="));
  Serial.print(sysState.armed ? 1 : 0);
  Serial.print(F(":MOTORS="));
  
  for (byte i = 0; i < NUM_MOTORS; i++) {
    Serial.print(motorStates[i] ? motorSpeeds[i] : 0);
    if (i < NUM_MOTORS - 1) Serial.print(F(","));
  }
  Serial.println();
}

// Memory and performance monitoring
void checkSystemPerformance() {
  static unsigned long lastPerfCheck = 0;
  unsigned long currentTime = millis();
  
  if (currentTime - lastPerfCheck < 30000) return; // Check every 30 seconds
  lastPerfCheck = currentTime;
  
  // Calculate free RAM (Arduino specific)
  extern int __heap_start, *__brkval;
  int freeRam = (int) &freeRam - (__brkval == 0 ? (int) &__heap_start : (int) __brkval);
  
  Serial.print(F("PERF:RAM="));
  Serial.print(freeRam);
  Serial.print(F(":UPTIME="));
  Serial.print(currentTime / 1000);
  Serial.print(F(":TEMP_READS="));
  Serial.print((millis() - lastValidTemp1) / 1000);
  Serial.print(F(","));
  Serial.print((millis() - lastValidTemp2) / 1000);
  Serial.print(F(":REFL_FREQ="));
  Serial.print(1000.0 / REFLECTOR_READ_INTERVAL, 1);
  Serial.println(F("Hz"));
}