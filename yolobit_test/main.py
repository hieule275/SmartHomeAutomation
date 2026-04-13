from mqtt import *
from yolobit import *
from homebit3_dht20 import DHT20
from homebit3_lcd1602 import LCD1602
from homebit3_rgbled import RGBLed
from machine import Pin
from mq import MQ
import time
import music

button_a.on_pressed = None
button_b.on_pressed = None
button_a.on_pressed_ab = button_b.on_pressed_ab = -1

brightness_value = 100
led_state = 'OFF'

fan_speed = 0
fanauto = 'OFF'

security_mode = 'OFF'
alarm_state = 'OFF'

gate_state = 'no one outside'

input_pin = ''
unlock_pin = '2005'
lock_pin = '2023'
door_state = 'LOCKED'

air_quality_state = 'OK'
fire_state = 'SAFE'

dht20 = DHT20()
lcd1602 = LCD1602()
tiny_rgb = RGBLed(pin14.pin, 4)
mq = MQ(Pin(pin1.adc_pin))

last_sensor_send = time.ticks_ms()
last_fan_auto_check = time.ticks_ms()
last_alarm_check = time.ticks_ms()
last_alarm_publish = time.ticks_ms()
last_gate_check = time.ticks_ms()
last_air_check = time.ticks_ms()
last_fire_check = time.ticks_ms()
last_fire_alarm = time.ticks_ms()

def update_lcd_text(line1, line2=''):
    lcd1602.clear()
    lcd1602.move_to(0, 0)
    lcd1602.putstr(str(line1))
    if line2 != '':
        lcd1602.move_to(0, 1)
        lcd1602.putstr(str(line2))

def set_fan_percent(percent):
    global fan_speed
    try:
        percent = int(percent)
    except:
        percent = 0

    if percent < 0:
        percent = 0
    if percent > 100:
        percent = 100

    fan_speed = percent
    pwm_value = round(translate(percent, 0, 100, 0, 1023))
    pin10.write_analog(pwm_value)
    print('Fan speed =', fan_speed)

def update_led():
    global led_state, brightness_value, security_mode

    if security_mode == 'ON':
        display.show(Image("10001:02080:00300:07040:60005"))
        return

    if led_state == 'ON':
        display.set_brightness(brightness_value)
        display.set_all('#ff0000')
    else:
        display.set_all('#000000')

def publish_alarm_state():
    mqtt.publish('indoor/alarm', alarm_state)

def publish_air_state():
    mqtt.publish('indoor/air_quality', air_quality_state)

def publish_fire_state():
    mqtt.publish('indoor/fire', fire_state)

def on_led_message(msg):
    global led_state
    msg = str(msg).strip()

    if msg == 'ON':
        led_state = 'ON'
    elif msg == 'OFF':
        led_state = 'OFF'

    update_led()
    print('LED state =', led_state)

def on_brightness_message(msg):
    global brightness_value
    try:
        brightness_value = int(str(msg).strip())
    except:
        return

    if brightness_value < 0:
        brightness_value = 0
    if brightness_value > 100:
        brightness_value = 100

    update_led()
    print('Brightness =', brightness_value)

def on_fan_message(msg):
    global fanauto
    if fanauto == 'OFF':
        set_fan_percent(str(msg).strip())
        mqtt.publish('indoor/fan_mode', 'MANUAL')
    else:
        print('Manual fan ignored because fanauto = ON')

def on_fanauto_message(msg):
    global fanauto
    msg = str(msg).strip()

    if msg == 'ON':
        fanauto = 'ON'
    else:
        fanauto = 'OFF'

    mqtt.publish('indoor/fanauto_status', fanauto)
    print('Fan auto =', fanauto)

def on_security_message(msg):
    global security_mode, alarm_state
    msg = str(msg).strip()

    if msg == 'ON':
        security_mode = 'ON'
    else:
        security_mode = 'OFF'
        alarm_state = 'OFF'
        publish_alarm_state()

    mqtt.publish('indoor/security_status', security_mode)
    update_led()
    print('Security mode =', security_mode)

def set_door_locked():
    global door_state
    pin6.servo_write(90)
    door_state = 'LOCKED'
    mqtt.publish('indoor/door', door_state)
    print('Door = LOCKED')

