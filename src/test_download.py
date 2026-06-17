#!/usr/bin/env python3
"""
测试下载功能 - 使用asyncssh
"""
import os
import sys
import asyncio
import asyncssh


async def test_direct_connection_async():
    """测试直接连接和下载（异步版本）"""
    print("=" * 50)
    print("测试直接连接和下载 (asyncssh)")
    print("=" * 50)
    
    # 请修改为您的服务器信息
    host = input("请输入服务器地址: ").strip()
    port = int(input("请输入端口 (默认22): ") or "22")
    username = input("请输入用户名: ").strip()
    password = input("请输入密码: ").strip()
    
    try:
        print(f"\n正在连接 {host}:{port}...")
        
        # 连接选项
        conn = await asyncssh.connect(
            host=host,
            port=port,
            username=username,
            password=password,
            known_hosts=None,  # 忽略主机密钥检查
            keepalive_interval=30,  # 保活间隔
            keepalive_count_max=3,  # 保活计数
        )
        
        print("连接成功!")
        
        # 创建SFTP客户端
        sftp = await conn.start_sftp_client()
        print("SFTP客户端创建成功!")
        
        # 获取主目录
        home = await sftp.normalize('.')
        print(f"\n主目录: {home}")
        
        # 列出目录内容
        print(f"\n目录内容 ({home}):")
        entries = await sftp.listdir(home)
        
        import stat as stat_module
        for entry in entries:
            is_dir = stat_module.S_ISDIR(entry.attrs.permissions)
            file_type = "目录" if is_dir else "文件"
            size = entry.attrs.size if not is_dir else "-"
            print(f"  [{file_type}] {entry.filename} ({size} bytes)")
        
        # 测试下载
        remote_file = input("\n请输入要下载的文件路径: ").strip()
        local_file = os.path.join(os.path.expanduser("~/Downloads"), os.path.basename(remote_file))
        
        print(f"\n开始下载: {remote_file} -> {local_file}")
        
        # 确保本地目录存在
        local_dir = os.path.dirname(local_file)
        if local_dir and not os.path.exists(local_dir):
            os.makedirs(local_dir, exist_ok=True)
        
        # 获取文件大小
        file_stat = await sftp.stat(remote_file)
        total_size = file_stat.size
        
        # 进度回调
        last_update = [asyncio.get_event_loop().time()]
        downloaded = [0]
        
        def progress_callback(data):
            """进度回调"""
            downloaded[0] += len(data)
            current_time = asyncio.get_event_loop().time()
            elapsed = current_time - last_update[0]
            
            if elapsed >= 0.5:
                percent = (downloaded[0] / total_size * 100) if total_size > 0 else 0
                print(f"\r下载进度: {downloaded[0]}/{total_size} bytes ({percent:.1f}%)", end="", flush=True)
                last_update[0] = current_time
        
        # 下载文件
        async with sftp.file(remote_file, 'rb') as remote:
            with open(local_file, 'wb') as local:
                chunk_size = 1024 * 1024  # 1MB
                while True:
                    data = await remote.read(chunk_size)
                    if not data:
                        break
                    local.write(data)
                    progress_callback(data)
        
        print(f"\n下载完成! 文件保存在: {local_file}")
        
        # 关闭连接
        sftp.exit()
        conn.close()
        await conn.wait_closed()
        
        print("\n测试成功!")
        
    except Exception as e:
        print(f"\n错误: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()


async def test_jump_connection_async():
    """测试跳板机连接和下载（异步版本）"""
    print("=" * 50)
    print("测试跳板机连接和下载 (asyncssh)")
    print("=" * 50)
    
    # 跳板机信息
    jump_host = input("请输入跳板机地址: ").strip()
    jump_port = int(input("请输入跳板机端口 (默认22): ") or "22")
    jump_user = input("请输入跳板机用户名: ").strip()
    jump_pass = input("请输入跳板机密码: ").strip()
    
    # 目标服务器信息
    target_host = input("请输入目标服务器地址: ").strip()
    target_port = int(input("请输入目标服务器端口 (默认22): ") or "22")
    target_user = input("请输入目标服务器用户名: ").strip()
    target_pass = input("请输入目标服务器密码: ").strip()
    
    try:
        # 连接跳板机
        print(f"\n正在连接跳板机 {jump_host}:{jump_port}...")
        
        jump_conn = await asyncssh.connect(
            host=jump_host,
            port=jump_port,
            username=jump_user,
            password=jump_pass,
            known_hosts=None,
            keepalive_interval=30,
            keepalive_count_max=3,
        )
        print("跳板机连接成功!")
        
        # 通过跳板机连接目标服务器
        print(f"\n正在连接目标服务器 {target_host}:{target_port}...")
        
        target_conn = await asyncssh.connect(
            host=target_host,
            port=target_port,
            username=target_user,
            password=target_pass,
            known_hosts=None,
            tunnel=jump_conn,  # 使用跳板机隧道
            keepalive_interval=30,
            keepalive_count_max=3,
        )
        print("目标服务器连接成功!")
        
        # 创建SFTP客户端
        sftp = await target_conn.start_sftp_client()
        print("SFTP客户端创建成功!")
        
        # 获取主目录
        home = await sftp.normalize('.')
        print(f"\n主目录: {home}")
        
        # 列出目录内容
        import stat as stat_module
        print(f"\n目录内容 ({home}):")
        entries = await sftp.listdir(home)
        
        for entry in entries:
            is_dir = stat_module.S_ISDIR(entry.attrs.permissions)
            file_type = "目录" if is_dir else "文件"
            size = entry.attrs.size if not is_dir else "-"
            print(f"  [{file_type}] {entry.filename} ({size} bytes)")
        
        # 测试下载
        remote_file = input("\n请输入要下载的文件路径: ").strip()
        local_file = os.path.join(os.path.expanduser("~/Downloads"), os.path.basename(remote_file))
        
        print(f"\n开始下载: {remote_file} -> {local_file}")
        
        # 确保本地目录存在
        local_dir = os.path.dirname(local_file)
        if local_dir and not os.path.exists(local_dir):
            os.makedirs(local_dir, exist_ok=True)
        
        # 获取文件大小
        file_stat = await sftp.stat(remote_file)
        total_size = file_stat.size
        
        # 进度回调
        last_update = [asyncio.get_event_loop().time()]
        downloaded = [0]
        
        def progress_callback(data):
            """进度回调"""
            downloaded[0] += len(data)
            current_time = asyncio.get_event_loop().time()
            elapsed = current_time - last_update[0]
            
            if elapsed >= 0.5:
                percent = (downloaded[0] / total_size * 100) if total_size > 0 else 0
                print(f"\r下载进度: {downloaded[0]}/{total_size} bytes ({percent:.1f}%)", end="", flush=True)
                last_update[0] = current_time
        
        # 下载文件
        async with sftp.file(remote_file, 'rb') as remote:
            with open(local_file, 'wb') as local:
                chunk_size = 1024 * 1024  # 1MB
                while True:
                    data = await remote.read(chunk_size)
                    if not data:
                        break
                    local.write(data)
                    progress_callback(data)
        
        print(f"\n下载完成! 文件保存在: {local_file}")
        
        # 关闭连接
        sftp.exit()
        target_conn.close()
        await target_conn.wait_closed()
        jump_conn.close()
        await jump_conn.wait_closed()
        
        print("\n测试成功!")
        
    except Exception as e:
        print(f"\n错误: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()


def test_direct_connection():
    """同步包装器"""
    asyncio.run(test_direct_connection_async())


def test_jump_connection():
    """同步包装器"""
    asyncio.run(test_jump_connection_async())


if __name__ == "__main__":
    print("SSH下载测试脚本 (asyncssh版本)")
    print("1. 测试直接连接")
    print("2. 测试跳板机连接")
    
    choice = input("请选择 (1/2): ").strip()
    
    if choice == "1":
        test_direct_connection()
    elif choice == "2":
        test_jump_connection()
    else:
        print("无效选择")
