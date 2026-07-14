# NVIDIA DeepStream

DeepStream is an NVIDIA-accelerated GStreamer graph. Its main advantage is keeping decode, batching, inference, tracking, and composition inside NVIDIA's native pipeline and device-memory model.

Use easy-rtsp as a source boundary, not as a frame-by-frame middleman:

```text
camera / file / custom Python source
                 ↓
             easy-rtsp
                 ↓  RTSP over TCP
            DeepStream
                 ↓
       inference / tracking / metadata
```

## Publish from easy-rtsp

On the source host:

```console
easy-rtsp relay rtsp://camera/live --serve edge --lan
```

This is useful when you want easy-rtsp to normalize camera access, reconnect upstream, or expose a predictable URL to a separate Jetson/dGPU service.

## Configure `deepstream-app`

Add an RTSP source group to a DeepStream application config:

```ini
[source0]
enable=1
type=4
uri=rtsp://192.168.1.42:8554/edge
select-rtp-protocol=4
latency=100
rtsp-reconnect-interval-sec=10
rtsp-reconnect-attempts=-1

[streammux]
live-source=1
batch-size=1
```

The important choices are:

- `type=4` selects a DeepStream RTSP source.
- `select-rtp-protocol=4` forces TCP, matching easy-rtsp's local MediaMTX transport.
- `live-source=1` tells the stream muxer that timestamps come from a live source.
- `batch-size` should normally match the number of enabled sources.

Run your normal DeepStream configuration:

```console
deepstream-app -c edge-app.txt
```

The exact inference, tracker, OSD, and sink groups remain model- and deployment-specific. NVIDIA's [reference application configuration](https://docs.nvidia.com/metropolis/deepstream/dev-guide/text/DS_ref_app_deepstream.html) is the source of truth for the installed DeepStream release.

## Multiple streams

Publish each easy-rtsp stream under a distinct path:

```text
rtsp://edge-host:8554/camera/front
rtsp://edge-host:8554/camera/loading-dock
rtsp://edge-host:8554/camera/parking
```

Then create one `[sourceN]` group per URL and set the streammux batch size to the source count.

!!! warning "One easy-rtsp process currently owns one generated MediaMTX path"
    Multiple independently started local servers cannot all bind the default port. For a multi-camera edge box, run one shared MediaMTX instance and have each easy-rtsp process publish to a full RTSP URL on that server.

Example:

```console
easy-rtsp relay rtsp://camera-a/live --serve rtsp://127.0.0.1:8554/camera/a
easy-rtsp relay rtsp://camera-b/live --serve rtsp://127.0.0.1:8554/camera/b
```

## When not to use easy-rtsp

If DeepStream can directly open the camera and all processing stays inside its graph, connect it directly. Passing frames through easy-rtsp's NumPy `map()` path would move them to CPU memory and re-encode them, defeating much of DeepStream's zero-copy advantage.

## Publishing DeepStream output

DeepStream can create its own encoded RTSP sink (`type=4`). Let DeepStream own that output when the analytics graph is already authoritative. Use MediaMTX separately when you need a shared routing layer, authentication, or browser-facing protocols.

## Platform boundary

DeepStream is intentionally not an easy-rtsp dependency. It is tied to supported NVIDIA GPUs, Jetson/dGPU platforms, CUDA, TensorRT, GStreamer, drivers, and specific Linux releases. Consult the current [DeepStream installation matrix](https://docs.nvidia.com/metropolis/deepstream/dev-guide/text/DS_Installation.html) before choosing an image or host OS.
