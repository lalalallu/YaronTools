# YaronTools

统一图形化 SSH 远程管理工具（Windows 版），集成文件浏览下载、远程配置文件编辑、PCD 点云坐标编辑三大功能模块。

## 功能特性

- **📁 文件浏览与下载**：远程目录浏览、文件下载，支持跳板机连接、断点续传、并行下载
- **Windows 原生体验**：任务栏下载进度、完成 Toast 通知、资源管理器定位、真实"下载"文件夹、长路径与非法文件名自动处理、重名自动加 (1) 后缀
- **⚙️ 远程配置编辑**：远程 INI 配置文件在线编辑（key=value），支持搜索过滤、修改标记、撤销
- **🔲 PCD 坐标编辑**：远程 PCD 点云坐标文件图形化编辑，分组编辑 x/y/z，格式保持
- **🔐 安全写入**：sudo 提权写入、自动备份（最多保留 5 个）、远程文件冲突检测
- **🔗 跳板机连接**：SSH 跳板机 / 堡垒机连接支持

## 系统要求

- Windows 10 / Windows 11
- Python 3.13+

> 注意：远端目标服务器为 Linux（SFTP 协议传输）。

## 安装

```powershell
pip install -r requirements.txt
```

## 使用方法

### 启动

```powershell
python main.py
```

### 连接服务器

1. 点击工具栏 **"连接"** 或菜单 **文件 → 新建连接**（Ctrl+N）
2. 选择连接模式（直连 / 跳板机）并填写服务器信息
3. 点击 **"保存并连接"**

连接面板中可设置 sudo 密码（留空则使用 SSH 密码）。

### 文件浏览（Ctrl+1）

- 路径栏输入路径回车跳转，双击文件夹进入
- 勾选文件 → 选择本地目录 → 点击"下载选中"
- 支持暂停/续传/取消/打开/在资源管理器中定位
- 默认保存到系统"下载"文件夹；文件名中的 Windows 非法字符自动替换；重名文件自动追加 ` (1)` 后缀

### 配置编辑（Ctrl+2）

- 在文件浏览中双击 `.cfg` 文件自动跳转，或手动输入路径
- 左侧树形列表：搜索过滤、双击编辑、右键删除
- 右侧快速编辑面板：选中参数后修改值 → 应用修改
- 修改过的行以黄色背景高亮
- 点击"保存到远程"或 Ctrl+S 保存（自动备份 + sudo 写入）

### PCD 编辑（Ctrl+3）

- 在文件浏览中双击 `.pcd` 文件自动跳转
- 左侧组列表，右侧编辑面板：可编辑每组的 4 个点的 x/y/z 坐标
- 应用修改 → 本地暂存 → 保存到远程
- 支持撤销本组 / 撤销全部

## 快捷键

| 快捷键 | 功能 |
|--------|------|
| Ctrl+N | 新建连接 |
| Ctrl+D | 断开连接 |
| Ctrl+S | 保存到远程 |
| Ctrl+Z | 撤销 |
| Ctrl+1/2/3 | 切换标签页 |
| Ctrl+Q | 退出 |

## 项目结构

```
src/
├── main.py                      # 程序入口
├── config.py                    # 连接配置持久化
├── requirements.txt
│
├── core/                        # 核心模块
│   ├── connection.py            # SSH 连接管理（asyncssh）
│   ├── sftp_client.py           # SFTP 操作封装
│   ├── sftp_extended.py         # SFTP 读写扩展
│   ├── downloader.py            # 文件下载管理器
│   ├── win_utils.py             # Windows 原生工具（文件名/长路径/通知）
│   ├── sudo_executor.py         # sudo 操作执行器
│   ├── backup_manager.py        # 远程文件备份管理
│   └── conflict_detector.py     # 远程文件冲突检测
│
├── models/                      # 数据模型
│   ├── server.py                # ServerConfig / JumpChain
│   ├── download_task.py         # DownloadTask
│   ├── config_entry.py          # ConfigEntry（配置条目）
│   └── pcd_model.py             # PCDDocument / Group / Point
│
├── parsers/                     # 文件解析器
│   ├── config_parser.py         # INI 配置解析 / 生成
│   └── pcd_parser.py            # PCD 格式解析 / 生成
│
├── ui/                          # 图形界面
│   ├── main_window.py           # 主窗口（QTabWidget 架构，含任务栏进度）
│   ├── dialogs/
│   │   └── connection_dialog.py # 连接配置对话框
│   ├── tabs/
│   │   ├── file_browser_tab.py  # 文件浏览标签页
│   │   ├── config_editor_tab.py # 配置编辑标签页
│   │   └── pcd_editor_tab.py    # PCD 编辑标签页
│   └── widgets/
│       ├── file_list_widget.py
│       ├── download_item_widget.py
│       └── server_info_widget.py
│
└── configs/
    └── configs.json             # 连接配置存储（exe 同目录，便携式）
```

## 打包

```powershell
pyinstaller --name "YaronTools" --windowed --onefile --clean `
  --hidden-import "PyQt6.sip" --hidden-import "asyncssh" --hidden-import "winotify" `
  --collect-all PyQt6 main.py
```

## 注意事项

- **杀毒软件误报**：PyInstaller 单文件打包可能触发杀毒软件误报，可将程序目录加入白名单或改用 `--onedir` 模式打包。
- **配置存储**：连接配置保存在程序同目录 `configs/configs.json`（便携式布局），请勿将程序安装在无写权限的目录（如 Program Files）。
