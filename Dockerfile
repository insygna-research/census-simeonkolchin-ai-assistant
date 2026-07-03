FROM python:3.11-slim

WORKDIR /app

# Shared browser location accessible by any user
ENV PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python packages using multiple PyPI mirrors for faster downloads
RUN pip install --no-cache-dir -r requirements.txt \
    -i https://pypi.tuna.tsinghua.edu.cn/simple \
    --trusted-host pypi.tuna.tsinghua.edu.cn \
    || pip install --no-cache-dir -r requirements.txt \
    -i https://mirrors.aliyun.com/pypi/simple/ \
    --trusted-host mirrors.aliyun.com \
    || pip install --no-cache-dir -r requirements.txt

# Install Playwright Chromium with all OS dependencies into shared path
RUN playwright install --with-deps chromium

# Copy application code
COPY . .

# Create non-root user
RUN useradd -m -u 1000 agent \
    && chown -R agent:agent /app
USER agent

# Expose port
EXPOSE 8080

# Run the application
CMD ["python", "main.py", "--host", "0.0.0.0", "--port", "8080"]
