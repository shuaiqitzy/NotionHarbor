"""
小红书收藏夹本地化 - 笔记爬取脚本 v2.0
读取 my_xhs_data.json 中的笔记列表，使用 MediaCrawler 爬取详情并保存到本地

特性：
- 智能检测：通过笔记 ID 检测是否已下载，支持增量更新
- 断点续爬：跳过已下载的笔记，只爬取新增内容
- 媒体下载：自动下载图片和视频到本地
"""

import asyncio
import json
import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Set
from urllib.parse import urlparse, parse_qs

import aiofiles
import aiohttp

# 添加 MediaCrawler 到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'MediaCrawler'))

from playwright.async_api import async_playwright, BrowserContext, Page

# MediaCrawler 导入
from MediaCrawler.media_platform.xhs.client import XiaoHongShuClient
from MediaCrawler.media_platform.xhs.login import XiaoHongShuLogin
from MediaCrawler.media_platform.xhs.help import parse_note_info_from_note_url
from MediaCrawler.tools import utils
from MediaCrawler.tools.cdp_browser import CDPBrowserManager

# ================= 配置 =================
SOURCE_FILE = "my_xhs_data.json"           # 收藏夹数据文件
DATA_DIR = "data_storage"                    # 本地存储目录
COOKIE_FILE = "cookie.txt"                   # Cookie 文件（可选）

# 爬取配置
ENABLE_CDP_MODE = True                       # 是否使用 CDP 模式（推荐）
HEADLESS = False                             # 是否无头模式（建议 False 方便登录）
CRAWLER_SLEEP_SEC = 2                        # 爬取间隔（秒）
MAX_CONCURRENCY = 2                          # 并发数
DOWNLOAD_MEDIA = True                        # 是否下载图片和视频

# ========================================


def sanitize_filename(name: str) -> str:
    """清洗文件名，移除非法字符"""
    if not name:
        return "untitled"
    # 移除 Windows 文件名非法字符
    name = re.sub(r'[<>:"/\\|?*\n\r\t]', '_', name)
    # 移除前后空白和点
    name = name.strip(' .')
    # 限制长度
    return name[:80] if name else "untitled"


def scan_downloaded_notes(album_dir: str) -> Set[str]:
    """扫描已下载的笔记 ID 集合"""
    downloaded_ids = set()
    
    if not os.path.exists(album_dir):
        return downloaded_ids
    
    for folder_name in os.listdir(album_dir):
        folder_path = os.path.join(album_dir, folder_name)
        metadata_path = os.path.join(folder_path, "metadata.json")
        
        # 只有存在 metadata.json 才算已下载
        if os.path.isdir(folder_path) and os.path.exists(metadata_path):
            # 从文件夹名提取笔记 ID（格式：title_noteId）
            parts = folder_name.rsplit('_', 1)
            if len(parts) == 2:
                downloaded_ids.add(parts[1])
    
    return downloaded_ids


def find_existing_note_folder(album_dir: str, note_id: str) -> Optional[str]:
    """查找已存在的笔记文件夹（通过笔记 ID）"""
    if not os.path.exists(album_dir):
        return None
    
    for folder_name in os.listdir(album_dir):
        if folder_name.endswith(f"_{note_id}"):
            folder_path = os.path.join(album_dir, folder_name)
            metadata_path = os.path.join(folder_path, "metadata.json")
            if os.path.exists(metadata_path):
                return folder_path
    
    return None


def parse_note_id_from_url(note_url: str) -> tuple:
    """从 URL 中解析笔记 ID 和 token 信息"""
    # URL 格式: https://www.xiaohongshu.com/board/xxx/note_id?xsec_token=xxx&xsec_source=xxx
    # 或者 id 直接包含 ?xsec_token=xxx
    
    if '?' in note_url:
        base_part, query_part = note_url.split('?', 1)
    else:
        base_part = note_url
        query_part = ""
    
    # 提取笔记 ID
    note_id = base_part.split('/')[-1] if '/' in base_part else base_part
    
    # 解析 token 参数
    params = {}
    if query_part:
        for param in query_part.split('&'):
            if '=' in param:
                key, value = param.split('=', 1)
                params[key] = value
    
    xsec_token = params.get('xsec_token', '')
    xsec_source = params.get('xsec_source', 'pc_feed')
    
    return note_id, xsec_token, xsec_source


