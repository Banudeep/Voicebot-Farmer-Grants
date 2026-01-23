# Voice Agent Dockerfile
# Multi-stage build for optimized image size

FROM python:3.11-slim as builder

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    make \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Final stage
FROM python:3.11-slim

# Install runtime dependencies
# Note: PyAudio dependencies included but may not be needed for browser-based audio
RUN apt-get update && apt-get install -y --no-install-recommends \
    portaudio19-dev \
    libasound2-dev \
    && rm -rf /var/lib/apt/lists/*

# Create app user for security
RUN useradd -m -u 1000 appuser && \
    mkdir -p /app/recordings && \
    chown -R appuser:appuser /app

# Copy Python dependencies from builder
COPY --from=builder /root/.local /home/appuser/.local

# Set environment variables
ENV PATH=/home/appuser/.local/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Set working directory
WORKDIR /app

# Copy application files
COPY . .

# Create recordings directory and ensure ownership of all files
RUN mkdir -p recordings && \
    chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

# Expose ports
# 8080: HTTP server for web UI
# 3000: WebSocket server for audio/communication
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import socket; s = socket.socket(); s.connect(('localhost', 8080)); s.close()" || exit 1

# Run the application
# Set PYTHONPATH to include src directory
ENV PYTHONPATH="${PYTHONPATH}:/app/src"

# Run the application
CMD ["python", "src/web_voice_agent.py"]

