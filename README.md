# Video Slideshow Automation

This project automatically creates video slideshows from image and music files, designed for easy deployment and hands-off operation. It integrates with Nextcloud for media sourcing and output, and features a Matrix bot for notifications and simple command-based control.

## Features

*   **Automated Video Creation:** Generates video slideshows from various image formats (JPEG, PNG, WebP, BMP) on a schedule.
*   **Flexible Media Sourcing:** Images and background music can be pulled from either local folders or a Nextcloud instance.
*   **Customizable Video Output:**
    *   Control how long each image is displayed.
    *   Optional countdown timer overlay for the last $X$ minutes.
    *   **Automatic Music Attribution:** Displays creator, artist, and link for background tracks (if a matching `.md` file exists).
*   **Smart Image Handling:** Images are automatically ordered numerically.
*   **Nextcloud Integration:** Seamlessly connects with your Nextcloud for image input, music input, and saving the final video.
*   **Background Music:** Randomly selects background music and fades it out smoothly as the video ends.
*   **Matrix Bot Control:**
    *   Receive automatic notifications (success/failure) in a Matrix chat room.
    *   Trigger video generation manually with a simple `!rebuild` command.
    *   Check the bot's status and access help commands directly from Matrix.
*   **Health Checks & Alerting:**
    *   **Podman Native Healthcheck:** Use a liveness pulse (heartbeat file) to monitor the container's health.
    *   **ntfy.sh Integration:** Receive instant push notifications for successful builds or critical failures on your self-hosted ntfy server.
    *   **Proactive Status Reporting:** Matrix `!status` command provides detailed metrics (uptime, last success, last heartbeat).
*   **Countdown Timer Overlay:** Optionally add a countdown timer to the final minutes of the video, with fixed top-middle positioning for high visibility.
*   **Runtime Configuration Management:** Override configuration settings on-the-fly via Matrix commands (`!set`, `!get`, `!config`, `!defaults`). Changes persist across container restarts.
*   **Fail-Fast Resource Validation:** Pre-flight checks verify all images, music, and upload paths exist before starting the render.
*   **Async Execution & Progress Tracking:** Heavy processing runs in background threads, keeping the bot responsive, with real-time progress bars available in `!status`.
*   **Containerized for Easy Deployment:** Provided as a Docker image for straightforward setup and management using Podman or Docker.

## Deployment

The application runs as a long-running service within a container. You'll build the container image, then run it using either Podman or Docker.

### Building the Container Image

To get started, you first need to build the container image from the project files.

```bash
nix build .#dockerImage
```

This command will create a Docker-compatible image. Once built, a `result` symlink will point to the `.tar.gz` archive of your image in the Nix store.

### Running the Container

After building the image, you can run it using either Podman or Docker. First, review the "Configuration" section below and create a `.env` file in the project's root directory. This file will contain all the necessary settings for your automation. A `.env.sample` is provided as a guide.

#### With Podman

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
  -v notices-data:/data \
  localhost/slideshow-builder:latest
```
    *   `-d`: Runs the container in detached mode (in the background).
    *   `--name notices-automation`: Assigns a memorable name to your container.
    *   `--restart always`: Ensures the container automatically restarts if it stops or the system reboots.
    *   `--env-file .env`: Mounts your `.env` file into the container for configuration.
    *   `-v notices-data:/data`: Creates a persistent volume for runtime configuration changes made via Matrix commands.
    *   `localhost/slideshow-builder:latest`: Specifies the image to run.

#### With Docker

1.  **Load the image into Docker:**
    ```bash
docker load -i result
```
2.  **Start the production container:**
    ```bash
docker run -d \
  --name notices-automation \
  --restart always \
  --env-file .env \
  -v notices-data:/data \
  localhost/slideshow-builder:latest
```
    The options are the same as for Podman.

### Using Docker Compose (Recommended for Docker Users)

For Docker users, `docker-compose` simplifies the management of your container. Create a `docker-compose.yml` file in your project root with the following content:

```yaml
version: '3.8'

services:
  notices-automation:
    image: localhost/slideshow-builder:latest
    container_name: notices-automation
    restart: always
    env_file:
      - .env
    volumes:
      - notices-data:/data
    # If you need to mount local folders for images/music/output, uncomment and adjust these:
    # volumes:
    #   - ./images:/app/images
    #   - ./music:/app/music
    #   - ./output:/app/output
    #   - notices-data:/data  # Keep this for persistent config
```

Then, you can manage your service with these commands:

*   **Start the service:**
    ```bash
