"""
扩展 SFTP 客户端 — 增加远程文件读取能力，不修改现有 core/sftp_client.py。
"""
import asyncio
from concurrent.futures import TimeoutError as FuturesTimeoutError

from core.sftp_client import SFTPClientWrapper
from core.connection import ConnectionError


class SFTPClientWrapperExt(SFTPClientWrapper):
    def read_file(self, remote_path: str) -> bytes:
        return self.sftp._run_async(self._async_read_file(remote_path), timeout=60)

    async def _async_read_file(self, remote_path: str) -> bytes:
        sftp_client = self.sftp._sftp
        data = bytearray()
        async with sftp_client.open(remote_path, 'rb') as f:
            while True:
                chunk = await f.read(1024 * 1024)
                if not chunk:
                    break
                data.extend(chunk)
        return bytes(data)

    def write_file(self, remote_path: str, content: bytes) -> None:
        self.sftp._run_async(self._async_write_file(remote_path, content), timeout=60)

    async def _async_write_file(self, remote_path: str, content: bytes):
        sftp_client = self.sftp._sftp
        async with sftp_client.open(remote_path, 'wb') as f:
            await f.write(content)
