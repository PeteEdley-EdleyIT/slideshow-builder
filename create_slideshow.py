import os
import glob
import math
import shutil
import tempfile
import traceback
import random
from PIL import Image

# Workaround for MoviePy + Pillow 10+ compatibility
# This MUST happen before moviepy imports to avoid AttributeError in some modules
if not hasattr(Image, 'ANTIALIAS'):
    # In Pillow 10+, ANTIALIAS was removed in favor of LANCZOS
    Image.ANTIALIAS = getattr(Image, 'LANCZOS', Image.BICUBIC)

from moviepy.editor import ImageClip, concatenate_videoclips, VideoFileClip, AudioClip, AudioFileClip, concatenate_audioclips, CompositeAudioClip
from moviepy.audio.fx.all import audio_fadeout
from moviepy.video.io.ffmpeg_writer import ffmpeg_write_video
from dotenv import load_dotenv
import numpy as np
import proglog

# Global silence for MoviePy progress bars
import proglog
class NullLogger(proglog.ProgressBarLogger):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
    def callback(self, *args, **kwargs): pass
    def update(self, *args, **kwargs): pass
    def message(self, *args, **kwargs): pass

proglog.default_bar_logger = lambda *args, **kwargs: NullLogger()

from nextcloud_client import NextcloudClient, sort_key

load_dotenv()  # Load environment variables from .env file

FPS = 5  # Frames per second for the video

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


