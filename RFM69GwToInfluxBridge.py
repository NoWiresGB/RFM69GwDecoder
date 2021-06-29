#!/usr/bin/python3 -u

# -*- coding: latin-1 -*-

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
import time
import signal
import argparse
import json

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
NODEFUNC_TRIGGER = 6

class SensorData(NamedTuple):
    sensor: str        # node id on the radio network
    measurement: str   # name of the measurement, e.g. power1, temp, etc
    value: float       # value of the measurmement

def readConfig(confFile):
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

    global rebroadcastEnabled
    global rebroadcastSensors
    global rebroadcastTopic

    myLog.info('Reading configuration file')

    config = configparser.ConfigParser()
    if confFile:
        myLog.info('Using config file: ' + confFile)
        config.read(confFile)
    else:
        config.read('/app/rfm69gwtoinfluxbridge.conf')

    try:
        logLevel = config['main']['loglevel']
    except KeyError:
        logLevel = 'ERROR'
        myLog.info('Defaulting to loglevel: ERROR')

    try:
        influxDbAddress = config['influxdb']['address']
    except KeyError:
        influxDbAddress = '192.168.0.254'
        myLog.info('Defaulting to InfluxDb address: 192.168.0.254')

    try:
        influxDbPort = int(config['influxdb']['port'])
    except KeyError:
        influxDbPort = 8086
        myLog.info('Defaulting to InfluxDb port: 8086')

    try:
        influxDbUser = config['influxdb']['user']
    except KeyError:
        influxDbUser = 'root'
        myLog.info('Defaulting to InfluxDb user: root')

    try:
        influxDbPassword = config['influxdb']['password']
    except KeyError:
        influxDbPassword = 'root'
        myLog.info('Defaulting to InfluxDb password: root')

    try:
        influxDbDatabase = config['influxdb']['database']
    except KeyError:
        influxDbDatabase = 'home_iot'
        myLog.info('Defaulting to InfluxDb database: home_iot')

    try:
        mqttAddress = config['mqtt']['address']
    except KeyError:
        mqttAddress = '192.168.0.254'
        myLog.info('Defaulting to MQTT address: 192.168.0.254')

    try:
        mqttPort = int(config['mqtt']['port'])
    except KeyError:
        mqttPort = 1883
        myLog.info('Defaulting to MQTT port: 1883')

    try:
        mqttUser = config['mqtt']['user']
    except KeyError:
        mqttUser = 'mqttuser'
        myLog.info('Defaulting to MQTT user: mqttuser')

    try:
        mqttPassword = config['mqtt']['password']
    except KeyError:
        mqttPassword = 'mqttpassword'
        myLog.info('Defaulting to MQTT password: mqttpassword')

    try:
        mqttTopic = config['mqtt']['topic']
    except KeyError:
        mqttTopic = 'RFM69Gw/+/+/+'
        myLog.info('Defaulting to MQTT topic: RFM69Gw/+/+/+')

    try:
        mqttRegex = config['mqtt']['regex']
    except KeyError:
        mqttRegex = 'RFM69Gw/([^/]+)/([^/]+)/([^/]+)'
        myLog.info('Defaulting to MQTT regex: RFM69Gw/([^/]+)/([^/]+)/([^/]+)')

    try:
        mqttClientId = config['mqtt']['clientId']
    except KeyError:
        mqttClientId = 'RFM69GwToInfluxDBBridge'
        myLog.info('Defaulting to MQTT client ID: RFM69GwToInfluxDBBridge')

    try:
        rebroadcastEnabled = config['rebroadcast'].getboolean('enabled')
    except KeyError:
        rebroadcastEnabled = False
        myLog.info('Defaulting to rebroadcast enabled: False')

    try:
        #rebroadcastSensors = config['rebroadcast']['sensor_list']
        rebroadcastSensors = json.loads(config.get('rebroadcast','sensor_list'))
    except KeyError:
        rebroadcastSensors = []
        myLog.info('Defaulting to rebroadcast sensor list: <empty>')

    try:
        rebroadcastTopic = config['rebroadcast']['topic']
    except KeyError:
        rebroadcastTopic = 'RFM69Bridge'
        myLog.info('Defaulting to rebroadcast topic: RFM69Bridge')


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

            if 'payload' not in data:
                #print('Not payload')
                return None

            #print('+ GW MAC: ' + gwMac + '\n+ Radio ID: ' + radioId + '\n+ Payload: ' + data)

            # process payload
            # first get the radio ID
            radioIdHex = payload[2:4] + payload[0:2]
            radioId = int(radioIdHex, 16)

            # get the sensor type
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
            elif (sensType == NODEFUNC_TRIGGER):
                rhHex = payload[6:8]
                trigger = int(rhHex, 16)
                rMeas.append(SensorData(radioId, 'trigger', trigger))

                rhHex = payload[10:12] + payload[8:10]
                vbatt = int(rhHex, 16)
                rMeas.append(SensorData(radioId, 'vbatt', vbatt))

                return rMeas
            else:
                # not sure what to do
                myLog.error('Unknown sensor type received: %s - %s', topic, payload)
                return None
        except:
            # handle exceptions
            myLog.error('Error while processing message: %s - %s', topic, payload)
    else:
        #print('No match')
        return None


