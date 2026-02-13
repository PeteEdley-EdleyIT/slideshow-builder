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

        Returns:
            tuple: (AudioClip, list of attributions)
                   Attributions is a list of tuples: (start_time, metadata_text)
        """
        music_files = []
        temp_music_dir = None

        if music_source == "nextcloud" and music_folder and self.nextcloud_client:
            print("Retrieving background music from Nextcloud (mp3 + md)...")
            # List and download both mp3 and metadata files
            music_files, temp_music_dir = self.nextcloud_client.list_and_download_files(
                music_folder, allowed_extensions=('.mp3', '.md')
            )
            if temp_music_dir:
                temp_dir_list.append(temp_music_dir)
        elif music_source == "local" and music_folder:
            # Get local files
            for ext in ('.mp3', '.md'):
                music_files.extend(glob.glob(os.path.join(music_folder, f"*{ext}")))
                music_files.extend(glob.glob(os.path.join(music_folder, f"*{ext.upper()}")))

        if not music_files:
            print("No music files found.")
            return None, []

        # Separate mp3 and md files
        mp3_files = [f for f in music_files if f.lower().endswith('.mp3')]
        md_files = [f for f in music_files if f.lower().endswith('.md')]
        
        # Link metadata to tracks
        track_metadata = {}
        for mp3 in mp3_files:
            base = os.path.splitext(mp3)[0]
            md_match = next((md for md in md_files if os.path.splitext(md)[0] == base), None)
            if md_match:
                try:
                    with open(md_match, 'r', encoding='utf-8') as f:
                        track_metadata[mp3] = f.read()
                except Exception as e:
                    print(f"Warning: Could not read metadata file {md_match}: {e}")
            else:
                track_metadata[mp3] = None

        print(f"Found {len(mp3_files)} music tracks. Creating background audio...")
        try:
            selected_music = []
            attributions = [] # List of (start_time, metadata_text)
            current_music_duration = 0
            music_pool = list(mp3_files)
            random.shuffle(music_pool)

            while current_music_duration < target_duration + 30:
                if not music_pool:
                    music_pool = list(mp3_files)
                    random.shuffle(music_pool)
                
                track_path = music_pool.pop(0)
                try:
                    track = AudioFileClip(track_path)
                    
                    # Record attribution if metadata exists
                    metadata = track_metadata.get(track_path)
                    if metadata and current_music_duration < target_duration:
                        attributions.append((current_music_duration, metadata))
                    
                    selected_music.append(track)
                    current_music_duration += track.duration
                except Exception as e:
                    print(f"Error loading music track {track_path}: {e}")

            if not selected_music:
                return None, []

            # Concatenate all selected music clips
            full_music = concatenate_audioclips(selected_music)
            
            # Fade out configuration
            fade_duration = 10
            audio_end = max(0, target_duration - 5)
            
            bg_music = full_music.subclip(0, audio_end).set_duration(audio_end)
            
            try:
                bg_music = audio_fadeout(bg_music, fade_duration)
            except Exception as e:
                print(f"WARNING: audio_fadeout failed: {e}")

            full_silent_audio = make_silent_audio(target_duration)
            slideshow_audio = CompositeAudioClip([full_silent_audio, bg_music])
            slideshow_audio.duration = target_duration
            
            return slideshow_audio, attributions

        except Exception as e:
            print(f"Error processing background music: {e}")
            return None, []