def create_slideshow(output_filepath, image_duration, target_video_duration,
                     image_folder=None, nextcloud_client=None,
                     nextcloud_image_path=None, nextcloud_upload_path=None,
                     append_video_path=None, append_video_source="local"):
    image_paths = []
    temp_nextcloud_dir = None
    append_video_clip = None
    temp_video_dir = None
    temp_music_dir = None # Initialize temp_music_dir
    fps = FPS

    music_files = []

    if nextcloud_client and nextcloud_image_path:
        print("Retrieving images from Nextcloud...")
        image_paths, temp_nextcloud_dir = nextcloud_client.list_and_download_files(nextcloud_image_path, allowed_extensions=('.jpg', '.jpeg'))
        if not image_paths:
            print("No images found in Nextcloud or an error occurred. Exiting.")
            return
            
        if MUSIC_SOURCE == "nextcloud" and MUSIC_FOLDER:
            print("Retrieving background music from Nextcloud...")
            music_files, temp_music_dir = nextcloud_client.list_and_download_files(MUSIC_FOLDER, allowed_extensions=('.mp3',))
            if not music_files:
                print("No music files found in Nextcloud folder.")
                music_files = []
        elif MUSIC_SOURCE == "local" and MUSIC_FOLDER:
             music_files = sorted(glob.glob(os.path.join(MUSIC_FOLDER, "*.mp3")))

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
            
        if MUSIC_SOURCE == "local" and MUSIC_FOLDER:
             music_files = sorted(glob.glob(os.path.join(MUSIC_FOLDER, "*.mp3")))
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

    # Standardize image size to 1920x1080
    target_size = (1920, 1080)
    print(f"Standardizing {len(image_paths)} images to {target_size}...")
    
    if slideshow_target_duration > 0:
        clips = []
        for p in image_paths:
            try:
                img = Image.open(p).convert("RGB")
                if img.size != target_size:
                    img = img.resize(target_size, Image.ANTIALIAS)
                clip = ImageClip(np.array(img)).set_duration(image_duration)
                clip.fps = fps
                clips.append(clip)
            except Exception as e:
                print(f"Warning: Could not process image {p}: {e}")

        if not clips:
            print("No valid image clips could be created. Proceeding with append video only.")
            slideshow_video = None
        else:
            sequence_duration = len(clips) * image_duration
            num_repeats = math.ceil(slideshow_target_duration / sequence_duration) if sequence_duration > 0 else 1
            repeated_clips = clips * int(num_repeats)

            slideshow_video = concatenate_videoclips(repeated_clips, method="chain")
            slideshow_video = slideshow_video.subclip(0, slideshow_target_duration).set_duration(slideshow_target_duration)
            
            # Audio Handling
            slideshow_audio = None
            if music_files:
                print(f"Found {len(music_files)} music tracks. Creating background audio...")
                try:
                    # Select random tracks and concatenate
                    selected_music = []
                    current_music_duration = 0
                    
                    # Create a pool to pick from
                    music_pool = list(music_files)
                    random.shuffle(music_pool)
                    
                    # If we run out of unique tracks, verify if we loop or just reuse
                    # For now simpliest is to just cycle through the shuffled list
                    while current_music_duration < slideshow_target_duration + 30: # Buffer
                        if not music_pool:
                            music_pool = list(music_files)
                            random.shuffle(music_pool)
                        
                        track_path = music_pool.pop(0)
                        try:
                            track = AudioFileClip(track_path)
                            selected_music.append(track)
                            current_music_duration += track.duration
                        except Exception as e:
                            print(f"Error loading music track {track_path}: {e}")
                    
                    if selected_music:
                        full_music = concatenate_audioclips(selected_music)
                        
                        # Apply trimming and fading
                        # Fade out starts 15s from end, lasts 10s, leaving 5s silence
                        fade_start = max(0, slideshow_target_duration - 15)
                        fade_duration = 10
                        audio_end = max(0, slideshow_target_duration - 5)
                        
                        # Clip to the end of audio (leaving 5s silence)
                        print(f"DEBUG: Trimming music to {audio_end}s (Slideshow duration: {slideshow_target_duration}s)")
                        bg_music = full_music.subclip(0, audio_end)
                        
                        # Apply fadeout at the end of the clip
                        # Note: audio_fadeout applies to the end of the clip
                        # Using explicit function call to ensure it applies
                        print(f"DEBUG: Applying audio_fadeout({fade_duration}) to bg_music (duration: {bg_music.duration}s)")
                        try:
                            # Try method first, if it fails or doesn't work, we'll strive for functional approach which is often more robust in older mpy
                            # But since we imported it, we can use the function form:
                            bg_music = audio_fadeout(bg_music, fade_duration)
                            print("DEBUG: Fadeout applied successfully.")
                        except Exception as e:
                            print(f"WARNING: audio_fadeout failed: {e}")
                            
                        bg_music = bg_music.set_duration(audio_end)
                        bg_music = bg_music.set_duration(audio_end)
                        
                        # Create a silent audio track for the full slideshow duration
                        # This ensures the audio track matches the video duration exactly, preventing overlap issues
                        def make_silent_frame(t):
                            if np.ndim(t) > 0:
                                return np.zeros((len(t), 2))
                            else:
                                return np.zeros(2)
                        
                        full_silent_audio = AudioClip(make_silent_frame, duration=slideshow_target_duration, fps=44100)
                        
                        # Composite the music over the silent track
                        # bg_music is already trimmed to audio_end (duration-5s)
                        # We set the start of bg_music to 0 (default)
                        slideshow_audio = CompositeAudioClip([full_silent_audio, bg_music])
                        slideshow_audio.duration = slideshow_target_duration
                        slideshow_audio.fps = 44100
                        
                        print(f"Background music configured with fadeout. Duration: {slideshow_audio.duration}s")
                    else:
                        print("Failed to load any valid music tracks.")
                except Exception as e:
                    print(f"Error processing background music: {e}")
                    slideshow_audio = None

            if slideshow_audio:
                # Explicitly set the audio on the slideshow video
                slideshow_video = slideshow_video.set_audio(slideshow_audio)
                print(f"DEBUG: Slideshow video audio set. Audio duration: {slideshow_video.audio.duration}s. Video duration: {slideshow_video.duration}s")
            else:
                # Fallback to silent audio to keep manual writer happy
                def make_silent_frame(t):
                    if np.ndim(t) > 0:
                        return np.zeros((len(t), 2))
                    else:
                        return np.zeros(2)
                
                silent_audio = AudioClip(make_silent_frame, duration=slideshow_target_duration, fps=44100)
                slideshow_video = slideshow_video.set_audio(silent_audio)

            slideshow_video.duration = slideshow_target_duration
            slideshow_video.fps = fps
    else:
        print("Slideshow target duration is 0 or less. Skipping slideshow.")
        slideshow_video = None

    if append_video_clip:
        # Match dimensions if necessary (simple concatenation might require same size)
        if slideshow_video and append_video_clip.size != slideshow_video.size:
            print(f"Resizing append video from {append_video_clip.size} to {slideshow_video.size}")
            append_video_clip = append_video_clip.resize(slideshow_video.size)
        elif not slideshow_video and append_video_clip.size != target_size:
            print(f"Resizing append video from {append_video_clip.size} to {target_size}")
            append_video_clip = append_video_clip.resize(target_size)
        
        # Ensure FPS match
        append_video_clip.fps = fps
        
        if slideshow_video:
            final_video = concatenate_videoclips([slideshow_video, append_video_clip], method="chain")
            final_video.duration = slideshow_video.duration + append_video_clip.duration
        else:
            final_video = append_video_clip
    elif slideshow_video:
        final_video = slideshow_video
    else:
        print("Error: No video content to write. Exiting.")
        return

    # Ensure fps is a float and not None
    if fps is None:
        fps = 29.97
    fps = float(fps)
    
    final_video.fps = fps
    if final_video.audio:
        final_video.audio.duration = final_video.duration
        final_video.audio.fps = 44100

    print(f"Final Video FPS attribute: {final_video.fps} (type: {type(final_video.fps)})")
    print(f"Writing video to {output_filepath} (Duration: {final_video.duration}s, FPS: {fps})...")
    output_dir = os.path.dirname(output_filepath)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir)

    print(f"Bypassing MoviePy decorators. Writing video manually...")
    audio_temp = None
    try:
        if final_video.audio:
            audio_temp = tempfile.NamedTemporaryFile(suffix=".m4a", delete=False).name
            print(f"Writing temporary audio to {audio_temp}...")
            final_video.audio.write_audiofile(
                audio_temp,
                fps=44100,
                codec="aac",
                logger=None,
                verbose=False
            )
        
        print(f"Writing final video to {output_filepath} using ffmpeg_write_video...")
        ffmpeg_write_video(
            final_video,
            output_filepath,
            fps,
            codec="libx264",
            audiofile=audio_temp,
            logger=None,
            verbose=False
        )
    except Exception as e:
        print(f"An error occurred during manual video writing: {e}")
        traceback.print_exc()
        return
    finally:
        if audio_temp and os.path.exists(audio_temp):
            try:
                os.remove(audio_temp)
            except:
                pass
        
        if append_video_clip:
            append_video_clip.close()
            
        if temp_music_dir and os.path.exists(temp_music_dir):
            try:
                shutil.rmtree(temp_music_dir)
            except:
                pass

        if temp_nextcloud_dir:
            print(f"Cleaning up temporary Nextcloud images directory: {temp_nextcloud_dir}")
            shutil.rmtree(temp_nextcloud_dir)
    
    if temp_video_dir:
        print(f"Cleaning up temporary Nextcloud video directory: {temp_video_dir}")
        shutil.rmtree(temp_video_dir)

    print(f"Slideshow video created successfully at {output_filepath}")


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
