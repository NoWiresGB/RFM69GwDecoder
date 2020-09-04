# RFM69GwToInfluxBridge
RFM69-Gateway to InfluxDb bridge

Generate default config
docker run --rm zmarkella/rfm69gw python3 /bin/RFM69GwToInfluxBridge.py config > rfm69gwtoinfluxbridge.conf.conf

Run the GW
docker run -d -v $PWD/rfm69gwtoinfluxbridge.conf:/etc/rfm69gwtoinfluxbridge.conf:ro zmarkella/rfm69gw
