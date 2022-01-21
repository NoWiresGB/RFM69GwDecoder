# RFM69GwToInfluxBridge
RFM69-Gateway to InfluxDb bridge

### Generate default config
```
docker run --rm zmarkella/rfm69gw python3 /app/RFM69GwToInfluxBridge.py -d > rfm69gwtoinfluxbridge.conf
```

### Run the GW
```
docker run -d -v $PWD/rfm69gwtoinfluxbridge.conf:/etc/rfm69gwtoinfluxbridge.conf:ro zmarkella/rfm69gw
```

## No more automated builds on Docker hub (but there's a Jenkins serveer!)
Currently, there's a Jenkins server that's set up to build both master branch and 'devel' tag, then push it to Docker hub.

Force the tag onto the current commit:
```
git tag -f -a devel
git push -f --tags
```
Both 'latest' and '-devel' tags are cross-platfrom builds for amd64 and armv7hf
