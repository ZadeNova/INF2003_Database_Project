"""Read a bounded raster image and store only a freshly encoded, metadata-free image."""

import warnings
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from django.core.exceptions import ValidationError
from PIL import Image, ImageOps, UnidentifiedImageError

MAX_UPLOAD = 2 * 1024 * 1024
MAX_PIXELS = 16_000_000
MAX_EDGE = 2048  # the longest side that is stored; a lossy upload otherwise grows into megabytes when re-encoded
ALLOWED_MIME = {"image/jpeg", "image/png", "image/webp"}


@dataclass(frozen=True)
class EncodedPhoto:
    data: bytes
    content_type: str


def clean_photo(upload):
    if upload.size > MAX_UPLOAD:
        raise ValidationError("Choose a photo no larger than 2 MB.")
    if upload.content_type not in ALLOWED_MIME or Path(upload.name).suffix.lower() == ".svg":
        raise ValidationError("Choose a JPEG, PNG or WebP photo.")
    original = upload.read(MAX_UPLOAD + 1)
    if len(original) > MAX_UPLOAD:
        raise ValidationError("Choose a photo no larger than 2 MB.")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(original)) as image:
                if image.format not in {"JPEG", "PNG", "WEBP"} or image.width * image.height > MAX_PIXELS:
                    raise ValidationError("Choose a JPEG, PNG or WebP photo up to 16 megapixels.")
                image.load()
                image = ImageOps.exif_transpose(image)
                # A new image discards comments, EXIF, ICC profiles and any trailing uploaded content.
                mode = "RGBA" if "A" in image.getbands() or "transparency" in image.info else "RGB"
                clean = Image.new(mode, image.size)
                clean.paste(image.convert(mode))
                clean.thumbnail((MAX_EDGE, MAX_EDGE))  # only ever shrinks
                format_name = "PNG" if mode == "RGBA" else "JPEG"
                for quality in (90, 80, 70) if format_name == "JPEG" else (None,):
                    output = BytesIO()
                    clean.save(output, format=format_name, **({"quality": quality} if quality else {}))
                    if output.tell() <= MAX_UPLOAD:  # rule 7: what is stored and served is bounded too
                        return EncodedPhoto(output.getvalue(), "image/png" if format_name == "PNG" else "image/jpeg")
                raise ValidationError(
                    "This photo is too detailed to store within 2 MB. Choose a smaller or simpler photo."
                )
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise ValidationError("This photo could not be read. Choose a JPEG, PNG or WebP image.") from None
