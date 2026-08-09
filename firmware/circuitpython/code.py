# Sundai sensor streamer — Microchip SAMD21 Curiosity PyKit Ruler (CircuitPython).
#
# Copy this to the board's CIRCUITPY drive as code.py. It streams the Ruler's
# integrated sensors as newline-delimited JSON over USB serial and accepts
# one-word commands back.
#
# The imports are wrapped because the exact sensor breakout on your Ruler may
# differ — a missing sensor drops its channel instead of killing the stream.

import time
import sys
import supervisor

import board

SAMPLE_S = 0.1  # 10 Hz

# ---- optional sensors -----------------------------------------------------
imu = None
try:
    import adafruit_lsm6ds.lsm6dsox as lsm
    imu = lsm.LSM6DSOX(board.I2C())
except Exception:
    pass

env = None
try:
    import adafruit_sht4x
    env = adafruit_sht4x.SHT4x(board.I2C())
except Exception:
    pass

prox = None
try:
    import adafruit_apds9960.apds9960
    prox = adafruit_apds9960.apds9960.APDS9960(board.I2C())
    prox.enable_proximity = True
    prox.enable_color = True
except Exception:
    pass

led = None
try:
    import digitalio
    led = digitalio.DigitalInOut(board.LED)
    led.direction = digitalio.Direction.OUTPUT
except Exception:
    pass


def handle(cmd):
    cmd = cmd.strip()
    if cmd == "LED_ON" and led:
        led.value = True
    elif cmd == "LED_OFF" and led:
        led.value = False
    elif cmd == "ALERT" and led:
        for _ in range(6):
            led.value = not led.value
            time.sleep(0.08)
        led.value = False
    elif cmd == "PING":
        print("pong")
    else:
        print("unknown cmd:", cmd)


print("sundai pykit streamer ready")
buf = ""

while True:
    # non-blocking read of host commands
    while supervisor.runtime.serial_bytes_available:
        ch = sys.stdin.read(1)
        if ch == "\n":
            handle(buf)
            buf = ""
        elif ch != "\r":
            buf += ch

    fields = ['"ms":%d' % (time.monotonic_ns() // 1_000_000)]

    if imu:
        try:
            ax, ay, az = imu.acceleration
            gx, gy, gz = imu.gyro
            fields += ['"accel_x":%.4f' % ax, '"accel_y":%.4f' % ay,
                       '"accel_z":%.4f' % az, '"gyro_x":%.4f' % gx,
                       '"gyro_y":%.4f' % gy, '"gyro_z":%.4f' % gz]
        except Exception:
            pass

    if env:
        try:
            t, h = env.measurements
            fields += ['"temp_c":%.2f' % t, '"humidity":%.2f' % h]
        except Exception:
            pass

    if prox:
        try:
            fields.append('"prox":%d' % prox.proximity)
            r, g, b, c = prox.color_data
            fields += ['"r":%d' % r, '"g":%d' % g, '"b":%d' % b, '"clear":%d' % c]
        except Exception:
            pass

    print("{" + ",".join(fields) + "}")
    time.sleep(SAMPLE_S)
