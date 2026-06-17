"""
服务器信息组件 - 显示连接状态
"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QPushButton, QFrame
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont

from models.server import JumpChain


class ServerInfoWidget(QFrame):
    """服务器信息组件"""
    
    disconnect_clicked = pyqtSignal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._jump_chain = None
        self._connected = False
        self._setup_ui()
    
    def _setup_ui(self):
        """设置界面"""
        self.setFrameStyle(QFrame.Shape.StyledPanel | QFrame.Shadow.Raised)
        self.setStyleSheet("""
            ServerInfoWidget {
                background-color: #f8f9fa;
                border: 1px solid #dee2e6;
                border-radius: 4px;
                padding: 8px;
            }
        """)
        self.setMinimumWidth(180)
        self.setMaximumWidth(250)
        
        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        
        # 标题
        title_label = QLabel("连接信息")
        title_label.setStyleSheet("font-weight: bold; font-size: 13px; color: #212529;")
        layout.addWidget(title_label)
        
        # 分隔线
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("background-color: #dee2e6;")
        layout.addWidget(line)
        
        # 跳板机信息（可隐藏）
        self.jump_widget = QWidget()
        jump_layout = QVBoxLayout(self.jump_widget)
        jump_layout.setContentsMargins(0, 0, 0, 0)
        jump_layout.setSpacing(2)
        
        jump_title = QLabel("跳板机:")
        jump_title.setStyleSheet("color: #6c757d; font-size: 11px;")
        jump_layout.addWidget(jump_title)
        
        self.jump_info_label = QLabel("未连接")
        self.jump_info_label.setStyleSheet("color: #212529;")
        self.jump_info_label.setWordWrap(True)
        jump_layout.addWidget(self.jump_info_label)
        
        layout.addWidget(self.jump_widget)
        
        # 目标服务器信息
        target_title = QLabel("目标服务器:")
        target_title.setStyleSheet("color: #6c757d; font-size: 11px; margin-top: 8px;")
        layout.addWidget(target_title)
        
        self.target_info_label = QLabel("未连接")
        self.target_info_label.setStyleSheet("color: #212529;")
        self.target_info_label.setWordWrap(True)
        layout.addWidget(self.target_info_label)
        
        # 当前目录
        path_title = QLabel("当前目录:")
        path_title.setStyleSheet("color: #6c757d; font-size: 11px; margin-top: 8px;")
        layout.addWidget(path_title)
        
        self.path_label = QLabel("-")
        self.path_label.setStyleSheet("color: #212529; font-size: 11px;")
        self.path_label.setWordWrap(True)
        layout.addWidget(self.path_label)
        
        layout.addStretch()
        
        # 状态指示器
        status_layout = QHBoxLayout()
        
        self.status_indicator = QLabel("●")
        self.status_indicator.setStyleSheet("color: #dc3545; font-size: 16px;")
        status_layout.addWidget(self.status_indicator)
        
        self.status_label = QLabel("未连接")
        self.status_label.setStyleSheet("color: #6c757d;")
        status_layout.addWidget(self.status_label)
        
        status_layout.addStretch()
        layout.addLayout(status_layout)
        
        # 断开按钮
        self.disconnect_btn = QPushButton("断开连接")
        self.disconnect_btn.clicked.connect(self.disconnect_clicked.emit)
        self.disconnect_btn.setEnabled(False)
        layout.addWidget(self.disconnect_btn)
    
    def setConnectionInfo(self, jump_chain: JumpChain):
        """设置连接信息"""
        self._jump_chain = jump_chain
        
        jump_servers = jump_chain.get_jump_servers()
        target = jump_chain.get_target()
        
        # 显示跳板机信息（如果有）
        if jump_servers:
            jump = jump_servers[0]
            self.jump_info_label.setText(f"{jump.username}@{jump.host}:{jump.port}")
            self.jump_widget.show()  # 显示跳板机信息
        else:
            # 直接连接模式，隐藏跳板机信息
            self.jump_widget.hide()
        
        # 显示目标服务器信息
        if target:
            self.target_info_label.setText(f"{target.username}@{target.host}:{target.port}")
        else:
            self.target_info_label.setText("无")
    
    def setCurrentPath(self, path: str):
        """设置当前目录"""
        self.path_label.setText(path)
    
    def setConnected(self, connected: bool):
        """设置连接状态"""
        self._connected = connected
        
        if connected:
            self.status_indicator.setStyleSheet("color: #198754; font-size: 16px;")
            self.status_label.setText("已连接")
            self.disconnect_btn.setEnabled(True)
        else:
            self.status_indicator.setStyleSheet("color: #dc3545; font-size: 16px;")
            self.status_label.setText("未连接")
            self.disconnect_btn.setEnabled(False)
            self.jump_info_label.setText("未连接")
            self.target_info_label.setText("未连接")
            self.path_label.setText("-")
    
    def isConnected(self) -> bool:
        """是否已连接"""
        return self._connected
