# MCF Notices Video Automation

This project is going to take a folder full of images in a jpeg format, and cobine them together into a video slide show.

Here are a list of required features to work through one by one we will not be moving on to the next feature until the current on is complete and tested.

# Development enviroment
The development enviroment will be a nixos machine and we will developing in python, using gemini-cli.  The development enviroment will be set up using via a nix flake and all project dependancies will be managed by the flake instead of somthing like pip and a venv.

# Deployment
Final deployment will be via a Docker image, built using Nix. The script will run via a cron job within the Docker image. Configuration will be managed via environment variables, which can be set in a `.env` file for local development.

## Building the Docker Image
To build the Docker image using Nix, run the following command from the project root:
```bash
nix build .#packages.dockerImage
```
This command will build the Docker image and place it in the Nix store. You can then load it into your Docker daemon using:
```bash
docker load < $(nix path-info .#packages.dockerImage)
```
Or, if you have `nix-daemon` and `docker` configured to work together, you might be able to directly load it.

## Running the Docker Image
Once loaded, you can run the image. For testing, you can run it interactively:
```bash
docker run -it --rm -v /path/to/your/local/.env:/app/.env notices-video-automation:latest /bin/bash
```
Inside the container, you can manually run the script:
```bash
python create_slideshow.py output/test_slideshow.mp4
```
For cron integration, we will need to set up the cron daemon within the Docker image. This is the next step.

# Features
## Complete
- [x] Initial minimun viable code - This needs to take images stored in a local folder and combine them into a video with each image being displayed for 10 seconds. The video needs to then be written out to another local folder
- [x] Get the slide show to repeat multiple times making the video 10 min long
- [x] Retrieve image files from nextcloud folder as an option along side local files
- [x] Save the video file to a nextcloud folder
- [x] Order image files numerically, placing non-prefixed files at the end of the sequence.
- [x] Refactor code to follow DRY principle and improve modularity (NextcloudClient class).
- [x] Lower FPS for slideshow efficiency.
- [x] Make output_filepath optional based on Nextcloud upload.

## TODO
==these are to be carried out one at a time in the order listed and a commit made to git once complted and fully tested==
- [ ] Integrate cron job into Docker image.

