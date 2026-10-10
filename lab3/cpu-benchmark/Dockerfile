FROM python:3.13-slim@sha256:7c61056e61ac89e852de05f3dc6fa51a6dd2181797bceed46aa725dd7cb2cd3b
RUN apt-get update && apt-get install -y --no-install-recommends pocl-opencl-icd ocl-icd-libopencl1 clinfo \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /work
COPY requirements.txt /app/requirements.txt
RUN python -m venv /app/.venv && /app/.venv/bin/python -m pip install --no-cache-dir -r /app/requirements.txt
ENV PATH="/app/.venv/bin:$PATH" PYTHONUTF8=1 PYTHONDONTWRITEBYTECODE=1 \
    POCL_MAX_PTHREAD_COUNT=1 POCL_CACHE_DIR=/work/.cache/pocl-cpu XDG_CACHE_HOME=/work/.cache/hashcat-cpu
CMD ["python", "-m", "lab3.src.benchmark", "--smoke", "--repeats", "3", "--backend", "threads", "--workers", "1", "--hashcat", "--hashcat-device", "cpu", "--hashcat-path", ".tools/hashcat/hashcat-7.1.2/hashcat.bin", "--output", "artifacts/cpu-summary"]