docker-compose up -d
```
*   **Stop the service:**
    ```bash
docker-compose down
```
*   **Restart the service:**
    ```bash
docker-compose restart
```

## Health Checks and Alerting

The slideshow automation includes built-in mechanisms to ensure high availability and provide proactive status updates.

### Podman/Docker Native Healthchecks

The container is configured to check its own health using a "heartbeat" file. This file (`/tmp/heartbeat`) is updated by the bot every 60 seconds.

1.  **Enable Heartbeat:** Set `ENABLE_HEARTBEAT=true` in your `.env` file.
2.  **Container Status:** Once enabled, Podman or Docker will automatically monitor the heartbeat. You can check the health status with:
    ```bash
    podman inspect notices-automation --format '{{.State.Health.Status}}'
    # Or for Docker:
    docker inspect notices-automation --format '{{.State.Health.Status}}'
    ```
    The status will transition from `starting` to `healthy` once the bot initializes.

### External Alerting (ntfy.sh)

You can receive instant push notifications for successful video builds or critical errors using [ntfy](https://ntfy.sh).

1.  **Configure ntfy:** Add the following to your `.env` file:
    ```bash
    NTFY_URL=https://ntfy.sh
    NTFY_TOPIC=your_secret_topic_name
    # NTFY_TOKEN=your_optional_access_token
    ```
2.  **Automatic Alerts:** The bot will automatically send a notification when:
    *   A video is successfully produced and uploaded.
    *   An error occurs during the generation process.

### Matrix Status Monitoring

The Matrix bot provides a `!status` command that reports:
*   **Bot Uptime:** How long the daemon has been running.
*   **Last Success:** The timestamp of the last successful video generation.
*   **Heartbeat:** The timestamp of the most recent internal health pulse.
*   **Scheduler Info:** When the next automated build is scheduled.

### Management Commands

Once your container is running, here are some useful commands:

*   **Restart Bot:** If you make changes to your `.env` file or wish to reset the bot:
    ```bash
podman restart notices-automation
# OR
docker restart notices-automation
```
### Updating the Automation

To apply updates (e.g., after building a new version of the image with code changes or updated dependencies):

1.  Stop and remove the old container:
    ```bash
podman stop notices-automation && podman rm notices-automation
# OR
docker stop notices-automation && docker rm notices-automation
```
    If using `docker-compose`, simply run `docker-compose down`.
2.  Re-run the updated `podman run` or `docker run` command from the "Running the Container" section above, or `docker-compose up -d` if using Docker Compose.

### Pushing to a Container Registry (Optional)

If you need to move your image to a different machine or share it via a container registry (like Docker Hub):

1.  **Tag the image:**
    ```bash
podman tag localhost/slideshow-builder:latest yourusername/slideshow-builder:latest
# OR
docker tag localhost/slideshow-builder:latest yourusername/slideshow-builder:latest
```
    (Replace `yourusername` with your registry username)
2.  **Push the image:**
    ```bash
