"""
Main script for the Video Slideshow Automation.

This script orchestrates the entire process of generating video slideshows
from images, optionally appending a video, adding background music, and
uploading the final video to Nextcloud. It also integrates with a Matrix
bot for scheduled and on-demand video generation and notifications.

Configuration is primarily managed through environment variables.
"""

import os
import sys
import asyncio
import glob
import math
import shutil
import tempfile
import traceback
import random
import time
from datetime import datetime
import requests
from PIL import Image

from video_utils import make_silent_audio, patch_moviepy
# Apply MoviePy patch for Pillow compatibility as early as possible
patch_moviepy()

from moviepy.editor import concatenate_videoclips
from moviepy.video.io.ffmpeg_writer import ffmpeg_write_video
from dotenv import load_dotenv
import numpy as np
import proglog

# Global silence for MoviePy progress bars
# MoviePy uses proglog for progress bars, which can be noisy.
# This NullLogger class overrides proglog's default behavior to suppress output.
class NullLogger(proglog.ProgressBarLogger):
    """A logger that suppresses all output from proglog (used by MoviePy)."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
    def callback(self, *args, **kwargs): pass
    def update(self, *args, **kwargs): pass
    def message(self, *args, **kwargs): pass

# Set proglog's default logger to our NullLogger to silence MoviePy
proglog.default_bar_logger = lambda *args, **kwargs: NullLogger()

from nextcloud_client import NextcloudClient, sort_key
from matrix_client import MatrixClient
from audio_manager import AudioManager
from slideshow_generator import SlideshowGenerator
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

# Load environment variables from .env file
load_dotenv()

# --- Global Constants ---
FPS = 5  # Frames per second for the output video
TARGET_SIZE = (1920, 1080)  # Target resolution for all images and videos
HEARTBEAT_FILE = "/tmp/heartbeat"

# --- Global Health State ---
# These are used for the Matrix !status command
last_success_time = None
last_heartbeat_time = None
start_time = time.time()

# --- Background Music Configuration (Default values, overridden by .env) ---
MUSIC_FOLDER = os.getenv("MUSIC_FOLDER", "images/")
MUSIC_SOURCE = os.getenv("MUSIC_SOURCE", "local")


def get_env_var(name, default=None, required=False):
    """
    Retrieves an environment variable, strips quotes, and handles default values.

    Args:
        name (str): The name of the environment variable.
        default (str, optional): The default value if the variable is not set. Defaults to None.
        required (bool, optional): If True, raises a ValueError if the variable is not set
                                   and no default is provided. Defaults to False.

    Returns:
        str: The value of the environment variable, or the default value.

    Raises:
        ValueError: If `required` is True and the variable is not set.
    """
    value = os.getenv(name, default)
    if value is not None:
        # Strip potential quotes from environment variable values
        value = value.strip().strip('"').strip("'")
    if required and value is None:
        raise ValueError(f"Environment variable '{name}' is required but not set.")
    return value


def get_env_int(name, default):
    """
    Retrieves an environment variable as an integer, with a default fallback.

    Args:
        name (str): The name of the environment variable.
        default (int): The default integer value if the variable is not set or invalid.

    Returns:
        int: The integer value of the environment variable, or the default.
    """
    try:
        return int(get_env_var(name, default=str(default)))
    except (ValueError, TypeError):
        return default


def get_env_bool(name, default=False):
    """
    Retrieves an environment variable as a boolean, with a default fallback.

    Recognizes "true" (case-insensitive) as True, anything else as False.

    Args:
        name (str): The name of the environment variable.
        default (bool): The default boolean value if the variable is not set.

    Returns:
        bool: The boolean value of the environment variable, or the default.
    """
    return get_env_var(name, str(default)).lower() == "true"


async def write_heartbeat():
    """
    Updates the heartbeat file to indicate the process is alive.
    Only called if ENABLE_HEARTBEAT is set to true.
    """
    global last_heartbeat_time
    try:
        with open(HEARTBEAT_FILE, "w") as f:
            f.write(str(time.time()))
        last_heartbeat_time = time.time()
    except Exception as e:
        print(f"ERROR: Failed to write heartbeat: {e}")


def send_ntfy(message, title=None, priority="default", tags=None):
    """
    Sends a notification to an ntfy.sh topic.
    Only triggered if NTFY_URL and NTFY_TOPIC are configured.

    Args:
        message (str): The notification message.
        title (str, optional): The title of the notification.
        priority (str, optional): Priority level (min, low, default, high, urgent).
        tags (list, optional): List of emojis or tags.
    """
    ntfy_url = get_env_var("NTFY_URL")
    ntfy_topic = get_env_var("NTFY_TOPIC")
    ntfy_token = get_env_var("NTFY_TOKEN")
    enable_ntfy = get_env_bool("ENABLE_NTFY", True)

    if not enable_ntfy:
        return

    if not ntfy_url or not ntfy_topic:
        return

    # Ensure URL ends with / and combine with topic
    base_url = ntfy_url.rstrip("/")
    if ntfy_topic.startswith("/"):
        ntfy_topic = ntfy_topic[1:]
    target_url = f"{base_url}/{ntfy_topic}"

    headers = {}
    if ntfy_token:
        headers["Authorization"] = f"Bearer {ntfy_token}"
    if title:
        # HTTP headers must be ISO-8859-1. We encode to UTF-8 then decode to latin-1 
        # to ensure the bytes are passed through, though some clients might not 
        # decode this correctly. ntfy handles this if you use the X-Title header 
        # but for simplicity we'll just ensure it's a valid string.
        try:
            headers["Title"] = title.encode('utf-8').decode('iso-8859-1')
        except UnicodeError:
            headers["Title"] = title.encode('ascii', 'replace').decode('ascii')
    if priority:
        headers["Priority"] = priority
    if tags:
        headers["Tags"] = ",".join(tags)

    try:
        # Use UTF-8 for the body, which is supported by ntfy
        response = requests.post(target_url, data=message.encode('utf-8'), headers=headers, timeout=10)
        response.raise_for_status()
    except Exception as e:
        print(f"ERROR: Failed to send ntfy notification to {target_url}: {e}")


def create_slideshow(output_filepath, config, nextcloud_client=None):
    """
    Orchestrates the creation of the video slideshow.

    This function handles sourcing images, optionally appending a video,
    adding background music, composing the final video, writing it to a file,
    and optionally uploading it to Nextcloud.

    Args:
        output_filepath (str): The local path where the final video will be saved.
        config (Config): An instance of the Config class containing all settings.
        nextcloud_client (NextcloudClient, optional): An initialized NextcloudClient
                                                      instance. Defaults to None.

    Returns:
        list: A list of basenames of the images included in the slideshow.
              Returns an empty list if no images are processed or an error occurs.

    Raises:
        RuntimeError: If no images are found in the specified source or no
                      video content can be created.
        ValueError: If no output path is specified and no Nextcloud upload path is configured.
    """
    temp_dirs = []  # List to keep track of temporary directories for cleanup
    append_video_clip = None
    fps = FPS  # Initialize FPS with global default

    # Initialize generator and audio manager
    generator = SlideshowGenerator(TARGET_SIZE)
    audio_mgr = AudioManager(nextcloud_client)

    try:
        # 1. Source Images
        image_paths = []
        if nextcloud_client and config.nc_image_path:
            print("Retrieving images from Nextcloud...")
            # Download images from Nextcloud
            image_paths, temp_img_dir = nextcloud_client.list_and_download_files(config.nc_image_path, allowed_extensions=('.jpg', '.jpeg'))
            if temp_img_dir:
                temp_dirs.append(temp_img_dir) # Add temp dir to cleanup list
        else:
            # Get local images
            image_paths = glob.glob(os.path.join(config.image_folder, "*.jpg"))
            image_paths.extend(glob.glob(os.path.join(config.image_folder, "*.jpeg")))
            image_paths.sort(key=sort_key) # Sort images numerically

        if not image_paths:
            raise RuntimeError("No images found in the specified source.")

        included_slides = [os.path.basename(p) for p in image_paths]

        # 2. Append Video
        if config.append_video_path:
            local_video_path = config.append_video_path
            if config.append_video_source == "nextcloud" and nextcloud_client:
                # Download append video from Nextcloud if source is Nextcloud
                local_video_path, temp_vid_dir = nextcloud_client.download_file(config.append_video_path)
                if temp_vid_dir:
                    temp_dirs.append(temp_vid_dir) # Add temp dir to cleanup list
            
            # Load and prepare the append video
            append_video_clip = generator.load_append_video(local_video_path, fps)
            if append_video_clip and append_video_clip.fps:
                # Adjust FPS based on appended video if it has a valid FPS
                fps = round(max(5, min(30, append_video_clip.fps)), 2)

        # 3. Calculate Durations
        slideshow_target_duration = config.target_video_duration
        if append_video_clip:
            # Adjust slideshow duration to accommodate the appended video
            slideshow_target_duration = max(0, config.target_video_duration - append_video_clip.duration)
            print(f"Adjusting slideshow duration to {slideshow_target_duration}s to accommodate appended video.")

        # 4. Create Slideshow Video
        slideshow_video = None
        if slideshow_target_duration > 0:
            slideshow_video = generator.create_video(image_paths, config.image_duration, slideshow_target_duration, fps)
            
            # 5. Background Audio
            slideshow_audio = audio_mgr.prepare_background_music(
                os.getenv("MUSIC_FOLDER", "images/"), # Use os.getenv directly for music config
                os.getenv("MUSIC_SOURCE", "local"),
                slideshow_target_duration,
                temp_dirs
            )
            
            if not slideshow_audio:
                # If no music, create silent audio to match slideshow duration
                slideshow_audio = make_silent_audio(slideshow_target_duration)
            
            # Set the audio for the slideshow video
            slideshow_video = slideshow_video.set_audio(slideshow_audio)

        # 6. Final Composition
        final_video = None
        if append_video_clip:
            if slideshow_video:
                # Concatenate slideshow and appended video
                final_video = concatenate_videoclips([slideshow_video, append_video_clip], method="chain")
            else:
                # If only append video exists
                final_video = append_video_clip
        else:
            # If only slideshow exists
            final_video = slideshow_video

        if not final_video:
            raise RuntimeError("No video content created.")

        final_video.fps = fps # Ensure final video has consistent FPS

        # 7. Write Video
        write_video_manually(final_video, output_filepath, fps)

        # 8. Upload
        if nextcloud_client and config.nc_upload_path:
            nextcloud_client.upload_file(output_filepath, config.nc_upload_path)
            
        return included_slides

    finally:
        # Clean up temporary files and directories
        if append_video_clip:
            append_video_clip.close() # Release resources for appended video
        for d in temp_dirs:
            if os.path.exists(d):
                shutil.rmtree(d) # Remove temporary directories


def write_video_manually(final_video, output_filepath, fps):
    """
    Handles the manual ffmpeg writing process to bypass MoviePy decorator issues.

    This function provides a more robust way to write the final video by
    explicitly handling audio extraction and then using `ffmpeg_write_video`.
    This helps avoid certain MoviePy internal issues, especially with audio.

    Args:
        final_video (VideoClip): The MoviePy VideoClip object to write.
        output_filepath (str): The local path where the video will be saved.
        fps (int): The frames per second for the output video.
    """
    print(f"Writing video to {output_filepath} (Duration: {final_video.duration}s, FPS: {fps})...")
    output_dir = os.path.dirname(output_filepath)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir) # Create output directory if it doesn't exist

    audio_temp = None
    try:
        if final_video.audio:
            # Write audio to a temporary file first
            audio_temp = tempfile.NamedTemporaryFile(suffix=".m4a", delete=False).name
            final_video.audio.write_audiofile(audio_temp, fps=44100, codec="aac", logger=None, verbose=False)
        
        # Write video using ffmpeg_write_video, linking the temporary audio file
        ffmpeg_write_video(final_video, output_filepath, fps, codec="libx264", audiofile=audio_temp, logger=None, verbose=False)
    finally:
        # Clean up temporary audio file
        if audio_temp and os.path.exists(audio_temp):
            os.remove(audio_temp)


class Config:
    """
    Loads and manages application configuration from environment variables.

    This class centralizes access to all configurable parameters, providing
    default values where necessary and type conversion (e.g., to int or bool).
    """
    def __init__(self):
        """
        Initializes the Config object by loading all relevant environment variables.
        """
        self.image_duration = get_env_int("IMAGE_DURATION", 10)
        self.target_video_duration = get_env_int("TARGET_VIDEO_DURATION", 600)
        self.image_folder = get_env_var("IMAGE_FOLDER", "images/")
        self.output_filepath = get_env_var("OUTPUT_FILEPATH")
        self.nc_url = get_env_var("NEXTCLOUD_URL")
        self.nc_user = get_env_var("NEXTCLOUD_USERNAME")
        self.nc_pass = get_env_var("NEXTCLOUD_PASSWORD")
        self.nc_image_path = get_env_var("NEXTCLOUD_IMAGE_PATH")
        self.nc_upload_path = get_env_var("UPLOAD_NEXTCLOUD_PATH")
        self.nc_insecure = get_env_bool("NEXTCLOUD_INSECURE_SSL", False)
        self.append_video_path = get_env_var("APPEND_VIDEO_PATH")
        self.append_video_source = get_env_var("APPEND_VIDEO_SOURCE", "local")
        self.matrix_homeserver = get_env_var("MATRIX_HOMESERVER")
        self.matrix_token = get_env_var("MATRIX_ACCESS_TOKEN")
        self.matrix_room = get_env_var("MATRIX_ROOM_ID")
        self.matrix_user_id = get_env_var("MATRIX_USER_ID")
        self.ntfy_url = get_env_var("NTFY_URL")
        self.ntfy_topic = get_env_var("NTFY_TOPIC")
        self.ntfy_token = get_env_var("NTFY_TOKEN")
        self.enable_ntfy = get_env_bool("ENABLE_NTFY", True)


async def run_automation(matrix=None):
    """
    The core logic for the slideshow automation, designed to be called by a
    scheduler or manual trigger.

    This asynchronous function encapsulates the entire video generation workflow,
    including Nextcloud interaction, video creation, and Matrix notifications.

    Args:
        matrix (MatrixClient, optional): An initialized MatrixClient instance.
                                        If None, a new one will be created based on config.
    """
    global last_success_time
    config = Config()
    created_matrix = False
    # If no MatrixClient is provided, create one based on configuration
    if not matrix:
        matrix = MatrixClient(config.matrix_homeserver, config.matrix_token, config.matrix_room, config.matrix_user_id)
        created_matrix = True # Flag to indicate if this function created the client

    client = None
    temp_output_file = None # To store path of temporary output file if created

    try:
        print("Starting scheduled slideshow automation...")
        
        # Send ntfy notification that we are starting (immediate feedback)
        send_ntfy(
            "Starting slideshow production...",
            title="Rebuild Started",
            priority="low",
            tags=["rocket", "running"]
        )

        # Initialize Nextcloud client if credentials are provided
        if config.nc_url and config.nc_user:
            client = NextcloudClient(config.nc_url, config.nc_user, config.nc_pass, verify_ssl=not config.nc_insecure)

        output_path = config.output_filepath
        # If no explicit output path is given but Nextcloud upload is configured,
        # create a temporary file for the video output.
        if not output_path and config.nc_upload_path:
            fd, output_path = tempfile.mkstemp(suffix=".mp4")
            os.close(fd) # Close the file descriptor immediately
            temp_output_file = output_path # Mark this file for later cleanup

        if not output_path:
            raise ValueError("No output path specified and no Nextcloud upload path configured.")

        # Create the slideshow video
        included_slides = create_slideshow(output_path, config, client)
        
        # Send success notification to Matrix if configured
        if matrix.is_configured():
            video_name = config.nc_upload_path or os.path.basename(output_path)
            await matrix.send_success(video_name, included_slides)
        
        last_success_time = time.time()
        print("Scheduled slideshow automation complete.")

        # Send ntfy notification
        video_name = config.nc_upload_path or os.path.basename(output_path)
        send_ntfy(
            f"Slideshow '{video_name}' produced successfully with {len(included_slides)} slides.",
            title="Slideshow Complete",
            priority="default",
            tags=["white_check_mark", "movie_camera"]
        )

    except Exception as e:
        error_msg = str(e)
        trace_str = traceback.format_exc()
        print(f"ERROR: {error_msg}\n{trace_str}")
        # Send failure notification to Matrix if configured
        if matrix.is_configured():
            await matrix.send_failure(error_msg, trace_str)
        
        # Send ntfy notification on failure
        send_ntfy(
            f"Slideshow production failed: {error_msg}",
            title="Slideshow Failed",
            priority="high",
            tags=["x", "boom"]
        )
    finally:
        # Clean up Matrix client if it was created by this function
        if created_matrix and matrix and matrix.is_configured():
            await matrix.close()
        # Remove temporary output file if it was created
        if temp_output_file and os.path.exists(temp_output_file):
            os.remove(temp_output_file)


async def handle_matrix_message(matrix, room, event):
    """
    Handles incoming Matrix messages, interpreting them as commands.

    This function is a callback for the Matrix client, processing commands
    like `!rebuild`, `!status`, and `!help`.

    Args:
        matrix (MatrixClient): The MatrixClient instance.
        room (nio.rooms.MatrixRoom): The Matrix room the event originated from.
        event (nio.events.room_events.RoomMessageText): The message event.
    """
    command = event.body.strip()
    print(f"Processing command: '{command}' from {event.sender}")
    
    # In a production scenario, you might want to add sender verification
    # (e.g., only allow specific user IDs to trigger commands)
    if command == "!rebuild":
        await matrix.send_message("🚀 Starting manual rebuild...")
        # Run the automation in a separate task to avoid blocking the Matrix listener
        asyncio.create_task(run_automation(matrix))
    elif command == "!status":
        uptime_seconds = int(time.time() - start_time)
        uptime_str = f"{uptime_seconds // 3600}h {(uptime_seconds % 3600) // 60}m {uptime_seconds % 60}s"
        
        last_success_str = datetime.fromtimestamp(last_success_time).strftime('%Y-%m-%d %H:%M:%S') if last_success_time else "Never"
        last_heartbeat_str = datetime.fromtimestamp(last_heartbeat_time).strftime('%Y-%m-%d %H:%M:%S') if last_heartbeat_time else "Disabled/Not yet run"
        
        status_msg = (
            "🤖 **Slideshow Bot Status**\n"
            f"⏱️ **Uptime**: {uptime_str}\n"
            f"✅ **Last Success**: {last_success_str}\n"
            f"💓 **Last Heartbeat**: {last_heartbeat_str}\n"
        )
        
        # Optional: check Nextcloud connectivity if configured
        config = Config()
        if config.nc_url and config.nc_user:
            try:
                from nextcloud_client import NextcloudClient
                # Just a quick check (not a full login if too heavy, but here we can afford it)
                nc = NextcloudClient(config.nc_url, config.nc_user, config.nc_pass, verify_ssl=not config.nc_insecure)
                status_msg += "☁️ **Nextcloud**: Connected\n"
            except Exception:
                status_msg += "☁️ **Nextcloud**: ❌ Connection Failed\n"
        
        await matrix.send_message(status_msg)
    elif command == "!help":
        help_text = (
            "Available commands:\n"
            "!rebuild - Trigger a manual video generation\n"
            "!status - Check if the bot is alive\n"
            "!help - Show this message"
        )
        await matrix.send_message(help_text)


async def main():
    """
    Main entry point for the long-running slideshow automation daemon.

    This function initializes the configuration, sets up the APScheduler
    for scheduled video generation, and starts the Matrix bot listener
    for interactive commands.
    """
    config = Config()
    cron_schedule = get_env_var("CRON_SCHEDULE", "0 1 * * 5") # Default to Friday 1:00 AM
    
    # Initialize Matrix client
    matrix = MatrixClient(config.matrix_homeserver, config.matrix_token, config.matrix_room, config.matrix_user_id)
    
    print(f"Starting Matrix bot daemon with cron schedule: {cron_schedule}")
    
    scheduler = AsyncIOScheduler()
    
    # Add the scheduled job for video generation
    try:
        trigger = CronTrigger.from_crontab(cron_schedule)
        scheduler.add_job(run_automation, trigger, args=[matrix], id="slideshow_job")
        print(f"Scheduled slideshow job with crontab: {cron_schedule}")
    except Exception as e:
        print(f"Failed to schedule job with cron '{cron_schedule}': {e}")
        print("Falling back to default Friday 1:00 AM schedule.")
        # Fallback to a default schedule if the configured one is invalid
        scheduler.add_job(run_automation, CronTrigger.from_crontab("0 1 * * 5"), args=[matrix], id="slideshow_job")

    # Optional Heartbeat Job
    if get_env_bool("ENABLE_HEARTBEAT", False):
        print("Enabling heartbeat mechanism...")
        scheduler.add_job(write_heartbeat, 'interval', minutes=1, id="heartbeat_job")
        # Run once immediately
        asyncio.create_task(write_heartbeat())

    scheduler.start() # Start the APScheduler

    # Matrix Listener
    if matrix.is_configured():
        # Register the message handler callback
        matrix.add_message_callback(lambda room, event: handle_matrix_message(matrix, room, event))
        # Run the Matrix listener in a background task to not block the main loop
        listener_task = asyncio.create_task(matrix.listen_forever())
        print("Matrix listener started.")
    else:
        print("Matrix not configured, running in scheduler-only mode.")
        listener_task = None

    # Keep the script running indefinitely
    try:
        while True:
            await asyncio.sleep(3600) # Sleep for an hour, or until interrupted
    except (KeyboardInterrupt, SystemExit):
        # Graceful shutdown on interruption
        scheduler.shutdown()
        if matrix:
            await matrix.close()
        if listener_task:
            listener_task.cancel()


if __name__ == "__main__":
    # Entry point for the script
    asyncio.run(main())
