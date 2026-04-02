"""Exercise: shorthand path vs full ``rtsp://`` URL (see ``parse_serve_endpoint``)."""

from __future__ import annotations

from easy_rtsp.config import StreamConfig
from easy_rtsp.serve_url import parse_serve_endpoint


def main() -> None:
    cfg = StreamConfig(server_host="127.0.0.1", server_port=8554)
    url, host, port, path = parse_serve_endpoint("cam1", cfg)
    print("shorthand 'cam1':", url, "| host:", host, "port:", port, "path:", path)

    cfg2 = StreamConfig()
    url2, host2, port2, path2 = parse_serve_endpoint(
        "rtsp://192.168.1.10:8554/mystream", cfg2
    )
    print("full URL:", url2, "| host:", host2, "port:", port2, "path:", path2)


if __name__ == "__main__":
    main()
