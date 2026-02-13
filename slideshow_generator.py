"""
Slideshow Generator for creating video clips from images and managing video appending.

This module provides the `SlideshowGenerator` class, which is responsible for
taking a list of image paths, standardizing them, and compiling them into a
repeating video slideshow. It also handles loading and preparing an optional
video clip to be appended to the slideshow.
"""

import os
import math
import numpy as np
from moviepy.editor import ImageClip, concatenate_videoclips, VideoFileClip, CompositeVideoClip
from video_utils import resize_image
from overlay_manager import TimerOverlay, MusicAttributionOverlay

class SlideshowGenerator:
    """
    Generates video slideshows from images and handles optional video appending.

    This class takes image paths, resizes images to a target resolution,
    creates video clips from them, and concatenates them into a repeating
    slideshow of a specified duration. It also provides functionality to
    load and prepare a video file for appending.

    Attributes:
        target_size (tuple): A tuple (width, height) representing the target
                             resolution for all images and appended videos.
    """
    def __init__(self, target_size=(1920, 1080)):
        """
        Initializes the SlideshowGenerator.

        Args:
            target_size (tuple, optional): The target resolution (width, height)
                                           for images and appended videos.
                                           Defaults to (1920, 1080).
        """
        self.target_size = target_size

    def create_video(self, image_paths, image_duration, target_duration, fps):
        """
        Creates a repeating slideshow video from a list of image paths.

        Each image is resized, converted into a video clip of `image_duration`,
        and then concatenated. The sequence of images is repeated as many times
        as necessary to meet the `target_duration`.

        Args:
            image_paths (list): A list of file paths to the images to be included
                                in the slideshow.
            image_duration (int): The duration (in seconds) for which each image
                                  should be displayed.
            target_duration (int): The desired total duration (in seconds) of the
                                   final slideshow video.
            fps (int): The frames per second for the output video.

        Returns:
            VideoClip: A MoviePy VideoClip object representing the generated
                       slideshow, or None if no images are provided or processed.
        """
        if not image_paths:
            return None

        print(f"Standardizing {len(image_paths)} images to {self.target_size}...")
        clips = []
        for p in image_paths:
            try:
                # Resize image and create an ImageClip
                img = resize_image(p, self.target_size)
                clip = ImageClip(np.array(img)).set_duration(image_duration)
                clip.fps = fps
                clips.append(clip)
            except Exception as e:
                print(f"Warning: Could not process image {p}: {e}")

        if not clips:
            return None

        # Calculate how many times the image sequence needs to be repeated
        sequence_duration = len(clips) * image_duration
        num_repeats = math.ceil(target_duration / sequence_duration) if sequence_duration > 0 else 1
        repeated_clips = clips * int(num_repeats)

        # Concatenate clips and set final duration and FPS
        slideshow_video = concatenate_videoclips(repeated_clips, method="chain")
        slideshow_video = slideshow_video.subclip(0, target_duration).set_duration(target_duration)
        slideshow_video.fps = fps
        
        return slideshow_video

    def load_append_video(self, video_path):
        """
        Loads and prepares a video clip to be appended to the slideshow.

        The video is resized to the `target_size` if necessary and its
        FPS is set to `target_fps`.

        Returns:
            VideoFileClip: A MoviePy VideoFileClip object representing the
                           prepared video, or None if the path is invalid
                           or an error occurs during loading/processing.
        """
        if not video_path or not os.path.exists(video_path):
            return None

        try:
            clip = VideoFileClip(video_path)
            # Resize the video clip if its dimensions do not match target_size
            if clip.size != self.target_size:
                print(f"Resizing append video from {clip.size} to {self.target_size}")
                clip = clip.resize(self.target_size)
            
            return clip
        except Exception as e:
            print(f"Error loading append video '{video_path}': {e}")
            return None
    def apply_timer_overlay(self, video_clip, start_time_offset, total_duration, position='top-middle'):
        """
        Applies a countdown timer overlay to a video clip starting at a specific time.
        
        Args:
            video_clip (VideoClip): The clip to overlay the timer on.
            start_time_offset (float): The time (in seconds) within the clip when the timer starts.
            total_duration (float): The total duration of the entire video (for countdown calculation).
            position (str): Timer position.

        Returns:
            VideoClip: The clip with the timer overlay.
        """
        timer = TimerOverlay(target_size=self.target_size)
        timer_clips = []
        
        # Calculate how long the timer should run on this clip
        overlay_duration = video_clip.duration - start_time_offset
        
        # Step through the overlay period in 1-second chunks
        for t in range(int(overlay_duration)):
            current_time_in_video = start_time_offset + t
            remaining = total_duration - current_time_in_video
            
            if remaining < 0:
                break
                
            t_clip = timer.create_countdown_clip(
                remaining_seconds=remaining,
                duration=1,
                position=position
            ).set_start(current_time_in_video)
            
            timer_clips.append(t_clip)
            
        if not timer_clips:
            return video_clip
            
        # Ensure the background clip is explicitly set to avoid inheritance issues
        from moviepy.editor import CompositeVideoClip
        return CompositeVideoClip([video_clip] + timer_clips).set_duration(video_clip.duration)

    def apply_music_attributions(self, video_clip, attributions, display_duration=30):
        """
        Applies music attribution overlays to the video clip.
        
        Args:
            video_clip (VideoClip): The video clip to overlay attributions on.
            attributions (list): List of (start_time, metadata_text) tuples.
            display_duration (int): How long each attribution should be shown.

        Returns:
            VideoClip: The video clip with attribution overlays.
        """
        if not attributions:
            return video_clip
            
        attr_overlay = MusicAttributionOverlay(target_size=self.target_size)
        attr_clips = []
        
        for start_time, metadata in attributions:
            # Create the attribution clip
            # Ensure it doesn't exceed the video duration
            duration = min(display_duration, video_clip.duration - start_time)
            if duration <= 0:
                continue
                
            a_clip = attr_overlay.create_attribution_clip(
                attribution_text=metadata,
                duration=duration
            ).set_start(start_time)
            
            attr_clips.append(a_clip)
            
        if not attr_clips:
            return video_clip
            
        from moviepy.editor import CompositeVideoClip
        return CompositeVideoClip([video_clip] + attr_clips).set_duration(video_clip.duration)
