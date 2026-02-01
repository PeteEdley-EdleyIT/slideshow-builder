import os
import glob
import math
import shutil
import tempfile
from PIL import Image

# Workaround for MoviePy + Pillow 10+ compatibility
# This MUST happen before moviepy imports to avoid AttributeError in some modules
if not hasattr(Image, 'ANTIALIAS'):
    # In Pillow 10+, ANTIALIAS was removed in favor of LANCZOS
    Image.ANTIALIAS = getattr(Image, 'LANCZOS', Image.BICUBIC)

from moviepy.editor import ImageClip, concatenate_videoclips, VideoFileClip, AudioClip
from dotenv import load_dotenv
import numpy as np

from nextcloud_client import NextcloudClient, sort_key

load_dotenv()  # Load environment variables from .env file

FPS = 5  # Frames per second for the video


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


def create_slideshow(output_filepath, image_duration, target_video_duration,
                     image_folder=None, nextcloud_client=None,
                     nextcloud_image_path=None, nextcloud_upload_path=None,
                     append_video_path=None, append_video_source="local"):
    image_paths = []
    temp_nextcloud_dir = None
    append_video_clip = None
    temp_video_dir = None
    fps = FPS

    if nextcloud_client and nextcloud_image_path:
        print("Retrieving images from Nextcloud...")
        image_paths, temp_nextcloud_dir = nextcloud_client.list_and_download_images(nextcloud_image_path)
        if not image_paths:
            print("No images found in Nextcloud or an error occurred. Exiting.")
            return
    elif image_folder:
        if not os.path.isdir(image_folder):
            print(f"Error: Image folder '{image_folder}' not found.")
            return
        image_paths = glob.glob(os.path.join(image_folder, "*.jpg"))
        image_paths.extend(glob.glob(os.path.join(image_folder, "*.jpeg")))
        image_paths.sort(key=sort_key)
        if not image_paths:
            print(f"No JPEG images found in '{image_folder}'.")
            return
    else:
        print("Error: No image source (local folder or Nextcloud) specified. Exiting.")
        return

    # Handle optional video append
    if append_video_path:
        local_video_path = append_video_path
        if append_video_source == "nextcloud":
            if nextcloud_client:
                local_video_path, temp_video_dir = nextcloud_client.download_file(append_video_path)
                if not local_video_path:
                    print(f"Failed to download video from Nextcloud: {append_video_path}")
            else:
                print("Nextcloud client not configured but nextcloud video source requested.")
                local_video_path = None

        if local_video_path and os.path.exists(local_video_path):
            try:
                append_video_clip = VideoFileClip(local_video_path)
                # Use video FPS if available, capped at 24-30 range or similar if needed
                # For now, let's just use the video's FPS to be safe.
                if append_video_clip.fps:
                    fps = round(max(5, min(30, append_video_clip.fps)), 2)
                print(f"Loaded append video: {local_video_path} (Duration: {append_video_clip.duration}s, FPS: {fps})")
            except Exception as e:
                print(f"Error loading append video '{local_video_path}': {e}")
                append_video_clip = None

    print(f"Found {len(image_paths)} images. Creating slideshow...")

    # Adjust target slideshow duration if video is appended
    slideshow_target_duration = target_video_duration
    if append_video_clip:
        slideshow_target_duration = max(0, target_video_duration - append_video_clip.duration)
        print(f"Adjusting slideshow duration to {slideshow_target_duration}s to accommodate appended video.")

    clips = [ImageClip(np.array(Image.open(p))).set_duration(image_duration) for p in image_paths]
    for clip in clips:
        clip.fps = fps
    
    if not clips:
        print("No valid image clips could be created. Exiting.")
        return

    sequence_duration = len(clips) * image_duration
    num_repeats = math.ceil(slideshow_target_duration / sequence_duration) if sequence_duration > 0 else 1
    repeated_clips = clips * int(num_repeats)

    slideshow_video = concatenate_videoclips(repeated_clips, method="compose")
    slideshow_video = slideshow_video.subclip(0, slideshow_target_duration).set_duration(slideshow_target_duration)
    
    # Add silent audio track to slideshow to match appended video
    # This avoids NoneType errors during concatenation of audio tracks
    silent_audio = AudioClip(lambda t: np.zeros((len(t) if hasattr(t, '__len__') else 1, 2)), duration=slideshow_target_duration, fps=44100)
    slideshow_video = slideshow_video.set_audio(silent_audio)
    slideshow_video.duration = slideshow_target_duration
    slideshow_video.fps = fps

    if append_video_clip:
        # Match dimensions if necessary (simple concatenation might require same size)
        if append_video_clip.size != slideshow_video.size:
            print(f"Resizing append video from {append_video_clip.size} to {slideshow_video.size}")
            append_video_clip = append_video_clip.resize(slideshow_video.size)
        
        # Ensure FPS match
        append_video_clip.fps = fps
        
        final_video = concatenate_videoclips([slideshow_video, append_video_clip], method="compose")
        final_video.duration = slideshow_video.duration + append_video_clip.duration
    else:
        final_video = slideshow_video

    final_video.fps = fps
    if final_video.audio:
        final_video.audio.duration = final_video.duration
        final_video.audio.fps = 44100

    print(f"Writing video to {output_filepath} (Duration: {final_video.duration}s, FPS: {final_video.fps})...")
    output_dir = os.path.dirname(output_filepath)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir)

    try:
        # Use write_videofile which handles audio and codecs correctly
        # preset='ultrafast' or 'medium' etc can be adjusted if needed
        final_video.write_videofile(
            output_filepath,
            fps=fps,
            codec="libx264",
            audio_codec="aac",
            audio_fps=44100,
            temp_audiofile="temp-audio.m4a",
            remove_temp=True,
            verbose=False,
            logger=None
        )
    except Exception as e:
        print(f"An error occurred during video writing: {e}")
        return
    finally:
        if append_video_clip:
            append_video_clip.close()

    print(f"Slideshow video created successfully at {output_filepath}")

    if temp_nextcloud_dir:
        print(f"Cleaning up temporary Nextcloud images directory: {temp_nextcloud_dir}")
        shutil.rmtree(temp_nextcloud_dir)
    
    if temp_video_dir:
        print(f"Cleaning up temporary Nextcloud video directory: {temp_video_dir}")
        shutil.rmtree(temp_video_dir)

    if nextcloud_client and nextcloud_upload_path:
        nextcloud_client.upload_file(output_filepath, nextcloud_upload_path)


