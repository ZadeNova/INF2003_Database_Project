import logging
import os

from django.conf import settings
from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
application = get_wsgi_application()

# One startup event per worker process, after Django configures the existing JSON logger.
logging.getLogger("mercer.runtime").info(
    "Application process started", extra={"fields": {"release": settings.RELEASE_ID}}
)
