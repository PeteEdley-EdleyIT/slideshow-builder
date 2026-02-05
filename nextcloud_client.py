"""
Nextcloud Client for WebDAV operations.

This module provides a client class `NextcloudClient` to interact with a Nextcloud
instance using its WebDAV API. It supports listing, downloading, and uploading
files, with specific handling for sorting numerically prefixed files.
"""

import os
import re
import requests
import xml.etree.ElementTree as ET
import tempfile
import shutil
from urllib.parse import quote

def sort_key(filepath):
    """
    Generates a sort key for a filepath to sort numerically-prefixed
    files first, followed by alphabetically sorted non-prefixed files.

    This function is designed to be used as the `key` argument in sorting
    functions (e.g., `list.sort()` or `sorted()`). It extracts a numeric
    prefix from the filename if present, prioritizing numerical order
    for such files, and then alphabetical order for all others.

    Args:
        filepath (str): The full path to the file.

    Returns:
        tuple: A tuple used for sorting.
               - If the filename has a numeric prefix: (0, int(number), filename)
               - If the filename does not have a numeric prefix: (1, filename, filename)
    """
    filename = os.path.basename(filepath)
    match = re.match(r'(\d+)', filename)
    if match:
        # Return a tuple for sorting: (0, number, filename)
        # 0 for numeric prefix, making it come first
        return (0, int(match.group(1)), filename)
    else:
        # 1 for non-numeric, making it come after
        return (1, filename, filename)


