import argparse
import os
import glob
from moviepy.editor import ImageClip, concatenate_videoclips
from moviepy.video.io.ffmpeg_writer import FFMPEG_VideoWriter
from dotenv import load_dotenv

load_dotenv() # Load environment variables from .env file

import math
import requests
import xml.etree.ElementTree as ET
import tempfile
import shutil

FPS = 24 # Frames per second for the video

def get_env_var(name, default=None, required=False):
    value = os.getenv(name, default)
    if required and value is None:
        raise ValueError(f"Environment variable '{name}' is required but not set.")
    return value

def get_nextcloud_image_paths(base_url, username, password, remote_path, verify_ssl=True):
    # Construct the full WebDAV URL for PROPFIND
    # The base_url should be something like "https://cloud.mcfchurch.co.uk/"
    # The remote_path should be something like "Uploads/Notices Slides"
    
    # Ensure base_url ends with a slash
    if not base_url.endswith('/'):
        base_url += '/'

    # Construct the full PROPFIND URL
    # Nextcloud WebDAV URL structure: base_url/remote.php/dav/files/username/path/to/folder
    propfind_url = f"{base_url}remote.php/dav/files/{username}/{remote_path}"
    
    # Clean up remote_path for consistent URL construction
    remote_path = remote_path.strip('/')
    
    # Create a temporary directory to store downloaded images
    temp_dir = tempfile.mkdtemp()
    downloaded_image_paths = []

    try:
        # WebDAV PROPFIND request to list files
        headers = {'Depth': '1'}
        response = requests.request(
            'PROPFIND',
            propfind_url,
            auth=(username, password),
            headers=headers,
            verify=verify_ssl
        )
        response.raise_for_status() # Raise an exception for HTTP errors

        # Parse XML response
        root = ET.fromstring(response.content)
        
        # Namespace for WebDAV properties
        ns = {'d': 'DAV:'}

        for response_elem in root.findall('d:response', ns):
            href_elem = response_elem.find('d:href', ns)
            if href_elem is not None:
                file_href = href_elem.text
                # Skip the base directory itself and non-image files
                if file_href == remote_path or not (file_href.lower().endswith('.jpg') or file_href.lower().endswith('.jpeg')):
                    continue
                
                # file_href from PROPFIND is usually the full path from WebDAV root, e.g., /remote.php/dav/files/username/path/to/file.jpg
                # Construct the full download URL using the base_url
                download_url = f"{base_url}{file_href.lstrip('/')}"
                local_filename = os.path.join(temp_dir, os.path.basename(file_href))

                print(f"Downloading {file_href} to {local_filename}...")
                download_response = requests.get(
                    download_url,
                    auth=(username, password),
                    verify=verify_ssl,
                    stream=True
                )
                download_response.raise_for_status()

                with open(local_filename, 'wb') as f:
                    for chunk in download_response.iter_content(chunk_size=8192):
                        f.write(chunk)
                downloaded_image_paths.append(local_filename)
                
    except requests.exceptions.RequestException as e:
        print(f"Error connecting to Nextcloud or during file operation: {e}")
        shutil.rmtree(temp_dir) # Clean up temp dir on error
        return None, None
    except ET.ParseError as e:
        print(f"Error parsing Nextcloud response: {e}")
        shutil.rmtree(temp_dir)
        return None, None
    
    return sorted(downloaded_image_paths), temp_dir


