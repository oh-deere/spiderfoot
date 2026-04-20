#
# Spiderfoot Dockerfile
#
# http://www.spiderfoot.net
#
# Usage:
#
#   sudo docker build -t spiderfoot .
#   sudo docker run -p 5001:5001 --security-opt no-new-privileges spiderfoot
#
# Using Docker volume for spiderfoot data
#
#   sudo docker run -p 5001:5001 -v /mydir/spiderfoot:/var/lib/spiderfoot spiderfoot
#
# Using SpiderFoot remote command line with web server
#
#   docker run --rm -it spiderfoot sfcli.py -s http://my.spiderfoot.host:5001/
#
# Running spiderfoot commands without web server (can optionally specify volume)
#
#   sudo docker run --rm spiderfoot sf.py -h
#
# Running a shell in the container for maintenance
#   sudo docker run -it --entrypoint /bin/sh spiderfoot
#
# Running spiderfoot unit tests in container
#
#   sudo docker build -t spiderfoot-test --build-arg REQUIREMENTS=test/requirements.txt .
#   sudo docker run --rm spiderfoot-test -m pytest .

# Build the SPA. Node is only present during this stage — the final
# runtime image carries only the emitted dist/ assets.
FROM node:22-slim AS ui-build
WORKDIR /app
COPY webui/package.json webui/package-lock.json webui/
RUN cd webui && npm ci
COPY webui/ webui/
RUN cd webui && npm run build


FROM python:3.12-slim-bookworm AS build
ARG REQUIREMENTS=requirements.txt
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc git curl swig \
        libssl-dev libffi-dev libxslt1-dev libxml2-dev \
        libjpeg-dev zlib1g-dev libopenjp2-7-dev \
    && rm -rf /var/lib/apt/lists/*
RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
COPY $REQUIREMENTS requirements.txt ./
RUN pip3 install --upgrade pip
RUN pip3 install -r "$REQUIREMENTS"



FROM python:3.12-slim-bookworm
WORKDIR /home/spiderfoot

# Place database and logs outside installation directory
ENV SPIDERFOOT_DATA=/var/lib/spiderfoot
ENV SPIDERFOOT_LOGS=/var/lib/spiderfoot/log
ENV SPIDERFOOT_CACHE=/var/lib/spiderfoot/cache

# Structured logging for Loki. Override with SPIDERFOOT_LOG_FORMAT=text
# for interactive debugging (e.g. docker run -it ... /bin/sh).
ENV SPIDERFOOT_LOG_FORMAT=json
ENV SPIDERFOOT_LOG_FILES=false

RUN apt-get update && apt-get install -y --no-install-recommends \
        libxslt1.1 libxml2 libjpeg62-turbo zlib1g libopenjp2-7 \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd spiderfoot \
    && useradd -m -g spiderfoot -d /home/spiderfoot -s /sbin/nologin \
               -c "SpiderFoot User" spiderfoot \
    && mkdir -p $SPIDERFOOT_DATA $SPIDERFOOT_LOGS $SPIDERFOOT_CACHE \
    && chown spiderfoot:spiderfoot $SPIDERFOOT_DATA $SPIDERFOOT_LOGS $SPIDERFOOT_CACHE

COPY . .
COPY --from=ui-build /app/webui/dist /home/spiderfoot/webui/dist
COPY --from=build /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

USER spiderfoot

EXPOSE 5001

# Run the application.
ENTRYPOINT ["/opt/venv/bin/python"]
CMD ["sf.py", "-l", "0.0.0.0:5001"]
