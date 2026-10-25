FROM python:3.13-slim-bookworm@sha256:ed86c82274b3c69b52fb5820f358f0bd7df0b603332063cb5c6e32bd220c3e6e
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /workspace
# Argos' package loader/tokenizer and its CTranslate2 engine suffice for batched review
# translation. We deliberately do not import its PyTorch/Stanza sentence segmenter.
COPY scripts/translation-requirements.txt scripts/translation-argos-requirements.txt /tmp/
RUN pip install --no-cache-dir -r /tmp/translation-requirements.txt && pip install --no-cache-dir --no-deps -r /tmp/translation-argos-requirements.txt
CMD ["python", "scripts/translate_reviews.py"]
