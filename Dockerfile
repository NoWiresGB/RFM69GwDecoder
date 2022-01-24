FROM python:3.7-slim AS build

WORKDIR /app
COPY RFM69GwDecoder.py /app/
COPY RFM69GwDecoderHealthCheck.py /app/
COPY rfm69gw-decoder.conf /app/
COPY rfm69gw-decoder.conf /app/rfm69gw-decoder.conf.default
COPY requirements.txt /app/

RUN pip3 install -r /app/requirements.txt

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 CMD [ "/usr/local/bin/python3", "/app/RFM69GwDecoderHealthCheck.py" ]

CMD ["/usr/local/bin/python3","/app/RFM69GwDecoder.py"]
