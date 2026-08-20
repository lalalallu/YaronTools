"""
下载项组件 - 显示单个下载任务的进度
"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QFrame
)
from PyQt6.QtCore import Qt, pyqtSignal
from datetime import datetime

from models.download_task import DownloadTask, DownloadStatus, DownloadProgress


class DownloadItemWidget(QFrame):
    """下载项组件"""
    
    pause_clicked = pyqtSignal(str)   # task_id
    resume_clicked = pyqtSignal(str)  # task_id
    cancel_clicked = pyqtSignal(str)  # task_id
    open_clicked = pyqtSignal(str)    # task_id
    
    def __init__(self, task: DownloadTask, parent=None):
        super().__init__(parent)
        self._task = task
        self._prev_status = None
        self._prev_percentage = -1
        self._prev_downloaded = -1
        self._setup_ui()
        self._update_display()
    
    def _setup_ui(self):
        """设置界面"""
        self.setFrameStyle(QFrame.Shape.StyledPanel | QFrame.Shadow.Raised)
        self.setStyleSheet("""
            DownloadItemWidget {
                background-color: #f8f9fa;
                border: 1px solid #dee2e6;
                border-radius: 4px;
                padding: 8px;
                margin: 2px;
            }
        """)
        
        layout = QVBoxLayout(self)
        layout.setSpacing(4)
        
        # 文件名行
        header_layout = QHBoxLayout()
        
        self.file_label = QLabel()
        self.file_label.setStyleSheet("font-weight: bold; color: #212529;")
        header_layout.addWidget(self.file_label)
        
        header_layout.addStretch()
        
        # 状态标签
        self.status_label = QLabel()
        self.status_label.setStyleSheet("color: #6c757d;")
        header_layout.addWidget(self.status_label)
        
        layout.addLayout(header_layout)

        self.progress_label = QLabel()
        self.progress_label.setStyleSheet(
            "font-weight: bold; font-size: 13px; color: #0d6efd;"
        )
        layout.addWidget(self.progress_label)

        # 详情行
        detail_layout = QHBoxLayout()

        self.speed_label = QLabel()
        self.speed_label.setStyleSheet("color: #6c757d; font-size: 11px;")
        detail_layout.addWidget(self.speed_label)

        detail_layout.addStretch()

        self.eta_label = QLabel()
        self.eta_label.setStyleSheet("color: #6c757d; font-size: 11px;")
        detail_layout.addWidget(self.eta_label)

        layout.addLayout(detail_layout)
        
        # 按钮行
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        self.pause_btn = QPushButton("暂停")
        self.pause_btn.setFixedWidth(60)
        self.pause_btn.clicked.connect(
            lambda: self.pause_clicked.emit(self._task.id)
        )
        button_layout.addWidget(self.pause_btn)
        
        self.resume_btn = QPushButton("继续")
        self.resume_btn.setFixedWidth(60)
        self.resume_btn.clicked.connect(
            lambda: self.resume_clicked.emit(self._task.id)
        )
        self.resume_btn.hide()
        button_layout.addWidget(self.resume_btn)
        
        self.cancel_btn = QPushButton("取消")
        self.cancel_btn.setFixedWidth(60)
        self.cancel_btn.clicked.connect(
            lambda: self.cancel_clicked.emit(self._task.id)
        )
        button_layout.addWidget(self.cancel_btn)
        
        self.open_btn = QPushButton("打开")
        self.open_btn.setFixedWidth(60)
        self.open_btn.clicked.connect(
            lambda: self.open_clicked.emit(self._task.id)
        )
        self.open_btn.hide()
        button_layout.addWidget(self.open_btn)
        
        layout.addLayout(button_layout)
    
    def _update_display(self):
        """更新显示"""
        task = self._task
        
        # 文件名
        self.file_label.setText(task.file_name)
        
        # 进度文字
        percentage = task.progress.percentage
        downloaded_str = DownloadProgress.format_size(task.progress.downloaded)
        total_str = DownloadProgress.format_size(task.progress.total)
        if task.status == DownloadStatus.DOWNLOADING:
            self.progress_label.setText(
                f"{percentage:.1f}%  {downloaded_str}/{total_str}"
            )
        elif task.status == DownloadStatus.COMPLETED:
            self.progress_label.setText(f"100%  {total_str}")
        else:
            self.progress_label.setText(f"{percentage:.1f}%  {downloaded_str}/{total_str}")

        # 速度
        if task.status == DownloadStatus.DOWNLOADING:
            speed_str = DownloadProgress.format_speed(task.progress.speed)
            self.speed_label.setText(f"速度: {speed_str}")
        else:
            self.speed_label.setText("")
        
        # 剩余时间
        if task.progress.eta > 0 and task.status == DownloadStatus.DOWNLOADING:
            eta_str = DownloadProgress.format_time(task.progress.eta)
            self.eta_label.setText(f"剩余: {eta_str}")
        else:
            self.eta_label.setText("")
        
        # 状态和按钮
        self._update_status_display()
    
    def _update_status_display(self):
        """更新状态显示"""
        status = self._task.status

        status_config = {
            DownloadStatus.PENDING: ("等待中", "#6c757d", "#6c757d"),
            DownloadStatus.DOWNLOADING: ("下载中", "#0d6efd", "#0d6efd"),
            DownloadStatus.PAUSED: ("已暂停", "#ffc107", "#ffc107"),
            DownloadStatus.COMPLETED: ("已完成", "#198754", "#198754"),
            DownloadStatus.FAILED: (f"失败: {self._task.error_message}", "#dc3545", "#dc3545"),
            DownloadStatus.CANCELLED: ("已取消", "#6c757d", "#6c757d"),
        }

        text, color, prog_color = status_config.get(status, ("未知", "#6c757d", "#6c757d"))
        self.status_label.setText(text)
        self.status_label.setStyleSheet(f"color: {color};")
        self.progress_label.setStyleSheet(f"font-weight: bold; font-size: 13px; color: {prog_color};")

        is_downloading = status == DownloadStatus.DOWNLOADING
        is_paused = status == DownloadStatus.PAUSED
        is_completed = status == DownloadStatus.COMPLETED

        self.pause_btn.setVisible(is_downloading)
        self.resume_btn.setVisible(is_paused)
        self.cancel_btn.setVisible(not is_completed)
        self.open_btn.setVisible(is_completed)
    
    def update_progress(self, downloaded: int, total: int):
        """更新进度"""
        self._task.progress.downloaded = downloaded
        self._task.progress.total = total
        self._update_display()
    
    def update_task(self, task: DownloadTask):
        """更新任务——仅在状态/进度变化时重绘"""
        changed = (
            task.status != self._prev_status
            or int(task.progress.percentage) != self._prev_percentage
            or task.progress.downloaded != self._prev_downloaded
        )
        if not changed:
            return
        self._prev_status = task.status
        self._prev_percentage = int(task.progress.percentage)
        self._prev_downloaded = task.progress.downloaded
        self._task = task
        self._update_display()
    
    @property
    def task_id(self) -> str:
        """任务ID"""
        return self._task.id