def parse_note_id_from_item(note_item: dict) -> tuple:
    """从笔记项中解析 ID 和 token"""
    raw_id = note_item.get('id', '')
    
    # ID 可能包含 ?xsec_token=xxx 格式
    if '?' in raw_id:
        note_id, query_part = raw_id.split('?', 1)
        params = {}
        for param in query_part.split('&'):
            if '=' in param:
                key, value = param.split('=', 1)
                params[key] = value
        xsec_token = params.get('xsec_token', '')
        xsec_source = params.get('xsec_source', 'pc_feed')
    else:
        note_id = raw_id
        # 尝试从 link 中获取 token
        link = note_item.get('link', '')
        if '?' in link:
            _, query_part = link.split('?', 1)
            params = {}
            for param in query_part.split('&'):
                if '=' in param:
                    key, value = param.split('=', 1)
                    params[key] = value
            xsec_token = params.get('xsec_token', '')
            xsec_source = params.get('xsec_source', 'pc_feed')
        else:
            xsec_token = ''
            xsec_source = 'pc_feed'
    
    return note_id, xsec_token, xsec_source


class FavoriteCrawler:
    """收藏夹爬虫"""
    
    def __init__(self):
        self.browser_context: Optional[BrowserContext] = None
        self.context_page: Optional[Page] = None
        self.xhs_client: Optional[XiaoHongShuClient] = None
        self.cdp_manager: Optional[CDPBrowserManager] = None
        self.user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        
    async def initialize(self):
        """初始化浏览器和客户端"""
        print("🚀 正在初始化浏览器...")
        
        async with async_playwright() as playwright:
            await self._launch_browser(playwright)
            await self._create_client()
            
            # 执行爬取
            await self._run_crawl()
            
            # 清理
            await self._cleanup()
    
    async def _launch_browser(self, playwright):
        """启动浏览器"""
        if ENABLE_CDP_MODE:
            print("📌 使用 CDP 模式启动浏览器...")
            try:
                self.cdp_manager = CDPBrowserManager()
                self.browser_context = await self.cdp_manager.launch_and_connect(
                    playwright=playwright,
                    playwright_proxy=None,
                    user_agent=self.user_agent,
                    headless=HEADLESS,
                )
            except Exception as e:
                print(f"⚠️ CDP 模式启动失败，使用标准模式: {e}")
                self.cdp_manager = None
                await self._launch_standard_browser(playwright)
        else:
            await self._launch_standard_browser(playwright)
        
        self.context_page = await self.browser_context.new_page()
        await self.context_page.goto("https://www.xiaohongshu.com")
        print("✅ 浏览器启动成功")
    
    async def _launch_standard_browser(self, playwright):
        """标准模式启动浏览器"""
        user_data_dir = os.path.join(os.getcwd(), "browser_data", "xhs_user_data_dir")
        self.browser_context = await playwright.chromium.launch_persistent_context(
            user_data_dir=user_data_dir,
            accept_downloads=True,
            headless=HEADLESS,
            viewport={"width": 1920, "height": 1080},
            user_agent=self.user_agent,
        )
        # 加载反检测脚本
        stealth_js = os.path.join(os.path.dirname(__file__), 'MediaCrawler', 'libs', 'stealth.min.js')
        if os.path.exists(stealth_js):
            await self.browser_context.add_init_script(path=stealth_js)
    
    async def _create_client(self):
        """创建 XHS 客户端"""
        print("🔧 正在创建客户端...")
        
        cookie_str, cookie_dict = utils.convert_cookies(await self.browser_context.cookies())
        
        self.xhs_client = XiaoHongShuClient(
            proxy=None,
            headers={
                "accept": "application/json, text/plain, */*",
                "accept-language": "zh-CN,zh;q=0.9",
                "content-type": "application/json;charset=UTF-8",
                "origin": "https://www.xiaohongshu.com",
                "referer": "https://www.xiaohongshu.com/",
                "user-agent": self.user_agent,
                "Cookie": cookie_str,
            },
            playwright_page=self.context_page,
            cookie_dict=cookie_dict,
        )
        
        # 检查登录状态
        if not await self.xhs_client.pong():
            print("⚠️ 未登录，请扫码登录...")
            login_obj = XiaoHongShuLogin(
                login_type="qrcode",
                login_phone="",
                browser_context=self.browser_context,
                context_page=self.context_page,
                cookie_str="",
            )
            await login_obj.begin()
            await self.xhs_client.update_cookies(browser_context=self.browser_context)
        
        print("✅ 客户端创建成功，登录状态正常")
    
    async def _run_crawl(self):
        """执行爬取任务"""
        # 读取收藏夹数据
        if not os.path.exists(SOURCE_FILE):
            print(f"❌ 找不到数据文件: {SOURCE_FILE}")
            return
        
        with open(SOURCE_FILE, 'r', encoding='utf-8') as f:
            albums = json.load(f)
        
        print(f"\n📚 共找到 {len(albums)} 个专辑")
        
        # 预扫描：统计所有笔记和已下载笔记
        total_notes = 0
        total_downloaded = 0
        total_new = 0
        
        album_stats = []
        for album in albums:
            album_name = album.get('name', '未命名专辑')
            notes = album.get('notes', [])
            safe_album_name = sanitize_filename(album_name)
            album_dir = os.path.join(DATA_DIR, safe_album_name)
            
            # 扫描该专辑已下载的笔记 ID
            downloaded_ids = scan_downloaded_notes(album_dir)
            
            # 统计新增笔记
            new_notes = []
            for note in notes:
                note_id, _, _ = parse_note_id_from_item(note)
                if note_id not in downloaded_ids:
                    new_notes.append(note)
            
            album_stats.append({
                'name': album_name,
                'notes': notes,
                'new_notes': new_notes,
                'downloaded_ids': downloaded_ids,
                'album_dir': album_dir,
            })
            
            total_notes += len(notes)
            total_downloaded += len(downloaded_ids)
            total_new += len(new_notes)
        
        print(f"\n📊 笔记统计:")
        print(f"   📝 总笔记数: {total_notes}")
        print(f"   ✅ 已下载: {total_downloaded}")
        print(f"   🆕 待下载: {total_new}")
        
        if total_new == 0:
            print(f"\n✨ 所有笔记都已下载，无需更新！")
            return
        
        print(f"\n🚀 开始爬取 {total_new} 条新笔记...\n")
        
        # 统计
        downloaded = 0
        skipped = 0
        failed = 0
        
        for album_info in album_stats:
            album_name = album_info['name']
            new_notes = album_info['new_notes']
            album_dir = album_info['album_dir']
            total_album_notes = len(album_info['notes'])
            
            if not new_notes:
                print(f"📁 {album_name}: 无新增笔记，跳过")
                continue
            
            print(f"\n{'='*50}")
            print(f"📁 专辑: {album_name}")
            print(f"   总数: {total_album_notes} | 已下载: {len(album_info['downloaded_ids'])} | 新增: {len(new_notes)}")
            print('='*50)
            
            os.makedirs(album_dir, exist_ok=True)
            
            for i, note_item in enumerate(new_notes, 1):
                note_id, xsec_token, xsec_source = parse_note_id_from_item(note_item)
                note_title = note_item.get('title', '')
                
                # 再次检查（防止并发问题）
                existing_folder = find_existing_note_folder(album_dir, note_id)
                if existing_folder:
                    print(f"  ⏭️ [{i}/{len(new_notes)}] 已存在: {note_title[:30]}...")
                    skipped += 1
                    continue
                
                print(f"  🆕 [{i}/{len(new_notes)}] 正在爬取: {note_title[:40]}...")
                
                try:
                    # 获取笔记详情
                    note_detail = await self._get_note_detail(note_id, xsec_token, xsec_source)
                    
                    if note_detail:
                        # 构建保存路径
                        safe_title = sanitize_filename(note_title)
                        note_folder = f"{safe_title}_{note_id}"
                        note_dir = os.path.join(album_dir, note_folder)
                        
                        # 保存数据
                        await self._save_note(
                            note_dir=note_dir,
                            note_detail=note_detail,
                            album_name=album_name,
                            original_item=note_item
                        )
                        downloaded += 1
                        print(f"      ✅ 保存成功")
                    else:
                        failed += 1
                        print(f"      ❌ 获取详情失败")
                    
                    # 爬取间隔
                    await asyncio.sleep(CRAWLER_SLEEP_SEC)
                    
                except Exception as e:
                    failed += 1
                    print(f"      ❌ 错误: {e}")
        
        # 打印统计
        print(f"\n{'='*50}")
        print(f"📊 本次爬取统计:")
        print(f"   ✅ 新下载: {downloaded}")
        print(f"   ⏭️ 跳过: {skipped}")
        print(f"   ❌ 失败: {failed}")
        print(f"   📝 处理: {downloaded + skipped + failed}/{total_new}")
        print('='*50)
        print(f"\n📦 本地总计: {total_downloaded + downloaded} 条笔记")
    
    async def _get_note_detail(self, note_id: str, xsec_token: str, xsec_source: str) -> Optional[Dict]:
        """获取笔记详情"""
        try:
            # 尝试 API 方式
            note_detail = await self.xhs_client.get_note_by_id(note_id, xsec_source, xsec_token)
            
            if not note_detail:
                # 尝试 HTML 方式
                note_detail = await self.xhs_client.get_note_by_id_from_html(
                    note_id, xsec_source, xsec_token, enable_cookie=True
                )
            
            if note_detail:
                note_detail.update({
                    "xsec_token": xsec_token,
                    "xsec_source": xsec_source
                })
            
            return note_detail
            
        except Exception as e:
            print(f"      ⚠️ 获取详情异常: {e}")
            return None
    
    async def _save_note(self, note_dir: str, note_detail: Dict, album_name: str, original_item: Dict):
        """保存笔记到本地"""
        os.makedirs(note_dir, exist_ok=True)
        
        # 准备 metadata
        metadata = {
            "note_id": note_detail.get("note_id", ""),
            "title": note_detail.get("title", ""),
            "desc": note_detail.get("desc", ""),
            "type": note_detail.get("type", "normal"),
            "user": {
                "user_id": note_detail.get("user_id", ""),
                "nickname": note_detail.get("nickname", ""),
                "avatar": note_detail.get("avatar", original_item.get("authorAvatar", "")),
            },
            "interact_info": {
                "liked_count": note_detail.get("liked_count", 0),
                "collected_count": note_detail.get("collected_count", 0),
                "comment_count": note_detail.get("comment_count", 0),
                "share_count": note_detail.get("share_count", 0),
            },
            "tag_list": note_detail.get("tag_list", []),
            "image_list": note_detail.get("image_list", []),
            "video_url": note_detail.get("video_url", ""),
            "time": note_detail.get("time", ""),
            "last_update_time": note_detail.get("last_update_time", ""),
            "album": album_name,
            "note_url": f"https://www.xiaohongshu.com/explore/{note_detail.get('note_id', '')}",
            "xsec_token": note_detail.get("xsec_token", ""),
        }
        
        # 保存 metadata.json
        metadata_path = os.path.join(note_dir, "metadata.json")
        async with aiofiles.open(metadata_path, 'w', encoding='utf-8') as f:
            await f.write(json.dumps(metadata, ensure_ascii=False, indent=2))
        
        # 下载媒体文件
        if DOWNLOAD_MEDIA:
            await self._download_media(note_dir, note_detail)
    
    async def _download_media(self, note_dir: str, note_detail: Dict):
        """下载媒体文件（图片和视频）"""
        # 下载图片
        image_list = note_detail.get("image_list", [])
        for idx, img in enumerate(image_list):
            url = img.get("url_default") or img.get("url") or ""
            if not url:
                continue
            
            try:
                content = await self.xhs_client.get_note_media(url)
                if content:
                    img_path = os.path.join(note_dir, f"image_{idx}.jpg")
                    async with aiofiles.open(img_path, 'wb') as f:
                        await f.write(content)
                    await asyncio.sleep(0.5)  # 避免请求过快
            except Exception as e:
                print(f"      ⚠️ 图片下载失败: {e}")
        
        # 下载视频
        video_url = note_detail.get("video_url", "")
        if not video_url:
            # 尝试从其他字段获取视频 URL
            video_info = note_detail.get("video", {})
            if isinstance(video_info, dict):
                media = video_info.get("media", {})
                stream = media.get("stream", {})
                for quality in ["h266", "h265", "h264", "av1"]:
                    streams = stream.get(quality, [])
                    if streams:
                        video_url = streams[0].get("master_url", "")
                        if video_url:
                            break
        
        if video_url:
            try:
                content = await self.xhs_client.get_note_media(video_url)
                if content:
                    video_path = os.path.join(note_dir, "video.mp4")
                    async with aiofiles.open(video_path, 'wb') as f:
                        await f.write(content)
            except Exception as e:
                print(f"      ⚠️ 视频下载失败: {e}")
    
    async def _cleanup(self):
        """清理资源"""
        print("\n🧹 正在清理资源...")
        if self.cdp_manager:
            await self.cdp_manager.cleanup()
        elif self.browser_context:
            await self.browser_context.close()
        print("✅ 清理完成")


