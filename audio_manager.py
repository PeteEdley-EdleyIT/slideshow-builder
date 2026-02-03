import os
import random
import glob
from moviepy.editor import AudioFileClip, concatenate_audioclips, CompositeAudioClip
from moviepy.audio.fx.all import audio_fadeout
from video_utils import make_silent_audio

class AudioManager:
    def __init__(self, nextcloud_client=None):
        self.nextcloud_client = nextcloud_client

    def prepare_background_music(self, music_folder, music_source, target_duration, temp_dir_list):
        """
        Retrieves, selects, and processes background music.
        """
        music_files = []
        temp_music_dir = None

        if music_source == "nextcloud" and music_folder and self.nextcloud_client:
            print("Retrieving background music from Nextcloud...")
            music_files, temp_music_dir = self.nextcloud_client.list_and_download_files(
                music_folder, allowed_extensions=('.mp3',)
            )
            if temp_music_dir:
                temp_dir_list.append(temp_music_dir)
        elif music_source == "local" and music_folder:
            music_files = sorted(glob.glob(os.path.join(music_folder, "*.mp3")))

        if not music_files:
            print("No music files found.")
            return None

        print(f"Found {len(music_files)} music tracks. Creating background audio...")
        try:
            selected_music = []
            current_music_duration = 0
            music_pool = list(music_files)
            random.shuffle(music_pool)

            # Buffer of 30s to ensure we cover the whole duration
            while current_music_duration < target_duration + 30:
                if not music_pool:
                    music_pool = list(music_files)
                    random.shuffle(music_pool)
                
                track_path = music_pool.pop(0)
                try:
                    track = AudioFileClip(track_path)
                    selected_music.append(track)
                    current_music_duration += track.duration
                except Exception as e:
                    print(f"Error loading music track {track_path}: {e}")

            if not selected_music:
                return None

            full_music = concatenate_audioclips(selected_music)
            
            # Fade out configuration: 15s from end, 10s fade, 5s silence
            fade_duration = 10
            audio_end = max(0, target_duration - 5)
            
            bg_music = full_music.subclip(0, audio_end).set_duration(audio_end)
            
            try:
                bg_music = audio_fadeout(bg_music, fade_duration)
            except Exception as e:
                print(f"WARNING: audio_fadeout failed: {e}")

            # Composite over silent track to ensure exact duration
            full_silent_audio = make_silent_audio(target_duration)
            slideshow_audio = CompositeAudioClip([full_silent_audio, bg_music])
            slideshow_audio.duration = target_duration
            
            return slideshow_audio

        except Exception as e:
            print(f"Error processing background music: {e}")
            return None
