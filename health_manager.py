"""
Health monitoring and notification management for the Video Slideshow Automation.

This module provides the `HealthManager` class to track bot metrics, manage
the heartbeat file for container health checks, and send ntfy notifications.
It also includes a `NullLogger` to silence MoviePy's verbose output.
"""

import os
import time
import requests
import proglog

# --- MoviePy Logging Tracking ---

class StatusLogger(proglog.ProgressBarLogger):
    """
    A logger that tracks progress from MoviePy and updates the HealthManager.
    """
    def __init__(self, health_mgr, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.health_mgr = health_mgr
        self.last_update = 0

    def callback(self, **kwargs):
        """Called when a task progresses."""
        if 'index' in kwargs and 'total' in kwargs:
            # Only update if there is a meaningful change to avoid spamming
            progress = int((kwargs['index'] / kwargs['total']) * 100)
            if progress != self.last_update:
                self.health_mgr.update_progress(progress)
                self.last_update = progress

    def bars_callback(self, bar, attr, value, old_value=None):
        """Called when a bar (task) is created or updated."""
        if attr == 'index':
            total = self.bars[bar]['total']
            if total > 0:
                progress = int((value / total) * 100)
                if progress != self.last_update:
                    self.health_mgr.update_progress(progress)
                    self.last_update = progress

def get_status_logger(health_mgr):
    """Returns a StatusLogger instance for MoviePy."""
    return StatusLogger(health_mgr)


# --- Health and Notification Management ---

class HealthManager:
    """
    Manages health metrics, heartbeats, and external notifications.

    Tracks start time, last success time, and updates the heartbeat file
    to indicate the process is still running. Handles ntfy.sh notifications.
    """
    HEARTBEAT_FILE = "/tmp/heartbeat"

    def __init__(self, config=None):
        """
        Initializes the HealthManager.

        Args:
            config (Config, optional): An instance of the Config class for ntfy settings.
        """
        self.config = config
        self.start_time = time.time()
        self.last_success_time = None
        self.last_heartbeat_time = None
        self.current_task = None
        self.current_stage = None
        self.progress = 0

    def update_status(self, stage, task=None):
        """Updates the current active status/stage of the bot."""
        self.current_stage = stage
        self.current_task = task
        if stage is None:
            self.progress = 0

    def update_progress(self, percentage):
        """Updates the progress percentage of the current task."""
        self.progress = percentage

    async def update_heartbeat(self):
        """
        Updates the heartbeat file with the current timestamp.
        
        This file is used by the container engine (e.g., Podman) to verify
        the health of the daemon.
        """
        try:
            # File I/O is usually blocking, but for a tiny heartbeat it's fine.
            # Making this async as it's orchestrated by the async loop.
            with open(self.HEARTBEAT_FILE, "w") as f:
                f.write(str(time.time()))
            self.last_heartbeat_time = time.time()
        except Exception as e:
            print(f"ERROR: Failed to write heartbeat: {e}")

    def mark_success(self):
        """Records the time of a successful automation run."""
        self.last_success_time = time.time()
        self.update_status(None) # Clear active status on completion

    def get_status_summary(self):
        """
        Generates a summary of the bot's health metrics.

        Returns:
            dict: A dictionary containing uptime, last success, and last heartbeat status.
        """
        uptime_seconds = int(time.time() - self.start_time)
        summary = {
            "uptime": f"{uptime_seconds // 3600}h {(uptime_seconds % 3600) // 60}m",
            "last_success": time.ctime(self.last_success_time) if self.last_success_time else "Never",
            "heartbeat_active": self.last_heartbeat_time is not None,
            "active_stage": self.current_stage,
            "active_task": self.current_task,
            "progress": self.progress
        }
        return summary

    def send_ntfy(self, message, title=None, priority="default", tags=None):
        """
        Sends a notification to an ntfy.sh topic.

        Args:
            message (str): The body of the notification.
            title (str, optional): The title of the notification. Emojis should be avoided here.
            priority (str, optional): Notification priority (e.g., 'high', 'low'). Defaults to 'default'.
            tags (list, optional): A list of tag keywords (e.g., ['rocket', 'boom']). Defaults to None.
        """
        if not self.config or not self.config.enable_ntfy:
            return

        ntfy_url = self.config.ntfy_url
        ntfy_topic = self.config.ntfy_topic
        ntfy_token = self.config.ntfy_token

        if not ntfy_url or not ntfy_topic:
            return

        # Ensure URL ends with / and combine with topic
        target_url = ntfy_url.rstrip('/') + '/' + ntfy_topic

        headers = {}
        if ntfy_token:
            headers["Authorization"] = f"Bearer {ntfy_token}"
        
        if title:
            # HTTP headers must be ISO-8859-1. Standard ntfy headers handles UTF-8 
            # if encoded correctly, but for simplicity we ensure it's a valid string.
            try:
                headers["Title"] = title.encode('utf-8').decode('iso-8859-1')
            except UnicodeError:
                headers["Title"] = title.encode('ascii', 'replace').decode('ascii')
        
        if priority:
            headers["Priority"] = priority
        if tags:
            headers["Tags"] = ",".join(tags)

        try:
            response = requests.post(target_url, data=message.encode('utf-8'), headers=headers, timeout=10)
            response.raise_for_status()
        except Exception as e:
            print(f"ERROR: Failed to send ntfy notification to {target_url}: {e}")
