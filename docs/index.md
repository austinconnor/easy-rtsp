---
hide:
  - navigation
  - toc
---

<div class="home-shell" markdown>

<section class="home-hero" markdown>

<div class="home-hero__copy" markdown>

<p class="home-eyebrow">Streaming for Python</p>

# RTSP, made easy.

Read from a camera, webcam, file, or NumPy frames. Transform video in Python, then publish it locally, across your LAN, or to an existing server.

<div class="home-actions" markdown>
[Get started](getting-started.md){ .md-button .md-button--primary }
[Explore edge CV](integrations/index.md){ .md-button }
</div>

<p class="home-support">Python 3.10+ &nbsp;·&nbsp; Windows, macOS, and Linux</p>

</div>

<div class="home-quickstart" markdown>

<div class="home-quickstart__bar">
  <span>Quick start</span>
  <span>Python</span>
</div>

```console
uv add easy-rtsp
```

```python
from easy_rtsp import Stream

stream = Stream.from_webcam(
    0,
    lan_access=True,
).serve("live")

print(stream.lan_viewer_urls)
stream.wait()
```

<div class="home-quickstart__footer" markdown>
[See LAN setup →](guides/lan-streaming.md)
</div>

</div>

</section>

<section class="home-section" markdown>

<p class="home-kicker">One small API</p>

## From source to stream

<p class="home-section__intro">The media plumbing stays out of your application. You choose the input, add the Python you need, and decide where the result should go.</p>

<div class="home-flow" markdown>

<div class="home-flow__item" markdown>
<span class="home-flow__number">01</span>
### Open
RTSP cameras, webcams, video files, or your own BGR NumPy frames.
</div>

<div class="home-flow__item" markdown>
<span class="home-flow__number">02</span>
### Transform
Chain clear, synchronous frame callbacks with `map()` when Python owns the processing.
</div>

<div class="home-flow__item" markdown>
<span class="home-flow__number">03</span>
### Publish
Serve locally, expose a copy-ready LAN URL, relay to RTSP, or publish SRT.
</div>

</div>

</section>

<section class="home-section home-section--rule" markdown>

<div class="home-split" markdown>

<div markdown>

<p class="home-kicker">Use the interface you want</p>

## CLI or Python

Start a reachable webcam stream from a shell:

```console
easy-rtsp webcam 0 --serve live --lan
```

Or build a processing pipeline in Python:

```python
Stream.open(camera_url).map(detect).serve("annotated").wait()
```

[Read the getting-started guide →](getting-started.md)

</div>

<div markdown>

<p class="home-kicker">Built for edge computer vision</p>

## A clean handoff to native tools

Keep lightweight transforms in Python, or use RTSP as the boundary to an accelerated media and inference stack.

<div class="home-link-list" markdown>
[**GStreamer**<span>Native media pipelines</span>](integrations/gstreamer.md)
[**NVIDIA DeepStream**<span>GPU video analytics</span>](integrations/deepstream.md)
[**NVIDIA Triton**<span>Model serving over HTTP or gRPC</span>](integrations/triton.md)
</div>

</div>

</div>

</section>

<section class="home-principle" markdown>

**Small by design.** NumPy is the only required Python runtime dependency. FFmpeg performs the media work; MediaMTX is optional and managed for you when you need a local or LAN RTSP server.

[See dependencies](operations/dependencies.md)

</section>

</div>
