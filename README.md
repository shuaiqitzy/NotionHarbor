# NotionHarbor - Your person knowledgement base

这是一个功能强大的多平台内容本地化管理工具，让你重新整理被扔进收藏夹或者文件传输助手的知识。支持小红书收藏夹与公众号文章的采集、解析、存储与可视化管理。项目提供收藏夹数据获取、公众号文章抓取、笔记与图文内容下载，并提供美观的 Web 界面进行浏览和管理。

未来将逐步扩展为一个个人内容知识库中心（NotionHarbor 的核心内容采集模块）。

## ✨ 功能特性

### 🔍 数据采集
#### 🟥 小红书相关功能
- **收藏夹数据获取**：自动获取小红书收藏夹中的所有专辑和笔记信息
- **增量更新**：智能检测已下载笔记，支持断点续爬，只爬取新增内容
- **媒体下载**：自动下载笔记中的图片和视频到本地
- **详情爬取**：获取笔记的完整信息（标题、描述、标签、互动数据等）

#### 🟩 公众号相关功能（待增）

- **公众号文章采集**：支持输入公众号文章链接，一键抓取正文内容  
- **图文结构解析**：自动解析标题、作者、发布时间、正文、图片等内容  
- **本地 Markdown / JSON 存储**：文章以结构化方式保存，方便后续索引与展示  
- **媒体下载**：自动下载公众号文章中的图片到本地  
- **多文章批量导入**：支持从 JSON 列表或 URL 文件中批量采集文章  
- **去重处理**：自动识别文章重复链接，避免重复保存  
- **增量同步**：重复执行脚本时仅抓取新增文章


### 🎨 Web 界面
- **美观的 UI**：现代化的界面设计，支持网格和列表两种视图模式
- **专辑管理**：支持创建自定义专辑，移动/复制笔记到不同专辑
- **搜索功能**：支持按标题、作者、标签搜索笔记
- **筛选功能**：按类型（图文/视频）、学习状态筛选笔记
- **星标功能**：标记重要笔记，快速访问
- **学习状态**：跟踪笔记的学习状态（已学习/未学习）
- **沉浸式查看**：全屏查看笔记详情，支持图片/视频切换
- **统计信息**：实时显示下载进度、存储占用等统计信息

### 💾 数据管理
- **本地存储**：所有数据保存在本地，无需担心数据丢失
- **结构化存储**：按专辑分类存储，便于管理和查找
- **元数据保存**：保存笔记的完整元数据信息

## 🛠️ 技术栈

- **后端框架**：FastAPI
- **前端技术**：原生 HTML/CSS/JavaScript
- **爬虫框架**：Playwright + MediaCrawler
- **数据存储**：本地文件系统（JSON + 媒体文件）
- **异步处理**：aiohttp, aiofiles

## 📋 前置要求

- Python 3.10+
- Node.js 16.0+（MediaCrawler 依赖）
- 已安装 Chrome/Chromium 浏览器

## 🚀 快速开始

### 1. 克隆项目

```bash
git clone git@github.com:shuaiqitzy/NotionHarbor.git
cd NotionHarbor
```

### 2. 安装依赖

```bash
# 安装 conda 虚拟环境
conda create -n NotionHarbor python=3.10 -y
conda activate myenv

# 安装 Playwright 浏览器驱动
pip install playwright
playwright install chromium

# 安装 MediaCrawler 依赖（如果需要）
cd MediaCrawler
pip install -r requirements.txt
cd ..
```

### 3. 获取收藏夹数据

运行收藏夹数据获取脚本：

```bash
python scrape_xhs.py
```

**操作步骤**：
1. 脚本会自动打开浏览器
2. 扫码登录小红书
3. 进入个人中心 -> 我的收藏
4. 点击进入具体的专辑
5. 在终端输入专辑名称，脚本会自动滚动并抓取该专辑的所有笔记
6. 重复步骤 4-5 获取其他专辑的数据
7. 输入 `q` 保存并退出

数据会保存到 `my_xhs_data.json` 文件中。

### 4. 爬取笔记详情

运行笔记详情爬取脚本：

```bash
python scrape_notes.py
```

**功能说明**：
- 自动读取 `my_xhs_data.json` 中的笔记列表
- 智能检测已下载的笔记，跳过已存在的笔记
- 自动下载笔记的图片和视频到本地
- 支持断点续爬，可随时中断和恢复

**配置选项**（在 `scrape_notes.py` 中）：
```python
ENABLE_CDP_MODE = True      # 是否使用 CDP 模式（推荐）
HEADLESS = False            # 是否无头模式（建议 False 方便登录）
CRAWLER_SLEEP_SEC = 2       # 爬取间隔（秒）
MAX_CONCURRENCY = 2         # 并发数
DOWNLOAD_MEDIA = True       # 是否下载图片和视频
```

### 5. 启动 Web 服务

```bash
python app.py
```

访问 `http://localhost:8000` 即可使用 Web 界面。

## 📁 项目结构

