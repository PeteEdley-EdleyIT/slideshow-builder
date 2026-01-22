import argparse
import os
import glob
from moviepy.editor import ImageClip, concatenate_videoclips
from moviepy.video.io.ffmpeg_writer import FFMPEG_VideoWriter

def create_slideshow(image_folder, output_filepath, image_duration=10):
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
    final_clip = concatenate_videoclips(clips)
    final_clip.fps = fps # Set fps for the final clip

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

    args = parser.parse_args()

    create_slideshow(args.image_folder, args.output_filepath, args.duration)
