import os
import sys

#print(f"DEBUG: Working directory: {os.getcwd()}")
#print(f"DEBUG: sys.path: {sys.path}")
import glob
import math
import shutil
import tempfile
import traceback
import random
from PIL import Image

from video_utils import make_silent_audio, patch_moviepy
patch_moviepy()

from moviepy.editor import concatenate_videoclips
from moviepy.video.io.ffmpeg_writer import ffmpeg_write_video
from dotenv import load_dotenv
import numpy as np
import proglog

# Global silence for MoviePy progress bars
class NullLogger(proglog.ProgressBarLogger):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
    def callback(self, *args, **kwargs): pass
    def update(self, *args, **kwargs): pass
    def message(self, *args, **kwargs): pass

proglog.default_bar_logger = lambda *args, **kwargs: NullLogger()

from nextcloud_client import NextcloudClient, sort_key
from matrix_client import MatrixClient
from audio_manager import AudioManager
from slideshow_generator import SlideshowGenerator

load_dotenv()

FPS = 5
TARGET_SIZE = (1920, 1080)

# --- Background Music Configuration ---
MUSIC_FOLDER = os.getenv("MUSIC_FOLDER", "images/")
MUSIC_SOURCE = os.getenv("MUSIC_SOURCE", "local")


def get_env_var(name, default=None, required=False):
    value = os.getenv(name, default)
    if value is not None:
        print(f"DEBUG: Internal variable '{name}' raw value: '{value}'")
        value = value.strip('"').strip("'")
    if required and value is None:
        raise ValueError(f"Environment variable '{name}' is required but not set.")
    return value


def get_env_int(name, default):
    try:
        return int(get_env_var(name, default=str(default)))
    except (ValueError, TypeError):
        return default


def get_env_bool(name, default=False):
    return get_env_var(name, str(default)).lower() == "true"


def create_slideshow(output_filepath, config, nextcloud_client=None):
    temp_dirs = []
    append_video_clip = None
    fps = FPS
    
    generator = SlideshowGenerator(TARGET_SIZE)
    audio_mgr = AudioManager(nextcloud_client)

    try:
        # 1. Source Images
        if nextcloud_client and config.nc_image_path:
            print("Retrieving images from Nextcloud...")
            image_paths, temp_img_dir = nextcloud_client.list_and_download_files(config.nc_image_path, allowed_extensions=('.jpg', '.jpeg'))
            if temp_img_dir: temp_dirs.append(temp_img_dir)
        else:
            image_paths = glob.glob(os.path.join(config.image_folder, "*.jpg"))
            image_paths.extend(glob.glob(os.path.join(config.image_folder, "*.jpeg")))
            image_paths.sort(key=sort_key)

        if not image_paths:
            raise RuntimeError("No images found in the specified source.")

        included_slides = [os.path.basename(p) for p in image_paths]

        # 2. Append Video
        if config.append_video_path:
            local_video_path = config.append_video_path
            if config.append_video_source == "nextcloud" and nextcloud_client:
                local_video_path, temp_vid_dir = nextcloud_client.download_file(config.append_video_path)
                if temp_vid_dir: temp_dirs.append(temp_vid_dir)
            
            append_video_clip = generator.load_append_video(local_video_path, fps)
            if append_video_clip and append_video_clip.fps:
                fps = round(max(5, min(30, append_video_clip.fps)), 2)

        # 3. Calculate Durations
        slideshow_target_duration = config.target_video_duration
        if append_video_clip:
            slideshow_target_duration = max(0, config.target_video_duration - append_video_clip.duration)
            print(f"Adjusting slideshow duration to {slideshow_target_duration}s to accommodate appended video.")

        # 4. Create Slideshow Video
        slideshow_video = None
        if slideshow_target_duration > 0:
            slideshow_video = generator.create_video(image_paths, config.image_duration, slideshow_target_duration, fps)
            
            # 5. Background Audio
            slideshow_audio = audio_mgr.prepare_background_music(
                os.getenv("MUSIC_FOLDER", "images/"),
                os.getenv("MUSIC_SOURCE", "local"),
                slideshow_target_duration,
                temp_dirs
            )
            
            if not slideshow_audio:
                slideshow_audio = make_silent_audio(slideshow_target_duration)
            
            slideshow_video = slideshow_video.set_audio(slideshow_audio)

        # 6. Final Composition
        if append_video_clip:
            if slideshow_video:
                final_video = concatenate_videoclips([slideshow_video, append_video_clip], method="chain")
            else:
                final_video = append_video_clip
        else:
            final_video = slideshow_video

        if not final_video:
            raise RuntimeError("No video content created.")

        final_video.fps = fps

        # 7. Write Video
        write_video_manually(final_video, output_filepath, fps)

        # 8. Upload
        if nextcloud_client and config.nc_upload_path:
            nextcloud_client.upload_file(output_filepath, config.nc_upload_path)
            
        return included_slides

    finally:
        if append_video_clip: append_video_clip.close()
        for d in temp_dirs:
            if os.path.exists(d): shutil.rmtree(d)


def write_video_manually(final_video, output_filepath, fps):
    """
    Handles the manual ffmpeg writing process to bypass MoviePy decorator issues.
    """
    print(f"Writing video to {output_filepath} (Duration: {final_video.duration}s, FPS: {fps})...")
    output_dir = os.path.dirname(output_filepath)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir)

    audio_temp = None
    try:
        if final_video.audio:
            audio_temp = tempfile.NamedTemporaryFile(suffix=".m4a", delete=False).name
            final_video.audio.write_audiofile(audio_temp, fps=44100, codec="aac", logger=None, verbose=False)
        
        ffmpeg_write_video(final_video, output_filepath, fps, codec="libx264", audiofile=audio_temp, logger=None, verbose=False)
    finally:
        if audio_temp and os.path.exists(audio_temp):
            os.remove(audio_temp)


class Config:
    def __init__(self):
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


def main():
    """
    Main entry point for the slideshow automation.
    """
    config = Config()
    matrix = MatrixClient(config.matrix_homeserver, config.matrix_token, config.matrix_room)
    client = None
    temp_output_file = None

    try:
        if config.nc_url and config.nc_user:
            client = NextcloudClient(config.nc_url, config.nc_user, config.nc_pass, verify_ssl=not config.nc_insecure)

        output_path = config.output_filepath
        if not output_path and config.nc_upload_path:
            fd, output_path = tempfile.mkstemp(suffix=".mp4")
            os.close(fd)
            temp_output_file = output_path

        if not output_path:
            raise ValueError("No output path specified and no Nextcloud upload path configured.")

        included_slides = create_slideshow(output_path, config, client)
        
        if matrix.is_configured():
            video_name = config.nc_upload_path or os.path.basename(output_path)
            matrix.send_success(video_name, included_slides)

    except Exception as e:
        error_msg = str(e)
        trace_str = traceback.format_exc()
        print(f"FATAL ERROR: {error_msg}\n{trace_str}")
        if matrix.is_configured():
            matrix.send_failure(error_msg, trace_str)
        sys.exit(1)
    finally:
        if temp_output_file and os.path.exists(temp_output_file):
            os.remove(temp_output_file)


if __name__ == "__main__":
    main()
