import re
from datetime import datetime
from typing import Optional

from core.sudo_executor import SudoExecutor, SudoPermissionError


class BackupManager:
    MAX_BACKUPS = 5

    def __init__(self, sudo_executor: Optional[SudoExecutor] = None):
        self._sudo = sudo_executor

    @staticmethod
    def get_backup_name(remote_path: str) -> str:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"{remote_path}.bak_{timestamp}"

    def create_backup(self, remote_path: str, sudo_password: str = "") -> Optional[str]:
        if not self._sudo:
            return None

        backup_name = self.get_backup_name(remote_path)
        command = SudoExecutor.build_cp_command(remote_path, backup_name)

        try:
            self._sudo.exec_sudo(command, sudo_password)
        except SudoPermissionError:
            raise
        except Exception as e:
            raise SudoPermissionError(f"创建备份失败: {e}")

        self.cleanup_old_backups(remote_path, sudo_password)
        return backup_name

    def cleanup_old_backups(self, remote_path: str, sudo_password: str = ""):
        if not self._sudo:
            return

        remote_dir = remote_path.rsplit("/", 1)[0]
        base_name = remote_path.rsplit("/", 1)[-1]
        pattern = re.compile(rf"^{re.escape(base_name)}\.bak_\d{{8}}_\d{{6}}$")

        try:
            out = self._sudo.exec_sudo(
                SudoExecutor.build_ls_command(remote_dir),
                sudo_password
            )
            all_files = out.strip().splitlines()
        except Exception:
            return

        backups = [f for f in all_files if pattern.match(f)]
        backups.sort(reverse=True)

        for old in backups[self.MAX_BACKUPS:]:
            try:
                self._sudo.exec_sudo(
                    SudoExecutor.build_rm_command(f"{remote_dir}/{old}"),
                    sudo_password
                )
            except Exception:
                pass

    def get_backup_list(self, remote_path: str, sudo_password: str = ""):
        if not self._sudo:
            return []

        remote_dir = remote_path.rsplit("/", 1)[0]
        base_name = remote_path.rsplit("/", 1)[-1]
        pattern = re.compile(rf"^{re.escape(base_name)}\.bak_\d{{8}}_\d{{6}}$")

        try:
            out = self._sudo.exec_sudo(
                SudoExecutor.build_ls_command(remote_dir),
                sudo_password
            )
            all_files = out.strip().splitlines()
        except Exception:
            return []

        backups = [f for f in all_files if pattern.match(f)]
        backups.sort(reverse=True)
        return backups
