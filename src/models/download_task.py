"""
下载任务模型
"""
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime
from enum import Enum
import uuid
import os


class DownloadStatus(Enum):
    """下载状态"""
    PENDING = "pending"        # 等待中
    DOWNLOADING = "downloading"  # 下载中
    PAUSED = "paused"          # 已暂停
    COMPLETED = "completed"     # 已完成
    FAILED = "failed"          # 失败
    CANCELLED = "cancelled"     # 已取消


@dataclass
class DownloadProgress:
    """下载进度"""
    downloaded: int = 0        # 已下载字节数
    total: int = 0             # 总字节数
    speed: float = 0.0         # 当前速度 (bytes/s)
    eta: int = 0               # 预计剩余时间 (秒)
    
    @property
    def percentage(self) -> float:
        """下载百分比"""
        if self.total == 0:
            return 0.0
        return (self.downloaded / self.total) * 100
    
    @property
    def is_completed(self) -> bool:
        """是否完成"""
        return self.downloaded >= self.total and self.total > 0
    
    @staticmethod
    def format_size(size: int) -> str:
        """格式化文件大小"""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size < 1024:
                return f"{size:.2f} {unit}" if unit != 'B' else f"{size} {unit}"
            size /= 1024
        return f"{size:.2f} PB"
    
    @staticmethod
    def format_speed(speed: float) -> str:
        """格式化速度"""
        return f"{DownloadProgress.format_size(int(speed))}/s"
    
    @staticmethod
    def format_time(seconds: int) -> str:
        """格式化时间"""
        if seconds < 60:
            return f"{seconds}秒"
        elif seconds < 3600:
            return f"{seconds // 60}分{seconds % 60}秒"
        else:
            hours = seconds // 3600
            minutes = (seconds % 3600) // 60
            return f"{hours}小时{minutes}分"


@dataclass
class DownloadTask:
    """下载任务"""
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    remote_path: str = ""           # 远程文件路径
    local_path: str = ""            # 本地保存路径
    file_name: str = ""             # 文件名
    file_size: int = 0              # 文件大小
    status: DownloadStatus = DownloadStatus.PENDING
    progress: DownloadProgress = field(default_factory=DownloadProgress)
    error_message: str = ""         # 错误信息
    create_time: datetime = field(default_factory=datetime.now)
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    
    # 断点续传相关
    temp_path: str = ""             # 临时文件路径
    resume_info_path: str = ""      # 续传信息文件路径
    supports_resume: bool = True     # 是否支持断点续传
    
    def __post_init__(self):
        """初始化后处理"""
        if not self.file_name:
            self.file_name = os.path.basename(self.remote_path)
        
        # 设置临时文件路径
        if self.local_path and not self.temp_path:
            self.temp_path = f"{self.local_path}.part"
            self.resume_info_path = f"{self.local_path}.resume"
    
    @property
    def is_active(self) -> bool:
        """是否处于活动状态"""
        return self.status in (DownloadStatus.PENDING, DownloadStatus.DOWNLOADING)
    
    @property
    def is_finished(self) -> bool:
        """是否已结束"""
        return self.status in (DownloadStatus.COMPLETED, DownloadStatus.FAILED, DownloadStatus.CANCELLED)
    
    def start(self):
        """开始下载"""
        self.status = DownloadStatus.DOWNLOADING
        self.start_time = datetime.now()
    
    def pause(self):
        """暂停下载"""
        self.status = DownloadStatus.PAUSED
    
    def resume(self):
        """恢复下载"""
        self.status = DownloadStatus.DOWNLOADING
    
    def complete(self):
        """完成下载"""
        self.status = DownloadStatus.COMPLETED
        self.end_time = datetime.now()
        self.progress.downloaded = self.progress.total
    
    def fail(self, error: str):
        """下载失败"""
        self.status = DownloadStatus.FAILED
        self.error_message = error
        self.end_time = datetime.now()
    
    def cancel(self):
        """取消下载"""
        self.status = DownloadStatus.CANCELLED
        self.end_time = datetime.now()
    
    def update_progress(self, downloaded: int, total: int = None):
        """更新进度"""
        self.progress.downloaded = downloaded
        if total:
            self.progress.total = total
    
    def get_resume_info(self) -> dict:
        """获取断点续传信息"""
        return {
            'id': self.id,
            'remote_path': self.remote_path,
            'local_path': self.local_path,
            'file_size': self.file_size,
            'downloaded': self.progress.downloaded,
            'temp_path': self.temp_path,
            'create_time': self.create_time.isoformat(),
        }
    
    @classmethod
    def from_resume_info(cls, info: dict) -> 'DownloadTask':
        """从断点续传信息创建任务"""
        task = cls(
            id=info.get('id', str(uuid.uuid4())[:8]),
            remote_path=info['remote_path'],
            local_path=info['local_path'],
            file_size=info['file_size'],
        )
        task.temp_path = info.get('temp_path', f"{task.local_path}.part")
        task.progress.downloaded = info.get('downloaded', 0)
        task.progress.total = task.file_size
        task.create_time = datetime.fromisoformat(info['create_time']) if 'create_time' in info else datetime.now()
        return task
