from pathlib import Path

from .errors import PipelineError
from .media import MediaTools
from .models import MediaInfo
from .storage import sha256_file


def ingest_local(source: Path, authorized: bool, media: MediaTools) -> tuple[MediaInfo, str]:
    if not authorized:
        raise PipelineError(
            "confirm permission to process this local recording with --authorized-local"
        )
    info = media.validate(source)
    return info, sha256_file(source)
