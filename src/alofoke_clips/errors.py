class PipelineError(Exception):
    """An actionable failure safe to report without dumping a secret or request body."""


class MediaError(PipelineError):
    pass


class ProviderError(PipelineError):
    pass


class ConfigurationError(PipelineError):
    pass


class JobPaused(PipelineError):
    """Cooperative pause after a completed stage has released its model resources."""
