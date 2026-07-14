# Troubleshooting

Start every diagnosis with:

```console
easy-rtsp doctor
```

Add `-v` to a streaming command for easy-rtsp diagnostics.

## The CLI prints `tcp://` instead of `rtsp://`

MediaMTX was not found and the local RTSP port was free, so easy-rtsp selected its single-client MPEG-TS fallback. Install MediaMTX or set `EASY_RTSP_MEDIAMTX`.

## A LAN device cannot connect

- Use a URL printed by `--lan`; `127.0.0.1` always refers to the receiving device itself.
- Allow inbound TCP on the configured RTSP port, default `8554`.
- Check for guest-network client isolation.
- Disable VPN software briefly to identify route conflicts.
- Confirm MediaMTX is installed; LAN mode intentionally refuses the non-RTSP fallback.

## WebRTC stays on loading

- Open a printed `LAN WebRTC:` URL rather than replacing hosts manually.
- Allow TCP `8889` and UDP/TCP `8189` by default.
- Test without a VPN and try a second browser.
- Confirm the page host is one of the candidates reported by easy-rtsp.

## A relay repeatedly reconnects

Test the camera URL with ffprobe or VLC from the same host. Then increase `retry_interval_sec`, set a finite `max_reconnect_attempts`, and verify whether TCP or UDP is more reliable for that camera.

```console
easy-rtsp relay rtsp://camera/live \
  --transport tcp \
  --retry-interval 5 \
  --max-reconnect-attempts 20
```

## Hardware encoding fails

An encoder name being recognized does not guarantee that the GPU driver and FFmpeg build support it. Check available encoders:

```console
ffmpeg -hide_banner -encoders
```

Remove `--video-encoder` to confirm the software H.264 path first.

## Recording or HLS is rejected

Side outputs require an RTSP publish target and either MediaMTX or an existing RTSP server. They are not available with SRT destinations or the TCP/MPEG-TS fallback.

## Publishing stops in the background

Inspect `stream.status()`:

```python
status = stream.status()
print(status.state, status.publish_error)
```

The CLI performs this check automatically and exits non-zero when the publisher fails.
