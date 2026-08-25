# syntax=docker/dockerfile:1
FROM python:3.12-slim-bookworm AS base

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    GOPATH=/go \
    PATH="/usr/local/go/bin:/go/bin:${PATH}" \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

# 1. Install system utilities and build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    sqlite3 \
    fontconfig \
    ca-certificates \
    build-essential \
    pkg-config \
    xz-utils \
    tar \
    && rm -rf /var/lib/apt/lists/*

# 2. Install Node.js (v20 LTS) & npm
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y --no-install-recommends nodejs && \
    npm install -g npm@latest && \
    rm -rf /var/lib/apt/lists/*

# 3. Install Go toolchain (1.23.6)
RUN ARCH=$(dpkg --print-architecture) && \
    if [ "$ARCH" = "amd64" ]; then GO_ARCH="amd64"; \
    elif [ "$ARCH" = "arm64" ]; then GO_ARCH="arm64"; \
    else GO_ARCH="amd64"; fi && \
    curl -fsSL "https://go.dev/dl/go1.23.6.linux-${GO_ARCH}.tar.gz" | tar -C /usr/local -xzf -

# 4. Install Typst binary
RUN ARCH=$(dpkg --print-architecture) && \
    if [ "$ARCH" = "amd64" ]; then TYPST_ARCH="x86_64-unknown-linux-musl"; \
    elif [ "$ARCH" = "arm64" ]; then TYPST_ARCH="aarch64-unknown-linux-musl"; \
    else TYPST_ARCH="x86_64-unknown-linux-musl"; fi && \
    TYPST_VERSION="v0.12.0" && \
    curl -fsSL "https://github.com/typst/typst/releases/download/${TYPST_VERSION}/typst-${TYPST_ARCH}.tar.xz" | \
    tar -xJf - --strip-components=1 -C /usr/local/bin "typst-${TYPST_ARCH}/typst" && \
    chmod +x /usr/local/bin/typst

WORKDIR /workspace

# 5. Install Playwright browser dependencies & Chromium
COPY package.json package-lock.json* ./
RUN npm install && \
    npx playwright install --with-deps chromium

# 6. Install Python dependencies
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# 7. Copy project fonts into system font library
COPY resume-engine/fonts/ /usr/local/share/fonts/resume-builder/
RUN fc-cache -f -v

# 8. Copy full repository
COPY . .

# Setup default alias for resume CLI
RUN echo 'alias resume="python3 /workspace/scripts/cli.py"' >> /root/.bashrc

CMD ["python3", "scripts/cli.py"]
