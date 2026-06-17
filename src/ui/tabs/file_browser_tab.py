import os
import threading
import subprocess
import platform
from datetime import datetime

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QSplitter, QScrollArea, QFileDialog, QMessageBox
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal

from models.download_task import DownloadTask, DownloadStatus
from core.sftp_client import SFTPClientWrapper, RemoteFile
from core.downloader import DownloadManager
from ui.widgets.file_list_widget import FileListWidget
from ui.widgets.download_item_widget import DownloadItemWidget


class FileBrowserTab(QWidget):
    files_loaded = pyqtSignal(object, object)
    file_double_clicked = pyqtSignal(object)

    def __init__(self, parent=None):
        super().__init__(parent)

        self._sftp = None
        self._downloader = None
        self._current_path = "/"
        self._download_widgets = {}
        self._loading_thread = None

        self._setup_ui()
        self._connect_signals()

        self._update_timer = QTimer()
        self._update_timer.timeout.connect(self._update_progress)
        self._update_timer.start(500)

        self.files_loaded.connect(self._on_directory_loaded)

    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(splitter)

        center_widget = QWidget()
        center_layout = QVBoxLayout(center_widget)
        center_layout.setContentsMargins(0, 0, 0, 0)

        path_layout = QHBoxLayout()
        path_layout.addWidget(QLabel("远程目录:"))

        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText("输入路径...")
        self.path_edit.returnPressed.connect(self._navigate_to_path)
        path_layout.addWidget(self.path_edit)

        self.browse_btn = QPushButton("浏览")
        self.browse_btn.clicked.connect(self._browse_home)
        path_layout.addWidget(self.browse_btn)

        self.refresh_btn = QPushButton("刷新")
        self.refresh_btn.clicked.connect(self._refresh_file_list)
        path_layout.addWidget(self.refresh_btn)

        center_layout.addLayout(path_layout)

        self.file_list = FileListWidget()
        center_layout.addWidget(self.file_list)

        splitter.addWidget(center_widget)

        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)

        selected_group = QWidget()
        selected_layout = QVBoxLayout(selected_group)

        selected_header = QHBoxLayout()
        self.selected_count_label = QLabel("已选文件 (0项, 共 0 B)")
        selected_header.addWidget(self.selected_count_label)

        self.clear_selection_btn = QPushButton("清空")
        self.clear_selection_btn.clicked.connect(self._clear_selection)
        selected_header.addWidget(self.clear_selection_btn)

        self.download_btn = QPushButton("下载选中")
        self.download_btn.clicked.connect(self._start_download)
        self.download_btn.setEnabled(False)
        selected_header.addWidget(self.download_btn)

        selected_layout.addLayout(selected_header)

        self.selected_list_label = QLabel("无选中文件")
        self.selected_list_label.setStyleSheet("color: #6c757d; padding: 8px;")
        selected_layout.addWidget(self.selected_list_label)

        local_path_layout = QHBoxLayout()
        local_path_layout.addWidget(QLabel("保存到:"))

        self.local_path_edit = QLineEdit()
        self.local_path_edit.setText(os.path.expanduser("~/Downloads"))
        local_path_layout.addWidget(self.local_path_edit)

        self.browse_local_btn = QPushButton("浏览...")
        self.browse_local_btn.clicked.connect(self._browse_local_path)
        local_path_layout.addWidget(self.browse_local_btn)

        selected_layout.addLayout(local_path_layout)
        right_layout.addWidget(selected_group)

        progress_group = QWidget()
        progress_layout = QVBoxLayout(progress_group)

        progress_header_layout = QHBoxLayout()
        progress_header = QLabel("下载进度")
        progress_header.setStyleSheet("font-weight: bold;")
        progress_header_layout.addWidget(progress_header)

        self.clear_completed_btn = QPushButton("清空已完成")
        self.clear_completed_btn.setFixedWidth(100)
        self.clear_completed_btn.clicked.connect(self._clear_completed_downloads)
        progress_header_layout.addWidget(self.clear_completed_btn)

        progress_layout.addLayout(progress_header_layout)

        self.download_scroll = QScrollArea()
        self.download_scroll.setWidgetResizable(True)
        self.download_scroll.setStyleSheet("QScrollArea { border: none; }")

        self.download_container = QWidget()
        self.download_container_layout = QVBoxLayout(self.download_container)
        self.download_container_layout.addStretch()

        self.download_scroll.setWidget(self.download_container)
        progress_layout.addWidget(self.download_scroll)

        self.total_progress_label = QLabel("总进度: 0%")
        progress_layout.addWidget(self.total_progress_label)

        right_layout.addWidget(progress_group)

        splitter.addWidget(right_widget)
        splitter.setSizes([600, 400])

    def _connect_signals(self):
        self.file_list.selection_changed.connect(self._on_selection_changed)
        self.file_list.file_double_clicked.connect(self._on_file_double_click)
        self.file_list.refresh_btn.clicked.connect(self._refresh_file_list)

    def set_sftp(self, sftp: SFTPClientWrapper):
        self._sftp = sftp
        if sftp:
            self._downloader = DownloadManager(sftp)
            self._downloader.add_progress_callback(self._on_download_progress)
            self._downloader.add_complete_callback(self._on_download_complete)
            self._downloader.add_error_callback(self._on_download_error)

    def set_connected(self, connected: bool):
        if not connected:
            self._sftp = None
            if self._downloader:
                self._downloader.stop()
                self._downloader = None
            self._download_widgets.clear()
            self.file_list.setFiles([])
            self.path_edit.clear()
            self.selected_list_label.setText("无选中文件")
            self.selected_list_label.setStyleSheet("color: #6c757d; padding: 8px;")
            self.selected_count_label.setText("已选文件 (0项, 共 0 B)")
            self.download_btn.setEnabled(False)

    def navigate_to(self, path: str):
        if not self._sftp:
            return
        self._current_path = path
        self.path_edit.setText(path)
        self._refresh_file_list()

    def _navigate_to_path(self):
        path = self.path_edit.text().strip()
        if not path:
            return
        if not self._sftp:
            QMessageBox.warning(self, "提示", "请先连接服务器")
            return
        try:
            if self._sftp.is_dir(path):
                self._current_path = self._sftp.normalize_path(path)
                self.path_edit.setText(self._current_path)
                self._refresh_file_list()
            else:
                QMessageBox.warning(self, "提示", f"'{path}' 不是有效目录")
        except Exception as e:
            QMessageBox.warning(self, "错误", f"无法访问目录: {str(e)}")

    def _browse_home(self):
        if self._sftp:
            home = self._sftp.get_home()
            self.path_edit.setText(home)
            self._navigate_to_path()

    def _refresh_file_list(self):
        if not self._sftp:
            return
        if self._loading_thread and self._loading_thread.is_alive():
            return

        self.file_list.setLoading(True)
        current_path = self._current_path
        sftp = self._sftp

        def load_directory():
            try:
                files = sftp.list_dir(current_path)
                if current_path != "/":
                    parent = os.path.dirname(current_path.rstrip('/'))
                    if not parent:
                        parent = "/"
                    parent_entry = RemoteFile(
                        name="..", path=parent, is_dir=True, size=0,
                        modify_time=datetime.now(), permissions="d---------"
                    )
                    files.insert(0, parent_entry)
                self.files_loaded.emit(files, None)
            except Exception as e:
                self.files_loaded.emit(None, str(e))

        self._loading_thread = threading.Thread(target=load_directory, daemon=True)
        self._loading_thread.start()

    def _on_directory_loaded(self, files, error):
        self._loading_thread = None
        if error:
            self.file_list.setLoading(False)
            QMessageBox.warning(self, "错误", f"无法列出目录: {error}")
            return
        if files is not None:
            self.file_list.setFiles(files)
            self.file_list.setLoading(False)

    def _on_file_double_click(self, file: RemoteFile):
        if file.is_dir:
            self._current_path = file.path
            self.path_edit.setText(file.path)
            self._refresh_file_list()
        else:
            self.file_double_clicked.emit(file)

    def _on_selection_changed(self, files: list):
        count = len(files)
        total_size = sum(f.size for f in files if not f.is_dir)
        self.selected_count_label.setText(
            f"已选文件 ({count}项, 共 {RemoteFile.format_size(total_size)})"
        )
        self.download_btn.setEnabled(count > 0)
        if files:
            file_names = [f"• {f.name} ({f.size_formatted})" for f in files[:5]]
            if len(files) > 5:
                file_names.append(f"... 还有 {len(files) - 5} 个文件")
            self.selected_list_label.setText("\n".join(file_names))
            self.selected_list_label.setStyleSheet("padding: 8px;")
        else:
            self.selected_list_label.setText("无选中文件")
            self.selected_list_label.setStyleSheet("color: #6c757d; padding: 8px;")

    def _clear_selection(self):
        self.file_list.clearSelection()

    def _browse_local_path(self):
        path = QFileDialog.getExistingDirectory(
            self, "选择保存目录", self.local_path_edit.text()
        )
        if path:
            self.local_path_edit.setText(path)

    def _start_download(self):
        files = self.file_list.getCheckedFiles()
        if not files:
            return
        local_dir = self.local_path_edit.text()
        if not local_dir:
            QMessageBox.warning(self, "提示", "请选择保存目录")
            return

        for file in files:
            if file.is_dir:
                continue
            try:
                local_path = os.path.join(local_dir, file.name)
                task = self._downloader.create_task(file.path, local_path, file.size)
                self._downloader.start_download(task.id)
                self._add_download_widget(task)
            except Exception as e:
                QMessageBox.warning(self, "错误", f"无法下载 {file.name}: {str(e)}")

        self.file_list.clearSelection()

    def _add_download_widget(self, task: DownloadTask):
        widget = DownloadItemWidget(task)
        widget.pause_clicked.connect(self._on_pause_clicked)
        widget.resume_clicked.connect(self._on_resume_clicked)
        widget.cancel_clicked.connect(self._on_cancel_clicked)
        widget.open_clicked.connect(self._on_open_clicked)

        self.download_container_layout.insertWidget(
            self.download_container_layout.count() - 1, widget
        )
        self._download_widgets[task.id] = widget

    def _on_pause_clicked(self, task_id: str):
        if self._downloader:
            self._downloader.pause_download(task_id)

    def _on_resume_clicked(self, task_id: str):
        if self._downloader:
            self._downloader.resume_download(task_id)

    def _on_cancel_clicked(self, task_id: str):
        if self._downloader:
            self._downloader.cancel_download(task_id)

    def _on_open_clicked(self, task_id: str):
        task = self._downloader.get_task(task_id) if self._downloader else None
        if task and task.local_path:
            if platform.system() == "Windows":
                os.startfile(task.local_path)
            elif platform.system() == "Darwin":
                subprocess.run(["open", task.local_path])
            else:
                subprocess.run(["xdg-open", task.local_path])

    def _on_download_progress(self, task_id: str, downloaded: int, total: int):
        pass

    def _on_download_complete(self, task_id: str, local_path: str):
        pass

    def _on_download_error(self, task_id: str, error: str):
        pass

    def _update_progress(self):
        if not self._downloader:
            return
        for task_id, widget in list(self._download_widgets.items()):
            task = self._downloader.get_task(task_id)
            if task:
                widget.update_task(task)
        progress = self._downloader.get_total_progress()
        self.total_progress_label.setText(
            f"总进度: {progress['percentage']:.1f}% | "
            f"已完成: {progress['completed_count']}/{progress['total_count']}"
        )

    def _clear_completed_downloads(self):
        if not self._downloader:
            return
        finished = {DownloadStatus.COMPLETED, DownloadStatus.FAILED, DownloadStatus.CANCELLED}
        to_remove = []
        for task_id, widget in self._download_widgets.items():
            task = self._downloader.get_task(task_id)
            if task and task.status in finished:
                to_remove.append(task_id)
        for task_id in to_remove:
            widget = self._download_widgets.pop(task_id)
            self.download_container_layout.removeWidget(widget)
            widget.deleteLater()
            self._downloader.remove_task(task_id)

    def close(self):
        if self._downloader:
            self._downloader.stop()
        self._update_timer.stop()
