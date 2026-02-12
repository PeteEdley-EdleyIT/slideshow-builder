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
from version import __version__
from settings_manager import get_settings_manager

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

        # 2. Run Engine with status reporting
        engine = VideoEngine(config, client)
        
        async def status_reporter(msg, stage):
            """Internal helper to notify Matrix and ntfy for each major step."""
            if matrix.is_configured():
                await matrix.send_message(msg)
            # Use specific tags for ntfy updates
            health_mgr.send_ntfy(msg, title=f"Update: {stage}", tags=["information_source"])

        included_slides = await engine.create_slideshow(output_path, status_callback=status_reporter)
        
        # 3. Final Success Reporting (Summary)
        health_mgr.mark_success()
        
        if matrix.is_configured():
            video_name = config.nc_upload_path or os.path.basename(output_path)
            # send_success already includes the slide list, so it's a good final summary
            await matrix.send_success(video_name, included_slides)
            
        health_mgr.send_ntfy(
            f"Slideshow production flow complete. {len(included_slides)} slides processed.",
            title="Production Complete",
            tags=["trophy"]
        )

    except Exception as e:
        error_msg = str(e)
        trace_str = traceback.format_exc()
        print(f"ERROR: {error_msg}\\n{trace_str}")
        
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
    
    # List of configurable settings
    CONFIGURABLE_SETTINGS = [
        "IMAGE_DURATION",
        "TARGET_VIDEO_DURATION",
        "CRON_SCHEDULE",
        "IMAGE_SOURCE",
        "MUSIC_SOURCE",
        "NEXTCLOUD_IMAGE_PATH",
        "UPLOAD_NEXTCLOUD_PATH",
        "APPEND_VIDEO_PATH",
        "APPEND_VIDEO_SOURCE",
        "ENABLE_HEARTBEAT",
        "NTFY_TOPIC",
        "ENABLE_NTFY",
        "ENABLE_TIMER",
        "TIMER_MINUTES",
        "TIMER_POSITION"
    ]
    
    if command == "!rebuild":
        await matrix.send_message("🚀 Starting manual rebuild...")
        asyncio.create_task(run_automation(matrix))
        
    elif command == "!status":
        stats = health_mgr.get_status_summary()
        
        status_msg = (
            "🤖 **Slideshow Bot Status**\n"
            f"🏷️ **Version**: {__version__}\n"
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
    
    elif command.startswith("!set "):
        # Parse: !set KEY VALUE
        parts = command.split(None, 2)
        if len(parts) < 3:
            await matrix.send_message("❌ Usage: !set KEY VALUE\nExample: !set IMAGE_DURATION 15")
            return
        
        key = parts[1].upper()
        value = parts[2]
        
        if key not in CONFIGURABLE_SETTINGS:
            await matrix.send_message(
                f"❌ '{key}' is not a configurable setting.\n"
                f"Use !config to see available settings."
            )
            return
        
        settings = get_settings_manager()
        settings.set(key, value)
        await matrix.send_message(f"✅ Set {key} = {value}\n\n⚠️ Changes will take effect on next rebuild.")
    
    elif command == "!get all":
        # Show all configurable settings and their current values
        config = Config()
        settings = get_settings_manager()
        overrides = settings.list_all()
        
        lines = ["📋 **Full Configuration Status**\n"]
        for key in CONFIGURABLE_SETTINGS:
            value = getattr(config, key.lower(), "Not set")
            is_override = key in overrides
            marker = "🔹" if is_override else "▫️"
            status = "(Override)" if is_override else "(Default)"
            lines.append(f"{marker} **{key}**: {value} {status}")
        
        lines.append("\n🔹 = Runtime Override active")
        lines.append("▫️ = Using .env/calculated default")
        await matrix.send_message("\n".join(lines))

    elif command.startswith("!get "):
        # Parse: !get KEY
        parts = command.split(None, 1)
        if len(parts) < 2:
            await matrix.send_message("❌ Usage: !get KEY\nExample: !get IMAGE_DURATION")
            return
        
        key = parts[1].upper()
        
        if key not in CONFIGURABLE_SETTINGS:
            await matrix.send_message(f"❌ '{key}' is not a configurable setting.")
            return
        
        config = Config()
        # Get the actual value being used
        value = getattr(config, key.lower(), "Not set")
        
        settings = get_settings_manager()
        db_value = settings.get(key)
        
        if db_value is not None:
            msg = f"📝 {key} = {value}\n(Runtime override active)"
        else:
            msg = f"📝 {key} = {value}\n(Using .env default)"
        
        await matrix.send_message(msg)
    
    elif command == "!config":
        # List all current configuration overrides
        settings = get_settings_manager()
        overrides = settings.list_all()
        
        if not overrides:
            msg = "📋 **Current Configuration**\n\nNo runtime overrides active.\nAll settings are using .env defaults.\n\nUse !set KEY VALUE to override a setting."
        else:
            override_list = "\n".join([f"• {k} = {v}" for k, v in overrides.items()])
            msg = f"📋 **Current Configuration Overrides**\n\n{override_list}\n\nUse !defaults to reset all to .env values."
        
        await matrix.send_message(msg)
    
    elif command == "!defaults":
        # Reset all settings to .env defaults
        settings = get_settings_manager()
        count = settings.reset_all()
        original_message = (
            f"♻️ Reset {count} configuration override(s).\n"
            f"All settings now use .env defaults.\n\n"
            f"⚠️ Changes will take effect on next rebuild."
        )
        await matrix.send_message(original_message)
        
    elif command == "!help":
        help_text = (
            "**Available Commands:**\n\n"
            "**Automation:**\n"
            "• !rebuild - Trigger a manual video generation\n"
            "• !status - Check the bot's health and uptime\n\n"
            "**Configuration:**\n"
            "• !set KEY VALUE - Override a configuration setting\n"
            "• !get KEY - View current value of a setting\n"
            "• !get all - View all settings and their status\n"
            "• !config - List only active configuration overrides\n"
            "• !defaults - Reset all settings to .env defaults\n\n"
            "• !help - Show this message\n\n"
            "**Configurable Settings:**\n"
            "IMAGE_DURATION, TARGET_VIDEO_DURATION, CRON_SCHEDULE,\n"
            "IMAGE_SOURCE, MUSIC_SOURCE,\n"
            "NEXTCLOUD_IMAGE_PATH, UPLOAD_NEXTCLOUD_PATH,\n"
            "APPEND_VIDEO_PATH, APPEND_VIDEO_SOURCE,\n"
            "ENABLE_HEARTBEAT, NTFY_TOPIC, ENABLE_NTFY,\n"
            "ENABLE_TIMER, TIMER_MINUTES, TIMER_POSITION"
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
