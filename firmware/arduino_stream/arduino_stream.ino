/*
 * Sundai sensor streamer — Arduino Uno Rev3 / Nano 33 IoT / Uno Q (MCU side).
 *
 * The board is deliberately dumb: read sensors, print one JSON object per line
 * over USB serial, listen for one-word commands back. All intelligence lives on
 * the laptop, where the foundation model runs.
 *
 * Out (every SAMPLE_MS):  {"soil":612,"temp_c":22.4,"lux":410,"btn":0}
 * In  (newline-terminated): PUMP_ON | PUMP_OFF | BUZZ | LED_ON | LED_OFF | PING
 *
 * Wiring (change the pins to match what you actually grabbed):
 *   A0  soil moisture analog out
 *   A1  LDR / light sensor
 *   A2  TMP36 temperature  (swap for DHT11 below if that's what you have)
 *   D2  push button (INPUT_PULLUP)
 *   D7  relay IN   (pump / lamp)
 *   D8  buzzer +
 *   D13 onboard LED
 */

const unsigned long SAMPLE_MS = 100;   // 10 Hz

const int PIN_SOIL  = A0;
const int PIN_LIGHT = A1;
const int PIN_TEMP  = A2;
const int PIN_BTN   = 2;
const int PIN_RELAY = 7;
const int PIN_BUZZ  = 8;
const int PIN_LED   = 13;

unsigned long lastSample = 0;
String inbuf = "";

void setup() {
  Serial.begin(115200);
  pinMode(PIN_BTN, INPUT_PULLUP);
  pinMode(PIN_RELAY, OUTPUT);
  pinMode(PIN_BUZZ, OUTPUT);
  pinMode(PIN_LED, OUTPUT);
  digitalWrite(PIN_RELAY, LOW);
  inbuf.reserve(32);
  // Non-JSON lines are treated as log output by the host, so this is safe.
  Serial.println("sundai streamer ready");
}

void handleCommand(String cmd) {
  cmd.trim();
  if (cmd == "PUMP_ON")       digitalWrite(PIN_RELAY, HIGH);
  else if (cmd == "PUMP_OFF") digitalWrite(PIN_RELAY, LOW);
  else if (cmd == "LED_ON")   digitalWrite(PIN_LED, HIGH);
  else if (cmd == "LED_OFF")  digitalWrite(PIN_LED, LOW);
  else if (cmd == "BUZZ")     { tone(PIN_BUZZ, 2200, 350); }
  else if (cmd == "ALERT")    { tone(PIN_BUZZ, 2800, 700); digitalWrite(PIN_LED, HIGH); }
  else if (cmd == "PING")     Serial.println("pong");
  else                        { Serial.print("unknown cmd: "); Serial.println(cmd); }
}

void loop() {
  while (Serial.available()) {
    char c = (char)Serial.read();
    if (c == '\n') { handleCommand(inbuf); inbuf = ""; }
    else if (c != '\r' && inbuf.length() < 30) inbuf += c;
  }

  unsigned long now = millis();
  if (now - lastSample < SAMPLE_MS) return;
  lastSample = now;

  int soil  = analogRead(PIN_SOIL);
  int light = analogRead(PIN_LIGHT);
  int traw  = analogRead(PIN_TEMP);
  // TMP36: 10 mV/degC, 500 mV offset, 5 V reference over 1024 counts.
  float tempC = ((traw * 5.0 / 1024.0) - 0.5) * 100.0;
  int btn = (digitalRead(PIN_BTN) == LOW) ? 1 : 0;

  Serial.print("{\"soil\":");    Serial.print(soil);
  Serial.print(",\"lux\":");     Serial.print(light);
  Serial.print(",\"temp_c\":");  Serial.print(tempC, 2);
  Serial.print(",\"btn\":");     Serial.print(btn);
  Serial.print(",\"ms\":");      Serial.print(now);
  Serial.println("}");
}
