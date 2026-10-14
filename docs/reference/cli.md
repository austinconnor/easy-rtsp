# Command-line reference

```console
easy-rtsp --help
easy-rtsp COMMAND --help
```

## Commands

| Command | Purpose |
| --- | --- |
| `doctor` | Report easy-rtsp, platform, FFmpeg, ffprobe, and MediaMTX versions. Exits non-zero if FFmpeg or ffprobe is missing. |
| `install-backends` | Download MediaMTX (checksum-verified) and print FFmpeg installation guidance. |
| `relay URL` | Ingest RTSP/RTSPS and republish it. |
| `webcam [INDEX]` | Capture a camera device and publish it. |
| `file PATH` | Decode a local video file and publish it. |

## Common publishing flags

Accepted by `relay`, `webcam`, and `file`.

| Flag | Description |
| --- | --- |
| `--serve ENDPOINT` | Shorthand path or full RTSP, RTSPS, or SRT destination. |
| `--server-host HOST` | Host used for shorthand destinations. |
| `--server-port PORT` | Port used for shorthand destinations. |
| `--lan` | Expose locally managed MediaMTX and print LAN URLs. |
| `--webrtc` / `--no-webrtc` | Toggle browser playback. |
| `--webrtc-port PORT` | WebRTC HTTP/signaling port. |
| `--webrtc-ice-port PORT` | WebRTC UDP/TCP ICE port. |
| `--record PATH` | Write an MP4 side output. |
| `--hls-dir DIR` | Write HLS playlist and segments. |
| `--hls-segment-time SEC` | Configure HLS segment duration. |
| `--hls-list-size N` | Segments kept in the HLS playlist (`0` keeps all). |
| `--fps FPS` | Publish frame rate override (default: probed from the source, else 30). |
| `--video-encoder NAME` | Select an FFmpeg video encoder, such as `h264_nvenc`. |
| `--bitrate RATE` | Video encoder bitrate, such as `4M`. |
| `--preset NAME` | `default`, `low_latency`, or `quality`. |
| `--low-latency-input` | Disable FFmpeg real-time input pacing. |
| `-v`, `--verbose` | Enable easy-rtsp diagnostic logging. |

## Relay flags

| Flag | Description |
| --- | --- |
| `--transport tcp\|udp` | RTSP input transport. |
| `--latency-ms MS` | RTSP ingest latency hint. |
| `--retry-interval SEC` | Delay between reconnect attempts. |
| `--max-reconnect-attempts N` | Retry limit; omitted means unlimited. |
| `--no-reconnect` | Disable RTSP input reconnects. |
| `--audio-mode MODE` | `off` or `passthrough` (copies source audio and video). |

## File flags

| Flag | Description |
| --- | --- |
| `--loop` / `--no-loop` | Toggle playback looping. |
| `--no-realtime` | Decode as fast as possible rather than pacing like a live source. |

## Output contract

Logs and warnings go to stderr. Machine-usable `Play:`, `WebRTC:`, `LAN:`, and `LAN WebRTC:` URLs go to stdout.

| Exit code | Meaning |
| --- | --- |
| `0` | Clean exit, including a Ctrl+C stop while streaming. |
| `1` | Configuration, dependency, or publishing error. The message includes the useful tail of the backend error (credentials redacted) rather than a Python traceback. |
| `2` | Invalid command-line arguments. |
| `130` | Interrupted with Ctrl+C before the stream started. |
