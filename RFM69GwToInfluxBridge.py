#!/usr/bin/python3 -u

""" RFM69Gw to InfluxDB Bridge
This script parses the RFM69Gw published MQTT data and stores the measurements in InfluxDB
"""

import re
from typing import NamedTuple
import paho.mqtt.client as mqtt
from influxdb import InfluxDBClient
import pprint
import configparser
import logging
import sys
import struct

logLevel = ''

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
NODEFUNC_TEMP_RH = 4
NODEFUNC_TEMP_PRESSURE = 5

class SensorData(NamedTuple):
    sensor: str        # node id on the radio network
    measurement: str   # name of the measurement, e.g. power1, temp, etc
    value: float       # value of the measurmement

def readConfig():
    global logLevel

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

    myLog.info('Reading configuration file')

    config = configparser.ConfigParser()
    config.read('/etc/rfm69gwtoinfluxbridge.conf')

    try:
        logLevel = config['main']['loglevel']
    except KeyError:
        logLevel = 'ERROR'

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
    myLog.info('Connected to MQTT with result code %s', str(rc))
    client.subscribe(mqttTopic)


def on_message(client, userdata, msg):
    # The callback for when a PUBLISH message is received from the server.
    myLog.debug('MQTT receive: %s %s', msg.topic, str(msg.payload))

    # parse received payload
    measurements = _parse_mqtt_message(msg.topic, msg.payload.decode('utf-8'))
    myLog.debug('Parsed measurements: %s', pprint.pformat(measurements))

    # write the measurements into the database
    if measurements is not None:
        _send_sensor_data_to_influxdb(measurements)


def _parse_mqtt_message(topic, payload):
    # this will store the return values
    rMeas = []

    match = re.match(mqttRegex, topic)
    if match:
        try:
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
            elif (sensType == NODEFUNC_TEMP_RH):
                tempHex = payload[8:10] + payload[6:8]
                temp = struct.unpack('>h', bytes.fromhex(tempHex))[0] / 100
                rMeas.append(SensorData(radioId, 'temp', temp))

                rhHex = payload[12:14] + payload[10:12]
                rh = int(rhHex, 16) / 100
                rMeas.append(SensorData(radioId, 'rh', rh))

                rhHex = payload[16:18] + payload[14:16]
                vbatt = int(rhHex, 16)
                rMeas.append(SensorData(radioId, 'vbatt', vbatt))

                return rMeas
            elif (sensType == NODEFUNC_TEMP_PRESSURE):
                tempHex = payload[8:10] + payload[6:8]
                temp = struct.unpack('>h', bytes.fromhex(tempHex))[0] / 100
                rMeas.append(SensorData(radioId, 'temp', temp))

                rhHex = payload[16:18] + payload[14:16] + payload[12:14] + payload[10:12]
                pressure = int(rhHex, 16) / 100
                rMeas.append(SensorData(radioId, 'pressure', pressure))

                rhHex = payload[16:18] + payload[14:16]
                vbatt = int(rhHex, 16)
                rMeas.append(SensorData(radioId, 'vbatt', vbatt))

                return rMeas
            else:
                # not sure what to do
                myLog.error('Unknown sensor type received: %s - %s', topic, payload);
                return None
        except:
            # handle exceptions
            myLog.error('Error while processing message: %s - %s', topic, payload);
    else:
        #print('No match')
        return None


def _send_sensor_data_to_influxdb(sensor_data):
    # construct the JSON
    json_body = []
    for m in sensor_data:
        json_body.append({ 'measurement': m.measurement, 'tags': { 'nodeid' : m.sensor }, 'fields' : { 'value' : m.value }})

    myLog.debug('Writing JSON to DB: %s', pprint.pformat(json_body))

    # write measurements to the database
    influxClient.write_points(json_body)


def _init_influxdb_database():
    databases = influxClient.get_list_database()
    # create database if it doesn't exist
    if len(list(filter(lambda x: x['name'] == influxDbDatabase, databases))) == 0:
        myLog.warning("Database doesn't exists - will create it")
        influxClient.create_database(influxDbDatabase)

    # switch database
    influxClient.switch_database(influxDbDatabase)
    myLog.info('Database selected')


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
    # check the command line parameters
    if len(sys.argv) > 1 and sys.argv[1] == 'config':
        c = open('/etc/rfm69gwtoinfluxbridge.conf.default', 'r')
        lines = c.readlines()
        for l in lines:
            print(l.strip())
        c.close()
        exit()

    # get an instance of the logger object
    myLog = logging.getLogger('RFM69GwToInflux')

    # set loglevel and log format
    logging.basicConfig(format='%(asctime)s [%(levelname)s] %(message)s', level=logging.INFO)
    myLog.info('RFM69Gw to InfluxDB bridge')

    # read the config file
    readConfig()

    # set loglevel
    myLog.setLevel(logging.getLevelName(logLevel))

    # open the InfluxDB connection
    influxClient = InfluxDBClient(influxDbAddress, influxDbPort, influxDbUser, influxDbPassword, None)

    main()
