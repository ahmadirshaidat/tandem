import io
import secrets
import warnings
from pathlib import Path
from typing import Protocol

from fastapi import HTTPException
from PIL import Image, UnidentifiedImageError

from app.core.config import settings

MAX_IMAGE_BYTES = 5 * 1024 * 1024
TYPES = {"PNG": "image/png", "JPEG": "image/jpeg", "WEBP": "image/webp", "GIF": "image/gif"}
Image.MAX_IMAGE_PIXELS = 20_000_000


class ImageStorage(Protocol):
    def put(self, data: bytes) -> str: ...
    def path(self, key: str) -> Path: ...
    def delete(self, key: str) -> None: ...


class LocalImageStorage:
    def put(self, data):
        settings.attachment_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        key = secrets.token_hex(32)
        path = self.path(key)
        with path.open("xb") as output:
            output.write(data)
        path.chmod(0o600)
        return key

    def path(self, key):
        if len(key) != 64 or any(c not in "0123456789abcdef" for c in key):
            raise ValueError("Invalid storage key")
        return settings.attachment_dir / key

    def delete(self, key):
        self.path(key).unlink(missing_ok=True)


storage: ImageStorage = LocalImageStorage()


def inspect_image(data):
    if not data or len(data) > MAX_IMAGE_BYTES:
        raise HTTPException(413, "Images must be between 1 byte and 5 MB")
    magic = (
        data.startswith(b"\x89PNG\r\n\x1a\n")
        or data.startswith(b"\xff\xd8\xff")
        or data.startswith((b"GIF87a", b"GIF89a"))
        or (data.startswith(b"RIFF") and data[8:12] == b"WEBP")
    )
    if not magic:
        raise HTTPException(415, "Use a valid PNG, JPEG, WebP or GIF image")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as image:
                kind, dimensions = image.format, image.size
                if kind not in TYPES:
                    raise ValueError("Unsupported image")
                image.verify()
        return TYPES[kind], *dimensions
    except (
        UnidentifiedImageError,
        SyntaxError,
        OSError,
        ValueError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ):
        raise HTTPException(415, "Use a valid PNG, JPEG, WebP or GIF image") from None
