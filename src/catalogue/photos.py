"""Read a bounded raster image and store only a freshly encoded, metadata-free image."""
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
import warnings

from django.core.exceptions import ValidationError
from PIL import Image, ImageOps, UnidentifiedImageError

MAX_UPLOAD = 2 * 1024 * 1024
MAX_PIXELS = 16_000_000
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
                output = BytesIO()
                # A new image discards comments, EXIF, ICC profiles and any trailing uploaded content.
                mode = "RGBA" if "A" in image.getbands() or "transparency" in image.info else "RGB"
                clean = Image.new(mode, image.size)
                clean.paste(image.convert(mode))
                format_name = "PNG" if mode == "RGBA" else "JPEG"
                clean.save(output, format=format_name, **({"quality": 90} if format_name == "JPEG" else {}))
                return EncodedPhoto(output.getvalue(), "image/png" if format_name == "PNG" else "image/jpeg")
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise ValidationError("This photo could not be read. Choose a JPEG, PNG or WebP image.") from None
