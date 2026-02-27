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
from health_manager import HealthManager
from video_engine import VideoEngine
from matrix_client import MatrixClient
from nextcloud_client import NextcloudClient
from video_utils import patch_moviepy
from version import __version__
from settings_manager import get_settings_manager
from bot_interface import BotInterface

# Initialize Global State
load_dotenv()
patch_moviepy()
# silence_moviepy() - Replaced by real-time ProgressLogger in HealthManager

# Global Health Instance
health_mgr = HealthManager()

async def run_automation(matrix=None):
    """
    High-level automation workflow called by the scheduler or manual trigger.
    """
    config = Config()
    health_mgr.config = config # Sync config for ntfy
    
    # Check if a job is already running
    if health_mgr.current_stage is not None:
        msg = "⚠️ A video production job is already in progress. Please try again later."
        print(f"ABORT: {msg}")
        
        if matrix and matrix.is_configured():
            await matrix.send_message(msg)
            
        asyncio.create_task(asyncio.to_thread(
            health_mgr.send_ntfy, 
            msg, 
            title="Production Skipped",
            priority="default",
            tags=["warning", "stopwatch"]
        ))
        return
    
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
        # Background the initial ntfy to avoid blocking
        asyncio.create_task(asyncio.to_thread(
            health_mgr.send_ntfy, 
            "Starting slideshow production...", 
            title="Rebuild Started", 
            priority="low", 
            tags=["rocket", "running"]
        ))

        # 1. Setup Clients
        health_mgr.update_status("Starting", "Setting up Nextcloud client")
        if config.nc_url and config.nc_user:
            client = NextcloudClient(
                config.nc_url, 
                config.nc_user, 
                config.nc_pass, 
                verify_ssl=not config.nc_insecure
            )

        health_mgr.update_status("Starting", "Checking output paths")
        output_path = config.output_filepath
        if not output_path and config.upload_nextcloud_path:
            fd, output_path = tempfile.mkstemp(suffix=".mp4")
            os.close(fd)
            temp_output_file = output_path

        if not output_path:
            raise ValueError("No output path specified and no Nextcloud upload path configured.")

        # 2. Run Engine with status reporting
        engine = VideoEngine(config, client, health_mgr=health_mgr)
        
        async def status_reporter(msg, stage):
            """Internal helper to notify Matrix and ntfy for each major step."""
            # Update health manager for !status command
            health_mgr.update_status(stage, msg.replace('✅ ', '').replace('💾 ', '').replace('☁️ ', ''))
            
            if matrix.is_configured():
                await matrix.send_message(msg)
            # Use specific tags for ntfy updates
            await asyncio.to_thread(health_mgr.send_ntfy, msg, title=f"Update: {stage}", tags=["information_source"])

        # Validate resources before starting heavy processing
        await engine.validate_resources()

        included_slides = await engine.create_slideshow(output_path, status_callback=status_reporter)
        
        # 3. Final Success Reporting (Summary)
        health_mgr.mark_success()
        
        if matrix.is_configured():
            video_name = config.upload_nextcloud_path or os.path.basename(output_path)
            # send_success already includes the slide list, so it's a good final summary
            await matrix.send_success(video_name, included_slides)
            
        await asyncio.to_thread(
            health_mgr.send_ntfy,
            f"Slideshow production flow complete. {len(included_slides)} slides processed.",
            title="Production Complete",
            tags=["trophy"]
        )

    except Exception as e:
        health_mgr.update_status(None) # Clear active status on error
        error_msg = str(e)
        trace_str = traceback.format_exc()
        print(f"ERROR: {error_msg}\\n{trace_str}")
        
        if matrix.is_configured():
            await matrix.send_failure(error_msg, trace_str)
        
        await asyncio.to_thread(
            health_mgr.send_ntfy,
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


def get_apscheduler_trigger(cron_str):
    """
    Creates an APScheduler CronTrigger from a standard crontab string.
    
    Translates the 5th field (weekday) from crontab standard (0,7=Sun, 1=Mon, ..., 6=Sat)
    to APScheduler standard (0=Mon, 1=Tue, ..., 6=Sun).
    """
    parts = cron_str.split()
    if len(parts) >= 5:
        weekday = parts[4]
        
        # Mapping: Crontab (0-7, 0/7=Sun) -> APScheduler (0-6, 0=Mon, 6=Sun)
        # Translation table: 
        # 1 -> 0 (Mon)
        # 2 -> 1 (Tue)
        # 3 -> 2 (Wed)
        # 4 -> 3 (Thu)
        # 5 -> 4 (Fri)
        # 6 -> 5 (Sat)
        # 0, 7 -> 6 (Sun)
        
        mapping = {
            "1": "0", "2": "1", "3": "2", "4": "3", "5": "4", "6": "5", "0": "6", "7": "6",
            "MON": "0", "TUE": "1", "WED": "2", "THU": "3", "FRI": "4", "SAT": "5", "SUN": "6"
        }
        
        if weekday.upper() in mapping:
            parts[4] = mapping[weekday.upper()]
        elif "-" in weekday:
            # Handle simple ranges like 1-5
            r_parts = weekday.split("-")
            if len(r_parts) == 2 and r_parts[0] in mapping and r_parts[1] in mapping:
                parts[4] = f"{mapping[r_parts[0].upper()]}-{mapping[r_parts[1].upper()]}"
        
        resolved_cron = " ".join(parts)
        return CronTrigger.from_crontab(resolved_cron)
    
    return CronTrigger.from_crontab(cron_str)


async def handle_matrix_message(matrix, room, event, scheduler=None):
    """Callback for handling Matrix commands."""
    command = event.body.strip()
    print(f"Processing command: '{command}' from {event.sender}")
    
    config = Config()
    ui = BotInterface()
    
    if command == "!rebuild":
        await matrix.send_message("🚀 Starting manual rebuild...")
        asyncio.create_task(run_automation(matrix))
        
    elif command == "!status":
        stats = health_mgr.get_status_summary()
        plain, html = ui.format_status(stats, config)
        await matrix.send_message(plain, html_message=html)
    
    elif command.startswith("!set "):
        # Parse: !set KEY VALUE
        parts = command.split(None, 2)
        if len(parts) < 3:
            await matrix.send_message("❌ Usage: !set KEY VALUE\nExample: !set IMAGE_DURATION 15")
            return
        
        key = parts[1].upper()
        value = parts[2]
        
        if key not in config.CONFIGURABLE_SETTINGS:
            await matrix.send_message(
                f"❌ '{key}' is not a configurable setting.\n"
                f"Use !get all to see available settings."
            )
            return
        
        settings = get_settings_manager()
        settings.set(key, value)
        
        # Immediate Rescheduling for Cron
        reschedule_msg = ""
        if key == "CRON_SCHEDULE" and scheduler:
            try:
                trigger = get_apscheduler_trigger(value)
                scheduler.reschedule_job("slideshow_job", trigger=trigger, misfire_grace_time=3600)
                
                # Log and inform user about next fire time
                job = scheduler.get_job("slideshow_job")
                next_fire = getattr(job, 'next_run_time', "Unknown")
                print(f"Schedule updated! Next run at: {next_fire}")
                reschedule_msg = f"\n🚀 Schedule updated! Next run at: {next_fire} (applied immediately)"
            except Exception as e:
                reschedule_msg = f"\n❌ Failed to reschedule: {e}"

        await matrix.send_message(f"✅ Set {key} = {value}{reschedule_msg}")
    
    elif command == "!get all":
        # Show all configurable settings grouped by category
        plain, html = ui.format_full_config(config)
        await matrix.send_message(plain, html_message=html)

    elif command.startswith("!get "):
        # Parse: !get KEY
        parts = command.split(None, 1)
        if len(parts) < 2:
            await matrix.send_message("❌ Usage: !get KEY\nExample: !get IMAGE_DURATION")
            return
        
        key = parts[1].upper()
        
        if key not in config.CONFIGURABLE_SETTINGS:
            await matrix.send_message(f"❌ '{key}' is not a configurable setting.")
            return
        
        # Get the actual value being used
        value = getattr(config, key.lower(), "Not set")
        
        if key.upper() == "CRON_SCHEDULE" and value != "Not set":
            try:
                import cron_descriptor
                import croniter
                from datetime import datetime
                
                desc = cron_descriptor.get_description(value)
                
                # Calculate next run time
                now = datetime.now()
                iter = croniter.croniter(value, now)
                next_run = iter.get_next(datetime)
                
                # Format as Next Run: YYYY-MM-DD HH:MM:SS
                time_str = next_run.strftime('%Y-%m-%d %H:%M:%S')
                
                value = f"{value} ({desc}) [Next Run: {time_str}]"
            except Exception as e:
                print(f"Error parsing cron for display: {e}")
                pass
        
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
            msg = "📋 Current Configuration\n\nNo runtime overrides active.\nAll settings are using .env defaults.\n\nUse !set KEY VALUE to override a setting."
        else:
            override_list = "\n".join([f"• {k} = {v}" for k, v in overrides.items()])
            msg = f"📋 Current Configuration Overrides\n\n{override_list}\n\nUse !defaults to reset all to .env values."
        
        await matrix.send_message(msg)
    
    elif command == "!defaults":
        # Reset all settings to .env defaults
        settings = get_settings_manager()
        count = settings.reset_all()
        original_message = (
            f"♻️ Reset {count} configuration override(s).\n"
            f"All settings now use .env defaults."
        )
        
        # Reset cron if needed
        if scheduler:
            try:
                trigger = get_apscheduler_trigger(config.cron_schedule)
                scheduler.reschedule_job("slideshow_job", trigger=trigger, misfire_grace_time=3600)
                
                job = scheduler.get_job("slideshow_job")
                next_fire = getattr(job, 'next_run_time', "Unknown")
                original_message += f"\n🚀 Schedule reset! Next run at: {next_fire} (applied immediately)"
            except Exception:
                pass

        await matrix.send_message(original_message)
        
    elif command == "!help":
        plain, html = ui.format_help(config)
        await matrix.send_message(plain, html_message=html)


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
    scheduler.start()
    
    # Schedule Video Production
    try:
        trigger = get_apscheduler_trigger(config.cron_schedule)
        scheduler.add_job(
            run_automation, 
            trigger, 
            args=[matrix], 
            id="slideshow_job", 
            max_instances=2, 
            misfire_grace_time=3600,
            replace_existing=True
        )
        
        job = scheduler.get_job("slideshow_job")
        next_fire = getattr(job, 'next_run_time', "Unknown")
        print(f"Scheduled slideshow job: {config.cron_schedule} (Next run: {next_fire})")
    except Exception as e:
        print(f"Failed to schedule job '{config.cron_schedule}': {e}. Using default Friday 1AM.")
        fallback_trigger = get_apscheduler_trigger("0 1 * * 5")
        scheduler.add_job(
            run_automation, 
            fallback_trigger, 
            args=[matrix], 
            id="slideshow_job", 
            max_instances=2, 
            misfire_grace_time=3600,
            replace_existing=True
        )

    # Schedule Heartbeat
    if config.enable_heartbeat:
        print("Enabling heartbeat mechanism...")
        scheduler.add_job(
            health_mgr.update_heartbeat, 
            'interval', 
            minutes=1, 
            id="heartbeat_job",
            replace_existing=True
        )
        asyncio.create_task(health_mgr.update_heartbeat())

    if matrix.is_configured():
        matrix.add_message_callback(lambda room, event: handle_matrix_message(matrix, room, event, scheduler=scheduler))
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
