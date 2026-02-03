# MCF Notices Video Automation

This project is going to take a folder full of images in a jpeg format, and cobine them together into a video slide show.

Here are a list of required features to work through one by one we will not be moving on to the next feature until the current on is complete and tested.

# Development enviroment
The development enviroment will be a nixos machine and we will developing in python, using gemini-cli.  The development enviroment will be set up using via a nix flake and all project dependancies will be managed by the flake instead of somthing like pip and a venv.

## Local Execution
To run the script locally for testing:
1. Ensure your environment is set up (either via `nix develop` or by sourcing the `.venv`).
2. Run the script:
   ```bash
   python3 create_slideshow.py
   ```

# Deployment
Final deployment is via a container image, built using Nix. The script runs via a cron job within the container. Configuration is managed via environment variables, which should be set in a `.env` file.

## Building the Image
To build the container image using Nix, run the following command from the project root:
```bash
nix build .#dockerImage
```
This command builds the image and creates a `result` symlink to the `.tar.gz` archive in the Nix store.

## Running with Podman
1.  **Load the image into Podman:**
    ```bash
    podman load -i result
    ```
2.  **Start the production container:**
    ```bash
    podman run -d \
      --name notices-automation \
      --restart always \
      --env-file .env \
      localhost/mcf-notices-builder:latest
    ```

## Management Commands
Use these commands to monitor and manage the running automation:

- **Check Logs (Startup/Cron):**
  ```bash
  podman logs -f notices-automation
  ```
- **View Script Output (Slideshow Logs):**
  ```bash
  podman exec notices-automation cat /var/log/slideshow.log
  ```
- **List Scheduled Tasks:**
  ```bash
  podman exec notices-automation crontab -l
  ```
- **Restart Automation:**
  ```bash
  podman restart notices-automation
  ```
- **Manual Trigger (Run Immediately):**
  ```bash
  podman exec notices-automation bash -c ". /app/.env.cron; python3 /app/create_slideshow.py"
  ```

## Updating the Automation
When you have built and loaded a new image, you must remove the old container and start a new one to apply changes:
```bash
podman stop notices-automation
podman rm notices-automation
# Then run the 'podman run' command from the 'Running with Podman' section
```

## Pushing to a Registry
1.  **Tag the image:**
    ```bash
    podman tag localhost/mcf-notices-builder:latest docker.io/pedley/mcf-notices-builder:latest
    ```
2.  **Push the image:**
    ```bash
    podman push docker.io/pedley/mcf-notices-builder:latest
    ```

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
- [x] Integrate cron job into Docker image.
- [x] Make cron schedule configurable via environment variable.
- [x] Optionally append a video file (local or Nextcloud) to the end of the slideshow, adjusting slide duration to maintain target video length.
- [x] Background Music: Specify folder (local/Nextcloud), random selection, fade out over last 15s (10s fade, 5s silence) of slideshow.
- [x] Notification System: Send success/failure messages to a Matrix chat room, including the list of slides or error details.

