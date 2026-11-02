# CPU image for public hosting. Model weights are NOT in the image: scripts/fetch_models.py
# downloads them into /models (a volume) at first start. The Gnani key is never in the image;
# pass GNANI_API_KEY at run time. See docs/DEPLOY.md.
#
# Built and started once with the translation models mounted from a local cache: /healthz
# answered, the process ran as uid 10001 and the health check reported healthy. The first-start
# download needs HF_TOKEN (the models are gated); that path has not been run.

FROM python:3.12-slim-bookworm

COPY --from=ghcr.io/astral-sh/uv:0.12.9 /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# pyproject pins torch to the CUDA index on Linux; the CPU wheel is installed separately instead,
# so none of the CUDA wheels (about 3 GB) are pulled. The exclusions match .github/workflows/ci.yml.
ARG NO_TORCH="--no-install-package torch --no-install-package triton \
 --no-install-package nvidia-cublas-cu12 --no-install-package nvidia-cuda-cupti-cu12 \
 --no-install-package nvidia-cuda-nvrtc-cu12 --no-install-package nvidia-cuda-runtime-cu12 \
 --no-install-package nvidia-cudnn-cu12 --no-install-package nvidia-cufft-cu12 \
 --no-install-package nvidia-cufile-cu12 --no-install-package nvidia-curand-cu12 \
 --no-install-package nvidia-cusolver-cu12 --no-install-package nvidia-cusparse-cu12 \
 --no-install-package nvidia-cusparselt-cu12 --no-install-package nvidia-nccl-cu12 \
 --no-install-package nvidia-nvjitlink-cu12 --no-install-package nvidia-nvshmem-cu12 \
 --no-install-package nvidia-nvtx-cu12"

COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project ${NO_TORCH}
RUN uv pip install --no-deps "torch==2.9.1" --index-url https://download.pytorch.org/whl/cpu

COPY src ./src
COPY scripts/fetch_models.py ./scripts/fetch_models.py
RUN uv sync --locked --no-dev --inexact ${NO_TORCH}

RUN useradd --system --uid 10001 --home-dir /app saathi \
    && mkdir -p /models /data /demo \
    && chown -R saathi /models /data

# HF_HOME is the model cache; /data holds the daily budget counter so a restart cannot reset it.
ENV HF_HOME=/models \
    SAATHI_PUBLIC=1 \
    SAATHI_BUDGET_FILE=/data/gnani_budget.json \
    SAATHI_DEMO_BUNDLE_DIR=/demo/bundle \
    SAATHI_DEMO_CLIPS_DIR=/demo/clips

USER saathi
VOLUME ["/models", "/data"]
EXPOSE 8000

# The first start downloads the models, so allow a long start period.
HEALTHCHECK --interval=30s --timeout=5s --start-period=900s --retries=3 \
    CMD python -c "import urllib.request as u; u.urlopen('http://127.0.0.1:8000/healthz', timeout=4)"

# --no-proxy-headers: uvicorn must not rewrite the client address from X-Forwarded-For. The app
# does that itself, and only for the proxies listed in SAATHI_TRUSTED_PROXIES.
CMD ["sh", "-c", "python scripts/fetch_models.py && exec uvicorn saathi.app:create_app --factory --host 0.0.0.0 --port 8000 --no-proxy-headers"]
