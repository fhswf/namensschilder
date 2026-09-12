FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install --no-install-recommends -y \
        ca-certificates \
        fonts-dejavu-core \
        fop \
        libqrencode4 \
    && rm -rf /var/lib/apt/lists/*

RUN python -m pip install \
        --disable-pip-version-check \
        --no-cache-dir \
        'typer>=0.16,<1'

COPY fonts /action/fonts
COPY assets /action/assets
COPY namensschilder.py /action/namensschilder.py
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh

RUN chmod +x /usr/local/bin/docker-entrypoint.sh

WORKDIR /github/workspace
ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
