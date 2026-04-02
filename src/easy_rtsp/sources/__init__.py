"""Source adapters."""

from easy_rtsp.sources.file import FileSource
from easy_rtsp.sources.frames import FrameGeneratorSource
from easy_rtsp.sources.rtsp import RtspSource
from easy_rtsp.sources.webcam import WebcamSource

__all__ = [
    "FileSource",
    "FrameGeneratorSource",
    "RtspSource",
    "WebcamSource",
]
