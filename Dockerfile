FROM python:3.7-slim AS build

WORKDIR /app
COPY RFM69GwToInfluxBridge.py /app/
COPY rfm69gwtoinfluxbridge.conf /app/
COPY rfm69gwtoinfluxbridge.conf /app/rfm69gwtoinfluxbridge.conf.default
COPY requirements.txt /app/

RUN pip3 install -r /app/requirements.txt

CMD ["/usr/local/bin/python3","/app/RFM69GwToInfluxBridge.py"]
