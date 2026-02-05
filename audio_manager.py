"""
Audio Manager for handling background music in video slideshows.

This module provides the `AudioManager` class responsible for retrieving,
selecting, and processing background music tracks from local or Nextcloud
sources, including looping and fade-out effects.
"""

import os
import random
import glob
from moviepy.editor import AudioFileClip, concatenate_audioclips, CompositeAudioClip
from moviepy.audio.fx.all import audio_fadeout
from video_utils import make_silent_audio

class AudioManager:
    """
    Manages the selection, processing, and integration of background music
    for video slideshows.

    It can fetch music files from local directories or a Nextcloud instance,
    loop them to match a target duration, and apply a fade-out effect.

    Attributes:
        nextcloud_client (NextcloudClient, optional): An instance of NextcloudClient
                                                      to interact with Nextcloud. Defaults to None.
    """
    def __init__(self, nextcloud_client=None):
        """
        Initializes the AudioManager.

        Args:
            nextcloud_client (NextcloudClient, optional): An initialized NextcloudClient
                                                          instance. Defaults to None.
        """
        self.nextcloud_client = nextcloud_client

    def prepare_background_music(self, music_folder, music_source, target_duration, temp_dir_list):
        """
        Retrieves, selects, and processes background music to match the target video duration.

        This method handles fetching music files from either a local folder or Nextcloud.
        It shuffles the available tracks and loops them as necessary to cover the
        `target_duration`, adding a buffer to ensure sufficient audio. A fade-out
        effect is applied towards the end of the generated audio clip.

        Args:
            music_folder (str): The path to the folder containing music files
                                (local path or Nextcloud remote path).
            music_source (str): Specifies where to retrieve music files from ('local' or 'nextcloud').
            target_duration (int): The desired duration (in seconds) of the background music.
            temp_dir_list (list): A list to which any created temporary directories
                                  (e.g., for downloaded Nextcloud music) will be appended.

        Returns:
            AudioClip: A MoviePy AudioClip object representing the prepared background music,
                       or None if no music files are found or an error occurs during processing.
        """
        music_files = []
        temp_music_dir = None

        if music_source == "nextcloud" and music_folder and self.nextcloud_client:
            print("Retrieving background music from Nextcloud...")
            # List and download music files from Nextcloud
            music_files, temp_music_dir = self.nextcloud_client.list_and_download_files(
                music_folder, allowed_extensions=('.mp3',)
            )
            if temp_music_dir:
                temp_dir_list.append(temp_music_dir) # Keep track of temp dir for cleanup
        elif music_source == "local" and music_folder:
            # Get local MP3 files
            music_files = sorted(glob.glob(os.path.join(music_folder, "*.mp3")))

        if not music_files:
            print("No music files found.")
            return None

        print(f"Found {len(music_files)} music tracks. Creating background audio...")
        try:
            selected_music = []
            current_music_duration = 0
            music_pool = list(music_files) # Create a mutable copy for shuffling
            random.shuffle(music_pool) # Randomize the order of tracks

            # Loop through music tracks, adding them until target_duration is met
            # Add a buffer (e.g., 30s) to ensure enough audio for fade-out and exact duration
            while current_music_duration < target_duration + 30:
                if not music_pool:
                    # If all tracks have been used, reshuffle and reuse
                    music_pool = list(music_files)
                    random.shuffle(music_pool)
                
                track_path = music_pool.pop(0) # Get a random track
                try:
                    track = AudioFileClip(track_path)
                    selected_music.append(track)
                    current_music_duration += track.duration
                except Exception as e:
                    print(f"Error loading music track {track_path}: {e}")
                    # Continue with other tracks even if one fails

            if not selected_music:
                return None

            # Concatenate all selected music clips
            full_music = concatenate_audioclips(selected_music)
            
            # Fade out configuration: Start fade 15s before end, fade over 10s, 5s silence
            fade_duration = 10 # Duration of the fade-out effect
            audio_end = max(0, target_duration - 5) # Point where audio should effectively end (5s before target_duration)
            
            # Subclip the concatenated music to the desired length for fade-out
            bg_music = full_music.subclip(0, audio_end).set_duration(audio_end)
            
            try:
                # Apply fade-out effect
                bg_music = audio_fadeout(bg_music, fade_duration)
            except Exception as e:
                print(f"WARNING: audio_fadeout failed: {e}")
                # Continue without fade-out if it fails

            # Composite over a silent track to ensure the exact target_duration
            # This handles cases where the music might be slightly shorter than target_duration
            full_silent_audio = make_silent_audio(target_duration)
            slideshow_audio = CompositeAudioClip([full_silent_audio, bg_music])
            slideshow_audio.duration = target_duration # Ensure final duration is exact
            
            return slideshow_audio

        except Exception as e:
            print(f"Error processing background music: {e}")
            return None
