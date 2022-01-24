#!/usr/bin/python3 -u

# -*- coding: latin-1 -*-

""" RFM69Gw Healthcheck 
This script checks the health of the RFM69GwToInfluxBridge
"""
import requests
import configparser

if __name__ == '__main__':
    # read the config file, so we can check the API port
    config = configparser.ConfigParser()
    config.read('/app/rfm69gwtoinfluxbridge.conf')
    apiPort = int(config['main']['apiport'])

    # fire off an API request to /status
    r = requests.get('http://localhost:' + str(apiPort) + '/status')

    # exit based on status code
    if r.status_code == 200:
        exit(0)
    else:
        exit(1)