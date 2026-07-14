# Command-line reference

```console
easy-rtsp --help
easy-rtsp COMMAND --help
```

## Commands

| Command | Purpose |
| --- | --- |
| `doctor` | Report platform, FFmpeg, ffprobe, and MediaMTX status. |
| `install-backends` | Download MediaMTX and print FFmpeg installation guidance. |
| `relay URL` | Ingest RTSP/RTSPS and republish it. |
| `webcam [INDEX]` | Capture a camera device and publish it. |
| `file PATH` | Decode a local video file and publish it. |

## Common publishing flags

| Flag | Description |
| --- | --- |
| `--serve ENDPOINT` | Shorthand path or full RTSP, RTSPS, or SRT destination. |
| `--server-host HOST` | Host used for shorthand destinations. |
| `--server-port PORT` | Port used for shorthand destinations. |
| `--lan` | Expose locally managed MediaMTX and print LAN URLs. |
| `--webrtc` / `--no-webrtc` | Toggle browser playback. |
| `--webrtc-port PORT` | WebRTC HTTP/signaling port. |
| `--record PATH` | Write an MP4 side output. |
| `--hls-dir DIR` | Write HLS playlist and segments. |
| `--hls-segment-time SEC` | Configure HLS segment duration. |
| `--video-encoder NAME` | Select an FFmpeg video encoder. |
| `--audio-mode MODE` | `off` or `passthrough`. |
| `--low-latency-input` | Disable FFmpeg real-time input pacing. |
| `-v`, `--verbose` | Enable easy-rtsp diagnostic logging. |

## Relay flags

| Flag | Description |
| --- | --- |
| `--transport tcp\|udp` | RTSP input transport. |
| `--retry-interval SEC` | Delay between reconnect attempts. |
| `--max-reconnect-attempts N` | Retry limit; omitted means unlimited. |
| `--no-reconnect` | Disable RTSP input reconnects. |

## File flags

| Flag | Description |
| --- | --- |
| `--fps FPS` | Override probed file FPS. |
| `--loop` / `--no-loop` | Toggle playback looping. |
| `--no-realtime` | Decode as fast as possible rather than pacing like a live source. |

## Output contract

Logs and warnings go to stderr. Machine-usable `Play:`, `WebRTC:`, `LAN:`, and `LAN WebRTC:` URLs go to stdout. Publishing failures return a non-zero exit code with the useful tail of the backend error rather than a Python traceback.