def set_door_unlocked():
    global door_state
    pin6.servo_write(180)
    door_state = 'UNLOCKED'
    mqtt.publish('indoor/door', door_state)
    print('Door = UNLOCKED')

def publish_lock_log(message):
    mqtt.publish('indoor/locklog', message)
    print('Lock log =', message)

def process_lock_pin():
    global input_pin, unlock_pin, lock_pin

    if input_pin == unlock_pin:
        update_lcd_text('Come in')
        music.play(music.POWER_UP, wait=True)
        set_door_unlocked()
        publish_lock_log('PIN correct - door unlocked')

    elif input_pin == lock_pin:
        update_lcd_text('Locked')
        music.play(music.POWER_UP, wait=True)
        set_door_locked()
        publish_lock_log('PIN correct - door locked')

    else:
        update_lcd_text('Wrong password')
        music.play(music.POWER_DOWN, wait=True)
        publish_lock_log('PIN wrong')

    input_pin = ''
    mqtt.publish('indoor/lock_input', input_pin)

def on_lock_message(msg):
    global input_pin

    msg = str(msg).strip()

    if msg in ['0','1','2','3','4','5','6','7','8','9']:
        if len(input_pin) < 4:
            input_pin = input_pin + msg
            update_lcd_text(input_pin)
            mqtt.publish('indoor/lock_input', input_pin)

        if len(input_pin) == 4:
            process_lock_pin()

    elif msg == '*':
        input_pin = ''
        update_lcd_text('Cleared')
        mqtt.publish('indoor/lock_input', input_pin)
        publish_lock_log('PIN cleared')

    elif msg == '#':
        if len(input_pin) > 0:
            process_lock_pin()

def send_temp_humi():
    global last_sensor_send

    if time.ticks_diff(time.ticks_ms(), last_sensor_send) >= 5000:
        dht20.read_dht20()

        temp = dht20.dht20_temperature()
        humi = dht20.dht20_humidity()

        temp_str = str(temp)
        humi_str = str(humi)

        update_lcd_text('T:' + temp_str, 'H:' + humi_str)

        mqtt.publish('indoor/nhietdo', temp_str)
        mqtt.publish('indoor/doam', humi_str)

        print('Temp =', temp_str)
        print('Humi =', humi_str)

        last_sensor_send = time.ticks_ms()

def handle_fan_auto():
    global last_fan_auto_check, fanauto

    if fanauto != 'ON':
        return

    if time.ticks_diff(time.ticks_ms(), last_fan_auto_check) < 2000:
        return

    dht20.read_dht20()
    temp = dht20.dht20_temperature()

    if temp < 31:
        auto_speed = 0
    elif temp < 32:
        auto_speed = 20
    elif temp < 33:
        auto_speed = 40
    elif temp < 34:
        auto_speed = 60
    else:
        auto_speed = 80

    set_fan_percent(auto_speed)
    mqtt.publish('indoor/fan', str(auto_speed))
    mqtt.publish('indoor/fan_mode', 'AUTO')

    print('Auto fan by temp =', temp, '=>', auto_speed)

    last_fan_auto_check = time.ticks_ms()

def play_alarm_step():
    music.play(['A5:1'], wait=True)
    music.play(['E5:1'], wait=True)

def handle_security():
    global security_mode, alarm_state, last_alarm_check, last_alarm_publish

    if security_mode != 'ON':
        return

    if pin16.read_digital() == 1:
        if alarm_state != 'ON':
            alarm_state = 'ON'
            publish_alarm_state()
            print('Alarm triggered')

        if time.ticks_diff(time.ticks_ms(), last_alarm_check) >= 1000:
            play_alarm_step()
            last_alarm_check = time.ticks_ms()
    else:
        if alarm_state != 'OFF':
            alarm_state = 'OFF'
            publish_alarm_state()
            print('Alarm cleared')

    if time.ticks_diff(time.ticks_ms(), last_alarm_publish) >= 3000:
        mqtt.publish('indoor/security_status', security_mode)
        mqtt.publish('indoor/alarm', alarm_state)
        last_alarm_publish = time.ticks_ms()