def create_slideshow(image_folder, output_filepath, image_duration=10, target_video_duration=600,
                     nextcloud_url=None, nextcloud_username=None, nextcloud_password=None, nextcloud_path=None,
                     verify_ssl=True,
                     upload_nextcloud_url=None, upload_nextcloud_username=None, upload_nextcloud_password=None,
                     upload_nextcloud_path=None):
    image_paths = []
    temp_nextcloud_dir = None

    if nextcloud_url and nextcloud_username and nextcloud_password and nextcloud_path:
        print("Retrieving images from Nextcloud...")
        image_paths, temp_nextcloud_dir = get_nextcloud_image_paths(
            nextcloud_url, nextcloud_username, nextcloud_password, nextcloud_path, verify_ssl
        )
        if not image_paths:
            print("No images found in Nextcloud or an error occurred. Exiting.")
            return
    elif image_folder: # Use local image folder if Nextcloud not specified
        # Ensure the image folder exists
        if not os.path.isdir(image_folder):
            print(f"Error: Image folder '{image_folder}' not found.")
            return

        # Find all JPEG images in the specified folder
        # Sort them to ensure a consistent order
        image_paths = sorted(glob.glob(os.path.join(image_folder, "*.jpg")))
        image_paths.extend(sorted(glob.glob(os.path.join(image_folder, "*.jpeg"))))

        if not image_paths:
            print(f"No JPEG images found in '{image_folder}'.")
            return
    else:
        print("Error: No image source (local folder or Nextcloud) specified. Exiting.")
        return

    print(f"Found {len(image_paths)} images. Creating slideshow...")

    # Create ImageClips for each image
    clips = []
    for image_path in image_paths:
        try:
            # Create a clip and set the duration
            clip = ImageClip(image_path).set_duration(image_duration)
            clips.append(clip)
            print(f"Added {os.path.basename(image_path)} to slideshow.")
        except Exception as e:
            print(f"Warning: Could not process image {image_path}. Error: {e}")

    if not clips:
        print("No valid image clips could be created. Exiting.")
        return

    # Concatenate all image clips.
    # Calculate the total duration of one sequence of images
    sequence_duration = len(clips) * image_duration

    # Calculate how many times to repeat the sequence to reach target_video_duration
    # We use math.ceil to ensure we have enough repetitions
    num_repeats = math.ceil(target_video_duration / sequence_duration) if sequence_duration > 0 else 1

    # Repeat the sequence of clips
    repeated_clips = []
    for _ in range(int(num_repeats)):
        repeated_clips.extend(clips)

    final_clip = concatenate_videoclips(repeated_clips)
    final_clip.fps = FPS # Set fps for the final clip

    # Trim the final clip to the exact target_video_duration
    final_clip = final_clip.subclip(0, target_video_duration)
    final_clip.duration = target_video_duration # Explicitly set duration after subclip

    # Write the result to a file
    print(f"Writing video to {output_filepath}...")
    
    # Ensure the output directory exists
    output_dir = os.path.dirname(output_filepath)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir)

    with FFMPEG_VideoWriter(output_filepath, final_clip.size, FPS, codec="libx264") as writer:
        for frame in final_clip.iter_frames():
            writer.write_frame(frame)

    print(f"Slideshow video created successfully at {output_filepath}")

    # Clean up temporary Nextcloud directory if it was created
    if temp_nextcloud_dir:
        print(f"Cleaning up temporary Nextcloud directory: {temp_nextcloud_dir}")
        shutil.rmtree(temp_nextcloud_dir)

    # Upload video to Nextcloud if configured
    if upload_nextcloud_url and upload_nextcloud_username and upload_nextcloud_password and upload_nextcloud_path:
        print(f"Uploading video to Nextcloud: {upload_nextcloud_path}...")
        try:
            # Ensure base_url ends with a slash
            if not upload_nextcloud_url.endswith('/'):
                upload_nextcloud_url += '/'
            
            # Construct the full upload URL
            # Nextcloud WebDAV URL structure: base_url/remote.php/dav/files/username/path/to/file.mp4
            full_upload_url = f"{upload_nextcloud_url}remote.php/dav/files/{upload_nextcloud_username}/{upload_nextcloud_path}"
            
            with open(output_filepath, 'rb') as video_file:
                response = requests.put(
                    full_upload_url,
                    data=video_file,
                    auth=(upload_nextcloud_username, upload_nextcloud_password),
                    verify=verify_ssl
                )
                response.raise_for_status()
            print(f"Video uploaded successfully to Nextcloud: {full_upload_url}")
        except requests.exceptions.RequestException as e:
            print(f"Error uploading video to Nextcloud: {e}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Create a slideshow video from a folder of JPEG images.")
    parser.add_argument("--image_folder", default="images/", help="Path to the folder containing JPEG images (default: images/).")
    parser.add_argument("output_filepath", help="Path and filename for the output video (e.g., output.mp4).")
    parser.add_argument("--duration", type=int, default=10,
                        help="Duration each image is displayed in seconds (default: 10).")
    parser.add_argument("--target_video_duration", type=int, default=600,
                        help="Target duration of the final video in seconds (default: 600 for 10 minutes).")

    args = parser.parse_args()

    # Retrieve Nextcloud configuration from environment variables
    nextcloud_url = get_env_var("NEXTCLOUD_URL")
    nextcloud_username = get_env_var("NEXTCLOUD_USERNAME")
    nextcloud_password = get_env_var("NEXTCLOUD_PASSWORD")
    nextcloud_path = get_env_var("NEXTCLOUD_PATH", default="")
    nextcloud_insecure_ssl = get_env_var("NEXTCLOUD_INSECURE_SSL", default="False").lower() == "true"

    # Retrieve Nextcloud upload configuration from environment variables
    upload_nextcloud_url = get_env_var("UPLOAD_NEXTCLOUD_URL")
    upload_nextcloud_username = get_env_var("UPLOAD_NEXTCLOUD_USERNAME")
    upload_nextcloud_password = get_env_var("UPLOAD_NEXTCLOUD_PASSWORD")
    upload_nextcloud_path = get_env_var("UPLOAD_NEXTCLOUD_PATH")

    # Determine image source
    if nextcloud_url and nextcloud_username and nextcloud_password:
        create_slideshow(
            image_folder=None, # Not used when Nextcloud is active
            output_filepath=args.output_filepath,
            image_duration=args.duration,
            target_video_duration=args.target_video_duration,
            nextcloud_url=nextcloud_url,
            nextcloud_username=nextcloud_username,
            nextcloud_password=nextcloud_password,
            nextcloud_path=nextcloud_path,
            verify_ssl=not nextcloud_insecure_ssl,
            upload_nextcloud_url=upload_nextcloud_url,
            upload_nextcloud_username=upload_nextcloud_username,
            upload_nextcloud_password=upload_nextcloud_password,
            upload_nextcloud_path=upload_nextcloud_path
        )
    else:
        create_slideshow(
            image_folder=args.image_folder,
            output_filepath=args.output_filepath,
            image_duration=args.duration,
            target_video_duration=args.target_video_duration,
            upload_nextcloud_url=upload_nextcloud_url,
            upload_nextcloud_username=upload_nextcloud_username,
            upload_nextcloud_password=upload_nextcloud_password,
            upload_nextcloud_path=upload_nextcloud_path
        )
