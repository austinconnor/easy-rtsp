"""Library-specific errors."""


class EasyRtspError(Exception):
    """Base class for easy-rtsp errors."""


class DependencyError(EasyRtspError):
    """A required external binary or optional dependency is missing."""


class ConfigurationError(EasyRtspError):
    """Invalid arguments or incompatible configuration."""


class SourceError(EasyRtspError):
    """Input source failed (open, read, or decode)."""


class PublishError(EasyRtspError):
    """Publishing or backend startup failed."""


class ProcessingError(EasyRtspError):
    """User transform or frame pipeline raised."""
