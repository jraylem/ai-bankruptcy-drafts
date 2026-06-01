import os
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class SFTPClient:
    def __init__(self):
        self.hostname = os.getenv("SFTP_HOST", "172.17.0.1")
        self.username = os.getenv("SFTP_USER", "ubuntu")
        self.key_path = os.getenv("SFTP_KEY_PATH", "/app/keys/id_rsa")
        self.destination = os.getenv("SFTP_DESTINATION", "/home/ubuntu/google-drive-archived-petitions")

    def _get_client(self):
        import paramiko
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(
            hostname=self.hostname,
            username=self.username,
            key_filename=self.key_path,
        )
        return ssh

    def push_file(self, source_path: str, filename: str) -> bool:
        """Upload a file to the Linux host via SFTP. Returns True on success."""
        ssh = None
        try:
            ssh = self._get_client()
            sftp = ssh.open_sftp()

            # Ensure destination directory exists on host
            try:
                sftp.stat(self.destination)
            except FileNotFoundError:
                sftp.mkdir(self.destination)

            destination_path = os.path.join(self.destination, filename)
            sftp.put(source_path, destination_path)
            sftp.close()

            logger.info(f"[sftp] Pushed {filename} → {destination_path}")
            return True

        except Exception as e:
            logger.error(f"[sftp] Failed to push {filename}: {e}")
            return False

        finally:
            if ssh:
                ssh.close()


# Module-level singleton
sftp_client = SFTPClient()
