FROM balenalib/amd64-alpine:3.12

ADD RFM69GwToInfluxBridge.py /bin/
ADD rfm69gwtoinfluxbridge.conf /etc/
ADD rfm69gwtoinfluxbridge.conf /etc/rfm69gwtoinfluxbridge.conf.default

RUN install_packages python3 py3-pip

RUN pip install influxdb paho.mqtt

CMD ["/usr/bin/python3", "/bin/RFM69GwToInfluxBridge.py"]
