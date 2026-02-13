"""
Bot Interface Module for formatting Matrix bot messages.

This module encapsulates all the logic for creating user-friendly 
plain text and HTML messages for the Matrix bot, keeping the 
main controller logic clean and focused.
"""

from version import __version__
from nextcloud_client import NextcloudClient
from settings_manager import get_settings_manager

class BotInterface:
    """
    Generates formatted messages for the Matrix bot.
    """

    @staticmethod
    def format_status(stats, config):
        """
        Formats the !status response.
        """
        status_msg = (
            "🤖 **Slideshow Bot Status**\n"
            f"🏷️ **Version**: {__version__}\n"
            f"⏱️ **Uptime**: {stats['uptime']}\n"
            f"✅ **Last Success**: {stats['last_success']}\n"
            f"💓 **Heartbeat Active**: {'Yes' if stats['heartbeat_active'] else 'No'}\n"
        )
        
        # Show active task if something is running
        if stats.get('active_stage'):
            task = stats.get('active_task', 'Processing')
            progress = stats.get('progress', 0)
            start_time = stats.get('job_start_time', 'Unknown')
            
            status_msg += f"\n🚀 **Current Activity**: {stats['active_stage']}\n"
            status_msg += f"📅 **Started At**: {start_time}\n"
            status_msg += f"📝 **Task**: {task}\n"
            if progress > 0:
                # Simple progress bar
                bars = progress // 10
                progress_bar = "▓" * bars + "░" * (10 - bars)
                status_msg += f"📊 **Progress**: [{progress_bar}] {progress}%\n"
        
        # Quick Nextcloud Connectivity Check
        if config.nc_url and config.nc_user:
            try:
                # We use a short timeout for the check
                NextcloudClient(
                    config.nc_url, 
                    config.nc_user, 
                    config.nc_pass, 
                    verify_ssl=not config.nc_insecure
                )
                status_msg += "☁️ **Nextcloud**: Connected\n"
            except Exception:
                status_msg += "☁️ **Nextcloud**: ❌ Connection Failed\n"
        
        return status_msg

    @staticmethod
    def format_full_config(config):
        """
        Formats the !get all response with categorized settings and emojis.
        """
        settings_mgr = get_settings_manager()
        overrides = settings_mgr.list_all()
        
        lines = ["📋 **Full Configuration Status**\n"]
        html_lines = ["<h3>📋 Full Configuration Status</h3>"]
        
        for category, keys in config.CONFIG_GROUPS.items():
            lines.append(f"\n{category}")
            cat_name = category.replace("**", "")
            html_lines.append(f"<h4>{cat_name}</h4>")
            
            for key in keys:
                if key is None:
                    lines.append("")
                    html_lines.append("<br/>")
                    continue
                    
                value = getattr(config, key.lower(), "Not set")
                is_override = key in overrides
                marker = "🔹" if is_override else "▫️"
                status = "(Override)" if is_override else "(Default)"
                
                # Plain text version
                lines.append(f"{marker} {key}: {value} {status}")
                
                # HTML version
                color = "blue" if is_override else "green"
                html_lines.append(
                    f"{marker} <font color='{color}'><b>{key}</b></font>: {value} <i>{status}</i><br/>"
                )
        
        lines.append("\n\n🔹 = Runtime Override active")
        lines.append("▫️ = Using .env/calculated default")
        
        html_lines.append("<p><br/>🔹 = <font color='blue'>Runtime Override active</font><br/>")
        html_lines.append("▫️ = <font color='green'>Using .env/calculated default</font></p>")
        
        return "\n".join(lines), "".join(html_lines)

    @staticmethod
    def format_help(config):
        """
        Formats the !help response with categorized settings in columns.
        """
        # Build Plain Text Help
        help_text = (
            "🤖 **Slideshow Bot Help**\n\n"
            "**🚀 Automation:**\n"
            "• `!rebuild` - Trigger a manual video generation\n"
            "• `!status` - Check the bot's health and uptime\n\n"
            "**⚙️ Configuration:**\n"
            "• `!set KEY VALUE` - Override a setting\n"
            "• `!get KEY` - View current value of a setting\n"
            "• `!get all` - View all settings and status\n"
            "• `!config` - List active overrides\n"
            "• `!defaults` - Reset all to .env defaults\n\n"
            "**❓ General:**\n"
            "• `!help` - Show this message\n\n"
            "**📝 Configurable Settings:**\n"
        )
        
        for category, keys in config.CONFIG_GROUPS.items():
            valid_keys = [k for k in keys if k is not None]
            help_text += f"\n{category}\n"
            help_text += ", ".join([f"`{k}`" for k in valid_keys]) + "\n"

        # Build HTML Help
        settings_html = ""
        for category, keys in config.CONFIG_GROUPS.items():
            valid_keys = [k for k in keys if k is not None]
            cat_name = category.replace("**", "")
            settings_html += f"<h4>{cat_name}</h4>"
            settings_html += "<table style='width:100%'>"
            for i in range(0, len(valid_keys), 2):
                col1 = valid_keys[i]
                col2 = valid_keys[i+1] if i+1 < len(valid_keys) else ""
                settings_html += f"<tr><td><code>{col1}</code></td><td>{f'<code>{col2}</code>' if col2 else ''}</td></tr>"
            settings_html += "</table>"

        html_help = (
            "<h3>🤖 Slideshow Bot Help</h3>"
            "<h4>🚀 Automation</h4>"
            "<ul>"
            "<li><code>!rebuild</code> - Trigger a manual video generation</li>"
            "<li><code>!status</code> - Check the bot's health and uptime</li>"
            "</ul>"
            "<h4>⚙️ Configuration</h4>"
            "<ul>"
            "<li><code>!set KEY VALUE</code> - Override a configuration setting</li>"
            "<li><code>!get KEY</code> - View current value of a setting</li>"
            "<li><code>!get all</code> - View all settings and their status</li>"
            "<li><code>!config</code> - List only active configuration overrides</li>"
            "<li><code>!defaults</code> - Reset all settings to .env defaults</li>"
            "</ul>"
            "<h4>❓ General</h4>"
            "<ul>"
            "<li><code>!help</code> - Show this message</li>"
            "</ul>"
            "<h4>📝 Configurable Settings</h4>"
            f"{settings_html}"
        )
        
        return help_text, html_help
