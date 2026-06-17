"""
下载管理器 - 使用asyncssh实现稳定下载
"""
import os
import time
import threading
from typing import Dict, List, Optional, Callable
from queue import Queue
from datetime import datetime

from models.download_task import DownloadTask, DownloadStatus, DownloadProgress
from .sftp_client import SFTPClientWrapper


class DownloadManager:
    """文件下载管理器"""
    
    def __init__(self, sftp_client: SFTPClientWrapper, max_concurrent: int = 2):
        """
        初始化下载管理器
        
        Args:
            sftp_client: SFTP客户端
            max_concurrent: 最大并发下载数
        """
        self._sftp = sftp_client
        self._max_concurrent = max_concurrent
        self._tasks: Dict[str, DownloadTask] = {}
        self._task_queue: Queue = Queue()
        self._workers: List[threading.Thread] = []
        self._running = False
        self._lock = threading.Lock()
        self._stop_flags: Dict[str, bool] = {}
        
        # 回调函数
        self._progress_callbacks: List[Callable[[str, int, int], None]] = []
        self._complete_callbacks: List[Callable[[str, str], None]] = []
        self._error_callbacks: List[Callable[[str, str], None]] = []
    
    def add_progress_callback(self, callback: Callable[[str, int, int], None]):
        """添加进度回调"""
        self._progress_callbacks.append(callback)
    
    def add_complete_callback(self, callback: Callable[[str, str], None]):
        """添加完成回调"""
        self._complete_callbacks.append(callback)
    
    def add_error_callback(self, callback: Callable[[str, str], None]):
        """添加错误回调"""
        self._error_callbacks.append(callback)
    
    def create_task(self, remote_path: str, local_path: str, 
                    file_size: int = 0) -> DownloadTask:
        """
        创建下载任务
        
        Args:
            remote_path: 远程文件路径
            local_path: 本地保存路径
            file_size: 文件大小
            
        Returns:
            下载任务
        """
        # 获取文件大小
        if file_size == 0:
            try:
                file_info = self._sftp.stat(remote_path)
                file_size = file_info.size
            except Exception as e:
                raise ValueError(f"无法获取文件大小: {str(e)}")
        
        task = DownloadTask(
            remote_path=remote_path,
            local_path=local_path,
            file_size=file_size
        )
        task.progress.total = file_size
        
        with self._lock:
            self._tasks[task.id] = task
            self._stop_flags[task.id] = False
        
        return task
    
    def get_task(self, task_id: str) -> Optional[DownloadTask]:
        """获取任务"""
        return self._tasks.get(task_id)
    
    def get_all_tasks(self) -> List[DownloadTask]:
        """获取所有任务"""
        return list(self._tasks.values())
    
    def start_download(self, task_id: str):
        """开始下载任务"""
        task = self.get_task(task_id)
        if not task:
            raise ValueError(f"任务不存在: {task_id}")
        
        task.status = DownloadStatus.PENDING
        self._stop_flags[task_id] = False
        self._task_queue.put(task_id)
        
        # 启动工作线程
        self._ensure_workers()
    
    def start_all(self):
        """开始所有待下载任务"""
        with self._lock:
            for task in self._tasks.values():
                if task.status in (DownloadStatus.PENDING, DownloadStatus.PAUSED):
                    self._stop_flags[task.id] = False
                    task.status = DownloadStatus.PENDING
                    self._task_queue.put(task.id)
        
        self._ensure_workers()
    
    def pause_download(self, task_id: str):
        """暂停下载"""
        task = self.get_task(task_id)
        if task:
            task.pause()
            self._stop_flags[task.id] = True
    
    def resume_download(self, task_id: str):
        """恢复下载"""
        task = self.get_task(task_id)
        if task and task.status == DownloadStatus.PAUSED:
            task.resume()
            self._stop_flags[task.id] = False
            self._task_queue.put(task.id)
            self._ensure_workers()
    
    def cancel_download(self, task_id: str):
        """取消下载"""
        task = self.get_task(task_id)
        if task:
            task.cancel()
            self._stop_flags[task.id] = True
            self._cleanup_temp_files(task)
    
    def remove_task(self, task_id: str):
        """移除任务"""
        with self._lock:
            task = self._tasks.pop(task_id, None)
            self._stop_flags.pop(task_id, None)
            if task:
                self._cleanup_temp_files(task)
    
    def _ensure_workers(self):
        """确保工作线程运行"""
        if not self._running:
            self._running = True
            for i in range(self._max_concurrent):
                worker = threading.Thread(
                    target=self._worker_loop,
                    name=f"DownloadWorker-{i}",
                    daemon=True
                )
                worker.start()
                self._workers.append(worker)
    
    def _worker_loop(self):
        """工作线程主循环"""
        while self._running:
            try:
                task_id = self._task_queue.get(timeout=1)
            except:
                continue
            
            task = self.get_task(task_id)
            if not task or task.status in (DownloadStatus.CANCELLED, DownloadStatus.COMPLETED):
                continue
            
            try:
                self._download_file(task)
            except Exception as e:
                task.fail(str(e))
                self._notify_error(task.id, str(e))
            
            self._task_queue.task_done()
    
    def _download_file(self, task: DownloadTask):
        """下载单个文件（支持断点续传）"""
        task.start()
        
        # 断点续传：检查是否存在已下载的部分临时文件
        offset = 0
        download_path = task.local_path  # 默认直接下载到目标路径
        
        if task.temp_path and os.path.exists(task.temp_path):
            offset = os.path.getsize(task.temp_path)
            if offset >= task.file_size:
                # 临时文件已完整，直接重命名完成
                final_path = task.local_path
                if os.path.exists(final_path):
                    os.remove(final_path)
                os.rename(task.temp_path, final_path)
                task.complete()
                self._notify_complete(task.id, task.local_path)
                return
            # 使用临时文件路径续传
            download_path = task.temp_path
            task.progress.downloaded = offset
        elif task.temp_path:
            # 全新下载，写入临时文件
            download_path = task.temp_path
            task.progress.downloaded = 0
        
        # 进度跟踪
        last_update = [time.time()]
        last_bytes = [offset]
        
        def progress_callback(downloaded: int, total: int):
            """进度回调函数"""
            # 检查是否停止
            if self._stop_flags.get(task.id, False):
                raise InterruptedError("下载已停止")
            
            # 更新任务进度
            task.progress.downloaded = downloaded
            task.progress.total = total
            
            # 计算速度（每0.5秒更新一次）
            current_time = time.time()
            elapsed = current_time - last_update[0]
            
            if elapsed >= 0.5:
                speed = (downloaded - last_bytes[0]) / elapsed
                remaining = total - downloaded
                eta = int(remaining / speed) if speed > 0 else 0
                
                task.progress.speed = speed
                task.progress.eta = eta
                
                # 通知进度更新
                self._notify_progress(task.id, downloaded, total)
                
                last_update[0] = current_time
                last_bytes[0] = downloaded
        
        try:
            # 使用SFTP下载文件到临时路径
            self._sftp.download_file(
                task.remote_path,
                download_path,
                callback=progress_callback,
                offset=offset
            )
            
            # 下载完成：如果使用了临时文件，重命名
            if download_path == task.temp_path:
                final_path = task.local_path
                if os.path.exists(final_path):
                    os.remove(final_path)
                os.rename(task.temp_path, final_path)
                # 清理续传信息文件
                if task.resume_info_path and os.path.exists(task.resume_info_path):
                    try:
                        os.remove(task.resume_info_path)
                    except:
                        pass
            
            task.complete()
            self._notify_complete(task.id, task.local_path)
            
        except InterruptedError:
            # 用户暂停 - 临时文件保留供续传使用
            task.status = DownloadStatus.PAUSED
        except Exception as e:
            # 下载失败
            task.fail(str(e))
            self._notify_error(task.id, str(e))
            raise
    
    def _cleanup_temp_files(self, task: DownloadTask):
        """清理临时文件"""
        try:
            if os.path.exists(task.temp_path):
                os.remove(task.temp_path)
            if os.path.exists(task.resume_info_path):
                os.remove(task.resume_info_path)
        except:
            pass
    
    def _notify_progress(self, task_id: str, downloaded: int, total: int):
        """通知进度更新"""
        for callback in self._progress_callbacks:
            try:
                callback(task_id, downloaded, total)
            except:
                pass
    
    def _notify_complete(self, task_id: str, local_path: str):
        """通知下载完成"""
        for callback in self._complete_callbacks:
            try:
                callback(task_id, local_path)
            except:
                pass
    
    def _notify_error(self, task_id: str, error: str):
        """通知下载错误"""
        for callback in self._error_callbacks:
            try:
                callback(task_id, error)
            except:
                pass
    
    def stop(self):
        """停止所有下载"""
        self._running = False
        
        # 设置所有停止标志
        for task_id in self._stop_flags:
            self._stop_flags[task_id] = True
        
        for task in self._tasks.values():
            if task.status == DownloadStatus.DOWNLOADING:
                task.pause()
    
    def get_total_progress(self) -> Dict:
        """获取总体进度"""
        total_size = 0
        downloaded = 0
        active_count = 0
        completed_count = 0
        
        for task in self._tasks.values():
            total_size += task.file_size
            downloaded += task.progress.downloaded
            if task.status == DownloadStatus.DOWNLOADING:
                active_count += 1
            elif task.status == DownloadStatus.COMPLETED:
                completed_count += 1
        
        return {
            'total_size': total_size,
            'downloaded': downloaded,
            'percentage': (downloaded / total_size * 100) if total_size > 0 else 0,
            'active_count': active_count,
            'completed_count': completed_count,
            'total_count': len(self._tasks)
        }