async def main():
    """主函数"""
    print("""
╔══════════════════════════════════════════════════════════╗
║         小红书收藏夹本地化 - 笔记爬取工具 v2.0            ║
╠══════════════════════════════════════════════════════════╣
║  功能：读取收藏夹数据，爬取笔记详情和媒体文件到本地        ║
║  特性：智能检测已下载笔记，支持增量更新                    ║
╚══════════════════════════════════════════════════════════╝
    """)
    
    # 检查数据文件
    if not os.path.exists(SOURCE_FILE):
        print(f"❌ 错误：找不到数据文件 {SOURCE_FILE}")
        print("请先运行收藏夹获取脚本生成数据文件")
        return
    
    # 创建存储目录
    os.makedirs(DATA_DIR, exist_ok=True)
    
    crawler = FavoriteCrawler()
    
    try:
        # 使用 async_playwright 的正确方式
        async with async_playwright() as playwright:
            # 启动浏览器
            if ENABLE_CDP_MODE:
                print("📌 使用 CDP 模式启动浏览器...")
                try:
                    crawler.cdp_manager = CDPBrowserManager()
                    crawler.browser_context = await crawler.cdp_manager.launch_and_connect(
                        playwright=playwright,
                        playwright_proxy=None,
                        user_agent=crawler.user_agent,
                        headless=HEADLESS,
                    )
                except Exception as e:
                    print(f"⚠️ CDP 模式启动失败，使用标准模式: {e}")
                    crawler.cdp_manager = None
                    user_data_dir = os.path.join(os.getcwd(), "browser_data", "xhs_user_data_dir")
                    crawler.browser_context = await playwright.chromium.launch_persistent_context(
                        user_data_dir=user_data_dir,
                        accept_downloads=True,
                        headless=HEADLESS,
                        viewport={"width": 1920, "height": 1080},
                        user_agent=crawler.user_agent,
                    )
                    stealth_js = os.path.join(os.path.dirname(__file__), 'MediaCrawler', 'libs', 'stealth.min.js')
                    if os.path.exists(stealth_js):
                        await crawler.browser_context.add_init_script(path=stealth_js)
            else:
                user_data_dir = os.path.join(os.getcwd(), "browser_data", "xhs_user_data_dir")
                crawler.browser_context = await playwright.chromium.launch_persistent_context(
                    user_data_dir=user_data_dir,
                    accept_downloads=True,
                    headless=HEADLESS,
                    viewport={"width": 1920, "height": 1080},
                    user_agent=crawler.user_agent,
                )
                stealth_js = os.path.join(os.path.dirname(__file__), 'MediaCrawler', 'libs', 'stealth.min.js')
                if os.path.exists(stealth_js):
                    await crawler.browser_context.add_init_script(path=stealth_js)
            
            crawler.context_page = await crawler.browser_context.new_page()
            await crawler.context_page.goto("https://www.xiaohongshu.com")
            print("✅ 浏览器启动成功")
            
            # 创建客户端
            print("🔧 正在创建客户端...")
            cookie_str, cookie_dict = utils.convert_cookies(await crawler.browser_context.cookies())
            
            crawler.xhs_client = XiaoHongShuClient(
                proxy=None,
                headers={
                    "accept": "application/json, text/plain, */*",
                    "accept-language": "zh-CN,zh;q=0.9",
                    "content-type": "application/json;charset=UTF-8",
                    "origin": "https://www.xiaohongshu.com",
                    "referer": "https://www.xiaohongshu.com/",
                    "user-agent": crawler.user_agent,
                    "Cookie": cookie_str,
                },
                playwright_page=crawler.context_page,
                cookie_dict=cookie_dict,
            )
            
            # 检查登录状态
            if not await crawler.xhs_client.pong():
                print("⚠️ 未登录，请扫码登录...")
                login_obj = XiaoHongShuLogin(
                    login_type="qrcode",
                    login_phone="",
                    browser_context=crawler.browser_context,
                    context_page=crawler.context_page,
                    cookie_str="",
                )
                await login_obj.begin()
                await crawler.xhs_client.update_cookies(browser_context=crawler.browser_context)
            
            print("✅ 客户端创建成功，登录状态正常")
            
            # 执行爬取
            await crawler._run_crawl()
            
            # 清理
            print("\n🧹 正在清理资源...")
            if crawler.cdp_manager:
                await crawler.cdp_manager.cleanup()
            elif crawler.browser_context:
                await crawler.browser_context.close()
            print("✅ 清理完成")
            
    except KeyboardInterrupt:
        print("\n\n⚠️ 用户中断，正在退出...")
    except Exception as e:
        print(f"\n❌ 发生错误: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())

