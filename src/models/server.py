"""
服务器配置模型
"""
from dataclasses import dataclass, field
from typing import List, Optional
from enum import Enum


class AuthType(Enum):
    """认证类型"""
    PASSWORD = "password"
    KEY = "key"


@dataclass
class ServerConfig:
    """服务器连接配置"""
    host: str
    port: int = 22
    username: str = ""
    password: Optional[str] = None
    private_key_path: Optional[str] = None
    passphrase: Optional[str] = None
    auth_type: AuthType = AuthType.PASSWORD
    
    def validate(self) -> bool:
        """验证配置有效性"""
        if not self.host:
            return False
        if not self.username:
            return False
        if self.auth_type == AuthType.PASSWORD and not self.password:
            return False
        if self.auth_type == AuthType.KEY and not self.private_key_path:
            return False
        return True
    
    def __str__(self) -> str:
        return f"{self.username}@{self.host}:{self.port}"


@dataclass
class JumpChain:
    """跳板机链配置"""
    servers: List[ServerConfig] = field(default_factory=list)
    
    def add_jump_server(self, server: ServerConfig):
        """添加跳板机"""
        self.servers.append(server)
    
    def set_target(self, server: ServerConfig):
        """设置目标服务器（最后一个）"""
        self.servers.append(server)
    
    def get_jump_servers(self) -> List[ServerConfig]:
        """获取跳板机列表（不含目标服务器）"""
        if len(self.servers) <= 1:
            return []
        return self.servers[:-1]
    
    def get_target(self) -> Optional[ServerConfig]:
        """获取目标服务器"""
        if not self.servers:
            return None
        return self.servers[-1]
    
    def validate(self) -> bool:
        """验证配置有效性"""
        if not self.servers:
            return False
        return all(s.validate() for s in self.servers)
    
    def __len__(self) -> int:
        return len(self.servers)
    
    def __str__(self) -> str:
        if not self.servers:
            return "未配置"
        
        parts = []
        for i, server in enumerate(self.servers):
            if i == len(self.servers) - 1:
                parts.append(f"目标: {server}")
            else:
                parts.append(f"跳板{i+1}: {server}")
        return " → ".join(parts)
