# syntax=docker/dockerfile:1.7
FROM nvidia/cuda:12.8.1-devel-ubuntu22.04 AS builder

ARG DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential cmake ninja-build python3 python3-dev python3-pip python3-venv \
    && rm -rf /var/lib/apt/lists/*
RUN python3 -m venv /opt/build && /opt/build/bin/pip install --no-cache-dir --upgrade pip build
WORKDIR /src
COPY . .
ENV CMAKE_ARGS="-DCMAKE_CUDA_ARCHITECTURES=75;80;86;89;90"
RUN --mount=type=cache,target=/root/.cache/pip \
    /opt/build/bin/pip wheel --no-deps --wheel-dir /wheelhouse .

FROM nvidia/cuda:12.8.1-runtime-ubuntu22.04
ARG DEBIAN_FRONTEND=noninteractive
ARG RIFT_UID=10001
ARG RIFT_GID=10001
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates python3 python3-pip python3-venv \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid "${RIFT_GID}" rift \
    && useradd --uid "${RIFT_UID}" --gid "${RIFT_GID}" --create-home --home-dir /var/lib/rift rift
RUN python3 -m venv /opt/rift && /opt/rift/bin/pip install --no-cache-dir --upgrade pip
COPY --from=builder /wheelhouse/*.whl /tmp/wheels/
RUN /opt/rift/bin/pip install --no-cache-dir /tmp/wheels/*.whl && rm -rf /tmp/wheels
COPY deploy/config/rift.yaml /etc/rift/rift.yaml
COPY deploy/healthcheck.py /opt/rift/deploy/healthcheck.py
RUN mkdir -p /var/lib/rift/.rift && chown -R rift:rift /var/lib/rift

ENV PATH="/opt/rift/bin:${PATH}" PYTHONUNBUFFERED=1 RIFT_STATE_ROOT=/var/lib/rift
WORKDIR /var/lib/rift
USER rift
EXPOSE 11734
ENTRYPOINT ["rift", "service", "gateway"]
CMD ["--config", "/etc/rift/rift.yaml", "--service", "chat"]
