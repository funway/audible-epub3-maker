# Use the official lightweight Python 3.11 image (based on Debian Bookworm)
FROM python:3.11-slim-bookworm

# Prevent Python from buffering stdout/stderr to ensure real-time logs in Docker
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install system dependencies
# - ffmpeg, for audio processing
# - tini, as init process (PID 1)
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg tini && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Copy only requirements.txt first to leverage Docker layer caching
COPY requirements.txt ./

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the entire project into the container's WORKDIR
COPY . .

# Declare that the container will listen on port 7860 at runtime
EXPOSE 7860

# Set tini as PID 1 to reap zombies and forward signals; 
ENTRYPOINT ["/usr/bin/tini", "--"]

# Define the default command to run when the container starts (after tini)
CMD [ "python3", "web_gui.py", "--host", "0.0.0.0", "--port", "7860" ]
