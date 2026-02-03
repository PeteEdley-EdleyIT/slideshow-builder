import numpy as np
from moviepy.editor import AudioClip
from PIL import Image

def patch_moviepy():
    """
    Workaround for MoviePy + Pillow 10+ compatibility.
    This MUST happen before moviepy imports to avoid AttributeError.
    """
    if not hasattr(Image, 'ANTIALIAS'):
        # In Pillow 10+, ANTIALIAS was removed in favor of LANCZOS
        Image.ANTIALIAS = getattr(Image, 'LANCZOS', Image.BICUBIC)

def make_silent_audio(duration, fps=44100):
    """
    Creates a silent stereo audio clip for the given duration.
    """
    def make_silent_frame(t):
        if np.ndim(t) > 0:
            return np.zeros((len(t), 2))
        else:
            return np.zeros(2)
    
    return AudioClip(make_silent_frame, duration=duration, fps=fps)

def resize_image(image_path, target_size):
    """
    Resizes an image to the target size while maintaining quality.
    """
    img = Image.open(image_path).convert("RGB")
    if img.size != target_size:
        return img.resize(target_size, Image.ANTIALIAS)
    return img
