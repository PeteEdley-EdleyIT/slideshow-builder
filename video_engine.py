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
import asyncio
from moviepy.editor import concatenate_videoclips
from moviepy.video.io.ffmpeg_writer import ffmpeg_write_video

from nextcloud_client import sort_key
from audio_manager import AudioManager
from slideshow_generator import SlideshowGenerator
from video_utils import make_silent_audio
from health_manager import get_status_logger

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
    def __init__(self, config, nextcloud_client=None, target_size=(1920, 1080), health_mgr=None):
        """
        Initializes the VideoEngine.

        Args:
            config (Config): An instance of the Config class containing settings.
            nextcloud_client (NextcloudClient, optional): Client for Nextcloud operations.
            target_size (tuple, optional): Target video resolution. Defaults to (1920, 1080).
            health_mgr (HealthManager, optional): Manager for status and progress.
        """
        self.config = config
        self.nc_client = nextcloud_client
        self.target_size = target_size
        self.health_mgr = health_mgr
        self.generator = SlideshowGenerator(target_size)
        self.audio_mgr = AudioManager(nextcloud_client)

    async def validate_resources(self):
        """
        Validates that all required resources (images, music, upload paths) exist
        before starting the time-consuming video generation.

        Raises:
            ValueError: If a required resource is missing or inaccessible.
        """
        if self.health_mgr:
            self.health_mgr.update_status("Validating", "Checking resources and paths")

        # 1. Check Image Source
        if self.config.image_source == "nextcloud":
            if not self.nc_client:
                raise ValueError("Nextcloud client not initialized but Nextcloud image source selected.")
            if not await asyncio.to_thread(self.nc_client.check_path_exists, self.config.nextcloud_image_path):
                raise ValueError(f"Nextcloud image path does not exist: {self.config.nextcloud_image_path}")
        else:
            if not os.path.isdir(self.config.images_folder):
                raise ValueError(f"Local images folder does not exist: {self.config.images_folder}")

        # 2. Check Music Source (if configured)
        if self.config.music_folder:
            if self.config.music_source == "nextcloud":
                if not self.nc_client:
                    raise ValueError("Nextcloud client not initialized but Nextcloud music source selected.")
                if not await asyncio.to_thread(self.nc_client.check_path_exists, self.config.music_folder):
                    raise ValueError(f"Nextcloud music folder does not exist: {self.config.music_folder}")
            else:
                if not os.path.isdir(self.config.music_folder):
                    raise ValueError(f"Local music folder does not exist: {self.config.music_folder}")

        # 3. Check Append Video (if configured)
        if self.config.append_video_path:
            if self.config.append_video_source == "nextcloud":
                if not self.nc_client:
                    raise ValueError("Nextcloud client not initialized but Nextcloud append video source selected.")
                if not await asyncio.to_thread(self.nc_client.check_path_exists, self.config.append_video_path):
                    raise ValueError(f"Nextcloud append video file does not exist: {self.config.append_video_path}")
            else:
                if not os.path.isfile(self.config.append_video_path):
                    raise ValueError(f"Local append video file does not exist: {self.config.append_video_path}")

        # 4. Check Nextcloud Upload Destination (Parent Directory)
        if self.config.upload_nextcloud_path:
            if not self.nc_client:
                raise ValueError("Nextcloud client not initialized but Nextcloud upload path configured.")
            
            # Check the parent directory of the upload path
            parent_dir = os.path.dirname(self.config.upload_nextcloud_path)
            if parent_dir and not await asyncio.to_thread(self.nc_client.check_path_exists, parent_dir):
                raise ValueError(f"Nextcloud upload destination directory does not exist: {parent_dir}")
        
        print("Resources and paths validated successfully.")
    async def create_slideshow(self, output_filepath, status_callback=None):
        """
        Executes the full slideshow generation workflow.

        Args:
            output_filepath (str): Local path where the final video file will be saved.
            status_callback (callable, optional): Async function(message, stage) for progress updates.

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
            if self.health_mgr:
                self.health_mgr.update_status("Sourcing", "Retrieving images")
            image_paths = await asyncio.to_thread(self._source_images, temp_dirs)

            included_slides = [os.path.basename(p) for p in image_paths]

            # 2. Prepare Append Video
            if self.config.append_video_path:
                if self.health_mgr:
                    self.health_mgr.update_status("Sourcing", f"Downloading {os.path.basename(self.config.append_video_path)}")
                local_video_path, fps_from_clip = await asyncio.to_thread(self._prepare_append_video, temp_dirs)
                append_video_clip = await asyncio.to_thread(self.generator.load_append_video, local_video_path)
                
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
                if self.health_mgr:
                    self.health_mgr.update_status("Generating", "Creating slideshow video")
                slideshow_video = await asyncio.to_thread(
                    self.generator.create_video, 
                    image_paths, self.config.image_duration, slideshow_target_duration, fps
                )
                
                if self.health_mgr:
                    self.health_mgr.update_status("Generating", "Preparing background music")
                slideshow_audio = await asyncio.to_thread(
                    self.audio_mgr.prepare_background_music,
                    self.config.music_folder, self.config.music_source, slideshow_target_duration, temp_dirs
                )
                
                if not slideshow_audio:
                    slideshow_audio = make_silent_audio(slideshow_target_duration)
                
                slideshow_video = slideshow_video.set_audio(slideshow_audio)

            # 5. Final Composition
            final_video = self._compose_final(slideshow_video, append_video_clip, fps)
            
            # Apply Timer Overlay if enabled
            if self.config.enable_timer:
                timer_start_at = max(0, final_video.duration - (self.config.timer_minutes * 60))
                print(f"Timer enabled: Overlaying countdown starting at {timer_start_at}s (last {self.config.timer_minutes} mins)")
                
                final_video = await asyncio.to_thread(
                    self.generator.apply_timer_overlay,
                    final_video, 
                    start_time_offset=timer_start_at, 
                    total_duration=final_video.duration,
                    position=self.config.timer_position
                )
            
            # 6. Export and Upload
            await asyncio.to_thread(self.write_video_manually, final_video, output_filepath, fps, health_mgr=self.health_mgr)
            
            if status_callback:
                filename = os.path.basename(output_filepath)
                await status_callback(f"💾 Video file successfully written to local storage: `{filename}`", "written")
            
            if self.nc_client and self.config.upload_nextcloud_path:
                if self.health_mgr:
                    self.health_mgr.update_status("Uploading", f"Uploading to {self.config.upload_nextcloud_path}")
                await asyncio.to_thread(self.nc_client.upload_file, output_filepath, self.config.upload_nextcloud_path)
                if status_callback:
                    await status_callback(f"☁️ Video successfully uploaded to Nextcloud: `{self.config.upload_nextcloud_path}`", "uploaded")
                
            return included_slides

        finally:
            if append_video_clip:
                append_video_clip.close()
            for d in temp_dirs:
                if os.path.exists(d):
                    shutil.rmtree(d)

    def _source_images(self, temp_dirs):
        """Internal helper to retrieve image paths from local or Nextcloud."""
        extensions = ('.jpg', '.jpeg', '.png', '.webp', '.bmp')
        
        if self.config.image_source == "nextcloud" and self.nc_client and self.config.nextcloud_image_path:
            print(f"Retrieving images from Nextcloud: {extensions}")
            image_paths, temp_img_dir = self.nc_client.list_and_download_files(
                self.config.nextcloud_image_path, allowed_extensions=extensions
            )
            if temp_img_dir:
                temp_dirs.append(temp_img_dir)
            return image_paths
        else:
            print(f"Retrieving images from local folder: {self.config.image_folder}")
            image_paths = []
            for ext in extensions:
                image_paths.extend(glob.glob(os.path.join(self.config.image_folder, f"*{ext}")))
                # Also handle uppercase extensions for local files
                image_paths.extend(glob.glob(os.path.join(self.config.image_folder, f"*{ext.upper()}")))
            
            # Remove duplicates if any (e.g. .JPG vs .jpg if OS is case-insensitive but glob isn't)
            image_paths = list(set(image_paths))
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
    def write_video_manually(final_video, output_filepath, fps, health_mgr=None):
        """
        Handles the manual ffmpeg writing process with progress tracking.
        """
        print(f"Writing video to {output_filepath} (Duration: {final_video.duration}s, FPS: {fps})...")
        output_dir = os.path.dirname(output_filepath)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir)

        # Setup progress tracking for the encoding stage
        logger = "bar" # MoviePy default
        if health_mgr:
            logger = get_status_logger(health_mgr)
            health_mgr.update_status("Encoding", "Generating final MP4")

        audio_temp = None
        try:
            if final_video.audio:
                audio_temp = tempfile.NamedTemporaryFile(suffix=".m4a", delete=False).name
                final_video.audio.write_audiofile(audio_temp, fps=44100, codec="aac", logger=logger, verbose=False)
            
            ffmpeg_write_video(final_video, output_filepath, fps, codec="libx264", audiofile=audio_temp, logger=logger, verbose=False)
        finally:
            if audio_temp and os.path.exists(audio_temp):
                os.remove(audio_temp)
