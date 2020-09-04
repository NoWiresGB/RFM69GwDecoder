FROM alpine:latest

ADD RFM69GwToInfluxBridge.py /bin/
ADD rfm69gwtoinfluxbridge.conf /etc/
ADD rfm69gwtoinfluxbridge.conf /etc/rfm69gwtoinfluxbridge.conf.default

RUN apk --no-cache add python3 py3-pip \
    && pip install influxdb paho.mqtt

CMD ["/usr/bin/python3", "/bin/RFM69GwToInfluxBridge.py"]
