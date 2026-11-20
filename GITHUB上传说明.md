# 上传到 GitHub 前说明

这个项目可以上传 GitHub，但不要直接把整个目录原样上传。当前目录里有 API Key、战役数据库、聊天记录、备份和大体积规则 PDF。

## 推荐仓库信息

```text
仓库名：mudeng-trpg-console
显示标题：幕灯 · AI 辅助 TRPG 主持台
英文标题：Mudeng — LLM-Assisted TRPG Host Console
```

GitHub Description：

```text
本地优先的 TRPG 主持台，使用大语言模型辅助叙事、NPC、线索、判定与规则检索。支持 CoC 7e / D&D 5e、多人房间、地图、角色卡和持久化存档。
项目仍在持续开发中，界面和体验较粗糙，但核心功能已可用。
```

建议 Topics：

```text
trpg ttrpg virtual-tabletop ai-gm llm call-of-cthulhu dnd5e fastapi websocket self-hosted
```

## 已经处理

项目根目录的 `.gitignore` 已扩展，默认排除：

- `ai_config.json`：包含 API Key
- `trpg.sqlite3` 和所有 `trpg.sqlite3.*`：包含房间、聊天、角色和存档
- `backups/`、`transcripts/`、`map-assets/`
- `.venv/`、`__pycache__/`
- `build/`、`dist/`、`发布/`、`*.exe`、`*.zip`
- `rules/*.pdf`、`rules/*.txt`：第三方规则书，公开仓库不要重新分发
- 本地测试截图和日志

## 推荐做法

### 1. 安装 Git for Windows

当前电脑还没有安装 `git` 命令。

下载安装：

```text
https://git-scm.com/download/win
```

安装后在项目目录打开 PowerShell。

### 2. 初始化仓库

```powershell
cd F:\codex备份\跑团
git init
git add .
git status
```

先检查 `git status`，确认没有出现：

```text
ai_config.json
trpg.sqlite3
rules/*.pdf
```

### 3. 创建首次提交

```powershell
git commit -m "feat: initial Mudeng TRPG console"
git branch -M main
```

### 4. 在 GitHub 创建仓库

在 GitHub 上新建仓库，不要勾选自动生成 README。

然后：

```powershell
git remote add origin https://github.com/你的用户名/仓库名.git
git push -u origin main
```

### 5. exe 不要放进源码仓库

`幕灯跑团.exe` 约 25 MB，适合放到 GitHub Releases：

```text
仓库 → Releases → Draft a new release
→ 上传 幕灯跑团.exe 或 幕灯跑团-一键版.zip
```

源码仓库只保留 Python、HTML、CSS、JS 和启动脚本。

## 上传前最后检查

```powershell
git ls-files | Select-String "ai_config|trpg.sqlite3|\.pdf$|\.env"
```

如果输出为空，说明敏感文件没有进入版本库。

## 如果 Key 已经上传过

立即去 DeepSeek 平台删除旧 Key 并创建新 Key。  
删除 GitHub 上的文件不等于从 Git 历史中删除，必要时用 `git filter-repo` 清理历史。

## 仓库建议

- 公开仓库：适合放源码和自己的文档
- 私有仓库：可以保留更多测试文件，但仍建议排除数据库和 Key
- 第三方规则书：不要公开分发 PDF
- Release：放 exe、zip、使用说明
