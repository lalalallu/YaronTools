"""
SSH连接管理器 - 使用asyncssh实现（更稳定）
使用单事件循环+后台线程模式，避免asyncio.run()创建多个事件循环的问题
"""
import asyncio
import asyncssh
import sys
import threading
from typing import Optional, Tuple, List, AsyncIterator
import socket
from concurrent.futures import TimeoutError as FuturesTimeoutError

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from models.server import ServerConfig, JumpChain


class ConnectionError(Exception):
    """连接错误"""
    pass


class AuthenticationError(ConnectionError):
    """认证失败"""
    pass


class TunnelError(ConnectionError):
    """隧道建立失败"""
    pass


class SSHConnectionManager:
    """SSH连接管理器，使用asyncssh实现"""
    
    def __init__(self, timeout: int = 30):
        """
        初始化连接管理器
        
        Args:
            timeout: 连接超时时间（秒）
        """
        self._timeout = timeout
        self._conn: Optional[asyncssh.SSHClientConnection] = None
        self._sftp: Optional[asyncssh.SFTPClient] = None
        self._connected = False
        
        # 创建单事件循环，在后台线程运行
        self._loop = asyncio.new_event_loop()
        self._loop_thread = threading.Thread(
            target=self._run_loop,
            name="AsyncSSHLoop",
            daemon=True
        )
        self._loop_thread.start()
    
    def _run_loop(self):
        """在后台线程运行事件循环"""
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()
    
    def _run_async(self, coro, timeout=None):
        """
        在事件循环中执行协程并等待结果
        
        Args:
            coro: 协程对象
            timeout: 超时时间（秒）
            
        Returns:
            协程返回值
        """
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        try:
            return future.result(timeout=timeout)
        except FuturesTimeoutError:
            future.cancel()
            raise ConnectionError(f"操作超时（{timeout}秒）")
    
    @property
    def is_connected(self) -> bool:
        """是否已连接"""
        return self._connected and self._conn is not None
    
    def connect(self, jump_chain: JumpChain) -> bool:
        """
        建立SSH连接
        
        Args:
            jump_chain: 跳板机链配置
            
        Returns:
            连接是否成功
        """
        return self._run_async(self._async_connect(jump_chain), timeout=self._timeout * 2)
    
    async def _async_connect(self, jump_chain: JumpChain) -> bool:
        """异步连接实现"""
        if not jump_chain.validate():
            raise ConnectionError("无效的连接配置")
        
        try:
            servers = jump_chain.servers
            jump_servers = jump_chain.get_jump_servers()
            target_server = jump_chain.get_target()
            
            # 构建连接选项
            connect_kwargs = {
                'host': target_server.host,
                'port': target_server.port,
                'username': target_server.username,
                'known_hosts': None,  # 忽略主机密钥检查
                'keepalive_interval': 30,  # 保活间隔
                'keepalive_count_max': 3,  # 保活计数
            }
            
            # 设置认证方式
            if target_server.auth_type.value == "key" and target_server.private_key_path:
                connect_kwargs['client_keys'] = [target_server.private_key_path]
                if target_server.passphrase:
                    connect_kwargs['passphrase'] = target_server.passphrase
            elif target_server.password:
                connect_kwargs['password'] = target_server.password
            
            # 如果有跳板机
            if jump_servers:
                jump = jump_servers[0]
                jump_kwargs = {
                    'host': jump.host,
                    'port': jump.port,
                    'username': jump.username,
                    'known_hosts': None,
                }
                
                if jump.auth_type.value == "key" and jump.private_key_path:
                    jump_kwargs['client_keys'] = [jump.private_key_path]
                    if jump.passphrase:
                        jump_kwargs['passphrase'] = jump.passphrase
                elif jump.password:
                    jump_kwargs['password'] = jump.password
                
                # 先连接跳板机
                jump_conn = await asyncssh.connect(**jump_kwargs)
                
                # 通过跳板机连接目标服务器
                connect_kwargs['tunnel'] = jump_conn
            
            # 连接目标服务器
            self._conn = await asyncssh.connect(**connect_kwargs)
            self._connected = True
            return True
            
        except asyncssh.PermissionDenied as e:
            raise AuthenticationError(f"认证失败: {str(e)}")
        except asyncssh.Error as e:
            raise TunnelError(f"SSH错误: {str(e)}")
        except socket.error as e:
            raise ConnectionError(f"网络错误: {str(e)}")
        except Exception as e:
            raise ConnectionError(f"连接失败: {str(e)}")
    
    def get_sftp(self):
        """获取SFTP客户端（同步包装）"""
        return self._run_async(self._async_get_sftp())
    
    async def _async_get_sftp(self):
        """异步获取SFTP客户端"""
        if not self.is_connected:
            raise ConnectionError("未连接到服务器")
        
        if self._sftp is None:
            self._sftp = await self._conn.start_sftp_client()
        
        return AsyncSFTPWrapper(self._sftp, self._loop)
    
    def execute_command(self, command: str, timeout: int = 60) -> Tuple[int, str, str]:
        """执行命令"""
        return self._run_async(self._async_execute(command, timeout))
    
    async def _async_execute(self, command: str, timeout: int):
        """异步执行命令"""
        if not self.is_connected:
            raise ConnectionError("未连接到服务器")
        
        result = await self._conn.run(command, timeout=timeout)
        return result.exit_status, result.stdout, result.stderr
    
    def close(self):
        """关闭连接"""
        if self._sftp:
            try:
                self._run_async(self._sftp.exit())
            except:
                pass
            self._sftp = None
        
        if self._conn:
            try:
                self._conn.close()
                self._run_async(self._conn.wait_closed())
            except:
                pass
            self._conn = None
        
        self._connected = False
        
        # 停止事件循环
        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False
    
    def __del__(self):
        self.close()


