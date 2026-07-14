# GStreamer

GStreamer is a good downstream consumer when you need a native plugin graph, a specialized codec or transport, hardware elements, or integration with an existing media application.

The clean boundary is RTSP:

```text
camera / file / Python frames
            ↓
        easy-rtsp
            ↓  RTSP over TCP
        GStreamer
            ↓
 display / appsink / inference / another transport
```

## 1. Publish a reachable stream

On the easy-rtsp host:

```console
easy-rtsp webcam 0 --serve edge --lan
```

Use the printed `LAN:` URL when GStreamer runs on another device. Use `Play:` when both processes run on the same host.

## 2. Validate it with `gst-launch`

```console
gst-launch-1.0 -v \
  rtspsrc location=rtsp://192.168.1.42:8554/edge protocols=tcp latency=100 \
  ! rtph264depay \
  ! h264parse \
  ! avdec_h264 \
  ! videoconvert \
  ! autovideosink sync=false
```

On PowerShell, place the pipeline on one line or replace each `\` continuation with a backtick.

`protocols=tcp` matches easy-rtsp's generated MediaMTX configuration. `latency` is GStreamer's receive jitter buffer in milliseconds; increase it for unstable networks and lower it carefully for interactive applications.

## 3. Hand decoded frames to an application

Replace the display sink with an `appsink` when a GStreamer application should own inference:

```text
rtspsrc location=rtsp://192.168.1.42:8554/edge protocols=tcp latency=100
! rtph264depay
! h264parse
! avdec_h264
! videoconvert
! video/x-raw,format=RGB
! appsink drop=true max-buffers=1 sync=false
```

The last three properties are a useful live-CV policy:

- `drop=true` prevents an unbounded backlog.
- `max-buffers=1` keeps only a small amount of work queued.
- `sync=false` lets the application consume the newest available frame rather than waiting on the display clock.

## Where should transforms live?

| Requirement | Put it in |
| --- | --- |
| A few lines of NumPy/OpenCV | easy-rtsp `map()` |
| Existing GStreamer plugin | GStreamer |
| Hardware-specific decoder/converter | GStreamer |
| Python owns business logic and annotations | easy-rtsp |
| Native application owns lifecycle and backpressure | GStreamer |

## Avoid decoding twice

If GStreamer already acquires, decodes, processes, and publishes the stream, adding easy-rtsp in the middle usually creates an unnecessary encode/decode boundary. Use easy-rtsp when its Python API, source handling, URL discovery, or MediaMTX startup removes meaningful application code.

See the official [`rtspsrc` documentation](https://gstreamer.freedesktop.org/documentation/rtsp/rtspsrc.html) for transport, latency, timeout, and clock behavior.

## Troubleshooting

### `no element "avdec_h264"`

Install the GStreamer libav plugin for the platform, or replace it with a hardware H.264 decoder available in that installation.

### It works locally but not across the LAN

Confirm you used `--lan`, selected a printed LAN URL, and allowed inbound TCP on easy-rtsp's RTSP port.

### Latency grows over time

Verify downstream elements are not accumulating buffers. For application sinks, use a bounded queue/drop policy and measure whether inference is slower than the source frame rate.
