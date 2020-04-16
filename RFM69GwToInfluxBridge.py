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
import configparser

influxDbAddress = ''
influxDbPort = 0
influxDbUser = ''
influxDbPassword = ''
influxDbDatabase = ''

mqttAddress = ''
mqttPort = 0
mqttUser = ''
mqttPassword = ''
mqttTopic = ''
mqttRegex = ''
mqttClientId = ''

# node type constants
NODEFUNC_POWER_SINGLE = 1
NODEFUNC_POWER_DOUBLE = 2
NODEFUNC_POWER_QUAD = 3

class SensorData(NamedTuple):
    sensor: str        # node id on the radio network
    measurement: str   # name of the measurement, e.g. power1, temp, etc
    value: float       # value of the measurmement

def readConfig():
    global influxDbAddress
    global influxDbPort
    global influxDbUser
    global influxDbPassword
    global influxDbDatabase

    global mqttAddress
    global mqttPort
    global mqttUser
    global mqttPassword
    global mqttTopic
    global mqttRegex
    global mqttClientId

    config = configparser.ConfigParser()
    config.read('/usr/local/etc/rfm69gwtoinfluxbridge.conf')

    try:
        influxDbAddress = config['influxdb']['address']
    except KeyError:
        influxDbAddress = '192.168.0.254'

    try:
        influxDbPort = int(config['influxdb']['port'])
    except KeyError:
        influxDbPort = 8086

    try:
        influxDbUser = config['influxdb']['user']
    except KeyError:
        influxDbUser = 'root'

    try:
        influxDbPassword = config['influxdb']['password']
    except KeyError:
        influxDbPassword = 'root'

    try:
        influxDbDatabase = config['influxdb']['database']
    except KeyError:
        influxDbDatabase = 'home_iot'

    try:
        mqttAddress = config['mqtt']['address']
    except KeyError:
        mqttAddress = '192.168.0.254'

    try:
        mqttPort = int(config['mqtt']['port'])
    except KeyError:
        mqttPort = 1883

    try:
        mqttUser = config['mqtt']['user']
    except KeyError:
        mqttUser = 'mqttuser'

    try:
        mqttPassword = config['mqtt']['password']
    except KeyError:
        mqttPassword = 'mqttpassword'

    try:
        mqttTopic = config['mqtt']['topic']
    except KeyError:
        mqttTopic = 'RFM69Gw/+/+/+'

    try:
        mqttRegex = config['mqtt']['regex']
    except KeyError:
        mqttRegex = 'RFM69Gw/([^/]+)/([^/]+)/([^/]+)'

    try:
        mqttClientId = config['mqtt']['clientId']
    except KeyError:
        mqttClientId = 'RFM69GwToInfluxDBBridge'


def on_connect(client, userdata, flags, rc):
    # The callback for when the client receives a CONNACK response from the server.
    print('Connected to MQTT with result code ' + str(rc))
    client.subscribe(mqttTopic)


def on_message(client, userdata, msg):
    # The callback for when a PUBLISH message is received from the server.
    #print('MQTT receive: ' + msg.topic + ' ' + str(msg.payload))
    measurements = _parse_mqtt_message(msg.topic, msg.payload.decode('utf-8'))
    #pprint.pprint(measurements)
    if measurements is not None:
        _send_sensor_data_to_influxdb(measurements)


def _parse_mqtt_message(topic, payload):
    # this will store the return values
    rMeas = []

    match = re.match(mqttRegex, topic)
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
    influxClient.write_points(json_body)


def _init_influxdb_database():
    databases = influxClient.get_list_database()
    # create database if it doesn't exist
    if len(list(filter(lambda x: x['name'] == influxDbDatabase, databases))) == 0:
        influxClient.create_database(influxDbDatabase)
    influxClient.switch_database(influxDbDatabase)


def main():
    # init InfluxDb
    _init_influxdb_database()

    # init MQTT client
    mqtt_client = mqtt.Client(mqttClientId)
    mqtt_client.username_pw_set(mqttUser, mqttPassword)
    mqtt_client.on_connect = on_connect
    mqtt_client.on_message = on_message

    # open MQTT connection and start listening to messages
    mqtt_client.connect(mqttAddress, mqttPort)
    mqtt_client.loop_forever()


if __name__ == '__main__':
    print('RFM69Gw to InfluxDB bridge')

    # read the config file
    readConfig()

    # notify systemd that we're up and running
    notify(Notification.READY)

    # open the InfluxDB connection
    influxClient = InfluxDBClient(influxDbAddress, influxDbPort, influxDbUser, influxDbPassword, None)

    main()
