"""
SFTP客户端封装 - 使用asyncssh实现
"""
import os
import stat
from typing import List, Optional, Callable
from dataclasses import dataclass
from datetime import datetime

from .connection import SSHConnectionManager, AsyncSFTPWrapper


@dataclass
class RemoteFile:
    """远程文件信息"""
    name: str
    path: str
    is_dir: bool
    size: int
    modify_time: datetime
    permissions: str
    
    @staticmethod
    def format_size(size: int) -> str:
        """格式化文件大小"""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size < 1024:
                return f"{size:.1f} {unit}" if unit != 'B' else f"{size} {unit}"
            size /= 1024
        return f"{size:.1f} PB"
    
    @property
    def size_formatted(self) -> str:
        """格式化后的大小"""
        return "-" if self.is_dir else self.format_size(self.size)
    
    @property
    def icon(self) -> str:
        """文件图标"""
        if self.is_dir:
            return "📁"
        # 根据扩展名返回图标
        ext = os.path.splitext(self.name)[1].lower()
        icons = {
            '.tar': '📦', '.zip': '📦', '.gz': '📦', '.rar': '📦', '.7z': '📦',
            '.jpg': '🖼️', '.jpeg': '🖼️', '.png': '🖼️', '.gif': '🖼️', '.bmp': '🖼️',
            '.mp3': '🎵', '.wav': '🎵', '.flac': '🎵',
            '.mp4': '🎬', '.avi': '🎬', '.mkv': '🎬', '.mov': '🎬',
            '.pdf': '📄', '.doc': '📄', '.docx': '📄', '.txt': '📄',
            '.py': '🐍', '.js': '📜', '.java': '☕', '.cpp': '⚙️', '.c': '⚙️',
            '.sh': '📜', '.bat': '📜',
            '.cfg': '⚙️', '.conf': '⚙️', '.ini': '⚙️',
        }
        return icons.get(ext, '📄')


