FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN addgroup --system savebot \
    && adduser --system --ingroup savebot --home /app savebot

COPY requirements.txt .
RUN pip install --upgrade pip \
    && pip install -r requirements.txt

COPY savebot ./savebot

RUN mkdir -p /data \
    && chown -R savebot:savebot /app /data

USER savebot

CMD ["python", "-m", "savebot.bot"]
