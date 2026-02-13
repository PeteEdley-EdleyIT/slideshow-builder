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


async def handle_matrix_message(matrix, room, event):
    """Callback for handling Matrix commands."""
    command = event.body.strip()
    print(f"Processing command: '{command}' from {event.sender}")
    
    # Shared configuration grouping for !get all and !help
    GROUPS = {
        "⚙️ **General**": ["IMAGE_DURATION", "TARGET_VIDEO_DURATION", "CRON_SCHEDULE"],
        "☁️ **Nextcloud**": [
            "NEXTCLOUD_UPLOAD_PATH", 
            None,
            "IMAGE_SOURCE", 
            "NEXTCLOUD_IMAGE_PATH", 
            None,
            "MUSIC_SOURCE", 
            "MUSIC_FOLDER", 
            None,
            "APPEND_VIDEO_SOURCE", 
            "APPEND_VIDEO_PATH"
        ],
        "⏱️ **Timer Settings**": ["ENABLE_TIMER", "TIMER_MINUTES", "TIMER_POSITION"],
        "💓 **Heartbeat**": ["ENABLE_HEARTBEAT"],
        "🔔 **NTFY**": ["ENABLE_NTFY", "NTFY_TOPIC"]
    }
    
    # Flatten GROUPS for validation and simple lists, filtering out None
    CONFIGURABLE_SETTINGS = []
    for keys in GROUPS.values():
        CONFIGURABLE_SETTINGS.extend([k for k in keys if k is not None])
    
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
        
        # Show active task if something is running
        if stats.get('active_stage'):
            task = stats.get('active_task', 'Processing')
            progress = stats.get('progress', 0)
            status_msg += f"\n🚀 **Current Activity**: {stats['active_stage']}\n"
            status_msg += f"📝 **Task**: {task}\n"
            if progress > 0:
                # Simple progress bar
                bars = progress // 10
                progress_bar = "▓" * bars + "░" * (10 - bars)
                status_msg += f"📊 **Progress**: [{progress_bar}] {progress}%\n"
        
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
        # Show all configurable settings grouped by category
        config = Config()
        settings = get_settings_manager()
        overrides = settings.list_all()
        
        lines = ["📋 **Full Configuration Status**\n"]
        html_lines = ["<h3>📋 Full Configuration Status</h3>"]
        
        for category, keys in GROUPS.items():
            lines.append(f"\n{category}")
            cat_name = category.replace("**", "")
            html_lines.append(f"<h4>{cat_name}</h4>")
            
            for key in keys:
                if key is None:
                    lines.append("")
                    html_lines.append("<br/>")
                    continue
                    
                value = getattr(config, key.lower(), "Not set")
                is_override = key in overrides
                marker = "🔹" if is_override else "▫️"
                status = "(Override)" if is_override else "(Default)"
                
                # Plain text version
                lines.append(f"{marker} {key}: {value} {status}")
                
                # HTML version
                color = "blue" if is_override else "green"
                html_lines.append(
                    f"{marker} <font color='{color}'><b>{key}</b></font>: {value} <i>{status}</i><br/>"
                )
        
        lines.append("\n\n🔹 = Runtime Override active")
        lines.append("▫️ = Using .env/calculated default")
        
        html_lines.append("<p><br/>🔹 = <font color='blue'>Runtime Override active</font><br/>")
        html_lines.append("▫️ = <font color='green'>Using .env/calculated default</font></p>")
        
        await matrix.send_message("\n".join(lines), html_message="".join(html_lines))

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
        # Build Plain Text Help
        help_text = (
            "🤖 **Slideshow Bot Help**\n\n"
            "**🚀 Automation:**\n"
            "• `!rebuild` - Trigger a manual video generation\n"
            "• `!status` - Check the bot's health and uptime\n\n"
            "**⚙️ Configuration:**\n"
            "• `!set KEY VALUE` - Override a setting\n"
            "• `!get KEY` - View current value of a setting\n"
            "• `!get all` - View all settings and status\n"
            "• `!config` - List active overrides\n"
            "• `!defaults` - Reset all to .env defaults\n\n"
            "**❓ General:**\n"
            "• `!help` - Show this message\n\n"
            "**📝 Configurable Settings:**\n"
        )
        
        for category, keys in GROUPS.items():
            valid_keys = [k for k in keys if k is not None]
            help_text += f"\n{category}\n"
            # Plain text settings list (comma separated for help)
            help_text += ", ".join([f"`{k}`" for k in valid_keys]) + "\n"

        # Build HTML Help
        settings_html = ""
        for category, keys in GROUPS.items():
            valid_keys = [k for k in keys if k is not None]
            cat_name = category.replace("**", "")
            settings_html += f"<h4>{cat_name}</h4>"
            settings_html += "<table style='width:100%'>"
            for i in range(0, len(valid_keys), 2):
                col1 = valid_keys[i]
                col2 = valid_keys[i+1] if i+1 < len(valid_keys) else ""
                settings_html += f"<tr><td><code>{col1}</code></td><td>{f'<code>{col2}</code>' if col2 else ''}</td></tr>"
            settings_html += "</table>"

        html_help = (
            "<h3>🤖 Slideshow Bot Help</h3>"
            "<h4>🚀 Automation</h4>"
            "<ul>"
            "<li><code>!rebuild</code> - Trigger a manual video generation</li>"
            "<li><code>!status</code> - Check the bot's health and uptime</li>"
            "</ul>"
            "<h4>⚙️ Configuration</h4>"
            "<ul>"
            "<li><code>!set KEY VALUE</code> - Override a configuration setting</li>"
            "<li><code>!get KEY</code> - View current value of a setting</li>"
            "<li><code>!get all</code> - View all settings and their status</li>"
            "<li><code>!config</code> - List only active configuration overrides</li>"
            "<li><code>!defaults</code> - Reset all settings to .env defaults</li>"
            "</ul>"
            "<h4>❓ General</h4>"
            "<ul>"
            "<li><code>!help</code> - Show this message</li>"
            "</ul>"
            "<h4>📝 Configurable Settings</h4>"
            f"{settings_html}"
        )
        
        await matrix.send_message(help_text, html_message=html_help)


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
