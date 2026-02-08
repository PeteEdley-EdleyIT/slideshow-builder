"""
Main Controller for the Video Slideshow Automation.

This script acts as the central coordinator, setting up the scheduler,
initializing the Matrix bot listener, and managing the overall automation
lifecycle. It utilizes specialized modules for configuration, health monitoring,
and video production.
"""

import asyncio
import os
import time
import traceback
import tempfile
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from dotenv import load_dotenv

# Internal Modules
from config_manager import Config, get_env_var, get_env_bool
from health_manager import HealthManager, silence_moviepy
from video_engine import VideoEngine
from matrix_client import MatrixClient
from nextcloud_client import NextcloudClient
from video_utils import patch_moviepy

# Initialize Global State
load_dotenv()
patch_moviepy()
silence_moviepy()

# Global Health Instance
health_mgr = HealthManager()

async def run_automation(matrix=None):
    """
    High-level automation workflow called by the scheduler or manual trigger.
    """
    config = Config()
    health_mgr.config = config # Sync config for ntfy
    
    # Initialize Matrix if not provided
    created_matrix = False
    if not matrix:
        matrix = MatrixClient(
            config.matrix_homeserver, 
            config.matrix_token, 
            config.matrix_room, 
            config.matrix_user_id
        )
        created_matrix = True

    client = None
    temp_output_file = None

    try:
        print("Starting scheduled slideshow automation...")
        health_mgr.send_ntfy(
            "Starting slideshow production...",
            title="Rebuild Started",
            priority="low",
            tags=["rocket", "running"]
        )

        # 1. Setup Clients
        if config.nc_url and config.nc_user:
            client = NextcloudClient(
                config.nc_url, 
                config.nc_user, 
                config.nc_pass, 
                verify_ssl=not config.nc_insecure
            )

        output_path = config.output_filepath
        if not output_path and config.nc_upload_path:
            fd, output_path = tempfile.mkstemp(suffix=".mp4")
            os.close(fd)
            temp_output_file = output_path

        if not output_path:
            raise ValueError("No output path specified and no Nextcloud upload path configured.")

        # 2. Run Engine
        engine = VideoEngine(config, client)
        included_slides = engine.create_slideshow(output_path)
        
        # 3. Success Reporting
        health_mgr.mark_success()
        
        if matrix.is_configured():
            video_name = config.nc_upload_path or os.path.basename(output_path)
            await matrix.send_success(video_name, included_slides)
            
        health_mgr.send_ntfy(
            f"Slideshow produced successfully with {len(included_slides)} slides.",
            title="Slideshow Complete",
            tags=["white_check_mark", "movie_camera"]
        )

    except Exception as e:
        error_msg = str(e)
        trace_str = traceback.format_exc()
        print(f"ERROR: {error_msg}\n{trace_str}")
        
        if matrix.is_configured():
            await matrix.send_failure(error_msg, trace_str)
        
        health_mgr.send_ntfy(
            f"Slideshow production failed: {error_msg}",
            title="Slideshow Failed",
            priority="high",
            tags=["x", "boom"]
        )
    finally:
        if created_matrix and matrix:
            await matrix.close()
        if temp_output_file and os.path.exists(temp_output_file):
            os.remove(temp_output_file)


async def handle_matrix_message(matrix, room, event):
    """Callback for handling Matrix commands."""
    command = event.body.strip()
    print(f"Processing command: '{command}' from {event.sender}")
    
    if command == "!rebuild":
        await matrix.send_message("🚀 Starting manual rebuild...")
        asyncio.create_task(run_automation(matrix))
        
    elif command == "!status":
        stats = health_mgr.get_status_summary()
        
        status_msg = (
            "🤖 **Slideshow Bot Status**\n"
            f"⏱️ **Uptime**: {stats['uptime']}\n"
            f"✅ **Last Success**: {stats['last_success']}\n"
            f"💓 **Heartbeat Active**: {'Yes' if stats['heartbeat_active'] else 'No'}\n"
        )
        
        # Quick Nextcloud Connectivity Check
        config = Config()
        if config.nc_url and config.nc_user:
            try:
                nc = NextcloudClient(config.nc_url, config.nc_user, config.nc_pass, verify_ssl=not config.nc_insecure)
                status_msg += "☁️ **Nextcloud**: Connected\n"
            except Exception:
                status_msg += "☁️ **Nextcloud**: ❌ Connection Failed\n"
        
        await matrix.send_message(status_msg)
        
    elif command == "!help":
        help_text = (
            "Available commands:\n"
            "!rebuild - Trigger a manual video generation\n"
            "!status - Check the bot's health and uptime\n"
            "!help - Show this message"
        )
        await matrix.send_message(help_text)


async def main():
    """Main daemon loop."""
    config = Config()
    health_mgr.config = config
    
    matrix = MatrixClient(
        config.matrix_homeserver, 
        config.matrix_token, 
        config.matrix_room, 
        config.matrix_user_id
    )
    
    print(f"Starting Matrix bot daemon with schedule: {config.cron_schedule}")
    
    scheduler = AsyncIOScheduler()
    
    # Schedule Video Production
    try:
        trigger = CronTrigger.from_crontab(config.cron_schedule)
        scheduler.add_job(run_automation, trigger, args=[matrix], id="slideshow_job")
        print(f"Scheduled slideshow job: {config.cron_schedule}")
    except Exception as e:
        print(f"Failed to schedule job '{config.cron_schedule}': {e}. Using default Friday 1AM.")
        scheduler.add_job(run_automation, CronTrigger.from_crontab("0 1 * * 5"), args=[matrix])

    # Schedule Heartbeat
    if config.enable_heartbeat:
        print("Enabling heartbeat mechanism...")
        scheduler.add_job(health_mgr.update_heartbeat, 'interval', minutes=1, id="heartbeat_job")
        asyncio.create_task(health_mgr.update_heartbeat())

    scheduler.start()

    if matrix.is_configured():
        matrix.add_message_callback(lambda room, event: handle_matrix_message(matrix, room, event))
        listener_task = asyncio.create_task(matrix.listen_forever())
        print("Matrix listener active.")
    else:
        print("Matrix not configured, running in scheduler-only mode.")
        listener_task = None

    try:
        while True:
            await asyncio.sleep(3600)
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()
        if matrix:
            await matrix.close()
        if listener_task:
            listener_task.cancel()

if __name__ == "__main__":
    asyncio.run(main())
