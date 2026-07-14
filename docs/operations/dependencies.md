# Dependencies

## Python

NumPy is the only required Python runtime dependency. OpenCV is optional:

```console
pip install "easy-rtsp[webcam]"
```

OpenCV powers webcam capture and snapshot encoding. Frame generation, RTSP/file ingest, publishing, and NumPy-only transforms do not require it.

## FFmpeg and ffprobe

FFmpeg performs decoding, encoding, and publishing. ffprobe discovers video dimensions and frame rates.

Both may be provided on `PATH` or explicitly:

=== "PowerShell"

    ```powershell
    $env:EASY_RTSP_FFMPEG = "C:\tools\ffmpeg\bin\ffmpeg.exe"
    $env:EASY_RTSP_FFPROBE = "C:\tools\ffmpeg\bin\ffprobe.exe"
    ```

=== "bash"

    ```bash
    export EASY_RTSP_FFMPEG=/usr/local/bin/ffmpeg
    export EASY_RTSP_FFPROBE=/usr/local/bin/ffprobe
    ```

## MediaMTX

MediaMTX provides the proper RTSP server used by local publishing. It is required for:

- `lan_access=True` / `--lan`
- WebRTC browser playback
- Multiple RTSP viewers
- Recording and HLS side outputs when no external RTSP server exists

Install it with:

```console
easy-rtsp install-backends
```

If it is not on `PATH`, set `EASY_RTSP_MEDIAMTX` to the executable.

## Confirm the environment

```console
easy-rtsp doctor
```

The command is safe to include in setup scripts and support requests.
