"""
Matrix Client for sending notifications and handling interactive commands.

This module provides the `MatrixClient` class, which uses the `matrix-nio`
library to connect to a Matrix homeserver, send messages to a specific room,
and listen for incoming commands. It includes basic support for End-to-End
Encryption (E2EE) by automatically trusting devices and requesting room keys.
"""

import os
import logging
import asyncio
from nio import AsyncClient, RoomMessageText, MegolmEvent, AsyncClientConfig, RoomKeyRequest, KeyVerificationEvent, KeyVerificationCancel, ToDeviceMessage
import time

# Configure logging for matrix-nio to suppress excessive debug output
logging.getLogger("nio").setLevel(logging.WARNING)
logging.getLogger("asyncio").setLevel(logging.WARNING)


class MatrixClient:
    """
    A client for interacting with a Matrix instance using the matrix-nio library.

    This class facilitates sending messages (success/failure notifications)
    and listening for commands in a specified Matrix room. It supports
    End-to-End Encryption (E2EE) by managing device verification and key requests.

    Attributes:
        homeserver_url (str): The base URL of the Matrix homeserver.
        access_token (str): The access token for the bot's Matrix account.
        room_id (str): The ID of the Matrix room for communication.
        user_id (str): The full Matrix ID of the bot user.
        store_path (str): Local directory to store encryption keys and client data.
        client (AsyncClient): The underlying `matrix-nio` AsyncClient instance.
    """
    def __init__(self, homeserver_url, access_token, room_id, user_id=None, store_path="matrix_store"):
        """
        Initializes the Matrix client.

        Args:
            homeserver_url (str): The base URL of the Matrix homeserver (e.g., https://matrix.org).
            access_token (str): The access token for the bot/user account.
            room_id (str): The ID of the room to send messages to (e.g., !roomid:example.com).
            user_id (str, optional): The full Matrix ID of the bot (e.g., @bot:example.com).
                                     If None, it will attempt to derive it later.
            store_path (str, optional): Directory to store encryption keys and client data.
                                        Defaults to "matrix_store".
        """
        self.homeserver_url = homeserver_url.rstrip('/') if homeserver_url else None
        self.access_token = access_token
        self.room_id = room_id
        self.user_id = user_id
        self.store_path = store_path
        self.client = None
        self._message_callback = None # Callback for handling incoming messages

    def is_configured(self):
        """
        Checks if the Matrix client has sufficient configuration to operate.

        Returns:
            bool: True if homeserver_url, access_token, and room_id are all set, False otherwise.
        """
        return bool(self.homeserver_url and self.access_token and self.room_id)

    async def _ensure_client(self):
        """
        Ensures that the `matrix-nio` AsyncClient is initialized and configured.

        This method creates the client if it doesn't exist, sets up encryption,
        and configures the access token and user ID.
        """
        if self.client is None:
            # Create store path if it doesn't exist for E2EE data
            if self.store_path and not os.path.exists(self.store_path):
                os.makedirs(self.store_path)

            # Configure client with encryption ENABLED and store sync tokens
            client_config = AsyncClientConfig(
                encryption_enabled=True,
                store_sync_tokens=True
            )
            self.client = AsyncClient(
                self.homeserver_url,
                self.user_id or "", # user_id can be empty initially if not provided
                ssl=True,
                store_path=self.store_path,
                config=client_config
            )
            self.client.access_token = self.access_token
            if self.user_id:
                self.client.user_id = self.user_id
            # Set a custom device ID if needed, otherwise nio generates one
            # self.client.device_id = "slideshow-bot-device"


    async def send_message(self, message, html_message=None):
        """
        Sends a message to the configured Matrix room.

        Args:
            message (str): The plain text message content.
            html_message (str, optional): The HTML formatted message content. Defaults to None.

        Returns:
            bool: True if the message was sent successfully, False otherwise.
        """
        if not self.is_configured():
            print("Matrix configuration missing or incomplete. Skipping notification.")
            return False

        try:
            await self._ensure_client() # Ensure client is ready
            
            content = {
                "msgtype": "m.text",
                "body": message
            }
            
            if html_message:
                content["format"] = "org.matrix.custom.html"
                content["formatted_body"] = html_message

            # Send the message to the room, ignoring unverified devices for simplicity
            # In a production E2EE setup, more robust device verification might be needed
            response = await self.client.room_send(
                room_id=self.room_id,
                message_type="m.room.message",
                content=content,
                ignore_unverified_devices=True # This is important for E2EE rooms
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
            # In a long-running daemon, we generally keep the client open.
            # It will be closed on application shutdown.
            pass

    async def send_success(self, video_name, slide_list):
        """
        Sends a success notification message to the Matrix room.

        Args:
            video_name (str): The name of the generated video.
            slide_list (list): A list of image basenames included in the slideshow.

        Returns:
            bool: True if the message was sent successfully, False otherwise.
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
        Sends a failure notification message to the Matrix room.

        Args:
            error_message (str): A brief description of the error.
            traceback_str (str, optional): The full traceback string for debugging. Defaults to None.

        Returns:
            bool: True if the message was sent successfully, False otherwise.
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
        Registers a callback function to be called when an incoming message is received.

        The callback function should be an asynchronous function that accepts
        `room_id` (str) and `event` (nio.events.room_events.RoomMessageText) as arguments.

        Args:
            callback (callable): The async function to be called on message receipt.
        """
        self._message_callback = callback

    async def _on_message(self, room_id, event):
        """
        Internal callback handler for incoming Matrix messages.

        This method filters out messages sent by the bot itself and
        dispatches valid messages to the registered `_message_callback`.

        Args:
            room_id (str): The ID of the room where the message was sent.
            event (nio.events.room_events.RoomMessageText): The incoming message event.
        """
        print(f"DEBUG: Received event type {type(event).__name__} from {event.sender}")
        print(f"DEBUG: Comparing sender '{event.sender}' with bot ID '{self.client.user_id}'")
        # Ignore our own messages to prevent infinite loops
        if event.sender == self.client.user_id:
            print("DEBUG: Ignoring our own message.")
            return

        print(f"DEBUG: Received Matrix event in room {room_id} (Target: {self.room_id}) from {event.sender}: {event.body}")
        # Process messages only from the configured room
        if room_id == self.room_id:
            if self._message_callback:
                # Call the registered message handler
                await self._message_callback(room_id, event)
        else:
            print(f"DEBUG: Event ignored (wrong room)")

    async def listen_forever(self):
        """
        Starts a continuous sync loop to listen for Matrix events.

        This method connects to the homeserver, joins the configured room,
        loads encryption keys, and processes incoming messages and encrypted events.
        It attempts to auto-trust devices and request keys for E2EE messages.
        """
        if not self.is_configured():
            print("Matrix configuration missing. Cannot listen.")
            return

        await self._ensure_client() # Ensure client is initialized

        # Auto-detect device ID and initialize crypto
        # This is crucial for E2EE to work correctly
        try:
            whoami_resp = await self.client.whoami()
            if hasattr(whoami_resp, 'device_id') and whoami_resp.device_id:
                self.client.device_id = whoami_resp.device_id
        except Exception as e:
            print(f"Error detecting device ID: {e}")

        # Initial sync to load account and crypto store
        # full_state=True ensures we get enough info for E2EE
        sync_resp = await self.client.sync(timeout=3000, full_state=True)
        
        # Load Olm machine for E2EE
        # This loads the encryption keys from the store_path
        if self.client.device_id:
            try:
                self.client.load_store()
                if self.client.olm and not self.client.olm.account:
                    self.client.olm.load()
            except Exception as e:
                print(f"Error loading crypto: {e}")
        
        # Join the configured room if not already joined
        await self.client.join(self.room_id)
        
        # Send an initial message to confirm bot is starting
        await self.send_message("🤖 Slideshow Bot is starting and listening for commands...")

        # Perform an initial sync to get the starting token for subsequent syncs
        sync_resp = await self.client.sync(timeout=30000)
        next_batch = sync_resp.next_batch # Token for the next sync request
        
        print(f"Matrix bot listening for messages in {self.room_id} starting at {next_batch}...")
        
        while True:
            try:
                # Continuous sync loop to fetch new events
                sync_resp = await self.client.sync(timeout=30000, since=next_batch)
                next_batch = sync_resp.next_batch # Update token for next iteration
                
                # Process to-device events (e.g., key requests, device list updates)
                if sync_resp.to_device_events:
                    for e in sync_resp.to_device_events:
                        # matrix-nio's internal callbacks handle most to-device events
                        pass

                # Process room events (messages, encrypted events)
                for room_id, room in sync_resp.rooms.join.items():
                    for event in room.timeline.events:
                        if isinstance(event, RoomMessageText):
                            # Handle plain text messages
                            await self._on_message(room_id, event)
                        elif isinstance(event, MegolmEvent):
                            # Handle encrypted messages (E2EE)
                            try:
                                # Perform a quick sync to ensure device lists are up-to-date
                                await self.client.sync(timeout=1000)
                                # Attempt to verify sender's devices and request keys
                                devices = list(self.client.device_store.active_user_devices(event.sender))
                                for device in devices:
                                    # Auto-trust devices for simplicity in this bot context
                                    # In a user client, this would involve user confirmation
                                    self.client.verify_device(device)
                                await self.client.request_room_key(event)
                            except Exception as e:
                                print(f"Failed to request encryption key for event {event.event_id}: {e}")
                                # Log the error but continue processing
            except Exception as e:
                import traceback
                print(f"Error in Matrix sync loop: {e}")
                traceback.print_exc()
                await asyncio.sleep(5) # Wait before retrying to prevent busy-looping

    async def close(self):
        """
        Closes the Matrix client connection gracefully.
        """
        if self.client:
            await self.client.close()
            self.client = None
