# SUFRA OS - the restaurant's operational system and its database.
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /srv/os
# pinned: see deploy/requirements.lock for why requirements.txt is not used
COPY deploy/requirements.lock ./requirements.lock
RUN pip install --no-cache-dir -r requirements.lock
COPY app ./app
COPY deploy ./deploy
# The database and every uploaded file live on the volume mounted at /data,
# never in the image: a redeploy replaces the image and must not replace them.
ENV NOVA_DB_PATH=/data/nova.db \
    SUFRA_360_VENUE=/srv/os/deploy/venue
EXPOSE 8123
ENTRYPOINT ["sh", "/srv/os/deploy/entrypoint.sh"]
