ARG BUILD_FROM=ghcr.io/home-assistant/aarch64-base-debian:bookworm
FROM ${BUILD_FROM}

# Set shell
SHELL ["/bin/bash", "-o", "pipefail", "-c"]

# Install required tools and dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    python3 \
    python3-pip \
    git \
    procps \
    bash \
    jq \
    && rm -rf /var/lib/apt/lists/*

# Install ttyd standalone binary for web terminal Ingress
RUN ARCH="$(uname -m)" && \
    if [ "$ARCH" = "x86_64" ] || [ "$ARCH" = "amd64" ]; then \
        curl -fsSL -o /usr/local/bin/ttyd https://github.com/tsl0922/ttyd/releases/download/1.7.7/ttyd.x86_64; \
    elif [ "$ARCH" = "aarch64" ] || [ "$ARCH" = "arm64" ]; then \
        curl -fsSL -o /usr/local/bin/ttyd https://github.com/tsl0922/ttyd/releases/download/1.7.7/ttyd.aarch64; \
    fi && \
    chmod +x /usr/local/bin/ttyd

# Install Google Antigravity CLI (agy)
RUN curl -fsSL https://antigravity.google/cli/install.sh | bash \
    && if [ -f /root/.local/bin/agy ]; then cp /root/.local/bin/agy /usr/local/bin/agy; fi \
    && if [ -f /root/bin/agy ]; then cp /root/bin/agy /usr/local/bin/agy; fi \
    && chmod +x /usr/local/bin/agy || true

# Set working directory
WORKDIR /app

# Copy application files
COPY bridge/ /app/bridge/
COPY run.sh /app/run.sh
COPY onboarding.sh /app/onboarding.sh

RUN chmod +x /app/run.sh /app/onboarding.sh

CMD [ "/app/run.sh" ]