class NextcloudClient:
    """
    A client for interacting with a Nextcloud instance via WebDAV.

    This class provides methods to authenticate with a Nextcloud server
    and perform file operations such as listing, downloading, and uploading
    files using the WebDAV protocol.

    Attributes:
        base_url (str): The base URL of the Nextcloud instance.
        auth (tuple): A tuple containing the username and password for authentication.
        verify_ssl (bool): Whether to verify SSL certificates for requests.
    """
    def __init__(self, base_url, username, password, verify_ssl=True):
        """
        Initializes the NextcloudClient.

        Args:
            base_url (str): The base URL of the Nextcloud instance (e.g., "https://your.nextcloud.com").
            username (str): The username for Nextcloud authentication.
            password (str): The password for Nextcloud authentication.
            verify_ssl (bool, optional): Whether to verify SSL certificates. Defaults to True.
                                         Set to False to bypass SSL verification (use with caution).
        """
        if not base_url.endswith('/'):
            base_url += '/'
        self.base_url = base_url
        self.auth = (username, password)
        self.verify_ssl = verify_ssl

    def _get_webdav_url(self, path):
        """
        Constructs the full WebDAV URL for a given path.

        This internal helper method formats the URL correctly for WebDAV
        operations, including encoding the username and path.

        Args:
            path (str): The path to the file or directory on Nextcloud.

        Returns:
            str: The full WebDAV URL.
        """
        user_encoded = quote(self.auth[0])
        path_encoded = quote(path.strip('/'), safe='/')
        return f"{self.base_url}remote.php/dav/files/{user_encoded}/{path_encoded}"

    def list_and_download_files(self, remote_path, allowed_extensions=None):
        """
        Lists files in a Nextcloud folder, downloads them to a temporary
        directory, and returns the sorted list of local paths.

        Files are sorted using the `sort_key` function, which prioritizes
        numerically prefixed filenames.

        Args:
            remote_path (str): Path on Nextcloud to list/download from (e.g., "Photos/Slideshow/").
            allowed_extensions (tuple, optional): A tuple of allowed file extensions
                                                  (e.g., ('.jpg', '.jpeg')). If None,
                                                  all files are considered. Defaults to None.

        Returns:
            tuple: A tuple containing:
                   - list: A sorted list of local file paths of downloaded images.
                   - str: The path to the temporary directory where files were downloaded.
                   Returns (None, None) if an error occurs.
        """
        propfind_url = self._get_webdav_url(remote_path)
        temp_dir = tempfile.mkdtemp()
        downloaded_image_paths = []

        try:
            # Use PROPFIND to get directory contents
            headers = {'Depth': '1'}
            response = requests.request('PROPFIND', propfind_url, auth=self.auth, headers=headers, verify=self.verify_ssl)
            response.raise_for_status() # Raise an exception for HTTP errors

            root = ET.fromstring(response.content)
            # Define XML namespace for DAV
            ns = {'d': 'DAV:'}

            # Iterate through each response element (each file/folder)
            for response_elem in root.findall('d:response', ns):
                href_elem = response_elem.find('d:href', ns)
                if href_elem is None:
                    continue

                file_href = href_elem.text
                # Skip the directory itself
                if file_href.strip('/') == remote_path.strip('/'):
                    continue
                
                # Filter by allowed extensions if specified
                if allowed_extensions:
                    # Check if the file_href ends with any of the allowed extensions
                    if not file_href.lower().endswith(allowed_extensions):
                        continue

                # Construct the full download URL and local path
                download_url = f"{self.base_url}{file_href.lstrip('/')}"
                local_filename = os.path.join(temp_dir, os.path.basename(file_href))

                print(f"Downloading {file_href} to {local_filename}...")
                download_response = requests.get(download_url, auth=self.auth, verify=self.verify_ssl, stream=True)
                download_response.raise_for_status()

                # Save the downloaded file
                with open(local_filename, 'wb') as f:
                    for chunk in download_response.iter_content(chunk_size=8192):
                        f.write(chunk)
                downloaded_image_paths.append(local_filename)

        except requests.exceptions.RequestException as e:
            print(f"Error connecting to Nextcloud or during file operation: {e}")
            shutil.rmtree(temp_dir) # Clean up temp directory on error
            return None, None
        except ET.ParseError as e:
            print(f"Error parsing Nextcloud response: {e}")
            shutil.rmtree(temp_dir) # Clean up temp directory on error
            return None, None

        downloaded_image_paths.sort(key=sort_key)
        return downloaded_image_paths, temp_dir

    def download_file(self, remote_path):
        """
        Downloads a single file from Nextcloud to a temporary directory.

        Args:
            remote_path (str): Path on Nextcloud to the file (e.g., "Videos/my_video.mp4").

        Returns:
            tuple: A tuple containing:
                   - str: The local path to the downloaded file.
                   - str: The path to the temporary directory where the file was downloaded.
                   Returns (None, None) if an error occurs.
        """
        download_url = self._get_webdav_url(remote_path)
        temp_dir = tempfile.mkdtemp()
        local_filename = os.path.join(temp_dir, os.path.basename(remote_path))

        print(f"Downloading {remote_path} from Nextcloud to {local_filename}...")
        try:
            download_response = requests.get(download_url, auth=self.auth, verify=self.verify_ssl, stream=True)
            download_response.raise_for_status()

            with open(local_filename, 'wb') as f:
                for chunk in download_response.iter_content(chunk_size=8192):
                    f.write(chunk)

            return local_filename, temp_dir
        except requests.exceptions.RequestException as e:
            print(f"Error downloading file from Nextcloud: {e}")
            shutil.rmtree(temp_dir)
            return None, None

    def upload_file(self, local_filepath, remote_path):
        """
        Uploads a local file to a specified path on Nextcloud.

        Args:
            local_filepath (str): The local path to the file to upload.
            remote_path (str): The destination path on Nextcloud (e.g., "Videos/uploaded_video.mp4").

        Raises:
            requests.exceptions.RequestException: If an error occurs during the upload.
        """
        upload_url = self._get_webdav_url(remote_path)
        print(f"Uploading video to Nextcloud: {remote_path}...")
        try:
            with open(local_filepath, 'rb') as video_file:
                response = requests.put(upload_url, data=video_file, auth=self.auth, verify=self.verify_ssl)
                response.raise_for_status() # Raise an exception for HTTP errors
            print(f"Video uploaded successfully to Nextcloud: {upload_url}")
        except requests.exceptions.RequestException as e:
            print(f"Error uploading video to Nextcloud: {e}")
            raise # Re-raise the exception after logging
