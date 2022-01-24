# RFM69GwToInfluxBridge
RFM69-Gateway Decoder

### Generate default config
```
docker run --rm zmarkella/rfm69gw-decoder python3 /app/RFM69GwDecoder.py -d > rfm69gw-decoder.conf
```

### Run the GW
```
docker run -d --name rfm69gw-decoder --restart=unless-stopped -v $PWD/rfm69gw-decoder.conf:/etc/rfm69gw-decoder.conf:ro zmarkella/rfm69gw-decoder
```

## No more automated builds on Docker hub (but there's a Jenkins serveer!)
Currently, there's a Jenkins server that's set up to build both master branch and 'devel' tag, then push it to Docker hub.

Force the tag onto the current commit:
```
git tag -f -a devel
git push -f --tags
```
Both 'latest' and '-devel' tags are cross-platfrom builds for amd64 and armv7hf
