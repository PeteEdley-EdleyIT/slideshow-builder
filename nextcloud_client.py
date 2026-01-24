import os
import re
import requests
import xml.etree.ElementTree as ET
import tempfile
import shutil

def sort_key(filepath):
    """
    Generates a sort key for a filepath to sort numerically-prefixed
    files first, followed by alphabetically sorted non-prefixed files.
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
    """
    def __init__(self, base_url, username, password, verify_ssl=True):
        if not base_url.endswith('/'):
            base_url += '/'
        self.base_url = base_url
        self.auth = (username, password)
        self.verify_ssl = verify_ssl

    def _get_webdav_url(self, path):
        """Constructs the full WebDAV URL for a given path."""
        return f"{self.base_url}remote.php/dav/files/{self.auth[0]}/{path.strip('/')}"

    def list_and_download_images(self, remote_path):
        """
        Lists images in a Nextcloud folder, downloads them to a temporary
        directory, and returns the sorted list of local paths.
        """
        propfind_url = self._get_webdav_url(remote_path)
        temp_dir = tempfile.mkdtemp()
        downloaded_image_paths = []

        try:
            headers = {'Depth': '1'}
            response = requests.request('PROPFIND', propfind_url, auth=self.auth, headers=headers, verify=self.verify_ssl)
            response.raise_for_status()

            root = ET.fromstring(response.content)
            ns = {'d': 'DAV:'}

            for response_elem in root.findall('d:response', ns):
                href_elem = response_elem.find('d:href', ns)
                if href_elem is None:
                    continue

                file_href = href_elem.text
                if file_href == remote_path or not (file_href.lower().endswith(('.jpg', '.jpeg'))):
                    continue

                download_url = f"{self.base_url}{file_href.lstrip('/')}"
                local_filename = os.path.join(temp_dir, os.path.basename(file_href))

                print(f"Downloading {file_href} to {local_filename}...")
                download_response = requests.get(download_url, auth=self.auth, verify=self.verify_ssl, stream=True)
                download_response.raise_for_status()

                with open(local_filename, 'wb') as f:
                    for chunk in download_response.iter_content(chunk_size=8192):
                        f.write(chunk)
                downloaded_image_paths.append(local_filename)

        except requests.exceptions.RequestException as e:
            print(f"Error connecting to Nextcloud or during file operation: {e}")
            shutil.rmtree(temp_dir)
            return None, None
        except ET.ParseError as e:
            print(f"Error parsing Nextcloud response: {e}")
            shutil.rmtree(temp_dir)
            return None, None

        downloaded_image_paths.sort(key=sort_key)
        return downloaded_image_paths, temp_dir

    def upload_file(self, local_filepath, remote_path):
        """Uploads a local file to a specified path on Nextcloud."""
        upload_url = self._get_webdav_url(remote_path)
        print(f"Uploading video to Nextcloud: {remote_path}...")
        try:
            with open(local_filepath, 'rb') as video_file:
                response = requests.put(upload_url, data=video_file, auth=self.auth, verify=self.verify_ssl)
                response.raise_for_status()
            print(f"Video uploaded successfully to Nextcloud: {upload_url}")
        except requests.exceptions.RequestException as e:
            print(f"Error uploading video to Nextcloud: {e}")