```
xhs/
├── app.py                  # FastAPI 后端服务
├── scrape_xhs.py          # 收藏夹数据获取脚本
├── scrape_notes.py        # 笔记详情爬取脚本
├── my_xhs_data.json       # 收藏夹数据文件（自动生成）
├── custom_albums.json     # 自定义专辑数据（自动生成）
├── learning_status.json   # 学习状态数据（自动生成）
├── starred_status.json    # 星标状态数据（自动生成）
├── requirements.txt       # Python 依赖
├── static/                # 前端静态文件
│   ├── index.html        # 主页面
│   ├── app.js            # 前端逻辑
│   └── style.css         # 样式文件
├── data_storage/          # 本地数据存储目录
│   └── [专辑名]/         # 按专辑分类存储
│       └── [笔记标题]_[笔记ID]/
│           ├── metadata.json  # 笔记元数据
│           ├── image_0.jpg    # 图片文件
│           ├── image_1.jpg
│           └── video.mp4       # 视频文件（如果有）
├── MediaCrawler/          # MediaCrawler 爬虫框架
│   └── ...
└── browser_data/          # 浏览器数据目录
    └── xhs_user_data_dir/ # 用户数据目录（保存登录状态）
```

## 🎯 使用说明

### Web 界面功能

1. **专辑浏览**
   - 左侧边栏显示所有专辑列表
   - 点击专辑名称切换查看不同专辑的笔记
   - 支持查看"全部笔记"、"已下载"、"星标"等特殊视图

2. **笔记管理**
   - 点击笔记卡片查看详情
   - 支持星标标记重要笔记
   - 支持标记学习状态
   - 支持移动/复制笔记到其他专辑

3. **搜索和筛选**
   - 顶部搜索框支持搜索标题、作者、标签
   - 支持按类型（图文/视频）筛选
   - 支持按学习状态筛选

4. **自定义专辑**
   - 点击左侧边栏的 `+` 按钮创建新专辑
   - 可以将笔记移动或复制到自定义专辑

5. **沉浸式查看**
   - 在笔记详情页点击"沉浸式查看"按钮
   - 全屏查看笔记内容，支持键盘左右键切换图片/视频

### API 接口

项目提供了完整的 RESTful API，主要接口包括：

- `GET /api/albums` - 获取专辑列表
- `GET /api/notes` - 获取笔记列表（支持分页、筛选）
- `GET /api/notes/{note_id}` - 获取笔记详情
- `GET /api/search` - 搜索笔记
- `GET /api/stats` - 获取统计信息
- `POST /api/custom-albums` - 创建自定义专辑
- `POST /api/notes/{note_id}/move` - 移动/复制笔记
- `POST /api/notes/{note_id}/learning-status` - 切换学习状态
- `POST /api/notes/{note_id}/starred-status` - 切换星标状态

详细 API 文档可在启动服务后访问 `http://localhost:8000/docs` 查看。

## ⚙️ 配置说明

### 爬虫配置

在 `scrape_notes.py` 中可以修改以下配置：

```python
SOURCE_FILE = "my_xhs_data.json"      # 收藏夹数据文件
DATA_DIR = "data_storage"             # 本地存储目录
CRAWLER_SLEEP_SEC = 2                 # 爬取间隔（秒，建议 >= 2）
MAX_CONCURRENCY = 2                   # 并发数（建议 <= 3）
DOWNLOAD_MEDIA = True                 # 是否下载媒体文件
```

### 服务配置

在 `app.py` 中可以修改以下配置：

```python
DATA_DIR = "data_storage"              # 数据存储目录
SOURCE_FILE = "my_xhs_data.json"      # 收藏夹数据文件
STATIC_DIR = "static"                 # 静态文件目录
```

## 📝 注意事项

1. **登录状态**：首次运行爬虫脚本需要扫码登录，登录状态会保存在 `browser_data/xhs_user_data_dir` 目录中，下次运行会自动使用。

2. **爬取频率**：建议设置合理的爬取间隔（`CRAWLER_SLEEP_SEC >= 2`），避免请求过于频繁导致账号异常。

3. **存储空间**：下载的图片和视频会占用较多存储空间，请确保有足够的磁盘空间。

4. **数据备份**：建议定期备份 `data_storage` 目录和 JSON 数据文件。

5. **合规使用**：本项目仅供学习研究使用，请遵守相关法律法规和平台服务条款。

## 🔧 故障排除

### 问题：爬虫无法登录

**解决方案**：
- 删除 `browser_data/xhs_user_data_dir` 目录，重新运行脚本登录
- 检查网络连接是否正常
- 尝试使用标准模式（设置 `ENABLE_CDP_MODE = False`）

### 问题：笔记下载失败

**解决方案**：
- 检查笔记链接是否有效
- 确认登录状态是否正常（运行 `scrape_notes.py` 时会自动检查）
- 查看终端错误信息，可能是网络问题或笔记已删除

### 问题：Web 界面无法访问

**解决方案**：
- 确认 `app.py` 是否正常运行
- 检查端口 8000 是否被占用
- 查看终端是否有错误信息

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

## 📄 许可证

本项目仅供学习研究使用。

## 🙏 致谢

- [MediaCrawler](https://github.com/NanmiCoder/MediaCrawler) - 优秀的自媒体平台爬虫框架
- [Playwright](https://playwright.dev/) - 强大的浏览器自动化工具
- [FastAPI](https://fastapi.tiangolo.com/) - 现代化的 Python Web 框架

## 📮 联系方式

如有问题或建议，欢迎提交 Issue。

---

**⭐ 如果这个项目对你有帮助，请给个 Star 支持一下！**

