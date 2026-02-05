# MCF Notices Video Automation

This project automatically creates video slideshows from image and music files, designed for easy deployment and hands-off operation. It integrates with Nextcloud for media sourcing and output, and features a Matrix bot for notifications and simple command-based control.

## Features

*   **Automated Video Creation:** Generates video slideshows from JPEG images on a schedule.
*   **Flexible Media Sourcing:** Images and background music can be pulled from either local folders or a Nextcloud instance.
*   **Customizable Video Output:**
    *   Control how long each image is displayed.
    *   Set the total duration of the final video.
    *   Optionally append an existing video to the end of the slideshow.
*   **Smart Image Handling:** Images are automatically ordered numerically.
*   **Nextcloud Integration:** Seamlessly connects with your Nextcloud for image input, music input, and saving the final video.
*   **Background Music:** Randomly selects background music and fades it out smoothly as the video ends.
*   **Matrix Bot Control:**
    *   Receive automatic notifications (success/failure) in a Matrix chat room.
    *   Trigger video generation manually with a simple `!rebuild` command.
    *   Check the bot's status and access help commands directly from Matrix.
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
  localhost/mcf-notices-builder:latest
```
    *   `-d`: Runs the container in detached mode (in the background).
    *   `--name notices-automation`: Assigns a memorable name to your container.
    *   `--restart always`: Ensures the container automatically restarts if it stops or the system reboots.
    *   `--env-file .env`: Mounts your `.env` file into the container for configuration.
    *   `localhost/mcf-notices-builder:latest`: Specifies the image to run.

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
  localhost/mcf-notices-builder:latest
```
    The options are the same as for Podman.

### Using Docker Compose (Recommended for Docker Users)

For Docker users, `docker-compose` simplifies the management of your container. Create a `docker-compose.yml` file in your project root with the following content:

```yaml
version: '3.8'

services:
  notices-automation:
    image: localhost/mcf-notices-builder:latest
    container_name: notices-automation
    restart: always
    env_file:
      - .env
    # If you need to mount local folders for images/music, uncomment and adjust these:
    # volumes:
    #   - ./images:/app/images
    #   - ./music:/app/music
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
### Management Commands

Once your container is running, here are some useful commands:

*   **Restart Bot:** If you make changes to your `.env` file or wish to reset the bot:
    ```bash
podman restart notices-automation
# OR
docker restart notices-automation
```
## Matrix Bot Usage

Your automation bot will send notifications and respond to commands in the Matrix room you configured.

*   **View Bot Status:** Send `!status` in the Matrix chat room to check if the bot is online.
*   **Manual Video Generation:** Send `!rebuild` in the Matrix chat room to immediately trigger the video generation process. The bot will notify you when it starts and finishes.
*   **Get Help:** Send `!help` in the Matrix chat room to see a list of available commands.

## Configuration

All aspects of the slideshow automation are configured via environment variables. You must create a `.env` file in the same directory as your `flake.nix` (or where you run your container commands) and fill it with your specific settings. Refer to the `.env.sample` file for a template.

| Variable Name            | Description                                                                                             | Default Value   |
| :----------------------- | :------------------------------------------------------------------------------------------------------ | :-------------- |
| `IMAGE_DURATION`         | Sets how long (in seconds) each individual image remains on screen in the slideshow.                    | `10`            |
| `TARGET_VIDEO_DURATION`  | Defines the desired total length of the final video in seconds. The slideshow will repeat to meet this duration. | `600` (`10 min`)| 
| `IMAGE_FOLDER`           | Specifies the local directory where the automation should look for source image files.                  | `images/`       |
| `OUTPUT_FILEPATH`        | The full local path, including filename (e.g., `/videos/output.mp4`), where the generated video will be saved. If left empty, and `UPLOAD_NEXTCLOUD_PATH` is set, a temporary file is used for generation. | (None)          |
| `NEXTCLOUD_URL`          | The base URL of your Nextcloud instance (e.g., `https://your.nextcloud.com`). Required for Nextcloud integration. | (None)          |
| `NEXTCLOUD_USERNAME`     | Your Nextcloud username for authentication. Required for Nextcloud integration.                         | (None)          |
| `NEXTCLOUD_PASSWORD`     | Your Nextcloud password for authentication. Required for Nextcloud integration.                         | (None)          |
| `NEXTCLOUD_IMAGE_PATH`   | The path within your Nextcloud instance where source image files are located (e.g., `Photos/Slideshow/`). | (None)          |
| `UPLOAD_NEXTCLOUD_PATH`  | The path within your Nextcloud instance where the final generated video should be uploaded (e.g., `Videos/Generated/`). | (None)          |
| `NEXTCLOUD_INSECURE_SSL` | Set to `true` if your Nextcloud instance uses a self-signed or invalid SSL certificate and you wish to proceed anyway. Use with extreme caution. | `false`         |
| `APPEND_VIDEO_PATH`      | The path to an additional video file to be appended after the main slideshow. Can be a local path or a Nextcloud path (if `APPEND_VIDEO_SOURCE` is `nextcloud`). | (None)          |
| `APPEND_VIDEO_SOURCE`    | Specifies where the `APPEND_VIDEO_PATH` refers to: `local` for a local file, or `nextcloud` for a file on your Nextcloud. | `local`         |
| `MUSIC_FOLDER`           | The local directory where background music files are stored.                                            | `images/`       |
| `MUSIC_SOURCE`           | Specifies where the automation should find background music files: `local` for a local folder, or `nextcloud` for a Nextcloud path. | `local`         |
| `MATRIX_HOMESERVER`      | The URL of your Matrix homeserver (e.g., `https://matrix.org`). Required for Matrix bot functionality. | (None)          |
| `MATRIX_ACCESS_TOKEN`    | An access token for your Matrix bot user. This token *must* have sufficient permissions (read/write to the room, send messages). Essential for Matrix bot. | (None)          |
| `MATRIX_ROOM_ID`         | The internal ID of the Matrix room where the bot will operate. This is often a string like `!roomid:homeserver.com`. Required for Matrix bot. | (None)          |
| `MATRIX_USER_ID`         | The full Matrix user ID of your bot (e.g., `@botname:yourhomeserver.com`). Required for Matrix bot.    | (None)          |
| `CRON_SCHEDULE`          | A cron expression that defines the schedule for automatic video generation. For example, `0 1 * * 5` means "every Friday at 1:00 AM". | `0 1 * * 5`     |
