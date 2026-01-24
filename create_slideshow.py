import argparse
import os
import glob
import re
from moviepy.editor import ImageClip, concatenate_videoclips
from moviepy.video.io.ffmpeg_writer import FFMPEG_VideoWriter
from dotenv import load_dotenv
import math
import requests
import xml.etree.ElementTree as ET
import tempfile
import shutil

load_dotenv()  # Load environment variables from .env file

FPS = 24  # Frames per second for the video


def sort_key(filepath):
    filename = os.path.basename(filepath)
    match = re.match(r'(\d+)', filename)
    if match:
        return (0, int(match.group(1)), filename)
    else:
        return (1, filename, filename)


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


class NextcloudClient:
    def __init__(self, base_url, username, password, verify_ssl=True):
        if not base_url.endswith('/'):
            base_url += '/'
        self.base_url = base_url
        self.auth = (username, password)
        self.verify_ssl = verify_ssl

    def _get_webdav_url(self, path):
        return f"{self.base_url}remote.php/dav/files/{self.auth[0]}/{path.strip('/')}"

    def list_and_download_images(self, remote_path):
        propfind_url = self._get_webdav_url(remote_path)
        temp_dir = tempfile.mkdtemp()
        downloaded_image_paths = []

        try:
            headers = {'Depth': '1'}
            response = requests.request('PROPFIND', propfind_url, auth=self.auth, headers=headers, verify=self.verify_ssl)
            response.raise_for_status()

            root = ET.fromstring(response.content)
            ns = {'d': 'DAV:'}

            for response_elem in root.findall('d:response', ns):
                href_elem = response_elem.find('d:href', ns)
                if href_elem is None:
                    continue

                file_href = href_elem.text
                if file_href == remote_path or not (file_href.lower().endswith(('.jpg', '.jpeg'))):
                    continue

                download_url = f"{self.base_url}{file_href.lstrip('/')}"
                local_filename = os.path.join(temp_dir, os.path.basename(file_href))

                print(f"Downloading {file_href} to {local_filename}...")
                download_response = requests.get(download_url, auth=self.auth, verify=self.verify_ssl, stream=True)
                download_response.raise_for_status()

                with open(local_filename, 'wb') as f:
                    for chunk in download_response.iter_content(chunk_size=8192):
                        f.write(chunk)
                downloaded_image_paths.append(local_filename)

        except requests.exceptions.RequestException as e:
            print(f"Error connecting to Nextcloud or during file operation: {e}")
            shutil.rmtree(temp_dir)
            return None, None
        except ET.ParseError as e:
            print(f"Error parsing Nextcloud response: {e}")
            shutil.rmtree(temp_dir)
            return None, None

        downloaded_image_paths.sort(key=sort_key)
        return downloaded_image_paths, temp_dir

    def upload_file(self, local_filepath, remote_path):
        upload_url = self._get_webdav_url(remote_path)
        print(f"Uploading video to Nextcloud: {remote_path}...")
        try:
            with open(local_filepath, 'rb') as video_file:
                response = requests.put(upload_url, data=video_file, auth=self.auth, verify=self.verify_ssl)
                response.raise_for_status()
            print(f"Video uploaded successfully to Nextcloud: {upload_url}")
        except requests.exceptions.RequestException as e:
            print(f"Error uploading video to Nextcloud: {e}")


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

    clips = [ImageClip(p).set_duration(image_duration) for p in image_paths]
    if not clips:
        print("No valid image clips could be created. Exiting.")
        return

    sequence_duration = len(clips) * image_duration
    num_repeats = math.ceil(target_video_duration / sequence_duration) if sequence_duration > 0 else 1
    repeated_clips = clips * int(num_repeats)

    # Create the final video by concatenating, setting FPS, and then trimming.
    video = concatenate_videoclips(repeated_clips)
    video.fps = FPS
    final_clip = video.subclip(0, target_video_duration)

    print(f"Writing video to {output_filepath}...")
    output_dir = os.path.dirname(output_filepath)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir)

    # Use the manual FFMPEG_VideoWriter to prevent persistent NoneType errors
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


if __name__ == "__main__":
    env_image_duration = get_env_int("IMAGE_DURATION", 10)
    env_target_video_duration = get_env_int("TARGET_VIDEO_DURATION", 600)

    parser = argparse.ArgumentParser(description="Create a slideshow video from a folder of JPEG images.")
    parser.add_argument("--image_folder", default="images/", help="Path to the folder containing JPEG images.")
    parser.add_argument("output_filepath", help="Path and filename for the output video.")
    parser.add_argument("--duration", type=int, default=env_image_duration, help=f"Duration each image is displayed in seconds (default: {env_image_duration}).")
    parser.add_argument("--target_video_duration", type=int, default=env_target_video_duration, help=f"Target duration of the final video in seconds (default: {env_target_video_duration}).")

    args = parser.parse_args()

    nc_url = get_env_var("NEXTCLOUD_URL")
    nc_user = get_env_var("NEXTCLOUD_USERNAME")
    nc_pass = get_env_var("NEXTCLOUD_PASSWORD")
    nc_image_path = get_env_var("NEXTCLOUD_PATH")
    nc_upload_path = get_env_var("UPLOAD_NEXTCLOUD_PATH")
    nc_insecure = get_env_var("NEXTCLOUD_INSECURE_SSL", "False").lower() == "true"

    client = None
    image_source_folder = args.image_folder
    if nc_url and nc_user and nc_pass and nc_image_path:
        client = NextcloudClient(nc_url, nc_user, nc_pass, verify_ssl=not nc_insecure)
        image_source_folder = None  # Disable local folder when using Nextcloud

    create_slideshow(
        output_filepath=args.output_filepath,
        image_duration=args.duration,
        target_video_duration=args.target_video_duration,
        image_folder=image_source_folder,
        nextcloud_client=client,
        nextcloud_image_path=nc_image_path,
        nextcloud_upload_path=nc_upload_path
    )