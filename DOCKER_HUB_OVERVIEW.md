# Video Slideshow Automation

**Automate the creation of dynamic video slideshows from your images and music, with seamless Nextcloud integration and Matrix bot control.**

This project provides a robust, containerized solution for generating engaging video slideshows on a schedule or on demand. Perfect for digital signage, community announcements, or personal media projects, it offers flexible media sourcing, customizable video output, and interactive management via Matrix chat.

## Key Features:

*   **Automated & Scheduled Video Generation:** Set it and forget it, or trigger manually.
*   **Flexible Media Sources:** Pull images and background music from local folders or Nextcloud.
*   **Customizable Output:** Control image display duration, total video length, and append additional video content.
*   **Smart Image Ordering:** Ensures your content flows logically.
*   **Nextcloud Integration:** Effortlessly syncs with your Nextcloud instance for media management.
*   **Interactive Matrix Bot:** Receive notifications, trigger builds, and check status directly from your Matrix chat room.
*   **Containerized Deployment:** Easy to deploy and manage using Podman or Docker.

## Get Started:

To quickly get the automation running, follow these steps. For full details on configuration and advanced usage, please refer to the comprehensive `README.md` in the project's GitHub repository.

1.  **Create your `.env` file:**
    Review the `README.md` for a list of environment variables and create a `.env` file in your project root. A `.env.sample` is provided as a guide.

2.  **Run the Container:**

    **With Podman:**
    ```bash
    podman pull pedley/slideshow-builder:latest
    podman run -d --name notices-automation --restart always --env-file .env pedley/slideshow-builder:latest
    ```

    **With Docker:**
    ```bash
    docker pull pedley/slideshow-builder:latest
    docker run -d --name notices-automation --restart always --env-file .env pedley/slideshow-builder:latest
    ```

    **Using Docker Compose (Recommended for Docker Users):**
    Create a `docker-compose.yml` file:
    ```yaml
    version: '3.8'
    services:
      notices-automation:
        image: pedley/slideshow-builder:latest
        container_name: notices-automation
        restart: always
        env_file:
          - .env
        # volumes:
        #   - ./images:/app/images
        #   - ./music:/app/music
    ```
    Then run:
    ```bash
    docker-compose up -d
    ```

For detailed configuration options, Matrix bot commands, and advanced deployment scenarios, please see the [full README.md](Link to your GitHub README.md here).