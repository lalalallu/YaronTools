# 数据模型模块
from .server import ServerConfig, JumpChain
from .download_task import DownloadTask, DownloadStatus, DownloadProgress

__all__ = [
    'ServerConfig',
    'JumpChain', 
    'DownloadTask',
    'DownloadStatus',
    'DownloadProgress'
]