def set_gate_rgb_detected():
    tiny_rgb.show(1, hex_to_rgb('#ff0000'))
    tiny_rgb.show(2, hex_to_rgb('#ffa500'))
    tiny_rgb.show(3, hex_to_rgb('#ffff00'))
    tiny_rgb.show(4, hex_to_rgb('#00ff00'))

def set_gate_rgb_off():
    tiny_rgb.show(0, hex_to_rgb('#000000'))

def handle_gate():
    global gate_state, last_gate_check

    if time.ticks_diff(time.ticks_ms(), last_gate_check) < 1000:
        return

    light_value = round(translate(pin0.read_analog(), 0, 4095, 0, 100))
    motion_value = pin16.read_digital()

    if light_value < 30 and motion_value == 1:
        new_state = 'there is a person outside'
        set_gate_rgb_detected()
    else:
        new_state = 'no one outside'
        set_gate_rgb_off()

    if new_state != gate_state:
        gate_state = new_state
        mqtt.publish('indoor/gate', gate_state)
        print('Gate =', gate_state)

    last_gate_check = time.ticks_ms()

def handle_air_quality():
    global air_quality_state, last_air_check

    if time.ticks_diff(time.ticks_ms(), last_air_check) < 3000:
        return

    air_value = pin1.read_analog()

    if air_value > 35:
        new_state = 'BAD'
    else:
        new_state = 'OK'

    lcd1602.clear()
    lcd1602.move_to(0, 0)
    lcd1602.putstr('Air:' + str(air_value))
    lcd1602.move_to(0, 1)
    lcd1602.putstr(new_state)

    mqtt.publish('indoor/air_value', str(air_value))

    if new_state != air_quality_state:
        air_quality_state = new_state
        publish_air_state()
        print('Air quality =', air_quality_state, 'value =', air_value)

    last_air_check = time.ticks_ms()

def play_fire_alarm_step():
    music.play(['A5:1'], wait=True)
    music.play(['E5:1'], wait=True)

def handle_fire():
    global fire_state, last_fire_check, last_fire_alarm

    if time.ticks_diff(time.ticks_ms(), last_fire_check) < 500:
        return

    if pin2.read_digital() == 0:
        new_state = 'FIRE'
    else:
        new_state = 'SAFE'

    if new_state != fire_state:
        fire_state = new_state
        publish_fire_state()
        print('Fire state =', fire_state)

    if fire_state == 'FIRE':
        lcd1602.clear()
        lcd1602.move_to(0, 0)
        lcd1602.putstr('Alarm')
        lcd1602.move_to(0, 1)
        lcd1602.putstr('Fire detected')

        if time.ticks_diff(time.ticks_ms(), last_fire_alarm) >= 2000:
            play_fire_alarm_step()
            last_fire_alarm = time.ticks_ms()

    last_fire_check = time.ticks_ms()

display.set_brightness(brightness_value)
display.set_all('#000000')
set_fan_percent(0)
set_gate_rgb_off()
set_door_locked()

mqtt.connect_wifi('Cafe', 'hieu2005')
mqtt.connect_broker(server='192.168.1.9', port=1883)

mqtt.on_receive_message('indoor/led', on_led_message)
mqtt.on_receive_message('indoor/brightness', on_brightness_message)
mqtt.on_receive_message('indoor/fan', on_fan_message)
mqtt.on_receive_message('indoor/fanauto', on_fanauto_message)
mqtt.on_receive_message('indoor/security', on_security_message)
mqtt.on_receive_message('indoor/lock', on_lock_message)

mqtt.publish('indoor/fanauto_status', fanauto)
mqtt.publish('indoor/security_status', security_mode)
mqtt.publish('indoor/alarm', alarm_state)
mqtt.publish('indoor/gate', gate_state)
mqtt.publish('indoor/door', door_state)
mqtt.publish('indoor/lock_input', input_pin)
mqtt.publish('indoor/air_quality', air_quality_state)
mqtt.publish('indoor/fire', fire_state)
mqtt.publish('indoor/air_value', '0')

print('MQTT ready')

while True:
    mqtt.check_message()
    send_temp_humi()
    handle_fan_auto()
    handle_security()
    handle_gate()
    handle_air_quality()
    handle_fire()
    time.sleep_ms(100)