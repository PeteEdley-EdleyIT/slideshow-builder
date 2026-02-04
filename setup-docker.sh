#!/bin/bash
# Start the Python daemon
echo "Starting Notices Video Automation Daemon..."
# In the container, logs will be visible via 'podman logs notices-automation'
exec python3 create_slideshow.py
