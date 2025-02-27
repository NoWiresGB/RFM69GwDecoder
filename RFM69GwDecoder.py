#!/usr/bin/python3 -u

# -*- coding: latin-1 -*-

""" RFM69Gw Decoder
This script parses the RFM69Gw published MQTT data and sends them to configured destinations (InfluxDb, Home Assistant, MQTT)
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
import threading
from werkzeug.serving import make_server
import flask

logLevel = ''
apiPort = 0

influxDbEnabled = False
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

rebroadcastEnabled = False
rebroadcastSensors = []
rebroadcastTopic = ''

haIntegrationEnabled = False
haBaseTopic = ''
haStatusTopic = ''

# this will hold [gwmac][sensorid][measurement] to show if we have provisoned this sensor
provisionedSensors = {}

# node type constants
NODEFUNC_POWER_SINGLE = 1
NODEFUNC_POWER_DOUBLE = 2
NODEFUNC_POWER_QUAD = 3
NODEFUNC_TEMP_RH = 4
NODEFUNC_TEMP_PRESSURE = 5
NODEFUNC_TRIGGER = 6

# our API server
app = flask.Flask(__name__)


class ServerThread(threading.Thread):

    def __init__(self, app):
        threading.Thread.__init__(self)
        myLog.info('Starting API server on port ' + str(apiPort))
        self.server = make_server('127.0.0.1', apiPort, app)
        self.ctx = app.app_context()
        self.ctx.push()

    def run(self):
        self.server.serve_forever()

    def shutdown(self):
        self.server.shutdown()


class SensorData(NamedTuple):
    gw: str             # gateway mac address
    sensor: str         # node id on the radio network
    type: int           # sensor type
    measurement: str    # name of the measurement, e.g. power1, temp, etc
    value: float        # value of the measurmement


@app.route('/status')
def hello_world():
    # right now just return 'running' with a 200 status
    return 'running'


def readConfig(confFile):
    global logLevel
    global apiPort

    global influxDbEnabled
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

    global haIntegrationEnabled
    global haBaseTopic
    global haStatusTopic

    myLog.info('Reading configuration file')

    config = configparser.ConfigParser()
    if confFile:
        myLog.info('Using config file: ' + confFile)
        config.read(confFile)
    else:
        config.read('/app/rfm69gw-decoder.conf')

    logLevel = config.get('main', 'loglevel', fallback='ERROR')
    apiPort = config.getint('main', 'apiport', fallback=5000)

    mqttAddress = config.get('mqtt', 'address', fallback='192.168.0.254')
    mqttPort = config.getint('mqtt', 'port', fallback=1883)
    mqttUser = config.get('mqtt', 'user', fallback='mqttuser')
    mqttPassword = config.get('mqtt', 'password', fallback='mqttpassword')
    mqttTopic = config.get('mqtt', 'topic', fallback='RFM69Gw/+/+/+')
    mqttRegex = config.get('mqtt', 'regex', fallback='RFM69Gw/([^/]+)/([^/]+)/([^/]+)')
    mqttClientId = config.get('mqtt', 'clientId', fallback='RFM69GwToInfluxDBBridge')

    influxDbEnabled = config.getboolean('influxdb', 'enabled', fallback=False)
    influxDbAddress = config.get('influxdb', 'address', fallback='192.168.0.254')
    influxDbPassword = config.getint('influxdb', 'port', fallback=8086)
    influxDbUser = config.get('influxdb', 'user', fallback='root')
    influxDbPassword = config.get('influxdb', 'password', fallback='root')
    influxDbDatabase = config.get('influxdb', 'database', fallback='home_iot')

    rebroadcastEnabled = config.getboolean('rebroadcast', 'enabled', fallback=False)
    rebroadcastSensors = json.loads(config.get('rebroadcast', 'sensor_list', fallback=[]))
    rebroadcastTopic = config.get('rebroadcast', 'topic', fallback='RFM69Bridge')

    haIntegrationEnabled = config.getboolean('ha_integration', 'enabled', fallback=False)
    haBaseTopic = config.get('ha_integration', 'base_topic', fallback='rfm69gw-decoder')
    haStatusTopic = config.get('ha_integration', 'ha_status_topic', fallback='homeassistant/status')


def on_connect(client, userdata, flags, rc):
    # The callback for when the client receives a CONNACK response from the server.
    myLog.info('Connected to MQTT with result code %s', str(rc))

    # if HA integration is enabled, we need to send a birth message
    if haIntegrationEnabled:
        mqtt_client.publish(haBaseTopic + '/status', 'online', 0, True)
        myLog.debug('Sending birth message to HA')

    # subscribe to the RFM69Gw topic
    client.subscribe(mqttTopic)
    # also subscribe to the HA status topic
    client.subscribe(haStatusTopic)


def on_message(client, userdata, msg):
    # The callback for when a PUBLISH message is received from the server.
    myLog.debug('MQTT receive: %s %s', msg.topic, str(msg.payload))

    # let's see what we got
    if msg.topic == haStatusTopic:
        # if HA is coming online, then we need to re-publish all of the sensors
        if msg.payload.decode("utf-8")  == 'online':
            myLog.info('HA is starting; send previous measurements')

            data_json = {}
            for g in provisionedSensors:
                for s in provisionedSensors[g]:
                    for m in provisionedSensors[g][s]:
                        sens = SensorData(g, s, -1, m, provisionedSensors[g][s][m]['value'])
                        try:
                            data_json[haBaseTopic + '/' + g + '/' + str(s)][m] = provisionedSensors[g][s][m]['value']
                        except KeyError:
                            # looks like we're missing the base key
                            data_json[haBaseTopic + '/' + g + '/' + str(s)] = {}
                            data_json[haBaseTopic + '/' + g + '/' + str(s)][m] = provisionedSensors[g][s][m]['value']

            # send the last measurement to HA
            myLog.debug('Sending measurements to HA:\n%s', json.dumps(data_json))
            for k in data_json:
                mqtt_client.publish(k, json.dumps(data_json[k]))
        else:
            myLog.info('HA is stopping; no need to do anything')
    else:
        # parse received payload
        measurements = _parse_mqtt_message(msg.topic, msg.payload.decode('utf-8'))
        myLog.debug('Parsed measurements:\n%s', pprint.pformat(measurements))

        # write the measurements into the database
        if measurements is not None:
            _send_sensor_data(measurements)

def s16(value):
    # turn hex number to signed integers
    return -(value & 0x8000) | (value & 0x7fff)

def _parse_mqtt_message(topic, payload):
    # this will store the return values
    rMeas = []

    match = re.match(mqttRegex, topic)
    if match:
        try:
            gwMac = match.group(1)
            # extract the MAC address (and strip out the colons)
            macMatch = re.match('.*-(..:..:..:..:..:..)-.*', gwMac)
            if macMatch:
                gwMac = macMatch.group(1).replace(':', '')
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
                power = s16(int(powerHex, 16))
                vrmsHex = payload[12:14] + payload[10:12]
                vrms = int(vrmsHex, 16) / 10

                rMeas.append(SensorData(gwMac, radioId, sensType, 'power1', power))
                rMeas.append(SensorData(gwMac, radioId, sensType, 'vrms', vrms))

                return rMeas
            elif (sensType == NODEFUNC_POWER_DOUBLE):
                powerHex = payload[8:10] + payload[6:8]
                power = s16(int(powerHex, 16))
                rMeas.append(SensorData(gwMac, radioId, sensType, 'power1', power))

                powerHex = payload[12:14] + payload[10:12]
                power = s16(int(powerHex, 16))
                rMeas.append(SensorData(gwMac, radioId, sensType, 'power2', power))

                vrmsHex = payload[16:18] + payload[14:16]
                vrms = int(vrmsHex, 16) / 10
                rMeas.append(SensorData(gwMac, radioId, sensType, 'vrms', vrms))

                return rMeas
            elif (sensType == NODEFUNC_POWER_QUAD):
                powerHex = payload[8:10] + payload[6:8]
                power = s16(int(powerHex, 16))
                rMeas.append(SensorData(gwMac, radioId, sensType, 'power1', power))

                powerHex = payload[12:14] + payload[10:12]
                power = s16(int(powerHex, 16))
                rMeas.append(SensorData(gwMac, radioId, sensType, 'power2', power))

                powerHex = payload[16:18] + payload[14:16]
                power = s16(int(powerHex, 16))
                rMeas.append(SensorData(gwMac, radioId, sensType, 'power3', power))

                powerHex = payload[20:22] + payload[18:20]
                power = s16(int(powerHex, 16))
                rMeas.append(SensorData(gwMac, radioId, sensType, 'power4', power))

                vrmsHex = payload[24:26] + payload[22:24]
                vrms = int(vrmsHex, 16) / 10
                rMeas.append(SensorData(gwMac, radioId, sensType, 'vrms', vrms))

                return rMeas
            elif (sensType == NODEFUNC_TEMP_RH):
                tempHex = payload[8:10] + payload[6:8]
                temp = struct.unpack('>h', bytes.fromhex(tempHex))[0] / 100
                rMeas.append(SensorData(gwMac, radioId, sensType, 'temp', temp))

                rhHex = payload[12:14] + payload[10:12]
                rh = int(rhHex, 16) / 100
                rMeas.append(SensorData(gwMac, radioId, sensType, 'rh', rh))

                rhHex = payload[16:18] + payload[14:16]
                vbatt = int(rhHex, 16)
                rMeas.append(SensorData(gwMac, radioId, sensType, 'vbatt', vbatt))

                return rMeas
            elif (sensType == NODEFUNC_TEMP_PRESSURE):
                tempHex = payload[8:10] + payload[6:8]
                temp = struct.unpack('>h', bytes.fromhex(tempHex))[0] / 100
                rMeas.append(SensorData(gwMac, radioId, sensType, 'temp', temp))

                rhHex = payload[16:18] + payload[14:16] + payload[12:14] + payload[10:12]
                pressure = int(rhHex, 16) / 100
                rMeas.append(SensorData(gwMac, radioId, sensType, 'pressure', pressure))

                rhHex = payload[16:18] + payload[14:16]
                vbatt = int(rhHex, 16)
                rMeas.append(SensorData(gwMac, radioId, sensType, 'vbatt', vbatt))

                return rMeas
            elif (sensType == NODEFUNC_TRIGGER):
                rhHex = payload[6:8]
                trigger = int(rhHex, 16)
                rMeas.append(SensorData(gwMac, radioId, sensType, 'trigger', trigger))

                rhHex = payload[10:12] + payload[8:10]
                vbatt = int(rhHex, 16)
                rMeas.append(SensorData(gwMac, radioId, sensType, 'vbatt', vbatt))

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


def get_device_class(sensor_data):
    if sensor_data.measurement == 'power1' or sensor_data.measurement == 'power2' or sensor_data.measurement == 'power3' or sensor_data.measurement == 'power4':
        return 'power'
    if sensor_data.measurement == 'vrms':
        return 'voltage'
    if sensor_data.measurement == 'temp':
        return 'temperature'
    if sensor_data.measurement == 'rh':
        return 'humidity'
    if sensor_data.measurement == 'vbatt':
        return 'voltage'
    if sensor_data.measurement == 'pressure':
        return 'pressure'
    return 'None'


def get_unit_of_measurement(sensor_data):
    if sensor_data.measurement == 'power1' or sensor_data.measurement == 'power2' or sensor_data.measurement == 'power3' or sensor_data.measurement == 'power4':
        return 'W'
    if sensor_data.measurement == 'vrms':
        return 'V'
    if sensor_data.measurement == 'temp':
        return '°C'
    if sensor_data.measurement == 'rh':
        return '%'
    if sensor_data.measurement == 'vbatt':
        return 'mV'
    if sensor_data.measurement == 'pressure':
        return 'mbar'
    return 'None'


def provision_sensor(sensor_data):
    json_body = {}

    json_body['availability'] = []
    json_body['availability'].append({})
    json_body['availability'][0]['topic'] = haBaseTopic + '/status'
    json_body['device'] = {}
    json_body['device']['identifiers'] = []
    json_body['device']['identifiers'].append('rfm69gw_' + sensor_data.gw + '_' + str(sensor_data.sensor))
    json_body['device']['manufacturer'] = 'Owltronics'
    json_body['device']['model'] = 'Owlet sensor'
    json_body['device']['name'] = haBaseTopic + '_' + sensor_data.gw + '_' + str(sensor_data.sensor)
    if (not sensor_data.measurement == 'trigger'):
        json_body['device_class'] = get_device_class(sensor_data)
    json_body['enabled_by_default'] = True
    json_body['name'] = sensor_data.gw + '-' + str(sensor_data.sensor) + '-' + sensor_data.measurement
    if (not sensor_data.measurement == 'trigger'):
        json_body['state_class'] = 'measurement'
    json_body['state_topic'] = haBaseTopic + '/' + sensor_data.gw + '/' + str(sensor_data.sensor)
    json_body['unique_id'] = sensor_data.gw + '_' + str(sensor_data.sensor) + '_' + sensor_data.measurement
    if (not sensor_data.measurement == 'trigger'):
        json_body['unit_of_measurement'] = get_unit_of_measurement(sensor_data)
    else:
        json_body['payload_on'] = 1
        json_body['payload_off'] = 0
    json_body['value_template'] = '{{ value_json.' + sensor_data.measurement + ' }}'

    if (not sensor_data.measurement == 'trigger'):
        t = 'homeassistant/sensor/' + haBaseTopic + '-' + sensor_data.gw + '-' + str(sensor_data.sensor) + '/' + sensor_data.measurement + '/config'
    else:
        t = 'homeassistant/binary_sensor/' + haBaseTopic + '-' + sensor_data.gw + '-' + str(sensor_data.sensor) + '/' + sensor_data.measurement + '/config'
    myLog.debug('Provisioning sensor in HA (%s):\n%s', t, json.dumps(json_body))

    # send the provisioning message - set the retain flag
    mqtt_client.publish(t, json.dumps(json_body), 0, True)


def _send_sensor_data(sensor_data):
    # check if we need to write to InfluxDb
    if influxDbEnabled:
        # construct the JSON
        json_body = []
        for m in sensor_data:
            json_body.append({ 'measurement': m.measurement, 'tags': { 'nodeid' : m.sensor }, 'fields' : { 'value' : m.value }})

        myLog.debug('Writing JSON to DB:\n%s', pprint.pformat(json_body))

        try:
            # write measurements to the database
            influxClient.write_points(json_body)
        except:
            myLog.error("Exception while writing data to database")

    # check if we need to rebroadcast the unpacked packet
    if rebroadcastEnabled:
        json_body = {}
        # now iterate through the measurements
        for m in sensor_data:
            # add the key if it doesn't exist
            if m.sensor not in json_body:
                json_body[m.sensor] = {}
            # now add the measurement and its value
            json_body[m.sensor][m.measurement] = m.value

        # now iterate through the transformed measurements and see what needs to be published
        for m in json_body:
            if m in rebroadcastSensors:
                # log the event
                myLog.debug('Rebroadcasting MQTT %s/%u/%s', rebroadcastTopic, m, pprint.pformat(json_body[m]))
                # publish the message
                mqtt_client.publish(rebroadcastTopic + '/' + str(m), json.dumps(json_body[m]))

    # check if we need to send the data to HA
    if haIntegrationEnabled:
        # we'll collect all the measurements here, so we avoid sending multiple MQTT messages for multi-sensor devices
        # format is data_json['state_topic']['measurement'] = value to send
        data_json = {}

        # now iterate through the measurements
        for m in sensor_data:
            # flag to mark if we need to provision the sensor to HA
            provisionSensor = True

            try:
                if provisionedSensors[m.gw]:
                    try:
                        if provisionedSensors[m.gw][m.sensor]:
                            try:
                                if provisionedSensors[m.gw][m.sensor][m.measurement]:
                                    provisionSensor = False
                            except KeyError:
                                # add the measurement key
                                provisionedSensors[m.gw][m.sensor][m.measurement] = {}
                                provisionedSensors[m.gw][m.sensor][m.measurement]['status'] = 1
                                provisionedSensors[m.gw][m.sensor][m.measurement]['value'] = m.value
                    except KeyError:
                        # add the sensor & measurement key
                        provisionedSensors[m.gw][m.sensor] = {}
                        provisionedSensors[m.gw][m.sensor][m.measurement] = {}
                        provisionedSensors[m.gw][m.sensor][m.measurement]['status'] = 1
                        provisionedSensors[m.gw][m.sensor][m.measurement]['value'] = m.value
            except KeyError:
                # add the GW, sensor & measurement key
                provisionedSensors[m.gw] = {}
                provisionedSensors[m.gw][m.sensor] = {}
                provisionedSensors[m.gw][m.sensor][m.measurement] = {}
                provisionedSensors[m.gw][m.sensor][m.measurement]['status'] = 1
                provisionedSensors[m.gw][m.sensor][m.measurement]['value'] = m.value
            
            if provisionSensor:
                # let's provision the sensor
                myLog.debug("Couldn't find sensor with parameters %s, %s, %s", m.gw, m.sensor, m.measurement)
                provision_sensor(m)
            
            try:
                data_json[haBaseTopic + '/' + m.gw + '/' + str(m.sensor)][m.measurement] = m.value
            except KeyError:
                # looks like we're missing the base key
                data_json[haBaseTopic + '/' + m.gw + '/' + str(m.sensor)] = {}
                data_json[haBaseTopic + '/' + m.gw + '/' + str(m.sensor)][m.measurement] = m.value

        # we're ready to send the measurements as all the sensors have been provisioned
        myLog.debug('Sending measurements to HA:\n%s', json.dumps(data_json))
        for k in data_json:
            mqtt_client.publish(k, json.dumps(data_json[k]))

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


def _init_mqtt():
    initialised = False

    global mqtt_client
    mqtt_client = mqtt.Client(mqttClientId)
    mqtt_client.username_pw_set(mqttUser, mqttPassword)
    mqtt_client.on_connect = on_connect
    mqtt_client.on_message = on_message

    # open MQTT connection and start listening to messages
    while not initialised:
        try:
            mqtt_client.connect(mqttAddress, mqttPort)
            # need to call loop as we need to process the connect response
            mqtt_client.loop()
            initialised = True
        except:
            myLog.error("Unable to connect to MQTT, retrying in 5 seconds")
            time.sleep(5)

    # enter network loop
    mqtt_client.loop_forever()


def main():
    # init InfluxDb (if enabled)
    if influxDbEnabled:
        _init_influxdb_database()

    # init MQTT
    _init_mqtt()


def signal_handler(sig, frame):
    myLog.info("Stopping gracefully")

    # if HA integration is enabled, we need to send a last will message
    if haIntegrationEnabled:
        mqtt_client.publish(haBaseTopic + '/status', 'offline', 0, True)
        myLog.debug('Sending last will message to HA')

    # stop MQTT loop
    mqtt_client.loop_stop()

    # stop our API server
    global server
    server.shutdown()

    # finally exit
    sys.exit(0)


if __name__ == '__main__':
    # deal with command line parameters
    parser = argparse.ArgumentParser()
    parser.add_argument("-d", "--default", help="dump default config to stdout", action="store_true")
    parser.add_argument("-c", "--config", help="override default configuration file")
    args = parser.parse_args()

    # check if we need to dump the config file
    if args.default:
        c = open('/app/rfm69gw-decoder.conf.default', 'r')
        lines = c.readlines()
        for l in lines:
            print(l.strip())
        c.close()
        exit()

    # get an instance of the logger object
    myLog = logging.getLogger('RFM69GwToInflux')

    # set loglevel and log format
    logging.basicConfig(format='%(asctime)s [%(levelname)s] %(message)s', level=logging.INFO)
    myLog.info('RFM69Gw Decoder')

    # read the config file
    readConfig(args.config)

    # set loglevel
    myLog.setLevel(logging.getLevelName(logLevel))

    # disable Flask logging
    apiServerLog = logging.getLogger('werkzeug')
    apiServerLog.setLevel(logging.ERROR)
    app.logger.disabled = True
    apiServerLog.disabled = True

    # start our API server
    global server
    server = ServerThread(app)
    server.start()

    if influxDbEnabled:
        # open the InfluxDB connection
        influxClient = InfluxDBClient(influxDbAddress, influxDbPort, influxDbUser, influxDbPassword, None)

    # add INT and TERM handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    main()
