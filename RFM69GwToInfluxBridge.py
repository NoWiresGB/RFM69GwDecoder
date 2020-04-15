#!/usr/bin/python3 -u

""" RFM69Gw to InfluxDB Bridge
This script parses the RFM69Gw published MQTT data and stores the measurements in InfluxDB
"""

import re
from typing import NamedTuple
import paho.mqtt.client as mqtt
from influxdb import InfluxDBClient
import pprint
from systemd.daemon import notify, Notification

INFLUXDB_ADDRESS = '192.168.0.254'
INFLUXDB_USER = 'root'
INFLUXDB_PASSWORD = 'root'
INFLUXDB_DATABASE = 'home_iot'

MQTT_ADDRESS = '192.168.0.254'
MQTT_USER = 'mqttuser'
MQTT_PASSWORD = 'mqttpassword'
MQTT_TOPIC = 'RFM69Gw/+/+/+'
MQTT_REGEX = 'RFM69Gw/([^/]+)/([^/]+)/([^/]+)'
MQTT_CLIENT_ID = 'RFM69GwToInfluxDBBridge'

# node type constants
NODEFUNC_POWER_SINGLE = 1
NODEFUNC_POWER_DOUBLE = 2
NODEFUNC_POWER_QUAD = 3

influxdb_client = InfluxDBClient(INFLUXDB_ADDRESS, 8086, INFLUXDB_USER, INFLUXDB_PASSWORD, None)

class SensorData(NamedTuple):
    sensor: str        # node id on the radio network
    measurement: str   # name of the measurement, e.g. power1, temp, etc
    value: float       # value of the measurmement


def on_connect(client, userdata, flags, rc):
    # The callback for when the client receives a CONNACK response from the server.
    print('Connected to MQTT with result code ' + str(rc))
    client.subscribe(MQTT_TOPIC)


def on_message(client, userdata, msg):
    # The callback for when a PUBLISH message is received from the server.
    print('MQTT receive: ' + msg.topic + ' ' + str(msg.payload))
    measurements = _parse_mqtt_message(msg.topic, msg.payload.decode('utf-8'))
    #pprint.pprint(measurements)
    if measurements is not None:
        _send_sensor_data_to_influxdb(measurements)


def _parse_mqtt_message(topic, payload):
    # this will store the return values
    rMeas = []

    match = re.match(MQTT_REGEX, topic)
    if match:
        gwMac = match.group(1)
        radioId = match.group(2)
        data = match.group(3)
        # Sensors have 'sens' in their name
        if 'payload' not in data:
            #print('Not payload')
            return None

        #print('+ GW MAC: ' + gwMac + '\n+ Radio ID: ' + radioId + '\n+ Payload: ' + data)

        # process payload
        # first get the radio ID
        #print('>> processed data')
        radioIdHex = payload[2:4] + payload[0:2]
        radioId = int(radioIdHex, 16)

        sensTypeHex = payload[4:6]
        sensType = int(sensTypeHex, 16)

        # process the rest of the payload based on sensor type
        if (sensType == NODEFUNC_POWER_SINGLE):
            powerHex = payload[8:10] + payload[6:8]
            power = int(powerHex, 16)
            vrmsHex = payload[12:14] + payload[10:12]
            vrms = int(vrmsHex, 16) / 10

            rMeas.append(SensorData(radioId, 'power1', power))
            rMeas.append(SensorData(radioId, 'vrms', vrms))

            return rMeas
        elif (sensType == NODEFUNC_POWER_DOUBLE):
            powerHex = payload[8:10] + payload[6:8]
            power = int(powerHex, 16)
            rMeas.append(SensorData(radioId, 'power1', power))

            powerHex = payload[12:14] + payload[10:12]
            power = int(powerHex, 16)
            rMeas.append(SensorData(radioId, 'power2', power))

            vrmsHex = payload[16:18] + payload[14:16]
            vrms = int(vrmsHex, 16) / 10
            rMeas.append(SensorData(radioId, 'vrms', vrms))

            return rMeas
        elif (sensType == NODEFUNC_POWER_QUAD):
            powerHex = payload[8:10] + payload[6:8]
            power = int(powerHex, 16)
            rMeas.append(SensorData(radioId, 'power1', power))

            powerHex = payload[12:14] + payload[10:12]
            power = int(powerHex, 16)
            rMeas.append(SensorData(radioId, 'power2', power))

            powerHex = payload[16:18] + payload[14:16]
            power = int(powerHex, 16)
            rMeas.append(SensorData(radioId, 'power3', power))

            powerHex = payload[20:22] + payload[18:20]
            power = int(powerHex, 16)
            rMeas.append(SensorData(radioId, 'power4', power))

            vrmsHex = payload[24:26] + payload[22:24]
            vrms = int(vrmsHex, 16) / 10
            rMeas.append(SensorData(radioId, 'vrms', vrms))

            return rMeas
        else:
            # not sure what to do
            return None
    else:
        #print('No match')
        return None


def _send_sensor_data_to_influxdb(sensor_data):
    json_body = []
    for m in sensor_data:
        json_body.append({ 'measurement': m.measurement, 'tags': { 'nodeid' : m.sensor }, 'fields' : { 'value' : m.value }})

    #pprint.pprint(json_body)
    influxdb_client.write_points(json_body)


def _init_influxdb_database():
    databases = influxdb_client.get_list_database()
    # create database if it doesn't exist
    if len(list(filter(lambda x: x['name'] == INFLUXDB_DATABASE, databases))) == 0:
        influxdb_client.create_database(INFLUXDB_DATABASE)
    influxdb_client.switch_database(INFLUXDB_DATABASE)


def main():
    _init_influxdb_database()

    mqtt_client = mqtt.Client(MQTT_CLIENT_ID)
    mqtt_client.username_pw_set(MQTT_USER, MQTT_PASSWORD)
    mqtt_client.on_connect = on_connect
    mqtt_client.on_message = on_message

    mqtt_client.connect(MQTT_ADDRESS, 1883)
    mqtt_client.loop_forever()


if __name__ == '__main__':
    print('RFM69Gw to InfluxDB bridge')

    # notify systemd that we're up and running
    notify(Notification.READY)

    main()
