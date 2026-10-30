FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Wheels only - Pillow, reportlab and xhtml2pdf need no system packages.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Uploads and collected static live outside the image so a rebuild keeps them.
RUN useradd -m kagan && mkdir -p /app/media /app/staticfiles && chown -R kagan: /app
USER kagan

EXPOSE 8000

# Migrations run at container start; set DEBUG=False and a real SECRET_KEY in the environment.
CMD ["sh", "-c", "python manage.py migrate --noinput && python manage.py collectstatic --noinput && gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 2 --threads 4 --timeout 120"]
