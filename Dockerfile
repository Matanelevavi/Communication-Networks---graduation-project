# WeatherWear: four network servers and the website, in one container.
# Only the HTTP port is published; DHCP, DNS, TCP and RUDP stay on loopback.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    BIND=0.0.0.0 \
    PORT=10000 \
    TRUST_PROXY=1

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY run.py .
COPY src ./src
RUN mkdir -p data \
    && useradd --create-home --uid 10001 weatherwear \
    && chown -R weatherwear /app/data

# never run as root, even inside the container
USER weatherwear

EXPOSE 10000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
    CMD python -c "import os,urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.environ[\"PORT\"]}/api/health', timeout=4)"

CMD ["python", "-m", "src.web.serve"]