class SFTPClientWrapper:
    """SFTP客户端封装"""
    
    def __init__(self, connection_manager: SSHConnectionManager):
        """
        初始化SFTP客户端
        
        Args:
            connection_manager: SSH连接管理器
        """
        self._connection = connection_manager
        self._sftp: Optional[AsyncSFTPWrapper] = None
    
    @property
    def sftp(self) -> AsyncSFTPWrapper:
        """获取SFTP客户端"""
        if self._sftp is None:
            self._sftp = self._connection.get_sftp()
        return self._sftp
    
    def list_dir(self, path: str, sort_by: str = "mtime") -> List[RemoteFile]:
        """
        列出目录内容
        
        Args:
            path: 目录路径
            sort_by: 排序方式，"mtime"按修改时间倒序，"name"按名称排序
            
        Returns:
            文件列表
        """
        files = []

        if not path or not path.strip():
            raise IOError("无法列出目录: 路径不能为空")

        entries = self._try_scandir(path)
        if entries is None:
            return self._list_dir_fallback(path, sort_by)

        for entry in entries:
            try:
                if entry.filename in ('.', '..'):
                    continue

                if not entry.filename or '\x00' in entry.filename:
                    continue

                file_path = path.rstrip('/') + '/' + entry.filename

                mode = entry.attrs.permissions
                perms = ""
                perms += "d" if stat.S_ISDIR(mode) else "-"
                perms += "r" if mode & stat.S_IRUSR else "-"
                perms += "w" if mode & stat.S_IWUSR else "-"
                perms += "x" if mode & stat.S_IXUSR else "-"
                perms += "r" if mode & stat.S_IRGRP else "-"
                perms += "w" if mode & stat.S_IWGRP else "-"
                perms += "x" if mode & stat.S_IXGRP else "-"
                perms += "r" if mode & stat.S_IROTH else "-"
                perms += "w" if mode & stat.S_IWOTH else "-"
                perms += "x" if mode & stat.S_IXOTH else "-"

                mtime = entry.attrs.mtime if hasattr(entry.attrs, 'mtime') and entry.attrs.mtime else 0
                modify_time = datetime.fromtimestamp(mtime) if mtime else datetime.now()

                size = entry.attrs.size if hasattr(entry.attrs, 'size') else 0

                file = RemoteFile(
                    name=entry.filename,
                    path=file_path,
                    is_dir=stat.S_ISDIR(mode),
                    size=size,
                    modify_time=modify_time,
                    permissions=perms
                )
                files.append(file)
            except Exception:
                continue

        # 排序：目录在前
        if sort_by == "mtime":
            # 按修改时间倒序（最新在前）
            files.sort(key=lambda f: (not f.is_dir, -f.modify_time.timestamp()))
        else:
            # 按名称排序
            files.sort(key=lambda f: (not f.is_dir, f.name.lower()))
        return files
    
    def stat(self, path: str) -> RemoteFile:
        """获取文件信息"""
        attr = self.sftp.stat(path)
        
        mode = attr.permissions if hasattr(attr, 'permissions') else 0
        perms = ""
        perms += "d" if stat.S_ISDIR(mode) else "-"
        perms += "r" if mode & stat.S_IRUSR else "-"
        perms += "w" if mode & stat.S_IWUSR else "-"
        perms += "x" if mode & stat.S_IXUSR else "-"
        perms += "r" if mode & stat.S_IRGRP else "-"
        perms += "w" if mode & stat.S_IWGRP else "-"
        perms += "x" if mode & stat.S_IXGRP else "-"
        perms += "r" if mode & stat.S_IROTH else "-"
        perms += "w" if mode & stat.S_IWOTH else "-"
        perms += "x" if mode & stat.S_IXOTH else "-"
        
        mtime = attr.mtime if hasattr(attr, 'mtime') and attr.mtime else 0
        modify_time = datetime.fromtimestamp(mtime) if mtime else datetime.now()
        
        return RemoteFile(
            name=os.path.basename(path),
            path=path,
            is_dir=stat.S_ISDIR(mode),
            size=attr.size if hasattr(attr, 'size') else 0,
            modify_time=modify_time,
            permissions=perms
        )
    
    def get_home(self) -> str:
        """获取用户主目录"""
        try:
            return self.sftp.realpath('.')
        except Exception:
            return "/"
    
    def normalize_path(self, path: str) -> str:
        """规范化路径"""
        try:
            return self.sftp.realpath(path)
        except Exception:
            return path
    
    def exists(self, path: str) -> bool:
        """检查文件是否存在"""
        try:
            self.sftp.stat(path)
            return True
        except:
            return False
    
    def is_dir(self, path: str) -> bool:
        if path == "/" or path.endswith(":/"):
            return True
        try:
            attr = self.sftp.stat(path)
            return stat.S_ISDIR(attr.permissions)
        except:
            return False
    
    def download_file(
        self,
        remote_path: str,
        local_path: str,
        callback: Optional[Callable[[int, int], None]] = None,
        offset: int = 0
    ):
        """
        下载文件
        
        Args:
            remote_path: 远程文件路径
            local_path: 本地保存路径
            callback: 进度回调函数 callback(downloaded, total)
            offset: 已下载的字节数偏移量（断点续传）
        """
        # 确保本地目录存在
        local_dir = os.path.dirname(local_path)
        if local_dir and not os.path.exists(local_dir):
            os.makedirs(local_dir, exist_ok=True)
        
        self.sftp.get(remote_path, local_path, callback=callback, offset=offset)
    
    def close(self):
        """关闭连接"""
        self._sftp = None

    def _try_scandir(self, path: str):
        """尝试多种路径格式的 scandir，返回 entries 列表或 None"""
        for p in (path, path.rstrip('/') + '/.'):
            try:
                return self.sftp.scandir(p)
            except Exception:
                continue
        return None

    def _list_dir_fallback(self, path: str, sort_by: str = "mtime") -> List[RemoteFile]:
        """通过 exec_command 作为 scandir 失败时的回退方案"""

        def _try_command(cmd: str) -> str:
            exit_status, stdout, stderr = self._connection.execute_command(cmd, timeout=15)
            if exit_status != 0:
                raise IOError(stderr.strip() or f"exit code {exit_status}")
            return stdout

        stdout = None
        path_no_quote = path.replace("'", "")
        for cmd in (
            f"ls -la '{path_no_quote}'",
            f"ls -la '{path_no_quote}/.'",
            f"ls -la {path_no_quote}",
        ):
            try:
                stdout = _try_command(cmd)
                break
            except Exception:
                continue

        if stdout is None:
            raise IOError(f"无法列出目录 {path}: scandir 和所有回退方案均失败")

        files = []
        for line in stdout.splitlines():
            line = line.strip()
            if not line or line.startswith("total "):
                continue
            parts = line.split(None, 8)
            if len(parts) < 9:
                continue

            perms = parts[0]
            name = parts[8]
            if name in ('.', '..'):
                continue

            is_dir = perms.startswith('d')
            try:
                size = int(parts[4])
            except ValueError:
                size = 0

            file_path = path.rstrip('/') + '/' + name
            modify_time = datetime.now()
            files.append(RemoteFile(
                name=name, path=file_path, is_dir=is_dir,
                size=size, modify_time=modify_time, permissions=perms
            ))

        if sort_by == "mtime":
            files.sort(key=lambda f: (not f.is_dir, f.name.lower()))
        else:
            files.sort(key=lambda f: (not f.is_dir, f.name.lower()))
        return files
