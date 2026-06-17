import asyncio
import base64
from concurrent.futures import TimeoutError as FuturesTimeoutError

from core.connection import SSHConnectionManager


class SudoPermissionError(PermissionError):
    pass


class SudoExecutor:
    def __init__(self, connection_manager: SSHConnectionManager):
        self._conn = connection_manager

    def exec_sudo(self, command: str, sudo_password: str, timeout: int = 30):
        return self._conn._run_async(
            self._async_exec_sudo(command, sudo_password),
            timeout=timeout + 10
        )

    async def _async_exec_sudo(self, command: str, sudo_password: str):
        conn = self._conn._conn
        if not conn:
            raise RuntimeError("未连接到远程服务器")

        safe_pwd = sudo_password.replace("'", "'\\''")
        escaped_cmd = command.replace("'", "'\\''")
        full_cmd = f"echo '{safe_pwd}' | sudo -S -- bash -c '{escaped_cmd}'"

        result = await conn.run(full_cmd, check=False)
        err_text = result.stderr or ""

        if result.exit_status != 0:
            err_lines = [
                ll for ll in err_text.splitlines()
                if 'password' not in ll.lower() and ll.strip()
            ]
            msg = "\n".join(err_lines) if err_lines else err_text
            if not msg.strip():
                msg = f"sudo 命令执行失败 (退出码 {result.exit_status})"
            raise SudoPermissionError(f"远程写入权限不足: {msg}")

        return result.stdout or ""

    def write_file_sudo(self, remote_path: str, content: str, sudo_password: str):
        data_b64 = base64.b64encode(content.encode("utf-8")).decode("ascii")
        safe_path = remote_path.replace("'", "'\\''")
        command = f"echo '{data_b64}' | base64 -d > '{safe_path}'"
        return self.exec_sudo(command, sudo_password, timeout=60)

    @staticmethod
    def build_cp_command(src: str, dst: str) -> str:
        return f"cp '{src}' '{dst}'"

    @staticmethod
    def build_rm_command(path: str) -> str:
        return f"rm -f '{path}'"

    @staticmethod
    def build_ls_command(path: str) -> str:
        return f"ls '{path}'"
