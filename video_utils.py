"""
Utility functions for video processing with MoviePy and Pillow.

This module provides helper functions for patching MoviePy for Pillow
compatibility, creating silent audio clips, and resizing images for
consistent video output.
"""

import numpy as np
from moviepy.editor import AudioClip
from PIL import Image

def patch_moviepy():
    """
    Workaround for MoviePy + Pillow 10+ compatibility.

    In Pillow 10 (Pillow 10.0.0 was released on July 1, 2023), the `ANTIALIAS`
    constant was removed. MoviePy versions prior to its update for Pillow 10+
    might still reference `Image.ANTIALIAS`. This function re-maps `ANTIALIAS`
    to `LANCZOS` (or `BICUBIC` as a fallback) to prevent `AttributeError`.

    This function MUST be called before any MoviePy imports that might
    internally use `Image.ANTIALIAS`.
    """
    if not hasattr(Image, 'ANTIALIAS'):
        # In Pillow 10+, ANTIALIAS was removed in favor of LANCZOS
        Image.ANTIALIAS = getattr(Image, 'LANCZOS', Image.BICUBIC)

def make_silent_audio(duration, fps=44100):
    """
    Creates a silent stereo audio clip for the given duration.

    This is useful for creating placeholder audio tracks or ensuring
    a consistent audio duration when compositing.

    Args:
        duration (float): The duration of the silent audio clip in seconds.
        fps (int, optional): The frames per second (sample rate) of the audio.
                             Defaults to 44100 Hz.

    Returns:
        AudioClip: A MoviePy AudioClip object representing the silent audio.
    """
    def make_silent_frame(t):
        """
        Generates a silent audio frame at time `t`.
        Returns a stereo (2-channel) array of zeros.
        """
        if np.ndim(t) > 0:
            # For an array of times (e.g., when MoviePy requests multiple frames)
            return np.zeros((len(t), 2))
        else:
            # For a single time point
            return np.zeros(2)
    
    return AudioClip(make_silent_frame, duration=duration, fps=fps)

def resize_image(image_path, target_size):
    """
    Resizes an image to the target size while maintaining aspect ratio
    and quality.

    The image is opened, converted to RGB, and then resized using
    `Image.ANTIALIAS` (which is mapped to `LANCZOS` or `BICUBIC` by `patch_moviepy`).

    Args:
        image_path (str): The file path to the image to be resized.
        target_size (tuple): A tuple (width, height) representing the desired
                             output resolution.

    Returns:
        PIL.Image.Image: The resized PIL Image object.
    """
    img = Image.open(image_path).convert("RGB")
    if img.size != target_size:
        # Use Image.ANTIALIAS (patched to LANCZOS/BICUBIC) for high-quality resizing
        return img.resize(target_size, Image.ANTIALIAS)
    return img
