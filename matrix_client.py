import requests
import json
import logging

class MatrixClient:
    def __init__(self, homeserver_url, access_token, room_id):
        """
        Initialize the Matrix client.
        
        :param homeserver_url: The base URL of the Matrix homeserver (e.g., https://matrix.org)
        :param access_token: The access token for the bot/user account
        :param room_id: The ID of the room to send messages to (e.g., !roomid:example.com)
        """
        self.homeserver_url = homeserver_url.rstrip('/') if homeserver_url else None
        self.access_token = access_token
        self.room_id = room_id
        self.headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        } if self.access_token else {}

    def is_configured(self):
        return bool(self.homeserver_url and self.access_token and self.room_id)

    def send_message(self, message, html_message=None):
        """
        Send a message to the configured Matrix room.
        
        :param message: The plain text message
        :param html_message: Optional HTML formatted message
        """
        if not self.is_configured():
            print("Matrix configuration missing or incomplete. Skipping notification.")
            return False

        # In Matrix v3, the endpoint includes a transaction ID which should be unique.
        # However, for simplicity, we can just use a timestamp or a random string.
        # Or even better, just use the endpoint that doesn't strictly require it if possible,
        # but usually it's /send/m.room.message/{txnId}
        import time
        txn_id = int(time.time() * 1000)
        url = f"{self.homeserver_url}/_matrix/client/v3/rooms/{self.room_id}/send/m.room.message/{txn_id}"
        
        payload = {
            "msgtype": "m.text",
            "body": message
        }
        
        if html_message:
            payload["format"] = "org.matrix.custom.html"
            payload["formatted_body"] = html_message

        try:
            response = requests.put(url, headers=self.headers, data=json.dumps(payload))
            response.raise_for_status()
            return True
        except Exception as e:
            print(f"Failed to send Matrix notification: {e}")
            if hasattr(e, 'response') and e.response is not None:
                print(f"Response content: {e.response.text}")
            return False

    def send_success(self, video_name, slide_list):
        """
        Send a success notification.
        """
        slides_str = "\n".join([f"- {s}" for s in slide_list])
        message = f"✅ Slideshow produced successfully!\nVideo: {video_name}\nIncluded slides:\n{slides_str}"
        
        slides_html = "".join([f"<li>{s}</li>" for s in slide_list])
        html_message = (
            f"<h3>✅ Slideshow produced successfully!</h3>"
            f"<p><b>Video:</b> {video_name}</p>"
            f"<p><b>Included slides:</b></p>"
            f"<ul>{slides_html}</ul>"
        )
        
        return self.send_message(message, html_message)

    def send_failure(self, error_message, traceback_str=None):
        """
        Send a failure notification.
        """
        message = f"❌ Slideshow production failed!\nError: {error_message}"
        if traceback_str:
            message += f"\n\nDetails:\n{traceback_str}"
            
        html_message = (
            f"<h3>❌ Slideshow production failed!</h3>"
            f"<p><font color='red'><b>Error:</b> {error_message}</font></p>"
        )
        if traceback_str:
            html_message += f"<p><b>Details:</b></p><pre><code>{traceback_str}</code></pre>"
            
        return self.send_message(message, html_message)