podman push yourusername/slideshow-builder:latest
# OR
docker push yourusername/slideshow-builder:latest
```

## Matrix Bot Usage

Your automation bot will send notifications and respond to commands in the Matrix room you configured.

*   **View Bot Status:** Send `!status` in the Matrix chat room to check if the bot is online, view its uptime, and see when the last video was successfully produced. If a production is currently running, it will show the active stage (e.g., Encoding) and a **visual progress bar**.
*   **Manual Video Generation:** Send `!rebuild` in the Matrix chat room to immediately trigger the video generation process. The bot will notify you when it starts and finishes.
*   **Runtime Configuration:** 
    *   `!set KEY VALUE` - Override a configuration setting (e.g., `!set IMAGE_DURATION 15`)
    *   `!get KEY` - View the current value of a setting
    *   `!get all` - View all configurable settings and their status (Override vs Default, with color-coding)
    *   `!config` - List only active configuration overrides
    *   `!defaults` - Reset all settings to .env defaults
*   **Get Help:** Send `!help` in the Matrix chat room to see a list of available commands in a clean, categorized layout.

## Configuration

All aspects of the slideshow automation are configured via environment variables. You must create a `.env` file in the same directory as your `flake.nix` (or where you run your container commands) and fill it with your specific settings. Refer to the `.env.sample` file for a template.

| Variable Name            | Description                                                                                             | Default Value   |
| :----------------------- | :------------------------------------------------------------------------------------------------------ | :-------------- |
| `IMAGE_DURATION`         | Sets how long (in seconds) each individual image remains on screen in the slideshow.                    | `10`            |
| `TARGET_VIDEO_DURATION`  | Defines the desired total length of the final video in seconds. The slideshow will repeat to meet this duration. | `600` (`10 min`)| 
| `IMAGE_SOURCE`           | Source of images: `nextcloud` or `local`. Defaults to `nextcloud` if `NEXTCLOUD_IMAGE_PATH` is set. If `local`, mount your folder to `/app/images`.  | (Auto)          |
| `MUSIC_SOURCE`           | Source of music: `nextcloud` or `local`. Defaults to `nextcloud` if `NEXTCLOUD_IMAGE_PATH` is set. If `local`, mount your folder to `/app/music`.    | (Auto)          |
| `NEXTCLOUD_URL`          | The base URL of your Nextcloud instance (e.g., `https://your.nextcloud.com`). Required for Nextcloud integration. | (None)          |
| `NEXTCLOUD_USERNAME`     | Your Nextcloud username for authentication. Required for Nextcloud integration.                         | (None)          |
| `NEXTCLOUD_PASSWORD`     | Your Nextcloud password for authentication. Required for Nextcloud integration.                         | (None)          |
| `NEXTCLOUD_IMAGE_PATH`   | The path within your Nextcloud instance where source image files are located (e.g., `Photos/Slideshow/`). | (None)          |
| `NEXTCLOUD_UPLOAD_PATH` | The path within your Nextcloud instance where the final generated video should be uploaded (e.g., `Videos/Generated/`). | (None)          |
| `NEXTCLOUD_INSECURE_SSL` | Set to `true` if your Nextcloud instance uses a self-signed or invalid SSL certificate and you wish to proceed anyway. Use with extreme caution. | `false`         |
| `APPEND_VIDEO_PATH`      | The path to an additional video file to be appended after the main slideshow. Can be a local path or a Nextcloud path (if `APPEND_VIDEO_SOURCE` is `nextcloud`). | (None)          |
| `APPEND_VIDEO_SOURCE`    | Specifies where the `APPEND_VIDEO_PATH` refers to: `local` for a local file, or `nextcloud` for a file on your Nextcloud. | `local`         |
| `MUSIC_FOLDER`           | Nextcloud path for background music (e.g., `Uploads/Music`) if `MUSIC_SOURCE` is `nextcloud`. Ignored if `MUSIC_SOURCE` is `local` (uses mounted `/app/music`). | `Uploads/Music` |
| `MUSIC_SOURCE`           | Specifies where the automation should find background music files: `local` for a local folder, or `nextcloud` for a Nextcloud path. | `local`         |
| `MATRIX_HOMESERVER`      | The URL of your Matrix homeserver (e.g., `https://matrix.org`). Required for Matrix bot functionality. | (None)          |
| `MATRIX_ACCESS_TOKEN`    | An access token for your Matrix bot user. This token *must* have sufficient permissions (read/write to the room, send messages). Essential for Matrix bot. | (None)          |
| `MATRIX_ROOM_ID`         | The internal ID of the Matrix room where the bot will operate. This is often a string like `!roomid:homeserver.com`. Required for Matrix bot. | (None)          | 
| `MATRIX_USER_ID`         | The full Matrix user ID of your bot (e.g., `@botname:yourhomeserver.com`). Required for Matrix bot.    | (None)          |
| `CRON_SCHEDULE`          | A cron expression that defines the schedule for automatic video generation. For example, `0 1 * * 5` means "every Friday at 1:00 AM". | `0 1 * * 5`     |
| `ENABLE_HEARTBEAT`       | Set to `true` to enable the creation of a heartbeat file (`/tmp/heartbeat`) for use with container healthchecks. | `false`         |
| `ENABLE_NTFY`            | Master switch to enable/disable ntfy notifications.                                                     | `false`         |
| `NTFY_URL`               | The base URL of your ntfy.sh server (e.g., `https://ntfy.sh` or your self-hosted instance). Notifications are only sent if both `NTFY_URL` and `NTFY_TOPIC` are set. | (None)          |
| `NTFY_TOPIC`             | The ntfy topic name to publish notifications to.                                                        | (None)          |
| `NTFY_TOKEN`             | Optional authentication token for your ntfy server.                                                     | (None)          |
| `ENABLE_TIMER`           | Set to `true` to enable a countdown timer overlay during the final minutes of the video.                | `false`         |
| `TIMER_MINUTES`          | Number of minutes before the end of the video to start the countdown.                                   | `5`             |
| `TIMER_POSITION`         | Position of the timer: `top-middle`, `bottom-right`, etc.                                               | `top-middle`    |
