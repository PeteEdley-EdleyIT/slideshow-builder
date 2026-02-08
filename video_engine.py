"""
Video Composition Engine for the Slideshow Automation.

This module orchestrates the creation of video slideshows by coordinating
Nextcloud assets, audio management, and video generation. It provides
the `VideoEngine` class to encapsulate the end-to-end production workflow.
"""

import os
import glob
import shutil
import tempfile
import math
from moviepy.editor import concatenate_videoclips
from moviepy.video.io.ffmpeg_writer import ffmpeg_write_video

from nextcloud_client import sort_key
from audio_manager import AudioManager
from slideshow_generator import SlideshowGenerator
from video_utils import make_silent_audio

class VideoEngine:
    """
    Orchestrates the creation, composition, and export of video slideshows.

    This engine handles the high-level workflow:
    1. Fetching images and videos from local or remote sources.
    2. Generating a repeating slideshow from images.
    3. Applying background music with fade-out.
    4. Composing the final video with optional appends.
    5. Writing the output and uploading to Nextcloud.
    """
    def __init__(self, config, nextcloud_client=None, target_size=(1920, 1080)):
        """
        Initializes the VideoEngine.

        Args:
            config (Config): An instance of the Config class containing settings.
            nextcloud_client (NextcloudClient, optional): Client for Nextcloud operations.
            target_size (tuple, optional): Target video resolution. Defaults to (1920, 1080).
        """
        self.config = config
        self.nc_client = nextcloud_client
        self.target_size = target_size
        self.generator = SlideshowGenerator(target_size)
        self.audio_mgr = AudioManager(nextcloud_client)

    def create_slideshow(self, output_filepath):
        """
        Executes the full slideshow generation workflow.

        Args:
            output_filepath (str): Local path where the final video file will be saved.

        Returns:
            list: A list of basenames of the images included in the slideshow.

        Raises:
            RuntimeError: If no images are found or video content cannot be created.
        """
        temp_dirs = []
        append_video_clip = None
        fps = 5 # Default starting FPS

        try:
            # 1. Source Images
            image_paths = self._source_images(temp_dirs)
            if not image_paths:
                raise RuntimeError("No images found in the specified source.")

            included_slides = [os.path.basename(p) for p in image_paths]

            # 2. Prepare Append Video
            if self.config.append_video_path:
                local_video_path, fps_from_clip = self._prepare_append_video(temp_dirs)
                append_video_clip = self.generator.load_append_video(local_video_path)
                
                if append_video_clip and append_video_clip.fps:
                    # Sync project FPS with the appended video
                    fps = round(max(5, min(30, append_video_clip.fps)), 2)
                    append_video_clip.fps = fps

            # 3. Calculate Durations
            slideshow_target_duration = self.config.target_video_duration
            if append_video_clip:
                slideshow_target_duration = max(0, self.config.target_video_duration - append_video_clip.duration)
                print(f"Adjusting slideshow duration to {slideshow_target_duration}s to accommodate appended video.")

            # 4. Generate Slideshow & Audio
            slideshow_video = None
            if slideshow_target_duration > 0:
                slideshow_video = self.generator.create_video(
                    image_paths, self.config.image_duration, slideshow_target_duration, fps
                )
                
                audio_folder = os.getenv("MUSIC_FOLDER", self.config.image_folder)
                audio_source = os.getenv("MUSIC_SOURCE", "local")
                
                slideshow_audio = self.audio_mgr.prepare_background_music(
                    audio_folder, audio_source, slideshow_target_duration, temp_dirs
                )
                
                if not slideshow_audio:
                    slideshow_audio = make_silent_audio(slideshow_target_duration)
                
                slideshow_video = slideshow_video.set_audio(slideshow_audio)

            # 5. Final Composition
            final_video = self._compose_final(slideshow_video, append_video_clip, fps)

            # 6. Export and Upload
            self.write_video_manually(final_video, output_filepath, fps)
            
            if self.nc_client and self.config.nc_upload_path:
                self.nc_client.upload_file(output_filepath, self.config.nc_upload_path)
                
            return included_slides

        finally:
            if append_video_clip:
                append_video_clip.close()
            for d in temp_dirs:
                if os.path.exists(d):
                    shutil.rmtree(d)

    def _source_images(self, temp_dirs):
        """Internal helper to retrieve image paths from local or Nextcloud."""
        if self.nc_client and self.config.nc_image_path:
            print("Retrieving images from Nextcloud...")
            image_paths, temp_img_dir = self.nc_client.list_and_download_files(
                self.config.nc_image_path, allowed_extensions=('.jpg', '.jpeg')
            )
            if temp_img_dir:
                temp_dirs.append(temp_img_dir)
            return image_paths
        else:
            image_paths = glob.glob(os.path.join(self.config.image_folder, "*.jpg"))
            image_paths.extend(glob.glob(os.path.join(self.config.image_folder, "*.jpeg")))
            image_paths.sort(key=sort_key)
            return image_paths

    def _prepare_append_video(self, temp_dirs):
        """Internal helper to download append video if required."""
        local_path = self.config.append_video_path
        if self.config.append_video_source == "nextcloud" and self.nc_client:
            local_path, temp_vid_dir = self.nc_client.download_file(self.config.append_video_path)
            if temp_vid_dir:
                temp_dirs.append(temp_vid_dir)
        return local_path, None

    def _compose_final(self, slideshow, append, fps):
        """Internal helper to concatenate clips into the final video."""
        if append:
            if slideshow:
                final = concatenate_videoclips([slideshow, append], method="chain")
            else:
                final = append
        else:
            final = slideshow
            
        if not final:
            raise RuntimeError("No video content created.")
            
        final.fps = fps
        return final

    @staticmethod
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
