FROM python:3.12-slim
ARG DEBIAN_FRONTEND=noninteractive
ARG RIFT_UID=10001
ARG RIFT_GID=10001
RUN groupadd --gid "${RIFT_GID}" rift \
    && useradd --uid "${RIFT_UID}" --gid "${RIFT_GID}" --create-home --home-dir /var/lib/rift rift
WORKDIR /src
COPY . .
RUN python -m pip install --no-cache-dir .
COPY deploy/config/node-agent.yaml /etc/rift/node-agent.yaml
COPY deploy/healthcheck.py /opt/rift/deploy/healthcheck.py
RUN mkdir -p /var/lib/rift && chown -R rift:rift /var/lib/rift /opt/rift

ENV PYTHONUNBUFFERED=1 RIFT_HOME=/var/lib/rift RIFT_STATE_ROOT=/var/lib/rift
WORKDIR /var/lib/rift
USER rift
EXPOSE 11750
ENTRYPOINT ["rift", "node", "serve"]
CMD ["--config", "/etc/rift/node-agent.yaml", "--root", "/var/lib/rift"]
