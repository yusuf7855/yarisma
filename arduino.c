/*
 * SpectraLoop Motor Control System - Arduino Final v3.2
 * Python Backend ile Full Uyumlu - MPU6050 Removed
 * 6 BLDC Motor + Relay Brake
 * Motor Pin Mapping: Thrust(3,7), Levitation(2,4,5,6)
 */

#include <Servo.h>

// Motor pinleri ve konfigürasyon
const int MOTOR_PINS[] = {2, 4, 5, 6, 3, 7}; // M1,M2,M3,M4,M5,M6
const int NUM_MOTORS = 6;
const int RELAY_BRAKE_PIN = 11; // Relay brake kontrol pini

// Servo nesneleri (ESC kontrolü için)
Servo motors[NUM_MOTORS];

// Motor durumları ve hızları
bool motorStates[NUM_MOTORS] = {false};
int motorSpeeds[NUM_MOTORS] = {0}; // Her motorun kendi hızı (0-100)

// Grup hızları
int levitationGroupSpeed = 0;  // Motorlar 1-4 (pins 2,4,5,6)
int thrustGroupSpeed = 0;      // Motorlar 5-6 (pins 3,7)

// Sistem durumu
bool systemArmed = false;
bool brakeActive = false;
bool relayBrakeActive = false;
unsigned long lastHeartbeat = 0;
unsigned long lastCommandTime = 0;

// ESC kalibrasyonu
const int ESC_MIN = 1000;
const int ESC_MAX = 2000;
const int ESC_NEUTRAL = 1500;

// Timing konfigürasyonu
const unsigned long COMMAND_COOLDOWN = 25;
const unsigned long HEARTBEAT_INTERVAL = 30000;

void setup() {
  Serial.begin(115200);
  Serial.setTimeout(500); // 500ms timeout - daha güvenilir
  
  Serial.println("SpectraLoop Motor Control v3.2");
  Serial.println("Python Backend Compatible");
  Serial.println("6-Motor + Relay Brake - MPU6050 Removed");
  
  // Relay brake pin setup
  pinMode(RELAY_BRAKE_PIN, OUTPUT);
  digitalWrite(RELAY_BRAKE_PIN, LOW); // Relay başlangıçta kapalı
  relayBrakeActive = false;
  
  // Motor başlatma
  for (int i = 0; i < NUM_MOTORS; i++) {
    motors[i].attach(MOTOR_PINS[i]);
    motors[i].writeMicroseconds(ESC_MIN);
    motorStates[i] = false;
    motorSpeeds[i] = 0;
  }
  
  delay(2000); // ESC kalibrasyonu
  
  Serial.println("READY");
  Serial.println("Pin Mapping:");
  Serial.println("Thrust: M5->Pin3, M6->Pin7");
  Serial.println("Levitation: M1->Pin2, M2->Pin4, M3->Pin5, M4->Pin6");
  Serial.println("Relay Brake: Pin8");
  Serial.println();
  Serial.println("Commands:");
  Serial.println("ARM/DISARM");
  Serial.println("MOTOR:1:START:50/MOTOR:1:STOP/MOTOR:1:SPEED:75");
  Serial.println("LEV_GROUP:START:60/LEV_GROUP:STOP/LEV_GROUP:SPEED:80");
  Serial.println("THR_GROUP:START:70/THR_GROUP:STOP/THR_GROUP:SPEED:90");
  Serial.println("BRAKE_ON/BRAKE_OFF");
  Serial.println("RELAY_BRAKE_ON/RELAY_BRAKE_OFF");
  Serial.println("EMERGENCY_STOP");
  Serial.println("STATUS/PING");
  Serial.flush();
}

void loop() {
  unsigned long currentTime = millis();
  
  // Komut işleme
  if (Serial.available() > 0 && (currentTime - lastCommandTime) > COMMAND_COOLDOWN) {
    String command = Serial.readStringUntil('\n');
    command.trim();
    if (command.length() > 0) {
      processCommand(command);
      lastCommandTime = currentTime;
    }
  }
  
  // Heartbeat
  if (currentTime - lastHeartbeat > HEARTBEAT_INTERVAL) {
    lastHeartbeat = currentTime;
    sendHeartbeat();
  }
  
  delay(5);
}

