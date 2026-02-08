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
from moviepy.editor import ImageClip, concatenate_videoclips, VideoFileClip
from video_utils import resize_image

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
