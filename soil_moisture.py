#!/usr/bin/env python3
import time
import firebase_admin
from firebase_admin import credentials, db
import RPi.GPIO as GPIO

# 1) Firebase başlat
cred = credentials.Certificate("senosors.json")
firebase_admin.initialize_app(cred, {
    'databaseURL': 'https://senosors-d1e4a-default-rtdb.europe-west1.firebasedatabase.app/'
})

# 2) GPIO ayarları
GPIO.setwarnings(False)
GPIO.setmode(GPIO.BCM)
RELAY_PIN    = 4
MOISTURE_PIN = 17
GPIO.setup(RELAY_PIN, GPIO.OUT)
GPIO.setup(MOISTURE_PIN, GPIO.IN)

# 3) Firebase referansları
soil_ref    = db.reference('soil_moisture')
motor_ref   = db.reference('motor')          # otomatik loglar
manual_ref  = db.reference('motor_manual')   # manuel komutlar

last_manual_ts   = 0
manual_override  = None
last_motor_state = None  # otomatik push için son durum

def timestamp_ms():
    return int(time.time() * 1000)

try:
    while True:
        # — A) Manuel komut oku (ilk iş) —
        manual_data = manual_ref.order_by_child('timestamp') \
                                .limit_to_last(1).get() or {}
        for entry in manual_data.values():
            ts = entry.get('timestamp', 0)
            if ts > last_manual_ts:
                manual_override = entry.get('running_value')
                last_manual_ts = ts
                print(f"[Manual] override={manual_override} at {ts}")

        # — B) Nem oku & logla —
        raw = GPIO.input(MOISTURE_PIN)
        moisture_val = raw  # ihtiyaç varsa `1-raw`
        soil_ref.push({
            'moisture_value': moisture_val,
            'timestamp': timestamp_ms()
        })
        print(f"[Auto] moisture={moisture_val}")

        # — C) Pompa kontrol — 
        if manual_override is not None:
            # Manuel mod: sadece röleyi değiştir, loglama yok
            if manual_override == 1:
                GPIO.output(RELAY_PIN, GPIO.HIGH)
                print("Pump ON (manual)")
            else:
                GPIO.output(RELAY_PIN, GPIO.LOW)
                print("Pump OFF (manual)")
                # Manuel kapama geldi: otomatik moda dön
                manual_override = None
            # Manuel modda otomatik push’u sıfırlayalım
            last_motor_state = None

        else:
            # Otomatik mod: nem bazlı
            desired = 1 if moisture_val == 0 else 0
            GPIO.output(RELAY_PIN, GPIO.HIGH if desired==1 else GPIO.LOW)

            # Sadece durum değiştiyse logla
            if desired != last_motor_state:
                motor_ref.push({
                    'running_value': desired,
                    'timestamp': timestamp_ms()
                })
                print(f"Pump {'ON' if desired==1 else 'OFF'} (auto)")
                last_motor_state = desired

        # — D) Döngü aralığı —
        time.sleep(1)

except KeyboardInterrupt:
    print("Çıkış ve GPIO temizleme")
    GPIO.cleanup()
