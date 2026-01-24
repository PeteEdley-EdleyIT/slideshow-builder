import os
import glob
import math
import shutil
import tempfile
from moviepy.editor import ImageClip, concatenate_videoclips
from moviepy.video.io.ffmpeg_writer import FFMPEG_VideoWriter
from dotenv import load_dotenv
from PIL import Image
import numpy as np

from nextcloud_client import NextcloudClient, sort_key

load_dotenv()  # Load environment variables from .env file

FPS = 5  # Frames per second for the video


def get_env_var(name, default=None, required=False):
    value = os.getenv(name, default)
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
                     nextcloud_image_path=None, nextcloud_upload_path=None):
    image_paths = []
    temp_nextcloud_dir = None

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

    print(f"Found {len(image_paths)} images. Creating slideshow...")

    clips = [ImageClip(np.array(Image.open(p))).set_duration(image_duration) for p in image_paths]
    if not clips:
        print("No valid image clips could be created. Exiting.")
        return

    sequence_duration = len(clips) * image_duration
    num_repeats = math.ceil(target_video_duration / sequence_duration) if sequence_duration > 0 else 1
    repeated_clips = clips * int(num_repeats)

    video = concatenate_videoclips(repeated_clips)
    video.fps = FPS
    final_clip = video.subclip(0, target_video_duration).set_duration(target_video_duration)

    print(f"Writing video to {output_filepath}...")
    output_dir = os.path.dirname(output_filepath)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir)

    try:
        with FFMPEG_VideoWriter(output_filepath, final_clip.size, FPS, codec="libx264") as writer:
            for frame in final_clip.iter_frames(fps=FPS):
                writer.write_frame(frame)
    except Exception as e:
        print(f"An error occurred during video writing: {e}")
        return

    print(f"Slideshow video created successfully at {output_filepath}")

    if temp_nextcloud_dir:
        print(f"Cleaning up temporary Nextcloud directory: {temp_nextcloud_dir}")
        shutil.rmtree(temp_nextcloud_dir)

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
            nextcloud_upload_path=config["nc_upload_path"]
        )
    finally:
        if temp_output_file_created and os.path.exists(final_output_filepath):
            print(f"Cleaning up temporary output file: {final_output_filepath}")
            os.remove(final_output_filepath)


if __name__ == "__main__":
    main()