def _send_sensor_data_to_influxdb(sensor_data):
    # construct the JSON
    json_body = []
    for m in sensor_data:
        json_body.append({ 'measurement': m.measurement, 'tags': { 'nodeid' : m.sensor }, 'fields' : { 'value' : m.value }})

    myLog.debug('Writing JSON to DB: %s', pprint.pformat(json_body))

    try:
        # write measurements to the database
        influxClient.write_points(json_body)
    except:
        myLog.error("Exception while writing data to database")

    # check if we need to rebroadcast the unpacked packet
    if rebroadcastEnabled:
        json_body = {}
        # now iterate through the measurements
        # should really check if there are measurements from more than one sensor in sensor_data
        # todo: iterate through m.sensor and group the MQTT publish messages by id
        radioId = 0
        for m in sensor_data:
            if m.sensor in rebroadcastSensors:
                radioId = m.sensor
                json_body[m.measurement] = m.value
        myLog.debug('Rebroadcasting MQTT %s/%u/%s', rebroadcastTopic, radioId, pprint.pformat(json_body))
        # publish the message
        mqtt_client.publish(rebroadcastTopic + '/' + str(radioId), json.dumps(json_body))


def _init_influxdb_database():
    initialised = False

    while not initialised:
        try:
            databases = influxClient.get_list_database()
            # create database if it doesn't exist
            if len(list(filter(lambda x: x['name'] == influxDbDatabase, databases))) == 0:
                myLog.warning("Database doesn't exists - will create it")
                influxClient.create_database(influxDbDatabase)

            # switch database
            influxClient.switch_database(influxDbDatabase)
            myLog.info('Database selected')
            initialised = True
        except:
            myLog.error('Database communication issue, retrying in 5 seconds')
            time.sleep(5)


def main():
    # init InfluxDb
    _init_influxdb_database()

    # init MQTT client
    global mqtt_client
    mqtt_client = mqtt.Client(mqttClientId)
    mqtt_client.username_pw_set(mqttUser, mqttPassword)
    mqtt_client.on_connect = on_connect
    mqtt_client.on_message = on_message

    # open MQTT connection and start listening to messages
    mqtt_client.connect(mqttAddress, mqttPort)
    mqtt_client.loop_forever()


def signal_handler(sig, frame):
    myLog.info("Stopping gracefully")
    mqtt_client.loop_stop()
    sys.exit(0)


if __name__ == '__main__':
    # deal with command line parameters
    parser = argparse.ArgumentParser()
    parser.add_argument("-d", "--default", help="dump default config to stdout", action="store_true")
    parser.add_argument("-c", "--config", help="override default configuration file")
    args = parser.parse_args()

    # check if we need to dump the config file
    if args.default:
        c = open('/app/rfm69gwtoinfluxbridge.conf.default', 'r')
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
    readConfig(args.config)

    # set loglevel
    myLog.setLevel(logging.getLevelName(logLevel))

    # open the InfluxDB connection
    influxClient = InfluxDBClient(influxDbAddress, influxDbPort, influxDbUser, influxDbPassword, None)

    # add INT and TERM handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    main()
