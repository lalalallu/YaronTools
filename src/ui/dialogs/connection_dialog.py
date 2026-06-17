"""
连接配置对话框 - 支持直接连接和跳板机连接，支持保存配置
"""
import os
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QLineEdit, QPushButton, QSpinBox, QRadioButton,
    QButtonGroup, QCheckBox, QFileDialog, QMessageBox, QGroupBox,
    QWidget, QComboBox
)
from PyQt6.QtCore import Qt, pyqtSignal
from typing import Optional

from models.server import ServerConfig, JumpChain, AuthType
from config import ConfigManager, SavedConnection


class ConnectionDialog(QDialog):
    """连接配置对话框"""
    
    connection_established = pyqtSignal(object)  # JumpChain
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("新建连接配置")
        self.setMinimumWidth(550)
        self._jump_chain = None
        self._config_manager = ConfigManager()
        self._setup_ui()
        self._load_saved_configs()
    
    def _setup_ui(self):
        """设置界面"""
        layout = QVBoxLayout(self)
        
        # 配置名称
        name_layout = QHBoxLayout()
        name_layout.addWidget(QLabel("配置名称:"))
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("我的服务器配置")
        name_layout.addWidget(self.name_edit)
        layout.addLayout(name_layout)
        
        # 连接模式选择
        mode_group = QGroupBox("连接模式")
        mode_layout = QVBoxLayout(mode_group)
        
        mode_btn_layout = QHBoxLayout()
        self.direct_radio = QRadioButton("直接连接")
        self.jump_radio = QRadioButton("通过跳板机连接")
        self.direct_radio.setChecked(True)
        
        mode_btn_layout.addWidget(self.direct_radio)
        mode_btn_layout.addWidget(self.jump_radio)
        mode_btn_layout.addStretch()
        mode_layout.addLayout(mode_btn_layout)
        
        # 保存配置下拉框
        saved_layout = QHBoxLayout()
        saved_layout.addWidget(QLabel("已保存配置:"))
        self.saved_combo = QComboBox()
        self.saved_combo.setMinimumWidth(200)
        saved_layout.addWidget(self.saved_combo)
        
        self.load_btn = QPushButton("加载")
        self.load_btn.clicked.connect(self._load_selected_config)
        saved_layout.addWidget(self.load_btn)
        
        self.delete_btn = QPushButton("删除")
        self.delete_btn.clicked.connect(self._delete_selected_config)
        saved_layout.addWidget(self.delete_btn)
        
        saved_layout.addStretch()
        mode_layout.addLayout(saved_layout)
        
        layout.addWidget(mode_group)
        
        # 跳板机设置组（默认隐藏）
        self.jump_group = QGroupBox("跳板机设置")
        jump_layout = QGridLayout(self.jump_group)
        
        jump_layout.addWidget(QLabel("主机地址:"), 0, 0)
        self.jump_host_edit = QLineEdit()
        self.jump_host_edit.setPlaceholderText("102.6.7.8")
        jump_layout.addWidget(self.jump_host_edit, 0, 1)
        
        jump_layout.addWidget(QLabel("端口:"), 0, 2)
        self.jump_port_spin = QSpinBox()
        self.jump_port_spin.setRange(1, 65535)
        self.jump_port_spin.setValue(22)
        jump_layout.addWidget(self.jump_port_spin, 0, 3)
        
        jump_layout.addWidget(QLabel("用户名:"), 1, 0)
        self.jump_user_edit = QLineEdit()
        self.jump_user_edit.setPlaceholderText("jump_user")
        jump_layout.addWidget(self.jump_user_edit, 1, 1, 1, 3)
        
        # 跳板机认证方式
        jump_auth_widget = self._create_auth_widget("jump", default_key_path="~/.ssh/id_rsa")
        jump_layout.addWidget(jump_auth_widget, 2, 0, 1, 4)
        
        self.jump_group.hide()
        layout.addWidget(self.jump_group)
        
        # 目标服务器设置组
        target_group = QGroupBox("目标服务器设置")
        target_layout = QGridLayout(target_group)
        
        target_layout.addWidget(QLabel("主机地址:"), 0, 0)
        self.target_host_edit = QLineEdit()
        self.target_host_edit.setPlaceholderText("192.168.1.235")
        target_layout.addWidget(self.target_host_edit, 0, 1)
        
        target_layout.addWidget(QLabel("端口:"), 0, 2)
        self.target_port_spin = QSpinBox()
        self.target_port_spin.setRange(1, 65535)
        self.target_port_spin.setValue(22)
        target_layout.addWidget(self.target_port_spin, 0, 3)
        
        target_layout.addWidget(QLabel("用户名:"), 1, 0)
        self.target_user_edit = QLineEdit()
        self.target_user_edit.setPlaceholderText("target_user")
        target_layout.addWidget(self.target_user_edit, 1, 1, 1, 3)
        
        # 目标服务器认证方式
        target_auth_widget = self._create_auth_widget("target", default_password=True)
        target_layout.addWidget(target_auth_widget, 2, 0, 1, 4)
        
        layout.addWidget(target_group)
        
        # 保存密码选项
        self.save_password_check = QCheckBox("保存密码 (不推荐)")
        layout.addWidget(self.save_password_check)
        
        # 按钮
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        self.test_btn = QPushButton("测试连接")
        self.test_btn.clicked.connect(self._test_connection)
        button_layout.addWidget(self.test_btn)
        
        self.cancel_btn = QPushButton("取消")
        self.cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_btn)
        
        self.save_btn = QPushButton("保存并连接")
        self.save_btn.setDefault(True)
        self.save_btn.clicked.connect(self._save_and_connect)
        button_layout.addWidget(self.save_btn)
        
        layout.addLayout(button_layout)
        
        # 连接模式切换信号
        self.direct_radio.toggled.connect(self._on_mode_changed)
        self.jump_radio.toggled.connect(self._on_mode_changed)
    
    def _create_auth_widget(self, prefix: str, 
                            default_key_path: str = "",
                            default_password: bool = False) -> QWidget:
        """创建认证方式组件"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # 认证方式选择
        auth_layout = QHBoxLayout()
        auth_label = QLabel("认证方式:")
        auth_layout.addWidget(auth_label)
        
        password_radio = QRadioButton("密码")
        key_radio = QRadioButton("SSH密钥")
        
        auth_group = QButtonGroup(widget)
        auth_group.addButton(password_radio, 0)
        auth_group.addButton(key_radio, 1)
        
        if default_password:
            password_radio.setChecked(True)
        else:
            key_radio.setChecked(True)
        
        auth_layout.addWidget(password_radio)
        auth_layout.addWidget(key_radio)
        auth_layout.addStretch()
        layout.addLayout(auth_layout)
        
        # 密码输入
        password_widget = QWidget()
        password_layout = QHBoxLayout(password_widget)
        password_layout.setContentsMargins(0, 0, 0, 0)
        
        password_layout.addWidget(QLabel("密码:"))
        password_edit = QLineEdit()
        password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        password_edit.setPlaceholderText("输入密码")
        password_layout.addWidget(password_edit)
        
        layout.addWidget(password_widget)
        
        # 密钥文件输入
        key_widget = QWidget()
        key_layout = QHBoxLayout(key_widget)
        key_layout.setContentsMargins(0, 0, 0, 0)
        
        key_layout.addWidget(QLabel("密钥文件:"))
        key_edit = QLineEdit()
        key_edit.setText(default_key_path)
        key_edit.setPlaceholderText("~/.ssh/id_rsa")
        key_layout.addWidget(key_edit)
        
        browse_btn = QPushButton("浏览")
        browse_btn.clicked.connect(
            lambda: self._browse_key_file(key_edit)
        )
        key_layout.addWidget(browse_btn)
        
        layout.addWidget(key_widget)
        
        # 密钥密码
        passphrase_widget = QWidget()
        passphrase_layout = QHBoxLayout(passphrase_widget)
        passphrase_layout.setContentsMargins(0, 0, 0, 0)
        
        passphrase_layout.addWidget(QLabel("密钥密码:"))
        passphrase_edit = QLineEdit()
        passphrase_edit.setEchoMode(QLineEdit.EchoMode.Password)
        passphrase_edit.setPlaceholderText("(可选)")
        passphrase_layout.addWidget(passphrase_edit)
        
        layout.addWidget(passphrase_widget)
        
        # 保存引用
        setattr(self, f"_{prefix}_password_radio", password_radio)
        setattr(self, f"_{prefix}_key_radio", key_radio)
        setattr(self, f"_{prefix}_auth_group", auth_group)
        setattr(self, f"_{prefix}_password_widget", password_widget)
        setattr(self, f"_{prefix}_key_widget", key_widget)
        setattr(self, f"_{prefix}_password_edit", password_edit)
        setattr(self, f"_{prefix}_key_edit", key_edit)
        setattr(self, f"_{prefix}_passphrase_edit", passphrase_edit)
        
        # 连接信号
        auth_group.buttonClicked.connect(
            lambda btn: self._on_auth_changed(prefix, btn)
        )
        
        # 初始状态
        if default_password:
            key_widget.hide()
            passphrase_widget.hide()
        else:
            password_widget.hide()
        
        return widget
    
    def _on_mode_changed(self):
        """连接模式改变"""
        if self.direct_radio.isChecked():
            self.jump_group.hide()
        else:
            self.jump_group.show()
    
    def _on_auth_changed(self, prefix: str, button: QRadioButton):
        """认证方式改变"""
        auth_group = getattr(self, f"_{prefix}_auth_group")
        is_password = (auth_group.id(button) == 0)
        
        password_widget = getattr(self, f"_{prefix}_password_widget")
        key_widget = getattr(self, f"_{prefix}_key_widget")
        passphrase_widget = getattr(self, f"_{prefix}_passphrase_edit").parent()
        
        if is_password:
            password_widget.show()
            key_widget.hide()
            passphrase_widget.hide()
        else:
            password_widget.hide()
            key_widget.show()
            passphrase_widget.show()
    
    def _browse_key_file(self, edit: QLineEdit):
        """浏览密钥文件"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择SSH密钥文件", 
            edit.text() or os.path.expanduser("~/.ssh"),
            "所有文件 (*);;PEM文件 (*.pem);;PPK文件 (*.ppk)"
        )
        if file_path:
            edit.setText(file_path)
    
    def _load_saved_configs(self):
        """加载已保存的配置列表"""
        self.saved_combo.clear()
        self.saved_combo.addItem("-- 选择已保存配置 --")
        
        names = self._config_manager.get_names()
        for name in names:
            self.saved_combo.addItem(name)
    
    def _load_selected_config(self):
        """加载选中的配置"""
        index = self.saved_combo.currentIndex()
        if index <= 0:
            return
        
        name = self.saved_combo.currentText()
        config = self._config_manager.get_by_name(name)
        if not config:
            return
        
        # 填充表单
        self.name_edit.setText(config.name)
        
        if config.use_jump:
            self.jump_radio.setChecked(True)
            self.jump_host_edit.setText(config.jump_host or "")
            self.jump_port_spin.setValue(config.jump_port)
            self.jump_user_edit.setText(config.jump_user or "")
            
            # 设置跳板机认证方式
            if config.jump_auth_type == "password":
                self._jump_password_radio.setChecked(True)
                self._jump_password_edit.setText(config.jump_password or "")
            else:
                self._jump_key_radio.setChecked(True)
                self._jump_key_edit.setText(config.jump_key_path or "")
                self._jump_passphrase_edit.setText(config.jump_passphrase or "")
        else:
            self.direct_radio.setChecked(True)
        
        # 目标服务器
        self.target_host_edit.setText(config.target_host)
        self.target_port_spin.setValue(config.target_port)
        self.target_user_edit.setText(config.target_user)
        
        # 设置目标服务器认证方式
        if config.target_auth_type == "password":
            self._target_password_radio.setChecked(True)
            self._target_password_edit.setText(config.target_password or "")
        else:
            self._target_key_radio.setChecked(True)
            self._target_key_edit.setText(config.target_key_path or "")
            self._target_passphrase_edit.setText(config.target_passphrase or "")
        
        self.save_password_check.setChecked(bool(config.target_password or config.jump_password))
    
    def _delete_selected_config(self):
        """删除选中的配置"""
        index = self.saved_combo.currentIndex()
        if index <= 0:
            return
        
        name = self.saved_combo.currentText()
        reply = QMessageBox.question(
            self, "确认删除",
            f"确定要删除配置 '{name}' 吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            self._config_manager.delete(name)
            self._load_saved_configs()
            QMessageBox.information(self, "成功", "配置已删除")
    
    def _get_server_config(self, prefix: str) -> Optional[ServerConfig]:
        """获取服务器配置"""
        if prefix == "jump":
            host_edit = self.jump_host_edit
            port_spin = self.jump_port_spin
            user_edit = self.jump_user_edit
        else:
            host_edit = self.target_host_edit
            port_spin = self.target_port_spin
            user_edit = self.target_user_edit
        
        if not host_edit.text().strip():
            return None
        
        auth_group = getattr(self, f"_{prefix}_auth_group")
        is_password = (auth_group.checkedId() == 0)
        
        password_edit = getattr(self, f"_{prefix}_password_edit")
        key_edit = getattr(self, f"_{prefix}_key_edit")
        passphrase_edit = getattr(self, f"_{prefix}_passphrase_edit")
        
        config = ServerConfig(
            host=host_edit.text().strip(),
            port=port_spin.value(),
            username=user_edit.text().strip(),
            auth_type=AuthType.PASSWORD if is_password else AuthType.KEY
        )
        
        if is_password:
            config.password = password_edit.text()
        else:
            config.private_key_path = key_edit.text().strip()
            config.passphrase = passphrase_edit.text() or None
        
        return config
    
    def _validate_input(self) -> tuple:
        """验证输入"""
        target_host = self.target_host_edit.text().strip()
        target_user = self.target_user_edit.text().strip()
        
        if not target_host:
            QMessageBox.warning(self, "提示", "请输入目标服务器地址")
            return False, None, None
        
        if not target_user:
            QMessageBox.warning(self, "提示", "请输入目标服务器用户名")
            return False, None, None
        
        # 获取配置
        target_config = self._get_server_config("target")
        
        if not target_config or not target_config.validate():
            QMessageBox.warning(self, "提示", "目标服务器配置不完整")
            return False, None, None
        
        # 如果是跳板机模式
        if self.jump_radio.isChecked():
            jump_config = self._get_server_config("jump")
            if not jump_config or not jump_config.validate():
                QMessageBox.warning(self, "提示", "跳板机配置不完整")
                return False, None, None
        else:
            jump_config = None
        
        return True, jump_config, target_config
    
    def _test_connection(self):
        """测试连接"""
        valid, jump_config, target_config = self._validate_input()
        if not valid:
            return
        
        self.test_btn.setEnabled(False)
        self.test_btn.setText("测试中...")
        
        try:
            from core.connection import SSHConnectionManager
            
            jump_chain = JumpChain()
            if jump_config:
                jump_chain.add_jump_server(jump_config)
            jump_chain.set_target(target_config)
            
            with SSHConnectionManager() as conn:
                if conn.connect(jump_chain):
                    if jump_config:
                        QMessageBox.information(
                            self, "成功", 
                            f"连接成功!\n\n跳板机: {jump_config}\n目标服务器: {target_config}"
                        )
                    else:
                        QMessageBox.information(
                            self, "成功", 
                            f"连接成功!\n\n目标服务器: {target_config}"
                        )
        except Exception as e:
            QMessageBox.critical(self, "连接失败", str(e))
        finally:
            self.test_btn.setEnabled(True)
            self.test_btn.setText("测试连接")
    
    def _save_and_connect(self):
        """保存并连接"""
        valid, jump_config, target_config = self._validate_input()
        if not valid:
            return
        
        # 保存配置
        name = self.name_edit.text().strip()
        if not name:
            name = f"{target_config.host}:{target_config.port}"
        
        save_password = self.save_password_check.isChecked()
        
        saved_conn = SavedConnection(
            name=name,
            use_jump=self.jump_radio.isChecked(),
            target_host=target_config.host,
            target_port=target_config.port,
            target_user=target_config.username,
            target_auth_type="password" if target_config.auth_type == AuthType.PASSWORD else "key",
            target_password=target_config.password if save_password and target_config.auth_type == AuthType.PASSWORD else None,
            target_key_path=target_config.private_key_path if target_config.auth_type == AuthType.KEY else None,
            target_passphrase=target_config.passphrase if save_password and target_config.auth_type == AuthType.KEY else None
        )
        
        if self.jump_radio.isChecked() and jump_config:
            saved_conn.jump_host = jump_config.host
            saved_conn.jump_port = jump_config.port
            saved_conn.jump_user = jump_config.username
            saved_conn.jump_auth_type = "password" if jump_config.auth_type == AuthType.PASSWORD else "key"
            saved_conn.jump_password = jump_config.password if save_password and jump_config.auth_type == AuthType.PASSWORD else None
            saved_conn.jump_key_path = jump_config.private_key_path if jump_config.auth_type == AuthType.KEY else None
            saved_conn.jump_passphrase = jump_config.passphrase if save_password and jump_config.auth_type == AuthType.KEY else None
        
        self._config_manager.add(saved_conn)
        
        # 创建连接
        self._jump_chain = JumpChain()
        if jump_config:
            self._jump_chain.add_jump_server(jump_config)
        self._jump_chain.set_target(target_config)
        
        self.connection_established.emit(self._jump_chain)
        self.accept()
    
    def get_jump_chain(self) -> Optional[JumpChain]:
        """获取跳板机链配置"""
        return self._jump_chain
