import argparse
import os
import glob
from moviepy.editor import ImageClip, concatenate_videoclips
from moviepy.video.io.ffmpeg_writer import FFMPEG_VideoWriter

import math

def create_slideshow(image_folder, output_filepath, image_duration=10, target_video_duration=600):
    # Ensure the image folder exists
    if not os.path.isdir(image_folder):
        print(f"Error: Image folder '{image_folder}' not found.")
        return

    # Find all JPEG images in the specified folder
    # Sort them to ensure a consistent order
    image_paths = sorted(glob.glob(os.path.join(image_folder, "*.jpg")))
    image_paths.extend(sorted(glob.glob(os.path.join(image_folder, "*.jpeg"))))

    if not image_paths:
        print(f"No JPEG images found in '{image_folder}'.")
        return

    print(f"Found {len(image_paths)} images. Creating slideshow...")

    # Create ImageClips for each image
    clips = []
    fps = 24 # Define fps for the writer and clip attribute
    for image_path in image_paths:
        try:
            # Create a clip and set the duration
            clip = ImageClip(image_path).set_duration(image_duration)
            clips.append(clip)
            print(f"Added {os.path.basename(image_path)} to slideshow.")
        except Exception as e:
            print(f"Warning: Could not process image {image_path}. Error: {e}")

    if not clips:
        print("No valid image clips could be created. Exiting.")
        return

    # Concatenate all image clips.
    # Calculate the total duration of one sequence of images
    sequence_duration = len(clips) * image_duration

    # Calculate how many times to repeat the sequence to reach target_video_duration
    # We use math.ceil to ensure we have enough repetitions
    num_repeats = math.ceil(target_video_duration / sequence_duration) if sequence_duration > 0 else 1

    # Repeat the sequence of clips
    repeated_clips = []
    for _ in range(int(num_repeats)):
        repeated_clips.extend(clips)

    final_clip = concatenate_videoclips(repeated_clips)
    final_clip.fps = fps # Set fps for the final clip

    # Trim the final clip to the exact target_video_duration
    final_clip = final_clip.subclip(0, target_video_duration)
    final_clip.duration = target_video_duration # Explicitly set duration after subclip

    # Write the result to a file
    print(f"Writing video to {output_filepath}...")
    
    # Ensure the output directory exists
    output_dir = os.path.dirname(output_filepath)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir)

    fps = 24 # Define fps for the writer
    with FFMPEG_VideoWriter(output_filepath, final_clip.size, fps, codec="libx264") as writer:
        for frame in final_clip.iter_frames():
            writer.write_frame(frame)

    print(f"Slideshow video created successfully at {output_filepath}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Create a slideshow video from a folder of JPEG images.")
    parser.add_argument("image_folder", help="Path to the folder containing JPEG images.")
    parser.add_argument("output_filepath", help="Path and filename for the output video (e.g., output.mp4).")
    parser.add_argument("--duration", type=int, default=10,
                        help="Duration each image is displayed in seconds (default: 10).")
    parser.add_argument("--target_video_duration", type=int, default=600,
                        help="Target duration of the final video in seconds (default: 600 for 10 minutes).")

    args = parser.parse_args()

    create_slideshow(args.image_folder, args.output_filepath, args.duration, args.target_video_duration)
