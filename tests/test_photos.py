"""A stored photo is bounded in size and edge length however the upload was compressed (AGENTS.md rule 7)."""

import os
from io import BytesIO

import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image

from catalogue import photos


def noisy(size, colour=False):
    """Detailed content that compresses badly, like a real photograph."""
    return Image.frombytes("RGB", size, os.urandom(size[0] * size[1] * 3)) if colour else Image.effect_noise(size, 60)


def upload(image, format_name, content_type, **options):
    data = BytesIO()
    image.convert("RGB").save(data, format=format_name, **options)
    return SimpleUploadedFile("photo", data.getvalue(), content_type=content_type)


def lossy_upload_within_the_limit(size):
    """The most detailed WebP of this size that is still small enough to be accepted as an upload."""
    image = noisy(size)
    for quality in (40, 25, 15, 10, 5, 1):
        source = upload(image, "WEBP", "image/webp", quality=quality)
        if source.size <= photos.MAX_UPLOAD:
            return source
    raise AssertionError("no quality fits")


def test_a_large_lossy_upload_is_shrunk_and_stays_within_the_limit():
    source = lossy_upload_within_the_limit((3000, 3000))
    assert source.size <= photos.MAX_UPLOAD  # accepted as an upload ...
    stored = photos.clean_photo(source)
    # ... and re-encoded it used to grow several times over; now it is shrunk and bounded.
    assert len(stored.data) <= photos.MAX_UPLOAD
    with Image.open(BytesIO(stored.data)) as image:
        assert max(image.size) == photos.MAX_EDGE and image.size[0] == image.size[1]


def test_a_small_photo_keeps_its_size_and_a_tall_one_keeps_its_shape():
    small = photos.clean_photo(upload(noisy((24, 16)), "PNG", "image/png"))
    with Image.open(BytesIO(small.data)) as image:
        assert image.size == (24, 16)
    tall = photos.clean_photo(lossy_upload_within_the_limit((900, 3000)))
    with Image.open(BytesIO(tall.data)) as image:
        assert max(image.size) == photos.MAX_EDGE and image.size == (614, 2048)  # 900 x 3000 scaled by 2048 / 3000


def test_a_photo_that_cannot_be_stored_within_the_limit_is_refused(monkeypatch):
    source = upload(noisy((1200, 1200)), "WEBP", "image/webp", quality=5)
    monkeypatch.setattr(photos, "MAX_UPLOAD", source.size)  # accepted as an upload, but its JPEG is bigger than that
    with pytest.raises(ValidationError, match="too detailed"):
        photos.clean_photo(source)
