import json
import os
import picamera
import re
import ssl
import subprocess
import sys
import time
from subprocess import PIPE, Popen
from threading import Lock
from concurrent.futures import ThreadPoolExecutor
import gpiozero
import boto3
from AWSIoTPythonSDK.MQTTLib import AWSIoTMQTTShadowClient


mutex = Lock()
executors = ThreadPoolExecutor(max_workers = 3)
serverproc = Popen(["ls"])
process_list = list()
live_stream_process = Popen(["ls"])
camera = picamera.PiCamera()


#Function that will cause an LED light to blink on and off
def pulse(light):
    light.on()
    time.sleep(2)
    light.off()
    time.sleep(2)
    light.on()
    time.sleep(2)
    light.off()
    time.sleep(2)
    light.on()
    time.sleep(2)
    light.off()

#Custom Callback method
#Callback methods are used with shadow operations to get the shadow document
#of the device in AWS. Once it has been retrieved we read the document and perform
#the appropriate action
def light_shadow_get_callback(payload, responseStatus, token):
    global led
    global device_shadow2
    payload_dict = json.loads(payload)
    device_type = payload_dict["state"]["reported"]["type"]
    
    if payload_dict["state"]["reported"]["command"] == "TURN_ON":
            led.on()
    elif payload_dict["state"]["reported"]["command"] == "TURN_OFF":
        led.off()
    else:
        pulse(led)

#Custom Callback method
#Callback methods are used with shadow operations to get the shadow document
#of the device in AWS. Once it has been retrieved we read the document and perform
#the appropriate action
def shadow_get_callback(payload, responseStatus, token):
    global s3
    global camera
    global bucket_name
    global device_shadow
    global serverproc
    global live_stream_process
    global process_list
    liveswitch = 0
    new_live_stream_url = ""
    payload_dict = json.loads(payload)
    device_type = payload_dict["state"]["reported"]["type"]
    url = payload_dict["state"]["desired"]["url"]
    if device_type == "CAMERA":
        if payload_dict["state"]["reported"]["camera"] == True:
            mutex.acquire()
            if not process_list:
                killAll(process_list)
            camera.close()
            camera = picamera.PiCamera()
            camera.capture('demo.png')
            s3.upload_file('demo.png', bucket_name, 'demo.png')
            camera.close()
            mutex.release()
            payload_dict["state"]["desired"]["camera"] = False
            future = executors.submit(update, {'payload':payload_dict})
            print(device_shadow.shadowUpdate(
                json.dumps(payload_dict), None, 5))
    
        elif payload_dict["state"]["reported"]["stream"] == True and payload_dict["state"]["reported"]["url"]== "" and payload_dict["state"]["desired"]["url"] == "" and payload_dict["state"]["reported"]["kill_stream"] == False:
            liveswitch = 1
            camera.close()
            try:
                serverproc = Popen(["ssh", "-o", "ServerAliveInterval=60", "-R",
                                    "80:localhost:8000", "serveo.net"], stdout=open("output.txt", "w"))
                process_list.append(serverproc)
        except subprocess.CalledProcessError as e:
                print(e)
                return
            time.sleep(2)
            with open('output.txt') as f:
                new_live_stream_url = f.readline().strip('\n').strip('\r')
                new_live_stream_url = new_live_stream_url[new_live_stream_url.rfind('https'):]
            payload_dict["state"]["desired"]["url"] = new_live_stream_url
            try:
                live_stream_process = Popen(["python3", "livestream.py"
                                ], stdout=subprocess.PIPE)
                                process_list.append(live_stream_process)
                out, error = live_stream_process.communicate()
                out = int.from_bytes(out, byteorder='big')
                if out != 0:
                else:
                    future = executors.submit(update, {'payload':payload_dict})
            except AssertionError as e:
        elif payload_dict["state"]["reported"]["kill_stream"] == True:
                killAll(process_list)


#Function used for updating the shadow document for the device.
#Updating rhe shadow is needed so that program does not repeatedly
#keep doing the action the user requested
def update(payload):
    state = payload["payload"]
    try:
        state["state"].pop("delta")
    except KeyError as e:
        pass
    finally:
        return device_shadow.shadowUpdate(json.dumps(state),None,5)
def killAll(processList):
    for i in processList:
        i.kill()


led = gpiozero.LED(21)
s3 = boto3.client('CLIENT_ID','ACCESS KEY', 'SECRET ACCESS KEY', region_name = 'us-east-1')

bucket_name = 'YOUR BUCKET NAME'

shadow_client = AWSIoTMQTTShadowClient("CLIENT ID")
shadow_client.configureEndpoint("YOUR ENDPOINT", 8883)
shadow_client.configureCredentials("ROOT CA","YOUR PRIVATE KEY", "YOUR CERTIFICATE")
device_shadow = shadow_client.createShadowHandlerWithName(
    "Room_security_1", True)
device_shadow2 = shadow_client.createShadowHandlerWithName(
    "Garage_Lights_1", True)
shadow_client.configureConnectDisconnectTimeout(10)
shadow_client.configureMQTTOperationTimeout(5)
shadow_client.connect(1200)

while True:
    device_shadow.shadowGet(shadow_get_callback, 5)
    time.sleep(2)
    device_shadow2.shadowGet(light_shadow_get_callback, 5)
    time.sleep(2)
