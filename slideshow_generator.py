import os
import math
import numpy as np
from moviepy.editor import ImageClip, concatenate_videoclips, VideoFileClip
from video_utils import resize_image

class SlideshowGenerator:
    def __init__(self, target_size=(1920, 1080)):
        self.target_size = target_size

    def create_video(self, image_paths, image_duration, target_duration, fps):
        """
        Creates a repeating slideshow video from a list of image paths.
        """
        if not image_paths:
            return None

        print(f"Standardizing {len(image_paths)} images to {self.target_size}...")
        clips = []
        for p in image_paths:
            try:
                img = resize_image(p, self.target_size)
                clip = ImageClip(np.array(img)).set_duration(image_duration)
                clip.fps = fps
                clips.append(clip)
            except Exception as e:
                print(f"Warning: Could not process image {p}: {e}")

        if not clips:
            return None

        sequence_duration = len(clips) * image_duration
        num_repeats = math.ceil(target_duration / sequence_duration) if sequence_duration > 0 else 1
        repeated_clips = clips * int(num_repeats)

        slideshow_video = concatenate_videoclips(repeated_clips, method="chain")
        slideshow_video = slideshow_video.subclip(0, target_duration).set_duration(target_duration)
        slideshow_video.fps = fps
        
        return slideshow_video

    def load_append_video(self, video_path, target_fps):
        """
        Loads and prepares the video clip to be appended.
        """
        if not video_path or not os.path.exists(video_path):
            return None

        try:
            clip = VideoFileClip(video_path)
            # Resize if needed
            if clip.size != self.target_size:
                print(f"Resizing append video from {clip.size} to {self.target_size}")
                clip = clip.resize(self.target_size)
            
            clip.fps = target_fps
            return clip
        except Exception as e:
            print(f"Error loading append video '{video_path}': {e}")
            return None