void processCommand(String command) {
  Serial.print("ACK:");
  Serial.println(command);
  
  if (command == "PING") {
    Serial.println("PONG:v3.2");
    
  } else if (command == "ARM") {
    armSystem();
    
  } else if (command == "DISARM") {
    disarmSystem();
    
  } else if (command == "STATUS") {
    sendStatus();
    
  } else if (command == "EMERGENCY_STOP") {
    emergencyStop();
    
  } else if (command == "BRAKE_ON") {
    setBrake(true);
    
  } else if (command == "BRAKE_OFF") {
    setBrake(false);
    
  } else if (command == "RELAY_BRAKE_ON") {
    setRelayBrake(true);
    
  } else if (command == "RELAY_BRAKE_OFF") {
    setRelayBrake(false);
    
  } else if (command.startsWith("MOTOR:")) {
    parseIndividualMotorCommand(command);
    
  } else if (command.startsWith("LEV_GROUP:")) {
    parseLevitationGroupCommand(command);
    
  } else if (command.startsWith("THR_GROUP:")) {
    parseThrustGroupCommand(command);
    
  } else {
    Serial.println("ERROR:Unknown_command");
  }
  
  Serial.flush();
}

void armSystem() {
  if (brakeActive) {
    Serial.println("ERROR:Cannot_arm_brake_active");
    return;
  }
  
  if (!relayBrakeActive) {
    Serial.println("ERROR:Cannot_arm_relay_inactive");
    return;
  }
  
  systemArmed = true;
  Serial.println("ARMED");
}

void disarmSystem() {
  systemArmed = false;
  for (int i = 0; i < NUM_MOTORS; i++) {
    setMotorSpeed(i, 0);
    motorStates[i] = false;
    motorSpeeds[i] = 0;
  }
  levitationGroupSpeed = 0;
  thrustGroupSpeed = 0;
  Serial.println("DISARMED");
}

void setRelayBrake(bool active) {
  relayBrakeActive = active;
  digitalWrite(RELAY_BRAKE_PIN, active ? HIGH : LOW);
  
  if (!active) {
    // Relay devre dışı bırakıldığında tüm motorları durdur
    for (int i = 0; i < NUM_MOTORS; i++) {
      setMotorSpeed(i, 0);
      motorStates[i] = false;
      motorSpeeds[i] = 0;
    }
    levitationGroupSpeed = 0;
    thrustGroupSpeed = 0;
    systemArmed = false; // Sistemi de disarm et
  }
  
  Serial.print("RELAY_BRAKE:");
  Serial.println(active ? "ON" : "OFF");
}

void parseIndividualMotorCommand(String command) {
  if (!systemArmed || brakeActive || !relayBrakeActive) {
    Serial.println("ERROR:System_not_ready");
    return;
  }
  
  // Format: MOTOR:1:START:50 / MOTOR:1:STOP / MOTOR:1:SPEED:75
  int firstColon = command.indexOf(':');
  int secondColon = command.indexOf(':', firstColon + 1);
  int thirdColon = command.indexOf(':', secondColon + 1);
  
  if (firstColon == -1 || secondColon == -1) {
    Serial.println("ERROR:Invalid_motor_command");
    return;
  }
  
  int motorNum = command.substring(firstColon + 1, secondColon).toInt();
  String action = command.substring(secondColon + 1, thirdColon != -1 ? thirdColon : command.length());
  
  if (motorNum < 1 || motorNum > NUM_MOTORS) {
    Serial.println("ERROR:Invalid_motor_number");
    return;
  }
  
  int motorIndex = motorNum - 1;
  
  if (action == "START") {
    int speed = 50; // Default
    if (thirdColon != -1) {
      speed = command.substring(thirdColon + 1).toInt();
    }
    
    if (speed < 0 || speed > 100) {
      Serial.println("ERROR:Invalid_speed");
      return;
    }
    
    motorStates[motorIndex] = true;
    motorSpeeds[motorIndex] = speed;
    setMotorSpeed(motorIndex, speed);
    
    Serial.print("MOTOR_STARTED:");
    Serial.print(motorNum);
    Serial.print(":");
    Serial.println(speed);
    
  } else if (action == "STOP") {
    motorStates[motorIndex] = false;
    motorSpeeds[motorIndex] = 0;
    setMotorSpeed(motorIndex, 0);
    
    Serial.print("MOTOR_STOPPED:");
    Serial.println(motorNum);
    
  } else if (action == "SPEED") {
    if (thirdColon == -1) {
      Serial.println("ERROR:Speed_missing");
      return;
    }
    
    int speed = command.substring(thirdColon + 1).toInt();
    if (speed < 0 || speed > 100) {
      Serial.println("ERROR:Invalid_speed");
      return;
    }
    
    motorSpeeds[motorIndex] = speed;
    if (motorStates[motorIndex]) {
      setMotorSpeed(motorIndex, speed);
    }
    
    Serial.print("MOTOR_SPEED:");
    Serial.print(motorNum);
    Serial.print(":");
    Serial.println(speed);
  }
}

