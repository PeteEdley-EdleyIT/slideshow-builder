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
        Initializes the Config object by loading all relevant environment variables.
        """
        # Slideshow Settings
        self.image_duration = get_env_int("IMAGE_DURATION", 10)
        self.target_video_duration = get_env_int("TARGET_VIDEO_DURATION", 600)
        
        # Hardcoded container paths for local files
        self.image_folder = "/app/images"
        self.output_folder = "/app/output"
        # Default to container path, but allow override (e.g. for Nextcloud path)
        self.music_folder = get_env_var("MUSIC_FOLDER", "/app/music")
        self.output_filepath = "/app/output/slideshow.mp4"
        
        # Nextcloud Configuration
        self.nc_url = get_env_var("NEXTCLOUD_URL")
        self.nc_user = get_env_var("NEXTCLOUD_USERNAME")
        self.nc_pass = get_env_var("NEXTCLOUD_PASSWORD")
        self.nc_image_path = get_env_var("NEXTCLOUD_IMAGE_PATH") # Deprecated, use nextcloud_image_path
        self.nextcloud_image_path = self.nc_image_path
        self.nc_upload_path = get_env_var("NEXTCLOUD_UPLOAD_PATH") # Deprecated, use upload_nextcloud_path
        self.upload_nextcloud_path = self.nc_upload_path
        self.nc_insecure = get_env_bool("NEXTCLOUD_INSECURE_SSL", False)
        
        # Source Selection (auto-detect based on Nextcloud config, or use explicit setting)
        # If NEXTCLOUD_IMAGE_PATH is set, default to nextcloud, otherwise local
        self.image_source = get_env_var("IMAGE_SOURCE", "nextcloud" if self.nextcloud_image_path else "local")
        self.music_source = get_env_var("MUSIC_SOURCE", "nextcloud" if self.nextcloud_image_path else "local")
        
        # Append Video Configuration
        self.append_video_path = get_env_var("APPEND_VIDEO_PATH")
        self.append_video_source = get_env_var("APPEND_VIDEO_SOURCE", "nextcloud" if self.append_video_path and self.nc_url else "local")
        
        # Matrix Bot Configuration
        self.matrix_homeserver = get_env_var("MATRIX_HOMESERVER")
        self.matrix_token = get_env_var("MATRIX_ACCESS_TOKEN")
        self.matrix_room = get_env_var("MATRIX_ROOM_ID")
        self.matrix_user_id = get_env_var("MATRIX_USER_ID")
        
        # ntfy Notification Configuration
        self.ntfy_url = get_env_var("NTFY_URL")
        self.ntfy_topic = get_env_var("NTFY_TOPIC")
        self.ntfy_token = get_env_var("NTFY_TOKEN")
        self.enable_heartbeat_ntfy = get_env_bool("ENABLE_HEARTBEAT_NTFY", True) # Specifically for health alerts
        self.enable_ntfy = get_env_bool("ENABLE_NTFY", True)
        
        # Scheduling & Health
        self.cron_schedule = get_env_var("CRON_SCHEDULE", "0 1 * * 5")
        self.enable_heartbeat = get_env_bool("ENABLE_HEARTBEAT", True)
        
        # Timer Overlay Configuration
        self.enable_timer = get_env_bool("ENABLE_TIMER", False)
        self.timer_minutes = get_env_int("TIMER_MINUTES", 5)
        self.timer_position = get_env_var("TIMER_POSITION", "auto")
