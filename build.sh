#!/usr/bin/env bash
set -e

# Usage: ./build.sh [--deploy]

# Default to not deploying
DEPLOY=false

# Check for deploy flag
for arg in "$@"; do
    if [[ "$arg" == "--deploy" ]] || [[ "$arg" == "deploy" ]]; then
        DEPLOY=true
    fi
done

echo "🔨 Building Docker image with Nix..."
# Build the image defined in flake.nix
nix build .#dockerImage

if [ "$DEPLOY" = true ]; then
    echo "📦 Deploying locally..."

    echo "  Loading image into Podman..."
    # Load the built image (results symlinked to ./result)
    podman load -i result

    # Check if a container with the name 'notices-automation' already exists
    if podman container exists notices-automation; then
        echo "  Stopping existing container..."
        podman stop notices-automation || true # Don't fail if already stopped
        echo "  Removing existing container..."
        podman rm notices-automation
    fi

    echo "  Starting new container..."
    # Run the container with the standard configuration
    # - restart always: auto-restart on failure/boot
    # - env-file .env: load configuration
    # - v notices-data:/data: persist database/keys/files
    # Prepare volume mounts
    MOUNT_ARGS="-v notices-data:/data"

    if [ -d "$(pwd)/images" ]; then
        echo "  Mounting local ./images..."
        MOUNT_ARGS="$MOUNT_ARGS -v $(pwd)/images:/app/images"
    fi
    
    if [ -d "$(pwd)/music" ]; then
        echo "  Mounting local ./music..."
        MOUNT_ARGS="$MOUNT_ARGS -v $(pwd)/music:/app/music"
    fi

    podman run -d \
      --name notices-automation \
      --restart always \
      --env-file .env \
      $MOUNT_ARGS \
      localhost/slideshow-builder:latest

    echo "✅ Deployment complete."
    echo "  Logs:   podman logs -f notices-automation"
    echo "  Status: Check via Matrix (!status) or 'podman ps'"
else
    echo "✅ Build complete. Result linked in ./result"
    echo "To deploy, run: ./build.sh --deploy"
fi
