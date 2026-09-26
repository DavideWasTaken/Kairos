FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

ENV PORT=8000 \
    WORKERS=2 \
    LOG_LEVEL=info

CMD ["sh", "-c", "exec uvicorn main:app --workers ${WORKERS:-2} --host 0.0.0.0 --port ${PORT:-8000} --log-level ${LOG_LEVEL:-info}"]
