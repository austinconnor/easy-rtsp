# Configuration

Pass options directly to a constructor or `serve()`. Internally they form a validated `StreamConfig`.

```python
stream = Stream.open(
    url,
    transport="tcp",
    retry_interval_sec=1.0,
    max_reconnect_attempts=10,
)
stream.serve("live", video_encoder="h264_nvenc")
```

## Input and reconnect

| Option | Default | Meaning |
| --- | --- | --- |
| `transport` | `"tcp"` | RTSP ingest transport: `tcp` or `udp`. |
| `latency_ms` | `None` | Optional RTSP ingest latency hint. |
| `reconnect` | `True` | Reopen an RTSP input after disconnect. |
| `retry_interval_sec` | `2.0` | Delay between reconnect attempts. |
| `max_reconnect_attempts` | `None` | Retry limit; `None` is unlimited. |
| `on_reconnecting` | `None` | Callback receiving the next attempt number. |
| `file_loop` | `True` | Restart file decoding after EOF. |
| `fps` | `None` | Override inferred output FPS. |

## Local server

| Option | Default | Meaning |
| --- | --- | --- |
| `server_host` | `"127.0.0.1"` | Host used by shorthand serve paths. |
| `server_port` | `8554` | RTSP port used by shorthand serve paths. |
| `lan_access` | `False` | Bind locally managed MediaMTX to the network and report LAN URLs. |
| `webrtc_enabled` | `False` | Enable MediaMTX browser playback. |
| `webrtc_http_port` | `8889` | WebRTC HTTP/signaling port. |

## Encoding and outputs

| Option | Default | Meaning |
| --- | --- | --- |
| `codec` | `"h264"` | Logical output codec. |
| `video_encoder` | `None` | Explicit FFmpeg encoder name. |
| `bitrate` | `None` | Encoder bitrate such as `"4M"`. |
| `preset` | `"default"` | `default`, `low_latency`, or `quality`. |
| `input_realtime_pace` | `None` | Control FFmpeg `-re` pacing for raw inputs. |
| `audio_mode` | `"off"` | `off` or RTSP relay `passthrough`. |
| `record_path` | `None` | Optional MP4 side output. |
| `hls_output_dir` | `None` | Optional HLS output directory. |
| `hls_segment_time` | `2.0` | HLS segment duration in seconds. |

## Advanced FFmpeg arguments

`extra_ffmpeg_input_args` and `extra_ffmpeg_output_args` accept lists of raw FFmpeg arguments. These are intentionally advanced escape hatches; prefer named options when one exists.