void parseLevitationGroupCommand(String command) {
  if (!systemArmed || brakeActive || !relayBrakeActive) {
    Serial.println("ERROR:System_not_ready");
    return;
  }
  
  int firstColon = command.indexOf(':');
  int secondColon = command.indexOf(':', firstColon + 1);
  
  if (firstColon == -1) {
    Serial.println("ERROR:Invalid_command");
    return;
  }
  
  String action = command.substring(firstColon + 1, secondColon != -1 ? secondColon : command.length());
  
  if (action == "START") {
    int speed = 50; // Default
    if (secondColon != -1) {
      speed = command.substring(secondColon + 1).toInt();
    }
    
    if (speed < 0 || speed > 100) {
      Serial.println("ERROR:Invalid_speed");
      return;
    }
    
    levitationGroupSpeed = speed;
    // Motorlar 1,2,3,4 (index 0,1,2,3)
    for (int i = 0; i < 4; i++) {
      motorStates[i] = true;
      motorSpeeds[i] = speed;
      setMotorSpeed(i, speed);
    }
    
    Serial.print("LEV_GROUP_STARTED:");
    Serial.println(speed);
    
  } else if (action == "STOP") {
    for (int i = 0; i < 4; i++) {
      motorStates[i] = false;
      motorSpeeds[i] = 0;
      setMotorSpeed(i, 0);
    }
    levitationGroupSpeed = 0;
    Serial.println("LEV_GROUP_STOPPED");
    
  } else if (action == "SPEED") {
    if (secondColon == -1) {
      Serial.println("ERROR:Speed_missing");
      return;
    }
    
    int speed = command.substring(secondColon + 1).toInt();
    if (speed < 0 || speed > 100) {
      Serial.println("ERROR:Invalid_speed");
      return;
    }
    
    levitationGroupSpeed = speed;
    for (int i = 0; i < 4; i++) {
      if (motorStates[i]) {
        motorSpeeds[i] = speed;
        setMotorSpeed(i, speed);
      }
    }
    
    Serial.print("LEV_GROUP_SPEED:");
    Serial.println(speed);
  }
}

void parseThrustGroupCommand(String command) {
  if (!systemArmed || brakeActive || !relayBrakeActive) {
    Serial.println("ERROR:System_not_ready");
    return;
  }
  
  int firstColon = command.indexOf(':');
  int secondColon = command.indexOf(':', firstColon + 1);
  
  if (firstColon == -1) {
    Serial.println("ERROR:Invalid_command");
    return;
  }
  
  String action = command.substring(firstColon + 1, secondColon != -1 ? secondColon : command.length());
  
  if (action == "START") {
    int speed = 50; // Default
    if (secondColon != -1) {
      speed = command.substring(secondColon + 1).toInt();
    }
    
    if (speed < 0 || speed > 100) {
      Serial.println("ERROR:Invalid_speed");
      return;
    }
    
    thrustGroupSpeed = speed;
    // Motorlar 5,6 (index 4,5)
    for (int i = 4; i < 6; i++) {
      motorStates[i] = true;
      motorSpeeds[i] = speed;
      setMotorSpeed(i, speed);
    }
    
    Serial.print("THR_GROUP_STARTED:");
    Serial.println(speed);
    
  } else if (action == "STOP") {
    for (int i = 4; i < 6; i++) {
      motorStates[i] = false;
      motorSpeeds[i] = 0;
      setMotorSpeed(i, 0);
    }
    thrustGroupSpeed = 0;
    Serial.println("THR_GROUP_STOPPED");
    
  } else if (action == "SPEED") {
    if (secondColon == -1) {
      Serial.println("ERROR:Speed_missing");
      return;
    }
    
    int speed = command.substring(secondColon + 1).toInt();
    if (speed < 0 || speed > 100) {
      Serial.println("ERROR:Invalid_speed");
      return;
    }
    
    thrustGroupSpeed = speed;
    for (int i = 4; i < 6; i++) {
      if (motorStates[i]) {
        motorSpeeds[i] = speed;
        setMotorSpeed(i, speed);
      }
    }
    
    Serial.print("THR_GROUP_SPEED:");
    Serial.println(speed);
  }
}