class AsyncSFTPWrapper:
    """SFTP客户端同步包装器"""
    
    def __init__(self, sftp: asyncssh.SFTPClient, loop: asyncio.AbstractEventLoop):
        self._sftp = sftp
        self._loop = loop
    
    def _run_async(self, coro, timeout=None):
        """在事件循环中执行协程"""
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        try:
            return future.result(timeout=timeout)
        except FuturesTimeoutError:
            future.cancel()
            raise ConnectionError(f"操作超时（{timeout}秒）")
    
    def scandir(self, path: str):
        """
        列出目录内容（带文件属性）
        scandir() 是异步生成器，一次性收集所有条目为列表返回
        """
        return self._run_async(self._collect_scandir(path))
    
    async def _collect_scandir(self, path: str):
        """收集scandir异步生成器的所有条目"""
        entries = []
        async for entry in self._sftp.scandir(path):
            entries.append(entry)
        return entries
    
    def stat(self, path: str):
        """获取文件信息"""
        return self._run_async(self._sftp.stat(path))
    
    def get(self, remotepath: str, localpath: str, callback=None, offset: int = 0):
        """
        下载文件
        
        Args:
            remotepath: 远程文件路径
            localpath: 本地保存路径
            callback: 进度回调 callback(downloaded, total)
            offset: 已下载的字节数偏移量（断点续传）
        """
        return self._run_async(self._async_get(remotepath, localpath, callback, offset))
    
    async def _async_get(self, remotepath: str, localpath: str, callback=None, offset: int = 0):
        """异步下载文件（支持断点续传）"""
        import os
        
        # 确保本地目录存在
        local_dir = os.path.dirname(localpath)
        if local_dir and not os.path.exists(local_dir):
            os.makedirs(local_dir, exist_ok=True)
        
        # 获取远程文件大小
        stat = await self._sftp.stat(remotepath)
        total_size = stat.size
        
        # 如果偏移量已经等于或超过文件大小，直接返回
        if offset >= total_size:
            if callback:
                callback(total_size, total_size)
            return
        
        # 使用 open() 打开远程文件
        async with self._sftp.open(remotepath, 'rb') as remote_file:
            # 断点续传：跳过已下载的部分
            if offset > 0:
                await remote_file.seek(offset)
            
            # 追加模式（断点续传）或覆盖模式（全新下载）
            mode = 'ab' if offset > 0 else 'wb'
            with open(localpath, mode) as local_file:
                chunk_size = 1024 * 1024  # 1MB
                downloaded = offset
                
                while True:
                    data = await remote_file.read(chunk_size)
                    if not data:
                        break
                    
                    local_file.write(data)
                    downloaded += len(data)
                    
                    if callback:
                        callback(downloaded, total_size)
    
    def realpath(self, path: str):
        """获取真实路径（替代 normalize）"""
        return self._run_async(self._sftp.realpath(path))
