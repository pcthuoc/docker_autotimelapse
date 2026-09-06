import json
import time
import paho.mqtt.client as mqtt

broker = "mqtt.congnghetimelapse.com"
port = 1883
user = "CAM-KCSHPT"
pw = "nT2A53g5UceB8daBKPWwPg"
topic = f"camera/{user}/cmd"

connected = False
def on_connect(client, userdata, flags, rc, props=None):
    global connected
    print(f"Connected to MQTT broker (rc={rc})")
    connected = True

client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="test_trigger_tool")
client.username_pw_set(user, pw)
client.on_connect = on_connect
client.connect(broker, port, 60)
client.loop_start()

for _ in range(50):
    if connected:
        break
    time.sleep(0.1)

payload = {
    "request_id": f"req-test-{int(time.time())}",
    "command": "capture_now",
    "payload": {}
}

info = client.publish(topic, json.dumps(payload), qos=1)
info.wait_for_publish(timeout=5)
print(f"Published capture_now to {topic} (mid={info.mid})")
time.sleep(2)
client.loop_stop()
client.disconnect()