def get_config():
    """
    Retrieves all configuration from environment variables.
    """
    config = {
        "image_duration": get_env_int("IMAGE_DURATION", 10),
        "target_video_duration": get_env_int("TARGET_VIDEO_DURATION", 600),
        "image_folder": get_env_var("IMAGE_FOLDER", "images/"),
        "output_filepath": get_env_var("OUTPUT_FILEPATH"),
        "nc_url": get_env_var("NEXTCLOUD_URL"),
        "nc_user": get_env_var("NEXTCLOUD_USERNAME"),
        "nc_pass": get_env_var("NEXTCLOUD_PASSWORD"),
        "nc_image_path": get_env_var("NEXTCLOUD_IMAGE_PATH"),
        "nc_upload_path": get_env_var("UPLOAD_NEXTCLOUD_PATH"),
        "nc_insecure": get_env_bool("NEXTCLOUD_INSECURE_SSL", False),
        "append_video_path": get_env_var("APPEND_VIDEO_PATH"),
        "append_video_source": get_env_var("APPEND_VIDEO_SOURCE", "local"),
    }
    return config


def main():
    """
    Main function to run the slideshow creation process.
    """
    config = get_config()

    client = None
    image_source_folder = config["image_folder"]
    if config["nc_url"] and config["nc_user"] and config["nc_pass"] and config["nc_image_path"]:
        client = NextcloudClient(config["nc_url"], config["nc_user"], config["nc_pass"], verify_ssl=not config["nc_insecure"])
        image_source_folder = None  # Disable local folder when using Nextcloud

    final_output_filepath = config["output_filepath"]
    temp_output_file_created = False

    if not final_output_filepath:
        if config["nc_upload_path"]:
            fd, path = tempfile.mkstemp(suffix=".mp4")
            os.close(fd)
            final_output_filepath = path
            temp_output_file_created = True
            print(f"No output filepath provided, creating temporary file: {final_output_filepath}")
        else:
            raise ValueError("OUTPUT_FILEPATH is required if UPLOAD_NEXTCLOUD_PATH is not set.")

    try:
        create_slideshow(
            output_filepath=final_output_filepath,
            image_duration=config["image_duration"],
            target_video_duration=config["target_video_duration"],
            image_folder=image_source_folder,
            nextcloud_client=client,
            nextcloud_image_path=config["nc_image_path"],
            nextcloud_upload_path=config["nc_upload_path"],
            append_video_path=config["append_video_path"],
            append_video_source=config["append_video_source"]
        )
    finally:
        if temp_output_file_created and os.path.exists(final_output_filepath):
            print(f"Cleaning up temporary output file: {final_output_filepath}")
            os.remove(final_output_filepath)


if __name__ == "__main__":
    main()
