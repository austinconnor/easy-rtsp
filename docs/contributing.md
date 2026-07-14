# Contributing

## Set up

```console
git clone https://github.com/austinconnor/easy-rtsp.git
cd easy-rtsp
uv sync --extra dev --group docs
```

## Run the checks

```console
uv run ruff check src tests
uv run pytest
uv run --group docs mkdocs build --strict
```

Manual integration examples live in `test_scripts/`. They cover cameras, files, relays, transforms, and timed synthetic publishing.

## Preview documentation

```console
uv run --group docs mkdocs serve
```

Open `http://127.0.0.1:8000`. Changes under `docs/` reload automatically.

## Documentation principles

- Keep examples executable and cross-platform where possible.
- State clearly when FFmpeg, MediaMTX, OpenCV, a camera, or network access is required.
- Treat the Pages site as canonical. The GitHub Wiki should stay a concise map into these versioned docs.
- Run the strict documentation build so broken internal links fail before deployment.
