#!/bin/bash

# Export environment variables for cron
# Cron runs in a clean environment, so we need to bridge the container's env vars.
# Export environment variables for cron, ensuring values are quoted to handle spaces
printenv | grep -v "no_proxy" | sed 's/^\([^=]*\)=\(.*\)/export \1="\2"/' > /app/.env.cron

# Create the crontab file
# We'll run it every 5 minutes by default
# We source the .env.cron (converting it to exports) before running the script
# Default to Friday at 1:00 AM if not set
CRON_SCHEDULE=${CRON_SCHEDULE:-"0 1 * * 5"}
# Strip potential surrounding quotes
CRON_SCHEDULE=$(echo "$CRON_SCHEDULE" | sed 's/^"//;s/"$//')
echo "$CRON_SCHEDULE . /app/.env.cron; python3 /app/create_slideshow.py >> /var/log/slideshow.log 2>&1" > /tmp/crontab.root

# Install crontab
crontab /tmp/crontab.root

# Start cron daemon in the foreground
echo "Starting cron daemon..."
exec cron -n
