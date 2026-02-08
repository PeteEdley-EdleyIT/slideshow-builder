# Video Slideshow Automation

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
Final deployment is via a container image, built using Nix. The script runs as a long-running daemon with internal scheduling. Configuration is managed via environment variables in a `.env` file.

> [!TIP]
> **Networking Tip**: If running health alerts (ntfy) on the same host as the container, use `NTFY_URL=http://host.containers.internal:8000` in your `.env` to allow the container to reach the host service reliably.

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
localhost/slideshow-builder:latest
    ```

## Management Commands
Use these commands to monitor and manage the running automation:

- **Check Logs (Daemon Output):**
  ```bash
  podman logs -f notices-automation
  ```
- **View Bot Status (via Matrix):**
  Send `!status` or `!help` in the Matrix chat room.
- **List Scheduled Tasks:**
  (Bot handles its own internal scheduling via APScheduler)
- **Restart Bot:**
  ```bash
  podman restart notices-automation
  ```
- **Manual Trigger (via Matrix):**
  Send `!rebuild` in the Matrix chat room.

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
    podman tag localhost/slideshow-builder:latest docker.io/pedley/slideshow-builder:latest
    ```
2.  **Push the image:**
    ```bash
    podman push docker.io/pedley/slideshow-builder:latest
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
- [x] Integrate cron job into Docker image (Replaced by APScheduler daemon).
- [x] Make cron schedule configurable via environment variable.
- [x] Optionally append a video file (local or Nextcloud) to the end of the slideshow, adjusting slide duration to maintain target video length.
- [x] Background Music: Specify folder (local/Nextcloud), random selection, fade out over last 15s (10s fade, 5s silence) of slideshow.
- [x] Notification System: Send success/failure messages to a Matrix chat room, including the list of slides or error details.
- [x] Interactive Matrix Bot: Switched from Cron to APScheduler, integrated `matrix-nio` for notifications and interactive commands (`!rebuild`, `!status`, `!help`).
- [x] Health Checks & Alerting: Podman native healthcheck via heartbeat file, ntfy.sh integration for success/failure alerts, and enhanced Matrix `!status` command.

## Future Ideas
- [ ] Add E2EE support for Matrix (requires persistent storage for keys).
- [ ] Add more commands (e.g., `!cancel`, `!config`).

## Full interactive matrix bot implementation plan
1. Recommended Library: matrix-nio
The industry standard for building Matrix bots in Python is matrix-nio.

Availability: It is available in nixpkgs as python311Packages.matrix-nio.
Features: It supports high-level bot interactions, including replying to messages, reactions, and importantly, End-to-End Encryption (E2EE) if your room requires it.
2. Architectural Shift: Cron vs. Daemon
Currently, your script is a "one-off": it starts, creates a video, and exits. To receive commands, the process needs to be a daemon (a long-running process) that stays connected to the Matrix server.

How you would structure it:

The Main Loop: Instead of cron starting the script, the container would start the Python script as a background service.
Interactive Commands: The script uses an AsyncClient to listen for events. When it sees a message like !rebuild, it calls the 
create_slideshow()
 function immediately.
Replacing Cron: You wouldn't even need cron anymore. You can use a Python library like apscheduler inside the same script to handle the "Friday at 1:00 AM" schedule. This puts all your logic in one place.
3. Example Command Logic
A simple interactive loop would look something like this:

python
async def message_callback(room, event):
    if event.sender == "@your_user:matrix.org":  # Security: Only allow you
        if event.body == "!rebuild":
            await client.room_send(room.room_id, "m.room.message", {"body": "🚀 Starting manual rebuild..."})
            # Run your existing create_slideshow logic here
            await client.room_send(room.room_id, "m.room.message", {"body": "✅ Manual rebuild complete!"})
4. Security & Authentication
Sender Filtering: You must check the event.sender ID. Without this, anyone in the room (or even anyone who finds your bot) could trigger a resource-heavy video render.
E2EE: If your Matrix room is encrypted, the bot needs a persistent directory in the container to store its "encryption keys" (a SQLite database).
Summary of what would change in your project:
flake.nix
: Add python311Packages.matrix-nio and python311Packages.apscheduler.
setup-docker.sh
: Change the entry point from starting cron to simply starting your 
create_slideshow.py
 (which would now be renamed or updated to be a long-running bot).
matrix_client.py
: Upgrade this from a simple "send-only" requests client to a full nio AsyncClient.
This is a great logical next step for the project because it gives you "chat-ops" control over your video production without needing to SSH into a server or wait for a cron job.

