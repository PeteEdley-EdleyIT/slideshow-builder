import os
import logging
import asyncio
from nio import AsyncClient, RoomMessageText, MegolmEvent, AsyncClientConfig, RoomKeyRequest, KeyVerificationEvent, KeyVerificationCancel, ToDeviceMessage
import time

class MatrixClient:
    def __init__(self, homeserver_url, access_token, room_id, user_id=None, store_path="matrix_store"):
        """
        Initialize the Matrix client using matrix-nio.
        
        :param homeserver_url: The base URL of the Matrix homeserver (e.g., https://matrix.org)
        :param access_token: The access token for the bot/user account
        :param room_id: The ID of the room to send messages to (e.g., !roomid:example.com)
        :param user_id: The full Matrix ID of the bot (e.g., @bot:example.com)
        :param store_path: Directory to store encryption keys (for E2EE)
        """
        self.homeserver_url = homeserver_url.rstrip('/') if homeserver_url else None
        self.access_token = access_token
        self.room_id = room_id
        self.user_id = user_id
        self.store_path = store_path
        self.client = None

    def is_configured(self):
        return bool(self.homeserver_url and self.access_token and self.room_id)

    async def _ensure_client(self):
        if self.client is None:
            # Create store path if it doesn't exist
            if self.store_path and not os.path.exists(self.store_path):
                os.makedirs(self.store_path)

            # Configure client with encryption ENABLED
            client_config = AsyncClientConfig(
                encryption_enabled=True,
                store_sync_tokens=True
            )
            self.client = AsyncClient(
                self.homeserver_url, 
                self.user_id or "", 
                ssl=True,
                store_path=self.store_path,
                config=client_config
            )
            self.client.access_token = self.access_token
            if self.user_id:
                self.client.user_id = self.user_id
            


    async def send_message(self, message, html_message=None):
        """
        Send a message to the configured Matrix room using matrix-nio.
        """
        if not self.is_configured():
            print("Matrix configuration missing or incomplete. Skipping notification.")
            return False

        try:
            await self._ensure_client()
            
            content = {
                "msgtype": "m.text",
                "body": message
            }
            
            if html_message:
                content["format"] = "org.matrix.custom.html"
                content["formatted_body"] = html_message

            response = await self.client.room_send(
                room_id=self.room_id,
                message_type="m.room.message",
                content=content,
                ignore_unverified_devices=True
            )
            
            # Check if response is successful
            from nio import RoomSendResponse
            if isinstance(response, RoomSendResponse):
                return True
            else:
                print(f"Failed to send Matrix notification: {response}")
                return False
                
        except Exception as e:
            print(f"Error in MatrixClient.send_message: {e}")
            return False
        finally:
            # We don't close the client here as it might be reused.
            # In a daemon, we might want to keep it open.
            pass

    async def send_success(self, video_name, slide_list):
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
        
        return await self.send_message(message, html_message)

    async def send_failure(self, error_message, traceback_str=None):
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
            
        return await self.send_message(message, html_message)

    def add_message_callback(self, callback):
        """
        Add a callback for incoming messages.
        The callback should be an async function taking (room, event).
        """
        self._message_callback = callback

    async def _on_message(self, room_id, event):
        print(f"DEBUG: Received event type {type(event).__name__} from {event.sender}")
        print(f"DEBUG: Comparing sender '{event.sender}' with bot ID '{self.client.user_id}'")
        # Ignore our own messages
        if event.sender == self.client.user_id:
            print("DEBUG: Ignoring our own message.")
            return

        print(f"DEBUG: Received Matrix event in room {room_id} (Target: {self.room_id}) from {event.sender}: {event.body}")
        if room_id == self.room_id:
            if hasattr(self, '_message_callback') and self._message_callback:
                # We pass the room_id string as the first argument to the callback
                await self._message_callback(room_id, event)
        else:
            print(f"DEBUG: Event ignored (wrong room)")

    async def listen_forever(self):
        """
        Start a manual sync loop to listen for events.
        """
        if not self.is_configured():
            print("Matrix configuration missing. Cannot listen.")
            return

        await self._ensure_client()

        # Auto-detect device ID and initialize crypto
        try:
            whoami_resp = await self.client.whoami()
            if hasattr(whoami_resp, 'device_id') and whoami_resp.device_id:
                self.client.device_id = whoami_resp.device_id
        except Exception as e:
            print(f"Error detecting device ID: {e}")

        # Initial sync to load account and crypto store
        sync_resp = await self.client.sync(timeout=3000, full_state=True)
        
        # Load Olm machine for E2EE
        if self.client.device_id:
            try:
                self.client.load_store()
                if self.client.olm and not self.client.olm.account:
                    self.client.olm.load()
            except Exception as e:
                print(f"Error loading crypto: {e}")
        await self.client.join(self.room_id)
        
        # Send initialization message
        await self.send_message("🤖 Notices Bot is starting and listening for commands...")

        # Initial sync to get starting token
        sync_resp = await self.client.sync(timeout=30000)
        next_batch = sync_resp.next_batch
        
        print(f"Matrix bot listening for messages in {self.room_id} starting at {next_batch}...")
        
        while True:
            try:
                sync_resp = await self.client.sync(timeout=30000, since=next_batch)
                next_batch = sync_resp.next_batch
                
                # Process to-device events for E2EE
                if sync_resp.to_device_events:
                    for e in sync_resp.to_device_events:
                        pass  # Callbacks handle these automatically 

                # Process room events
                for room_id, room in sync_resp.rooms.join.items():
                    for event in room.timeline.events:
                        if isinstance(event, RoomMessageText):
                            await self._on_message(room_id, event)
                        elif isinstance(event, MegolmEvent):
                            # Encrypted message - auto-trust sender and request keys
                            try:
                                await self.client.sync(timeout=1000)
                                devices = list(self.client.device_store.active_user_devices(event.sender))
                                for device in devices:
                                    self.client.verify_device(device)
                                await self.client.request_room_key(event)
                            except Exception as e:
                                print(f"Failed to request encryption key: {e}")


                
            except Exception as e:
                import traceback
                print(f"Error in Matrix sync loop: {e}")
                traceback.print_exc()
                await asyncio.sleep(5)

    async def close(self):
        if self.client:
            await self.client.close()
            self.client = None