void setBrake(bool active) {
  brakeActive = active;
  
  if (active) {
    for (int i = 0; i < NUM_MOTORS; i++) {
      setMotorSpeed(i, 0);
      motorStates[i] = false;
      motorSpeeds[i] = 0;
    }
    levitationGroupSpeed = 0;
    thrustGroupSpeed = 0;
    Serial.println("BRAKE_ON");
  } else {
    Serial.println("BRAKE_OFF");
  }
}

void emergencyStop() {
  systemArmed = false;
  brakeActive = true;
  relayBrakeActive = false;
  digitalWrite(RELAY_BRAKE_PIN, LOW); // Relay'i kapat
  
  for (int i = 0; i < NUM_MOTORS; i++) {
    setMotorSpeed(i, 0);
    motorStates[i] = false;
    motorSpeeds[i] = 0;
  }
  
  levitationGroupSpeed = 0;
  thrustGroupSpeed = 0;
  
  Serial.println("EMERGENCY_STOP");
}

void setMotorSpeed(int motorIndex, int speedPercent) {
  if (motorIndex < 0 || motorIndex >= NUM_MOTORS) return;
  
  int pwmValue;
  if (speedPercent == 0) {
    pwmValue = ESC_MIN;
  } else {
    pwmValue = map(speedPercent, 0, 100, ESC_MIN + 50, ESC_MAX);
  }
  
  motors[motorIndex].writeMicroseconds(pwmValue);
}

void sendStatus() {
  Serial.println("STATUS_START");
  Serial.print("Armed:");
  Serial.println(systemArmed ? "1" : "0");
  Serial.print("Brake:");
  Serial.println(brakeActive ? "1" : "0");
  Serial.print("RelayBrake:");
  Serial.println(relayBrakeActive ? "1" : "0");
  Serial.print("LevGroupSpeed:");
  Serial.println(levitationGroupSpeed);
  Serial.print("ThrGroupSpeed:");
  Serial.println(thrustGroupSpeed);
  
  Serial.print("Motors:");
  for (int i = 0; i < NUM_MOTORS; i++) {
    Serial.print(motorStates[i] ? "1" : "0");
    if (i < NUM_MOTORS - 1) Serial.print(",");
  }
  Serial.println();
  
  Serial.print("IndividualSpeeds:");
  for (int i = 0; i < NUM_MOTORS; i++) {
    Serial.print(motorSpeeds[i]);
    if (i < NUM_MOTORS - 1) Serial.print(",");
  }
  Serial.println();
  
  Serial.print("PinMapping:");
  for (int i = 0; i < NUM_MOTORS; i++) {
    Serial.print(MOTOR_PINS[i]);
    if (i < NUM_MOTORS - 1) Serial.print(",");
  }
  Serial.println();
  
  Serial.println("STATUS_END");
}

void sendHeartbeat() {
  Serial.print("HEARTBEAT:");
  Serial.print(millis() / 1000);
  Serial.print(",");
  Serial.print(systemArmed ? "1" : "0");
  Serial.print(",");
  Serial.print(brakeActive ? "1" : "0");
  Serial.print(",");
  Serial.print(relayBrakeActive ? "1" : "0");
  
  int activeCount = 0;
  for (int i = 0; i < NUM_MOTORS; i++) {
    if (motorStates[i]) activeCount++;
  }
  Serial.print(",");
  Serial.println(activeCount);
}