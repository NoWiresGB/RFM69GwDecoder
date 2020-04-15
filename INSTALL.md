* Copy RFM69GwToInfluxBridge.py to /usr/local/bin/ (make sure that the file is executable)
* Copy rfm69gwtoinfluxbridge.service to /etc/systemd/system

* Install service using
```
systemctl enable rfm69gwtoinfluxbridge.service
```

* Start service using
```
systemctl start rfm69gwtoinfluxbridge
```
