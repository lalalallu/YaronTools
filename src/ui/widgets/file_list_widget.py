"""
文件列表组件 - 显示远程文件列表
"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableView, 
    QLineEdit, QPushButton, QLabel, QHeaderView,
    QAbstractItemView, QCheckBox
)
from PyQt6.QtCore import Qt, pyqtSignal, QAbstractTableModel, QModelIndex
from PyQt6.QtGui import QFont
from typing import List, Set
from datetime import datetime

from core.sftp_client import RemoteFile


class FileModel(QAbstractTableModel):
    """文件列表数据模型"""
    
    HEADERS = ["选择", "类型", "大小", "修改时间", "文件名"]
    
    def __init__(self, files: List[RemoteFile] = None):
        super().__init__()
        self._files = files or []
        self._checked: Set[int] = set()
    
    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return len(self._files)
    
    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return len(self.HEADERS)
    
    def headerData(self, section: int, orientation: Qt.Orientation, 
                   role: int = Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return self.HEADERS[section]
        return None
    
    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        
        row = index.row()
        col = index.column()
        file = self._files[row]
        
        if role == Qt.ItemDataRole.DisplayRole:
            if col == 1:  # 类型
                return file.icon
            elif col == 2:  # 大小
                return file.size_formatted
            elif col == 3:  # 修改时间
                return file.modify_time.strftime("%Y-%m-%d %H:%M")
            elif col == 4:  # 文件名
                return file.name
        
        elif role == Qt.ItemDataRole.CheckStateRole and col == 0:
            return Qt.CheckState.Checked if row in self._checked else Qt.CheckState.Unchecked
        
        elif role == Qt.ItemDataRole.FontRole and col == 4:
            font = QFont()
            if file.is_dir:
                font.setBold(True)
            return font
        
        elif role == Qt.ItemDataRole.TextAlignmentRole:
            if col == 2:  # 大小右对齐
                return Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            return Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        
        return None
    
    def setData(self, index: QModelIndex, value, role: int = Qt.ItemDataRole.EditRole) -> bool:
        if role == Qt.ItemDataRole.CheckStateRole and index.column() == 0:
            row = index.row()
            if value == Qt.CheckState.Checked.value:
                self._checked.add(row)
            else:
                self._checked.discard(row)
            self.dataChanged.emit(index, index)
            return True
        return False
    
    def flags(self, index: QModelIndex):
        default_flags = super().flags(index)
        if index.column() == 0:
            return default_flags | Qt.ItemFlag.ItemIsUserCheckable
        return default_flags
    
    def setFiles(self, files: List[RemoteFile]):
        """设置文件列表"""
        self.beginResetModel()
        self._files = files
        self._checked.clear()
        self.endResetModel()
    
    def getFiles(self) -> List[RemoteFile]:
        """获取所有文件"""
        return self._files
    
    def getCheckedFiles(self) -> List[RemoteFile]:
        """获取选中的文件"""
        return [self._files[i] for i in sorted(self._checked) if i < len(self._files)]
    
    def checkAll(self, checked: bool):
        """全选/取消全选"""
        self.beginResetModel()
        if checked:
            self._checked = set(range(len(self._files)))
        else:
            self._checked.clear()
        self.endResetModel()
    
    def getFile(self, row: int) -> RemoteFile:
        """获取指定行的文件"""
        return self._files[row]


class FileListWidget(QWidget):
    """文件列表组件（支持分页加载）"""
    
    PAGE_SIZE = 200  # 每页加载200个文件
    
    file_selected = pyqtSignal(object)  # RemoteFile
    file_double_clicked = pyqtSignal(object)  # RemoteFile (用于进入目录)
    selection_changed = pyqtSignal(list)  # List[RemoteFile]
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._all_files: List[RemoteFile] = []  # 完整文件列表
        self._displayed_count: int = 0           # 当前已显示数量
        self._setup_ui()
    
    def _setup_ui(self):
        """设置界面"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # 工具栏
        toolbar = QHBoxLayout()
        
        # 全选复选框
        self.select_all_check = QCheckBox("全选")
        self.select_all_check.stateChanged.connect(self._on_select_all)
        toolbar.addWidget(self.select_all_check)
        
        toolbar.addStretch()
        
        # 搜索框
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("🔍 搜索文件...")
        self.search_edit.textChanged.connect(self._on_search)
        self.search_edit.setMaximumWidth(200)
        toolbar.addWidget(self.search_edit)
        
        # 刷新按钮
        self.refresh_btn = QPushButton("刷新")
        toolbar.addWidget(self.refresh_btn)
        
        layout.addLayout(toolbar)
        
        # 文件列表表格
        self.table = QTableView()
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(True)
        
        # 设置模型
        self.model = FileModel()
        self.table.setModel(self.model)
        
        # 设置列宽
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        
        self.table.setColumnWidth(0, 50)
        self.table.setColumnWidth(1, 50)
        self.table.setColumnWidth(2, 100)
        self.table.setColumnWidth(3, 150)
        
        # 连接信号
        self.table.doubleClicked.connect(self._on_double_click)
        self.model.dataChanged.connect(self._on_data_changed)
        
        layout.addWidget(self.table)
        
        # 底部区域：状态栏 + 加载更多按钮
        bottom_layout = QHBoxLayout()
        
        # 状态栏
        self.status_label = QLabel("共 0 个项目")
        bottom_layout.addWidget(self.status_label)
        
        bottom_layout.addStretch()
        
        # 加载更多按钮（初始隐藏）
        self.load_more_btn = QPushButton("加载更多...")
        self.load_more_btn.setFixedWidth(120)
        self.load_more_btn.clicked.connect(self._load_more)
        self.load_more_btn.hide()
        bottom_layout.addWidget(self.load_more_btn)
        
        layout.addLayout(bottom_layout)
        
        # 加载覆盖层（初始隐藏）
        self.loading_overlay = QLabel("正在加载目录...", self.table)
        self.loading_overlay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.loading_overlay.setStyleSheet("""
            QLabel {
                background-color: rgba(255, 255, 255, 200);
                color: #0d6efd;
                font-size: 16px;
                font-weight: bold;
                border: none;
                padding: 20px;
            }
        """)
        self.loading_overlay.hide()
    
    def resizeEvent(self, event):
        """窗口大小变化时调整覆盖层位置"""
        super().resizeEvent(event)
        if hasattr(self, 'loading_overlay') and self.loading_overlay:
            self.loading_overlay.setGeometry(0, 0, self.table.width(), self.table.height())
    
    def setLoading(self, loading: bool):
        """设置加载状态"""
        if loading:
            self.loading_overlay.setGeometry(0, 0, self.table.width(), self.table.height())
            self.loading_overlay.show()
            self.table.setEnabled(False)
            self.load_more_btn.hide()
            self.status_label.setText("正在加载...")
        else:
            self.loading_overlay.hide()
            self.table.setEnabled(True)
            self._update_status()
    
    def setFiles(self, files: List[RemoteFile]):
        """
        设置完整文件列表（只显示前 PAGE_SIZE 个）
        
        Args:
            files: 完整排序后的文件列表（含 .. 条目）
        """
        self._all_files = files
        self._displayed_count = 0
        self._show_page(0)
    
    def _show_page(self, start_index: int):
        """
        从 start_index 开始显示一页数据
        
        Args:
            start_index: 起始索引
        """
        end = min(start_index + self.PAGE_SIZE, len(self._all_files))
        page_files = self._all_files[:end]
        self._displayed_count = end
        
        self.model.setFiles(page_files)
        self._update_status()
        
        # 控制"加载更多"按钮显示
        has_more = self._displayed_count < len(self._all_files)
        self.load_more_btn.setVisible(has_more)
    
    def _load_more(self):
        """加载更多文件"""
        if self._displayed_count < len(self._all_files):
            self._show_page(self._displayed_count)
    
    def getCheckedFiles(self) -> List[RemoteFile]:
        """获取选中的文件"""
        return self.model.getCheckedFiles()
    
    def clearSelection(self):
        """清除选择"""
        self.model.checkAll(False)
        self.select_all_check.setChecked(False)
    
    def _on_select_all(self, state: int):
        """全选/取消全选"""
        checked = state == Qt.CheckState.Checked.value
        self.model.checkAll(checked)
        self._emit_selection()
    
    def _on_search(self, text: str):
        """搜索过滤"""
        # TODO: 实现搜索过滤
        pass
    
    def _on_double_click(self, index: QModelIndex):
        """双击事件"""
        file = self.model.getFile(index.row())
        self.file_double_clicked.emit(file)
    
    def _on_data_changed(self):
        """数据变化"""
        self._emit_selection()
    
    def _emit_selection(self):
        """发送选择变化信号"""
        checked = self.model.getCheckedFiles()
        self.selection_changed.emit(checked)
    
    def _update_status(self):
        """更新状态栏"""
        visible_files = self.model.getFiles()
        dirs = sum(1 for f in visible_files if f.is_dir)
        file_count = len(visible_files) - dirs
        total_size = sum(f.size for f in visible_files if not f.is_dir)
        
        total_all = len(self._all_files)
        if total_all > self._displayed_count:
            self.status_label.setText(
                f"已显示 {self._displayed_count}/{total_all} 个项目 "
                f"({dirs} 个文件夹, {file_count} 个文件, "
                f"总大小: {RemoteFile.format_size(total_size)})"
            )
        else:
            self.status_label.setText(
                f"共 {len(visible_files)} 个项目 "
                f"({dirs} 个文件夹, {file_count} 个文件, "
                f"总大小: {RemoteFile.format_size(total_size)})"
            )
