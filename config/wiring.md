# Rover Wiring Guide

## L298N Motor Driver → Arduino Mega

```
Arduino Mega          L298N
─────────────────────────────────
D5  (PWM)        →   ENA
D6  (PWM)        →   ENB
D7               →   IN1
D8               →   IN2
D9               →   IN3
D10              →   IN4
GND              →   GND
```

**Motor wiring:**
- Left  motor  → L298N OUT1 / OUT2
- Right motor  → L298N OUT3 / OUT4
- 12V battery  → L298N 12V input
- L298N 5V out → Arduino 5V (if no separate supply)

## CSI Camera → Jetson Nano

- Ribbon cable into CAM0 (30-pin, contacts facing heatsink)
- Ensure cable is fully seated and locking tab is closed

## Arduino Mega → Jetson Nano

- USB-A to USB-B cable
- Jetson sees it as /dev/ttyACM0 (or ttyACM1 if another device)
- Check: `ls /dev/ttyACM*`

## Power distribution

```
12V LiPo ──┬──→ L298N motor supply
           └──→ DC-DC buck (5V 4A) → Jetson Nano barrel jack
```

> Warning: Do NOT power the Jetson from the L298N 5V regulator under load.
> It cannot supply sufficient current. Use a dedicated 5V/4A regulator.

## Optional sensors (recommended for better SLAM)

| Sensor         | Connection | Notes                          |
|----------------|------------|--------------------------------|
| MPU-6050 IMU   | I2C (SDA/SCL on Mega pins 20/21) | 3.3V |
| Wheel encoders | Digital pins D2/D3 (interrupt) | per motor |
| RPLidar A1     | USB → Jetson | replaces camera obstacle detection |
