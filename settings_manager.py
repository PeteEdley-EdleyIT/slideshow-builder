"""
Settings Manager for persistent runtime configuration.

This module provides a database-backed settings store that allows runtime
configuration changes via Matrix commands. Settings are stored in a SQLite
database and persist across container restarts when mounted as a volume.
"""

import os
from peewee import SqliteDatabase, Model, CharField, TextField, DoesNotExist

# Database configuration - hardcoded to /data for container use
DB_DIR = "/data"
DB_PATH = os.path.join(DB_DIR, "settings.db")

# Initialize database
db = SqliteDatabase(DB_PATH)


class Setting(Model):
    """
    Model representing a single configuration setting.
    
    Attributes:
        key (str): The setting name (unique).
        value (str): The setting value (stored as text).
    """
    key = CharField(unique=True, primary_key=True)
    value = TextField()

    class Meta:
        database = db


class SettingsManager:
    """
    Manages persistent runtime configuration settings.
    
    This class provides methods to get, set, delete, and list configuration
    settings stored in a SQLite database. It handles database initialization
    and provides a clean interface for runtime configuration management.
    """
    
    def __init__(self):
        """
        Initializes the SettingsManager and ensures the database is ready.
        """
        self._ensure_db()
    
    def _ensure_db(self):
        """
        Ensures the database directory exists and tables are created.
        """
        # Create data directory if it doesn't exist
        os.makedirs(DB_DIR, exist_ok=True)
        
        # Connect and create tables
        db.connect(reuse_if_open=True)
        db.create_tables([Setting], safe=True)
    
    def get(self, key, default=None):
        """
        Retrieves a setting value from the database.
        
        Args:
            key (str): The setting key to retrieve.
            default (str, optional): Default value if the key doesn't exist.
        
        Returns:
            str: The setting value, or the default if not found.
        """
        try:
            setting = Setting.get(Setting.key == key)
            return setting.value
        except DoesNotExist:
            return default
    
    def set(self, key, value):
        """
        Sets a setting value in the database.
        
        Args:
            key (str): The setting key to set.
            value (str): The value to store.
        
        Returns:
            bool: True if successful.
        """
        Setting.replace(key=key, value=str(value)).execute()
        return True
    
    def delete(self, key):
        """
        Deletes a setting from the database.
        
        Args:
            key (str): The setting key to delete.
        
        Returns:
            bool: True if the setting was deleted, False if it didn't exist.
        """
        deleted = Setting.delete().where(Setting.key == key).execute()
        return deleted > 0
    
    def reset_all(self):
        """
        Deletes all settings from the database.
        
        This effectively resets all configuration to .env defaults.
        
        Returns:
            int: The number of settings deleted.
        """
        count = Setting.delete().execute()
        return count
    
    def list_all(self):
        """
        Lists all settings currently stored in the database.
        
        Returns:
            dict: A dictionary of all settings (key: value pairs).
        """
        settings = {}
        for setting in Setting.select():
            settings[setting.key] = setting.value
        return settings
    
    def close(self):
        """
        Closes the database connection.
        """
        if not db.is_closed():
            db.close()


# Global instance for easy access
_settings_manager = None


def get_settings_manager():
    """
    Returns the global SettingsManager instance.
    
    Returns:
        SettingsManager: The global settings manager instance.
    """
    global _settings_manager
    if _settings_manager is None:
        _settings_manager = SettingsManager()
    return _settings_manager
