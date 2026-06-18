import os

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QTabWidget,
    QFrame, QCheckBox, QStatusBar,
    QToolBar, QMenu, QMenuBar, QMessageBox
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtGui import QAction, QShortcut, QKeySequence

from models.server import JumpChain
from core.connection import SSHConnectionManager
from core.sftp_client import RemoteFile
from core.sftp_extended import SFTPClientWrapperExt
from core.sudo_executor import SudoExecutor
from core.backup_manager import BackupManager
from core.conflict_detector import ConflictDetector

from ui.dialogs.connection_dialog import ConnectionDialog
from ui.tabs.file_browser_tab import FileBrowserTab
from ui.tabs.config_editor_tab import ConfigEditorTab
from ui.tabs.pcd_editor_tab import PCDEditorTab


class UnifiedMainWindow(QMainWindow):
    connection_established = pyqtSignal()
    connection_lost = pyqtSignal()
    remote_path_changed = pyqtSignal(str)

    def __init__(self):
        super().__init__()

        self._connection: SSHConnectionManager = None
        self._sftp: SFTPClientWrapperExt = None
        self._sudo_executor: SudoExecutor = None
        self._backup_manager: BackupManager = None
        self._conflict_detector: ConflictDetector = None

        self._jump_chain: JumpChain = None
        self._current_remote_path: str = "/"
        self._sudo_password: str = ""

        self._file_browser_tab: FileBrowserTab = None
        self._config_editor_tab: ConfigEditorTab = None
        self._pcd_editor_tab: PCDEditorTab = None

        self._setup_ui()
        self._setup_menu()
        self._setup_toolbar()
        self._setup_statusbar()
        self._setup_shortcuts()
        self._connect_signals()

    def _setup_ui(self):
        self.setWindowTitle("YaronTools")
        self.setGeometry(100, 100, 1400, 900)
        self.setMinimumSize(1200, 700)

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        conn_panel = QFrame()
        conn_panel.setFrameStyle(QFrame.Shape.StyledPanel)
        conn_panel.setMaximumHeight(90)
        conn_layout = QVBoxLayout(conn_panel)
        conn_layout.setContentsMargins(8, 6, 8, 6)
        conn_layout.setSpacing(4)

        top_row = QHBoxLayout()
        self._status_indicator = QLabel("● 未连接")
        self._status_indicator.setStyleSheet("color: gray; font-weight: bold;")
        top_row.addWidget(self._status_indicator)
        top_row.addStretch()

        conn_layout.addLayout(top_row)

        path_row = QHBoxLayout()
        path_row.addWidget(QLabel("远程路径:"))

        self._path_edit = QLineEdit()
        self._path_edit.setPlaceholderText("/")
        self._path_edit.returnPressed.connect(self._navigate_to_path)
        path_row.addWidget(self._path_edit)

        self._jump_btn = QPushButton("跳转")
        self._jump_btn.clicked.connect(self._navigate_to_path)
        self._jump_btn.setEnabled(False)
        path_row.addWidget(self._jump_btn)

        self._disconnect_btn = QPushButton("断开")
        self._disconnect_btn.clicked.connect(self._do_disconnect)
        self._disconnect_btn.setEnabled(False)
        path_row.addWidget(self._disconnect_btn)

        conn_layout.addLayout(path_row)

        sudo_row = QHBoxLayout()
        self._sudo_check = QCheckBox("使用 sudo 提权写入")
        self._sudo_check.setChecked(True)
        self._sudo_check.toggled.connect(self._on_sudo_toggle)
        sudo_row.addWidget(self._sudo_check)

        sudo_row.addWidget(QLabel("sudo 密码:"))
        self._sudo_password_edit = QLineEdit()
        self._sudo_password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._sudo_password_edit.setMaximumWidth(160)
        self._sudo_password_edit.setPlaceholderText("留空同SSH密码")
        sudo_row.addWidget(self._sudo_password_edit)

        sudo_row.addWidget(QLabel("(留空则同 SSH 密码)"))
        sudo_row.addStretch()

        conn_layout.addLayout(sudo_row)

        layout.addWidget(conn_panel)

        self._tab_widget = QTabWidget()
        layout.addWidget(self._tab_widget)

        self._file_browser_tab = FileBrowserTab()
        self._tab_widget.addTab(self._file_browser_tab, "📁 文件浏览")

        self._config_editor_tab = ConfigEditorTab()
        self._tab_widget.addTab(self._config_editor_tab, "⚙️ 配置编辑")

        self._pcd_editor_tab = PCDEditorTab()
        self._tab_widget.addTab(self._pcd_editor_tab, "🔲 PCD编辑")

        self._tab_widget.currentChanged.connect(self._on_tab_changed)

    def _setup_menu(self):
        menubar = self.menuBar()

        file_menu = menubar.addMenu("文件(&F)")

        connect_action = QAction("新建连接(&N)", self)
        connect_action.setShortcut("Ctrl+N")
        connect_action.triggered.connect(self._show_connection_dialog)
        file_menu.addAction(connect_action)

        disconnect_action = QAction("断开连接(&D)", self)
        disconnect_action.setShortcut("Ctrl+D")
        disconnect_action.triggered.connect(self._do_disconnect)
        file_menu.addAction(disconnect_action)

        file_menu.addSeparator()

        exit_action = QAction("退出(&X)", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        edit_menu = menubar.addMenu("编辑(&E)")

        undo_action = QAction("撤销(&Z)", self)
        undo_action.setShortcut("Ctrl+Z")
        undo_action.triggered.connect(self._do_undo)
        edit_menu.addAction(undo_action)

        save_action = QAction("保存(&S)", self)
        save_action.setShortcut("Ctrl+S")
        save_action.triggered.connect(self._do_save)
        edit_menu.addAction(save_action)

        edit_menu.addSeparator()

        refresh_action = QAction("刷新(&R)", self)
        refresh_action.setShortcut("F5")
        refresh_action.triggered.connect(self._do_refresh)
        edit_menu.addAction(refresh_action)

        tools_menu = menubar.addMenu("工具(&T)")

        file_browse_action = QAction("文件浏览", self)
        file_browse_action.setShortcut("Ctrl+1")
        file_browse_action.triggered.connect(lambda: self._tab_widget.setCurrentIndex(0))
        tools_menu.addAction(file_browse_action)

        config_action = QAction("配置编辑", self)
        config_action.setShortcut("Ctrl+2")
        config_action.triggered.connect(lambda: self._tab_widget.setCurrentIndex(1))
        tools_menu.addAction(config_action)

        pcd_action = QAction("PCD编辑", self)
        pcd_action.setShortcut("Ctrl+3")
        pcd_action.triggered.connect(lambda: self._tab_widget.setCurrentIndex(2))
        tools_menu.addAction(pcd_action)

        help_menu = menubar.addMenu("帮助(&H)")
        about_action = QAction("关于(&A)", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)

    def _setup_toolbar(self):
        toolbar = QToolBar("主工具栏")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        connect_btn = QPushButton("连接")
        connect_btn.clicked.connect(self._show_connection_dialog)
        toolbar.addWidget(connect_btn)

        disconnect_btn = QPushButton("断开")
        disconnect_btn.clicked.connect(self._do_disconnect)
        toolbar.addWidget(disconnect_btn)

        toolbar.addSeparator()

        refresh_btn = QPushButton("刷新")
        refresh_btn.clicked.connect(self._do_refresh)
        toolbar.addWidget(refresh_btn)

        save_btn = QPushButton("保存")
        save_btn.clicked.connect(self._do_save)
        toolbar.addWidget(save_btn)

        undo_btn = QPushButton("撤销")
        undo_btn.clicked.connect(self._do_undo)
        toolbar.addWidget(undo_btn)

    def _setup_statusbar(self):
        self.statusBar().showMessage("就绪")

    def _setup_shortcuts(self):
        QShortcut(QKeySequence("Ctrl+N"), self).activated.connect(self._show_connection_dialog)
        QShortcut(QKeySequence("Ctrl+D"), self).activated.connect(self._do_disconnect)
        QShortcut(QKeySequence("Ctrl+S"), self).activated.connect(self._do_save)

    def _connect_signals(self):
        self._file_browser_tab.file_double_clicked.connect(self._on_file_double_click)

    def _on_sudo_toggle(self, checked: bool):
        self._sudo_password_edit.setEnabled(checked)

    def _propagate_sudo_password(self):
        if self._sudo_check.isChecked():
            pwd = self._sudo_password_edit.text()
            if not pwd:
                pwd = self._sudo_password
            self._config_editor_tab.set_sudo_password(pwd)
            self._pcd_editor_tab.set_sudo_password(pwd)
        else:
            self._config_editor_tab.set_sudo_password("")
            self._pcd_editor_tab.set_sudo_password("")

    def _show_connection_dialog(self):
        dialog = ConnectionDialog(self)
        dialog.connection_established.connect(self._on_connection_established)
        dialog.exec()

    def _on_connection_established(self, jump_chain: JumpChain):
        try:
            self._connection = SSHConnectionManager()
            self._connection.connect(jump_chain)
            self._sftp = SFTPClientWrapperExt(self._connection)
            self._sudo_executor = SudoExecutor(self._connection)
            self._backup_manager = BackupManager(self._sudo_executor)
            self._conflict_detector = ConflictDetector()
            self._jump_chain = jump_chain
            target = jump_chain.get_target() if jump_chain else None
            self._sudo_password = target.password if target else ""

            home = self._sftp.get_home()
            self._current_remote_path = home
            self._path_edit.setText(home)

            self._file_browser_tab.set_sftp(self._sftp)
            self._file_browser_tab.set_connected(True)
            self._file_browser_tab.navigate_to(home)

            self._config_editor_tab.set_services(self._sftp, self._sudo_executor, self._backup_manager)
            self._config_editor_tab.set_connected(True)
            self._propagate_sudo_password()

            self._pcd_editor_tab.set_services(self._sftp, self._sudo_executor, self._backup_manager)
            self._pcd_editor_tab.set_connected(True)
            self._propagate_sudo_password()

            self._status_indicator.setText("● 已连接")
            self._status_indicator.setStyleSheet("color: green; font-weight: bold;")
            self._jump_btn.setEnabled(True)
            self._disconnect_btn.setEnabled(True)

            target = jump_chain.get_target() if jump_chain else None
            info = ""
            if jump_chain and len(jump_chain.servers) > 1:
                jump = jump_chain.servers[0]
                info = f"{jump.username}@{jump.host}:{jump.port} → "
            if target:
                info += f"{target.username}@{target.host}:{target.port}"
            self.statusBar().showMessage(f"已连接: {info}")

            self.connection_established.emit()

        except Exception as e:
            QMessageBox.critical(self, "连接失败", str(e))

    def _do_disconnect(self):
        self._file_browser_tab.set_connected(False)
        self._config_editor_tab.set_connected(False)
        self._pcd_editor_tab.set_connected(False)

        if self._connection:
            self._connection.close()
            self._connection = None
        self._sftp = None
        self._sudo_executor = None
        self._backup_manager = None
        self._conflict_detector = None
        self._jump_chain = None

        self._status_indicator.setText("● 未连接")
        self._status_indicator.setStyleSheet("color: gray; font-weight: bold;")
        self._path_edit.clear()
        self._jump_btn.setEnabled(False)
        self._disconnect_btn.setEnabled(False)

        self.statusBar().showMessage("已断开连接")
        self.connection_lost.emit()

    def _navigate_to_path(self):
        path = self._path_edit.text().strip()
        if not path or not self._sftp:
            return
        try:
            if self._sftp.is_dir(path):
                self._current_remote_path = self._sftp.normalize_path(path)
                self._path_edit.setText(self._current_remote_path)
                self._file_browser_tab.navigate_to(self._current_remote_path)
                self.remote_path_changed.emit(self._current_remote_path)
            else:
                self._current_remote_path = path
                self._path_edit.setText(self._current_remote_path)
                self.remote_path_changed.emit(path)
                ext = os.path.splitext(path)[1].lower()
                if ext == '.cfg':
                    self._config_editor_tab.load_file(path)
                    self._tab_widget.setCurrentIndex(1)
                elif ext == '.pcd':
                    self._pcd_editor_tab.load_file(path)
                    self._tab_widget.setCurrentIndex(2)
        except Exception as e:
            QMessageBox.warning(self, "错误", str(e))

    def _on_file_double_click(self, file: RemoteFile):
        if file.is_dir:
            self._current_remote_path = file.path
            self._path_edit.setText(file.path)
            self.remote_path_changed.emit(file.path)
            return

        ext = os.path.splitext(file.name)[1].lower()
        self._current_remote_path = file.path
        self._path_edit.setText(file.path)

        if ext == '.cfg':
            self._config_editor_tab.load_file(file.path)
            self._tab_widget.setCurrentIndex(1)
        elif ext == '.pcd':
            self._pcd_editor_tab.load_file(file.path)
            self._tab_widget.setCurrentIndex(2)

    def _on_tab_changed(self, index: int):
        if not self._sftp or not self._current_remote_path:
            return

        tab = self._tab_widget.widget(index)
        if tab is self._config_editor_tab:
            ext = os.path.splitext(self._current_remote_path)[1].lower()
            if ext == '.cfg':
                self._config_editor_tab.load_file(self._current_remote_path)
        elif tab is self._pcd_editor_tab:
            ext = os.path.splitext(self._current_remote_path)[1].lower()
            if ext == '.pcd':
                self._pcd_editor_tab.load_file(self._current_remote_path)

    def _do_save(self):
        self._propagate_sudo_password()
        current_tab = self._tab_widget.currentWidget()
        if current_tab is self._config_editor_tab:
            if not self._config_editor_tab.has_unsaved_changes():
                QMessageBox.information(self, "提示", "没有需要保存的修改。")
                return
            self._config_editor_tab.do_save()
        elif current_tab is self._pcd_editor_tab:
            if not self._pcd_editor_tab.has_unsaved_changes():
                QMessageBox.information(self, "提示", "没有需要保存的修改。")
                return
            self._pcd_editor_tab.do_save()

    def _do_undo(self):
        current_tab = self._tab_widget.currentWidget()
        if current_tab is self._config_editor_tab:
            self._config_editor_tab._do_undo()
        elif current_tab is self._pcd_editor_tab:
            self._pcd_editor_tab._do_undo_all()

    def _do_refresh(self):
        if not self._sftp:
            return
        current_tab = self._tab_widget.currentWidget()
        if current_tab is self._file_browser_tab:
            self._file_browser_tab._refresh_file_list()
        elif current_tab is self._config_editor_tab and self._current_remote_path:
            reply = QMessageBox.question(
                self, "确认刷新",
                "刷新将重新加载远程文件，未保存的修改将丢失。确定继续？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                self._config_editor_tab.load_file(self._current_remote_path)
        elif current_tab is self._pcd_editor_tab and self._current_remote_path:
            reply = QMessageBox.question(
                self, "确认刷新",
                "刷新将重新加载远程文件，未保存的修改将丢失。确定继续？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                ext = os.path.splitext(self._current_remote_path)[1].lower()
                if ext == '.pcd':
                    self._pcd_editor_tab.load_file(self._current_remote_path)

    def _show_about(self):
        QMessageBox.about(
            self, "关于",
            "<h3>YaronTools</h3>"
            "<p>版本: 2.0.0</p>"
            "<p>统一图形化SSH远程管理工具，整合三大功能模块：</p>"
            "<ul>"
            "<li>📁 <b>文件浏览</b> — 远程文件浏览与下载，支持断点续传</li>"
            "<li>⚙️ <b>配置编辑</b> — 远程 INI 配置文件的在线编辑</li>"
            "<li>🔲 <b>PCD编辑</b> — 远程 PCD 点云坐标文件的图形化编辑</li>"
            "</ul>"
            "<p>功能特性:</p>"
            "<ul>"
            "<li>SSH 跳板机连接</li>"
            "<li>大文件断点续传、并行下载</li>"
            "<li>sudo 提权写入</li>"
            "<li>远程文件备份与冲突检测</li>"
            "</ul>"
        )

    def closeEvent(self, event):
        if self._file_browser_tab:
            self._file_browser_tab.close()
        if self._connection:
            self._connection.close()
        event.accept()
