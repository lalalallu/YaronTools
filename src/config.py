"""
配置管理模块 - 保存和加载服务器配置
"""
import os
import sys
import json
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, asdict
from datetime import datetime

from models.server import ServerConfig, JumpChain, AuthType


# 配置文件路径 - 保存在可执行文件同目录（打包后）或项目根目录（开发时）
if getattr(sys, 'frozen', False):
    # PyInstaller 打包后：configs 放在 exe 同目录
    BASE_DIR = os.path.dirname(sys.executable)
else:
    # 开发环境：configs 放在项目根目录
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

CONFIG_DIR = os.path.join(BASE_DIR, "configs")
CONFIG_FILE = os.path.join(CONFIG_DIR, "configs.json")


def ensure_config_dir():
    """确保配置目录存在"""
    if not os.path.exists(CONFIG_DIR):
        os.makedirs(CONFIG_DIR, exist_ok=True)


@dataclass
class SavedConnection:
    """保存的连接配置"""
    name: str
    jump_host: Optional[str] = None
    jump_port: int = 22
    jump_user: Optional[str] = None
    jump_auth_type: str = "password"
    jump_password: Optional[str] = None
    jump_key_path: Optional[str] = None
    jump_passphrase: Optional[str] = None
    target_host: str = ""
    target_port: int = 22
    target_user: str = ""
    target_auth_type: str = "password"
    target_password: Optional[str] = None
    target_key_path: Optional[str] = None
    target_passphrase: Optional[str] = None
    use_jump: bool = False
    created_time: str = ""
    last_used_time: str = ""
    
    def __post_init__(self):
        if not self.created_time:
            self.created_time = datetime.now().isoformat()
    
    def to_jump_chain(self) -> JumpChain:
        """转换为JumpChain对象"""
        chain = JumpChain()
        
        if self.use_jump:
            jump_config = ServerConfig(
                host=self.jump_host or "",
                port=self.jump_port,
                username=self.jump_user or "",
                auth_type=AuthType.PASSWORD if self.jump_auth_type == "password" else AuthType.KEY,
                password=self.jump_password if self.jump_auth_type == "password" else None,
                private_key_path=self.jump_key_path if self.jump_auth_type == "key" else None,
                passphrase=self.jump_passphrase if self.jump_auth_type == "key" else None
            )
            chain.add_jump_server(jump_config)
        
        target_config = ServerConfig(
            host=self.target_host,
            port=self.target_port,
            username=self.target_user,
            auth_type=AuthType.PASSWORD if self.target_auth_type == "password" else AuthType.KEY,
            password=self.target_password if self.target_auth_type == "password" else None,
            private_key_path=self.target_key_path if self.target_auth_type == "key" else None,
            passphrase=self.target_passphrase if self.target_auth_type == "key" else None
        )
        chain.set_target(target_config)
        
        return chain


class ConfigManager:
    """配置管理器"""
    
    def __init__(self):
        self._configs: List[SavedConnection] = []
        self._load()
    
    def _load(self):
        """加载配置"""
        ensure_config_dir()
        
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self._configs = [SavedConnection(**item) for item in data]
            except Exception as e:
                print(f"加载配置失败: {e}")
                self._configs = []
    
    def _save(self):
        """保存配置"""
        ensure_config_dir()
        
        try:
            data = [asdict(config) for config in self._configs]
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"保存配置失败: {e}")
    
    def get_all(self) -> List[SavedConnection]:
        """获取所有配置"""
        return self._configs.copy()
    
    def get_names(self) -> List[str]:
        """获取所有配置名称"""
        return [config.name for config in self._configs]
    
    def get_by_name(self, name: str) -> Optional[SavedConnection]:
        """根据名称获取配置"""
        for config in self._configs:
            if config.name == name:
                return config
        return None
    
    def add(self, config: SavedConnection):
        """添加配置"""
        # 检查是否已存在同名配置
        for i, existing in enumerate(self._configs):
            if existing.name == config.name:
                # 更新现有配置
                config.created_time = existing.created_time
                config.last_used_time = datetime.now().isoformat()
                self._configs[i] = config
                self._save()
                return
        
        # 添加新配置
        self._configs.append(config)
        self._save()
    
    def update(self, config: SavedConnection):
        """更新配置"""
        for i, existing in enumerate(self._configs):
            if existing.name == config.name:
                config.last_used_time = datetime.now().isoformat()
                self._configs[i] = config
                self._save()
                return
    
    def delete(self, name: str):
        """删除配置"""
        self._configs = [c for c in self._configs if c.name != name]
        self._save()
    
    def update_last_used(self, name: str):
        """更新最后使用时间"""
        for config in self._configs:
            if config.name == name:
                config.last_used_time = datetime.now().isoformat()
                self._save()
                return


# 全局配置管理器实例
config_manager = ConfigManager()
