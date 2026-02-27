"""
Configuration management for the Video Slideshow Automation.

This module provides utility functions for retrieving environment variables
with proper stripping and type conversion, and a `Config` class to centralize
all application settings. Configuration values can be overridden at runtime
via the settings database.
"""

import os
from settings_manager import get_settings_manager

def get_env_var(name, default=None, required=False):
    """
    Retrieves a configuration value, checking the database first, then environment variables.
    
    This function enables runtime configuration changes via Matrix commands.
    Priority: Database override > Environment variable > Default value

    Args:
        name (str): The name of the configuration variable.
        default (str, optional): The default value if the variable is not set. Defaults to None.
        required (bool, optional): If True, raises a ValueError if the variable is not set
                                   and no default is provided. Defaults to False.

    Returns:
        str: The value of the configuration variable, or the default value.

    Raises:
        ValueError: If `required` is True and the variable is not set.
    """
    # Check database first for runtime overrides
    settings = get_settings_manager()
    db_value = settings.get(name)
    
    if db_value is not None:
        value = db_value
    else:
        # Fall back to environment variable
        value = os.getenv(name, default)
    
    if value is not None:
        # Strip potential quotes from environment variable values
        value = value.strip().strip('"').strip("'")
    if required and value is None:
        raise ValueError(f"Configuration variable '{name}' is required but not set.")
    return value


def get_env_int(name, default):
    """
    Retrieves an environment variable as an integer, with a default fallback.

    Args:
        name (str): The name of the environment variable.
        default (int): The default integer value if the variable is not set or invalid.

    Returns:
        int: The integer value of the environment variable, or the default.
    """
    try:
        return int(get_env_var(name, default=str(default)))
    except (ValueError, TypeError):
        return default


def get_env_bool(name, default=False):
    """
    Retrieves an environment variable as a boolean, with a default fallback.

    Recognizes "true" (case-insensitive) as True, anything else as False.

    Args:
        name (str): The name of the environment variable.
        default (bool): The default boolean value if the variable is not set.

    Returns:
        bool: The boolean value of the environment variable, or the default.
    """
    return get_env_var(name, str(default)).lower() == "true"


class Config:
    """
    Loads and manages application configuration from environment variables.

    This class centralizes access to all configurable parameters, providing
    default values where necessary and type conversion (e.g., to int or bool).
    
    For local file operations, paths are hardcoded to standard container locations:
    - Images: /app/images
    - Output: /app/output
    - Music: /app/music
    
    Users mount volumes to these paths and use SOURCE variables to select local vs Nextcloud.
    """
    def __init__(self):
        """
        Initializes the Config object. Metadata for UI and groups is static.
        """
        # --- Metadata for Bot UI ---
        # Logical grouping of settings for !help and !get all
        self.CONFIG_GROUPS = {
            "⚙️ **General**": ["IMAGE_DURATION", "TARGET_VIDEO_DURATION", "CRON_SCHEDULE"],
            "☁️ **Nextcloud**": [
                "NEXTCLOUD_UPLOAD_PATH", 
                None,
                "IMAGE_SOURCE", 
                "NEXTCLOUD_IMAGE_PATH", 
                None,
                "MUSIC_SOURCE", 
                "MUSIC_FOLDER", 
                None,
                "APPEND_VIDEO_SOURCE", 
                "APPEND_VIDEO_PATH"
            ],
            "⏱️ **Timer Settings**": ["ENABLE_TIMER", "TIMER_MINUTES", "TIMER_POSITION"],
            "💓 **Heartbeat**": ["ENABLE_HEARTBEAT"],
            "🔔 **NTFY**": ["ENABLE_NTFY", "NTFY_TOPIC"]
        }
        
        # Flattened list for validation, filtering out spacers (None)
        self.CONFIGURABLE_SETTINGS = []
        for keys in self.CONFIG_GROUPS.values():
            self.CONFIGURABLE_SETTINGS.extend([k for k in keys if k is not None])

        # Hardcoded container paths - these do not change at runtime
        self.image_folder = "/app/images"
        self.output_folder = "/app/output"
        self.output_filepath = "/app/output/slideshow.mp4"

    @property
    def images_folder(self):
        """Alias for image_folder used by VideoEngine."""
        return self.image_folder

    # --- Dynamic Properties ---
    # These call get_env_var/int/bool every time, ensuring hot-reloading from DB

    @property
    def image_duration(self):
        return get_env_int("IMAGE_DURATION", 10)

    @property
    def target_video_duration(self):
        return get_env_int("TARGET_VIDEO_DURATION", 600)

    @property
    def music_folder(self):
        return get_env_var("MUSIC_FOLDER", "/app/music")

    @property
    def nc_url(self):
        return get_env_var("NEXTCLOUD_URL")

    @property
    def nc_user(self):
        return get_env_var("NEXTCLOUD_USERNAME")

    @property
    def nc_pass(self):
        return get_env_var("NEXTCLOUD_PASSWORD")

    @property
    def nextcloud_image_path(self):
        return get_env_var("NEXTCLOUD_IMAGE_PATH")

    @property
    def upload_nextcloud_path(self):
        return get_env_var("NEXTCLOUD_UPLOAD_PATH")

    @property
    def nc_insecure(self):
        return get_env_bool("NEXTCLOUD_INSECURE_SSL", False)

    @property
    def image_source(self):
        return get_env_var("IMAGE_SOURCE", "nextcloud" if self.nextcloud_image_path else "local")

    @property
    def music_source(self):
        return get_env_var("MUSIC_SOURCE", "nextcloud" if self.nextcloud_image_path else "local")

    @property
    def append_video_path(self):
        return get_env_var("APPEND_VIDEO_PATH")

    @property
    def append_video_source(self):
        return get_env_var("APPEND_VIDEO_SOURCE", "nextcloud" if self.append_video_path and self.nc_url else "local")

    @property
    def matrix_homeserver(self):
        return get_env_var("MATRIX_HOMESERVER")

    @property
    def matrix_token(self):
        return get_env_var("MATRIX_ACCESS_TOKEN")

    @property
    def matrix_room(self):
        return get_env_var("MATRIX_ROOM_ID")

    @property
    def matrix_user_id(self):
        return get_env_var("MATRIX_USER_ID")

    @property
    def ntfy_url(self):
        return get_env_var("NTFY_URL")

    @property
    def ntfy_topic(self):
        return get_env_var("NTFY_TOPIC")

    @property
    def ntfy_token(self):
        return get_env_var("NTFY_TOKEN")

    @property
    def enable_heartbeat_ntfy(self):
        return get_env_bool("ENABLE_HEARTBEAT_NTFY", True)

    @property
    def enable_ntfy(self):
        return get_env_bool("ENABLE_NTFY", True)

    @property
    def cron_schedule(self):
        return get_env_var("CRON_SCHEDULE", "0 1 * * 5")

    @property
    def enable_heartbeat(self):
        return get_env_bool("ENABLE_HEARTBEAT", True)

    @property
    def enable_timer(self):
        return get_env_bool("ENABLE_TIMER", False)

    @property
    def timer_minutes(self):
        return get_env_int("TIMER_MINUTES", 5)

    @property
    def timer_position(self):
        return get_env_var("TIMER_POSITION", "auto")
