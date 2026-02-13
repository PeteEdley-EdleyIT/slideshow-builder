"""
Overlay Management for the Video Slideshow Automation.

This module provides utilities for generating dynamic overlay clips, 
such as countdown timers, at fixed positions.
"""

from moviepy.editor import TextClip, ColorClip, CompositeVideoClip

class TimerOverlay:
    """
    Handles the generation of countdown timer clips at a fixed position.
    """
    def __init__(self, target_size=(1920, 1080), font='DejaVu-Sans', font_size=70, color='white'):
        self.target_size = target_size
        self.font = font
        self.font_size = font_size
        self.color = color

    def create_countdown_clip(self, remaining_seconds, duration, position='top-middle'):
        """
        Creates a single timer clip for a specific duration at a fixed position.
        
        Args:
            remaining_seconds (int): The starting number for the countdown (e.g., 300 for 5:00).
            duration (float): How long the clip should last (usually 1 second).
            position (str): Positioning hint. Defaults to 'top-middle'.

        Returns:
            VideoClip: A moviepy clip with the timer.
        """
        mins, secs = divmod(int(remaining_seconds), 60)
        timer_text = f"{mins:02d}:{secs:02d}"
        
        # Dimensions for the timer box
        box_w, box_h = 260, 110
        
        # Create the text clip
        txt_clip = TextClip(
            timer_text, 
            fontsize=self.font_size, 
            color=self.color, 
            font=self.font,
            method='caption',
            size=(box_w - 10, box_h - 10)
        ).set_duration(duration)
        
        # Add a subtle background semi-transparent box for readability
        bg_clip = ColorClip(size=(box_w, box_h), color=(0, 0, 0), ismask=False).set_opacity(0.4).set_duration(duration)
        
        # Fixed position logic
        if position == 'top-middle':
            # Horizontal: centered. Vertical: 50 pixels from top.
            x = (self.target_size[0] - box_w) // 2
            y = 50
            pos = (x, y)
        else:
            # Fallback to bottom-right
            pos = ("right", "bottom")
        
        # Composite them
        timer_layered = CompositeVideoClip([bg_clip, txt_clip.set_position("center")], size=(box_w, box_h))
        return timer_layered.set_position(pos)


class MusicAttributionOverlay:
    """
    Handles the generation of music attribution overlays.
    """
    def __init__(self, target_size=(1920, 1080), font='DejaVu-Sans', font_size=24, color='white'):
        self.target_size = target_size
        self.font = font
        self.font_size = font_size
        self.color = color

    def create_attribution_clip(self, attribution_text, duration, position='bottom-right'):
        """
        Creates an attribution overlay for a specific duration.
        
        Args:
            attribution_text (str): The text to display (Creator, Artist, Title, Link).
            duration (float): How long the overlay should last.
            position (str): Positioning hint. Defaults to 'bottom-right'.

        Returns:
            VideoClip: A moviepy clip with the attribution.
        """
        # Clean up text (strip leading/trailing whitespace and newlines)
        text = attribution_text.strip()
        
        # Max width is 1/3 of the screen
        max_w = self.target_size[0] // 3
        
        # Create the text clip
        txt_clip = TextClip(
            text, 
            fontsize=self.font_size, 
            color=self.color, 
            font=self.font,
            method='caption',
            size=(max_w - 40, None), # Let height be dynamic but bounded
            align='East' if 'right' in position else 'West'
        ).set_duration(duration)
        
        # Get actual text dimensions
        txt_w, txt_h = txt_clip.size
        box_w, box_h = txt_w + 40, txt_h + 30
        
        # Add a semi-transparent box for readability
        bg_clip = ColorClip(size=(box_w, box_h), color=(0, 0, 0), ismask=False).set_opacity(0.6).set_duration(duration)
        
        # Fixed position logic
        if position == 'bottom-left':
            # Horizontal: 50 pixels from left. Vertical: 50 pixels from bottom.
            x = 50
            y = self.target_size[1] - box_h - 50
            pos = (x, y)
        elif position == 'bottom-right':
            # Horizontal: 50 pixels from right. Vertical: 50 pixels from bottom.
            x = self.target_size[0] - box_w - 50
            y = self.target_size[1] - box_h - 50
            pos = (x, y)
        else:
            # Fallback
            pos = ("right", "bottom")
            
        # Composite them
        attr_layered = CompositeVideoClip([bg_clip, txt_clip.set_position("center")], size=(box_w, box_h))
        return attr_layered.set_position(pos)
