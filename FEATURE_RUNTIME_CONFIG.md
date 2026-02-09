# Runtime Configuration Management Feature

## Overview
This feature allows users to override configuration settings at runtime via Matrix commands. All changes persist across container restarts and rebuilds when the `/data` directory is mounted as a volume.

## Implementation Details

### New Files
1. **`settings_manager.py`**: Manages persistent configuration storage using Peewee ORM and SQLite
   - Database location: `/data/settings.db` (hardcoded for container use)
   - Provides CRUD operations for configuration settings
   - Thread-safe singleton pattern for global access

### Modified Files
1. **`config_manager.py`**: Updated to check database first, then fall back to environment variables
   - Priority: Database override > Environment variable > Default value
   - Maintains backward compatibility with existing code

2. **`create_slideshow.py`**: Added Matrix commands for configuration management
   - `!set KEY VALUE` - Override a configuration setting
   - `!get KEY` - View current value of a setting
   - `!config` - List all active configuration overrides
   - `!defaults` - Reset all settings to .env defaults
   - `!help` - Updated to show new commands

3. **Documentation Updates**:
   - `GEMINI.md`: Updated deployment instructions and feature list
   - `README.md`: Added volume mount requirements and new commands
   - `DOCKER_HUB_OVERVIEW.md`: Updated quick start guide

## Configurable Settings
The following settings can be overridden at runtime:
- `IMAGE_DURATION`
- `TARGET_VIDEO_DURATION`
- `CRON_SCHEDULE`
- `IMAGE_SOURCE`
- `MUSIC_SOURCE`
- `NEXTCLOUD_IMAGE_PATH`
- `UPLOAD_NEXTCLOUD_PATH`
- `APPEND_VIDEO_PATH`
- `APPEND_VIDEO_SOURCE`
- `ENABLE_HEARTBEAT`
- `NTFY_TOPIC`
- `ENABLE_NTFY`
- `ENABLE_TIMER`
- `TIMER_MINUTES`
- `TIMER_POSITION`

## Usage Examples

### Via Matrix Commands
```
!set IMAGE_DURATION 15
!set CRON_SCHEDULE "0 2 * * 6"
!get IMAGE_DURATION
!config
!defaults
```

### Deployment
```bash
# Podman
podman run -d \
  --name notices-automation \
  --restart always \
  --env-file .env \
  -v notices-data:/data \
  localhost/slideshow-builder:latest

# Docker Compose
services:
  notices-automation:
    image: localhost/slideshow-builder:latest
    volumes:
      - notices-data:/data
```

## Testing
The implementation has been tested locally:
- Settings manager initialization ✓
- Database CRUD operations ✓
- Config manager integration ✓
- Override priority (DB > ENV > Default) ✓

## Notes
- Changes take effect on the next rebuild (not immediately)
- The `/data` volume must be mounted for persistence
- Settings are stored in SQLite for simplicity and reliability
- No additional dependencies required (Peewee already in flake.nix)
