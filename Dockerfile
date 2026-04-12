FROM mcr.microsoft.com/playwright/python:v1.40.0-jammy

# HuggingFace requires applications to run as a non-root user (id 1000)
RUN useradd -m -u 1000 user
USER user

ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH

WORKDIR $HOME/app

# Copy the project files
COPY --chown=user . $HOME/app

# Install Python requirements
RUN pip install --no-cache-dir --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

# Install chromium engine natively
RUN playwright install chromium

# HuggingFace strictly requires port 7860
EXPOSE 7860

# Start command
CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "7860"]
