FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN groupadd --gid 1000 savebot \
    && useradd --uid 1000 --gid savebot --home-dir /app --shell /usr/sbin/nologin --no-create-home savebot

COPY requirements.txt .
RUN pip install --upgrade pip \
    && pip install -r requirements.txt

COPY savebot ./savebot

RUN mkdir -p /data \
    && chown -R savebot:savebot /app /data

USER savebot

CMD ["python", "-m", "savebot.bot"]
