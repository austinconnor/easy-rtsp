# Recording and HLS

Duplicate an RTSP publish into local side outputs without creating a second encode pipeline.

```console
easy-rtsp relay rtsp://camera/live \
  --serve live \
  --record recordings/camera.mp4 \
  --hls-dir public/hls
```

Python uses the corresponding configuration fields:

```python
from easy_rtsp import Stream

stream = Stream.open(
    "rtsp://camera/live",
    record_path="recordings/camera.mp4",
    hls_output_dir="public/hls",
    hls_segment_time=2.0,
).serve("live")
stream.wait()
```

The HLS directory contains `index.m3u8` and media segments. easy-rtsp writes these files but does not start an HTTP server for them; serve the directory with your application or web server.

!!! note
    Side outputs require MediaMTX or an existing RTSP server. They are unavailable with the single-client TCP/MPEG-TS fallback and with SRT destinations.

## Encoder selection

Use any FFmpeg encoder available in the installed build:

```console
easy-rtsp webcam 0 --serve live --video-encoder h264_nvenc
```

Common alternatives include `h264_qsv` and `h264_amf`. Availability depends on the host GPU, drivers, and FFmpeg build.
