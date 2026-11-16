# syntax=docker/dockerfile:1.7
ARG CUDA_VERSION=12.8.0
# Upstream requires Python >=3.12, provided by Ubuntu 24.04.
ARG UBUNTU_VERSION=24.04
ARG TORCH_CUDA_TAG=cu128

FROM nvidia/cuda:${CUDA_VERSION}-cudnn-runtime-ubuntu${UBUNTU_VERSION} AS builder
ARG TORCH_CUDA_TAG
ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.12 python3.12-venv python3.12-dev build-essential git ca-certificates \
    && rm -rf /var/lib/apt/lists/*
RUN python3.12 -m venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH
RUN pip install --upgrade pip setuptools wheel
RUN pip install --index-url https://download.pytorch.org/whl/${TORCH_CUDA_TAG} \
    torch==2.9.1 torchaudio==2.9.1
WORKDIR /build
COPY engine/model /build/engine/model
COPY engine/third_party/fusealign-multilingual /build/engine/third_party/fusealign-multilingual
# Install only the native model package, not the uv workspace's SGL/MLX/web backends.
RUN pip install /build/engine/third_party/fusealign-multilingual /build/engine/model hf_transfer
COPY docker/requirements.api.txt /tmp/requirements.api.txt
RUN pip install -r /tmp/requirements.api.txt
RUN find /opt/venv -type d -name __pycache__ -exec rm -rf {} +

FROM nvidia/cuda:${CUDA_VERSION}-cudnn-runtime-ubuntu${UBUNTU_VERSION}
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1 \
    LANG=C.UTF-8 LC_ALL=C.UTF-8 \
    HF_HOME=/root/.cache/huggingface HF_HUB_ENABLE_HF_TRANSFER=1 \
    PATH=/opt/venv/bin:$PATH
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.12 ffmpeg libsndfile1 ca-certificates libgomp1 \
    && rm -rf /var/lib/apt/lists/*
COPY --from=builder /opt/venv /opt/venv
WORKDIR /opt/api
COPY app /opt/api/app
COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
VOLUME ["/voices", "/root/.cache"]
EXPOSE 8000
ENTRYPOINT ["/entrypoint.sh"]
CMD []
