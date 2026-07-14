# LAN streaming

Expose a local stream to phones, televisions, laptops, and other devices on the same network with one flag:

```console
easy-rtsp webcam 0 --serve live --lan
```

The CLI reports both the local URL and discovered network addresses:

```text
Play: rtsp://127.0.0.1:8554/live
LAN: rtsp://192.168.1.42:8554/live
```

Open the `LAN:` URL on the other device. If several network adapters are present, the primary route is printed first.

## Python

```python
from easy_rtsp import Stream

stream = Stream.from_webcam(0, lan_access=True).serve("live")
for url in stream.lan_viewer_urls:
    print(url)
stream.wait()
```

## Browser playback

Enable WebRTC when the receiving device should use a browser:

```console
easy-rtsp webcam 0 --serve live --lan --webrtc
```

Open the printed `LAN WebRTC:` URL. The equivalent Python properties are `webrtc_play_url` and `lan_webrtc_play_urls`.

## Firewall ports

| Mode | Default inbound ports |
| --- | --- |
| RTSP over TCP | TCP `8554` |
| WebRTC signaling | TCP `8889` |
| WebRTC media | UDP or TCP `8189` |

Use your configured `--server-port` or `--webrtc-port` when those defaults are overridden.

!!! warning "Trusted networks only"
    The generated LAN server does not configure authentication. Anyone who can reach the host on that network may be able to view or replace the configured publisher path. Do not expose it directly to the public internet.

## When another device cannot connect

1. Confirm both devices are on the same non-guest network.
2. Try the first printed LAN address.
3. Allow MediaMTX through the host firewall, or allow the ports above.
4. Temporarily disable a VPN to rule out route and virtual-adapter conflicts.
5. Check whether the router enables client isolation, common on guest Wi-Fi.

See [Troubleshooting](../operations/troubleshooting.md) for deeper checks.
