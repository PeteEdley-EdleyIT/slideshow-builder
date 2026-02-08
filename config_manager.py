"""
Configuration management for the Video Slideshow Automation.

This module provides utility functions for retrieving environment variables
with proper stripping and type conversion, and a `Config` class to centralize
all application settings.
"""

import os

def get_env_var(name, default=None, required=False):
    """
    Retrieves an environment variable, strips quotes, and handles default values.

    Args:
        name (str): The name of the environment variable.
        default (str, optional): The default value if the variable is not set. Defaults to None.
        required (bool, optional): If True, raises a ValueError if the variable is not set
                                   and no default is provided. Defaults to False.

    Returns:
        str: The value of the environment variable, or the default value.

    Raises:
        ValueError: If `required` is True and the variable is not set.
    """
    value = os.getenv(name, default)
    if value is not None:
        # Strip potential quotes from environment variable values
        value = value.strip().strip('"').strip("'")
    if required and value is None:
        raise ValueError(f"Environment variable '{name}' is required but not set.")
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
    """
    def __init__(self):
        """
        Initializes the Config object by loading all relevant environment variables.
        """
        # Slideshow Settings
        self.image_duration = get_env_int("IMAGE_DURATION", 10)
        self.target_video_duration = get_env_int("TARGET_VIDEO_DURATION", 600)
        self.image_folder = get_env_var("IMAGE_FOLDER", "images/")
        self.output_filepath = get_env_var("OUTPUT_FILEPATH")
        
        # Nextcloud Configuration
        self.nc_url = get_env_var("NEXTCLOUD_URL")
        self.nc_user = get_env_var("NEXTCLOUD_USERNAME")
        self.nc_pass = get_env_var("NEXTCLOUD_PASSWORD")
        self.nc_image_path = get_env_var("NEXTCLOUD_IMAGE_PATH")
        self.nc_upload_path = get_env_var("UPLOAD_NEXTCLOUD_PATH")
        self.nc_insecure = get_env_bool("NEXTCLOUD_INSECURE_SSL", False)
        
        # Append Video Configuration
        self.append_video_path = get_env_var("APPEND_VIDEO_PATH")
        self.append_video_source = get_env_var("APPEND_VIDEO_SOURCE", "local")
        
        # Matrix Bot Configuration
        self.matrix_homeserver = get_env_var("MATRIX_HOMESERVER")
        self.matrix_token = get_env_var("MATRIX_ACCESS_TOKEN")
        self.matrix_room = get_env_var("MATRIX_ROOM_ID")
        self.matrix_user_id = get_env_var("MATRIX_USER_ID")
        
        # ntfy Notification Configuration
        self.ntfy_url = get_env_var("NTFY_URL")
        self.ntfy_topic = get_env_var("NTFY_TOPIC")
        self.ntfy_token = get_env_var("NTFY_TOKEN")
        self.enable_ntfy = get_env_bool("ENABLE_HEARTBEAT_NTFY", True) # Specifically for health alerts
        self.enable_automation_ntfy = get_env_bool("ENABLE_NTFY", True)
        
        # Scheduling & Health
        self.cron_schedule = get_env_var("CRON_SCHEDULE", "0 1 * * 5")
        self.enable_heartbeat = get_env_bool("ENABLE_HEARTBEAT", True)
