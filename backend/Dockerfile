FROM python:3.12-slim

WORKDIR /app

# The build backend needs the package tree present, so copy everything before
# installing. Compose bind-mounts /app over this for live reload in dev.
COPY . .
RUN pip install --no-cache-dir -e ".[dev]"

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
