# syntax=docker/dockerfile:1.10
# The API and the agent worker share one image; compose picks the command.
# Base images are pinned by digest, Python packages by uv.lock, and the speech models by
# checksum, so an image tag names exactly the code and models that were evaluated.

FROM ghcr.io/astral-sh/uv:0.11.13@sha256:841c8e6fe30a8b07b4478d12d0c608cba6de66102d29d65d1cc423af86051563 AS uv

FROM python:3.12.15-slim-bookworm@sha256:34386ef0cb081344d7ec1c103ba398e6e9f64e9ab3a1509accc92a4e24a07258

COPY --from=uv /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Dependencies first, so code changes don't reinstall them.
COPY pyproject.toml uv.lock .python-version README.md ./
RUN uv sync --locked --no-dev --no-install-project

COPY src ./src
COPY config ./config
COPY data ./data
RUN uv sync --locked --no-dev

# Kokoro, the agent's voice. Docker checks each file against its checksum.
ADD --checksum=sha256:7d5df8ecf7d4b1878015a32686053fd0eebe2bc377234608764cc0ef3636a6c5 \
    https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx \
    /app/models/kokoro/kokoro-v1.0.onnx
ADD --checksum=sha256:bca610b8308e8d99f32e6fe4197e7ec01679264efed0cac9140fe9c29f1fbf7d \
    https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin \
    /app/models/kokoro/voices-v1.0.bin

# Whisper, which hears the caller: fetched now so a call never waits on a download.
ARG WHISPER_MODEL=base.en
ENV HF_HOME=/app/models/hf \
    HF_HUB_OFFLINE=1 \
    MODELS_DIR=/app/models \
    WHISPER_MODEL=${WHISPER_MODEL} \
    PATH=/app/.venv/bin:$PATH
RUN HF_HUB_OFFLINE=0 python -c "from faster_whisper import WhisperModel; \
WhisperModel('${WHISPER_MODEL}', device='cpu', compute_type='int8')"

RUN useradd --system --uid 10001 --home /app app \
    && mkdir -p /app/recordings && chown app /app/recordings
USER app

# The API by default; the worker's command is set in compose.
EXPOSE 8000
CMD ["uvicorn", "voice_order.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
