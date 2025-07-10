# Use ubuntu:24.04 as the base image for the builder stage
FROM ubuntu:24.04 AS base

# Define build arguments
ARG POETRY_VERSION=2.1.3
ARG TARGETARCH

ENV PYTHONUNBUFFERED=1 \
    # prevents python creating .pyc files
    PYTHONDONTWRITEBYTECODE=1 \
    \
    # pip
    PIP_NO_CACHE_DIR=off \
    PIP_DISABLE_PIP_VERSION_CHECK=on \
    PIP_DEFAULT_TIMEOUT=100 \
    \
    # poetry
    # make poetry install to this location
    # make poetry create the virtual environment in the project's root
    # it gets named `.venv`
    POETRY_VIRTUALENVS_IN_PROJECT=true \
    POETRY_VIRTUALENVS_CREATE=1 \
    # do not ask any interactive question
    POETRY_NO_INTERACTION=1 \
    \
    # paths
    # this is where our requirements + virtual environment will live
    PYSETUP_PATH="/opt/renovate/app" \
    VENV_PATH="/opt/renovate/app/.venv" \
    # cache directory for poetry
    POETRY_CACHE_DIR=/tmp/poetry_cache \
    # ensure venv is in PATH
    PATH="/opt/renovate/app/.venv/bin:$PATH" \
    \
    # timezone
    TZ="UTC" \
    \
    # other
    DEBIAN_FRONTEND=noninteractive \
    PYTHON=python3.13

# Set the timezone (cached layer)
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# Install Python and basic dependencies with apt cache mount
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && \
    apt-get install -y software-properties-common && \
    add-apt-repository ppa:deadsnakes/ppa && \
    apt-get update && apt-get install -y \
    $PYTHON \
    $PYTHON-venv \
    tzdata \
    && dpkg-reconfigure -f noninteractive tzdata \
    && update-alternatives --install /usr/bin/python python /usr/bin/python3.13 1

# Create virtual environment and install poetry with pip cache mount
RUN --mount=type=cache,target=/root/.cache/pip \
    $PYTHON -m venv $VENV_PATH && \
    $VENV_PATH/bin/pip install --upgrade pip setuptools poetry==$POETRY_VERSION

# Print versions to confirm
RUN $VENV_PATH/bin/pip --version && $VENV_PATH/bin/poetry --version

FROM base AS builder

# Install build dependencies with apt cache mount
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && \
    apt-get install -y \
    $PYTHON-dev \
    build-essential \
    gcc \
    g++ \
    libffi-dev \
    git \
    curl

# Set working directory
WORKDIR $PYSETUP_PATH

# Copy dependency files first for better caching
COPY pyproject.toml poetry.lock ./
COPY README.md ./

# Copy application code (needed for poetry install)
COPY src/ ./src/

# Install dependencies with multiple cache mounts for optimal performance
RUN --mount=type=cache,target=$POETRY_CACHE_DIR \
    --mount=type=cache,target=/root/.cache/pip \
    --mount=type=cache,target=/root/.cache/pypoetry \
    poetry install --only main

FROM base AS runtime

# Install minimal runtime dependencies with apt cache mount
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && \
    apt-get install -y \
    git \
    curl

# Create non-root user
RUN useradd --create-home --shell /bin/bash renovate

# Copy the application and virtual environment from the builder stage
WORKDIR $PYSETUP_PATH
COPY --from=builder ${PYSETUP_PATH} ${PYSETUP_PATH}
COPY --from=builder ${VENV_PATH} ${VENV_PATH}

# Change ownership to non-root user
RUN chown -R renovate:renovate /opt/renovate

# Switch to non-root user
USER renovate

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run the application
CMD ["python", "-m", "renovate_agent.main"]
