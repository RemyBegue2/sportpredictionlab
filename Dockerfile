FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    THE_ODDS_API_CACHE=/tmp/odds_api_cache \
    APP_DATABASE_PATH=/tmp/sports_prediction_v3_4.db \
    PYTHONPATH=/app

RUN groupadd --system app && useradd --system --gid app --home-dir /app app
WORKDIR /app

COPY requirements-web.txt .
RUN pip install --no-cache-dir -r requirements-web.txt

COPY --chown=app:app . .
RUN python -c "import site; from pathlib import Path; Path(site.getsitepackages()[0], 'sports_prediction_lab.pth').write_text('/app\n', encoding='utf-8')" \
    && python -c "import sports_predictor; from sports_predictor.cloud_config import CloudSettings; print('runtime import ok')"
USER app
RUN python -m scripts.ensure_artifacts

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:' + __import__('os').environ.get('PORT','8000') + '/api/health', timeout=3)" || exit 1

CMD ["sh","-c","uvicorn webapp:app --host 0.0.0.0 --port ${PORT:-8000} --no-server-header"]
