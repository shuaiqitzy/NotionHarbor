"""
小红书收藏夹本地化 - FastAPI 后端
提供数据接口和静态文件服务
"""

import json
import os
import re
from pathlib import Path
from typing import Optional, List, Dict, Any

from fastapi import FastAPI, HTTPException, Query, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import subprocess
import asyncio

# ================= 配置 =================
DATA_DIR = "data_storage"
SOURCE_FILE = "my_xhs_data.json"
CUSTOM_ALBUMS_FILE = "custom_albums.json"  # 自定义专辑存储文件
LEARNING_STATUS_FILE = "learning_status.json"  # 学习状态存储文件
STARRED_STATUS_FILE = "starred_status.json"  # 星标状态存储文件
STATIC_DIR = "static"
# ========================================

app = FastAPI(
    title="小红书收藏夹", 
    description="本地化收藏夹展示",
    version="2.0"
)

# 允许跨域
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ================= 数据模型 =================
class NoteBasic(BaseModel):
    """笔记基础信息"""
    id: str
    title: str
    cover: str
    author: str
    authorAvatar: str
    type: str
    likes: str
    collects: int
    link: str
    tags: list
    album: str = ""
    hasLocal: bool = False  # 是否已下载到本地


class Album(BaseModel):
    """专辑信息"""
    name: str
    count: int


class CreateAlbumRequest(BaseModel):
    """创建专辑请求"""
    name: str


class MoveNoteRequest(BaseModel):
    """移动/复制笔记请求"""
    target_album: str
    operation: str  # "copy" 或 "move"


class NoteDetail(BaseModel):
    """笔记详情"""
    id: str
    title: str
    desc: str
    author: str
    authorId: str
    authorAvatar: str
    likes: int
    collects: int
    comments: int
    shares: int
    tags: list
    images: list
    video: Optional[str] = None
    type: str


# ================= 工具函数 =================
def get_source_data() -> list:
    """读取原始收藏夹数据"""
    if not os.path.exists(SOURCE_FILE):
        return []
    with open(SOURCE_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)


def get_custom_albums() -> dict:
    """读取自定义专辑数据"""
    if not os.path.exists(CUSTOM_ALBUMS_FILE):
        return {}
    with open(CUSTOM_ALBUMS_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_custom_albums(data: dict):
    """保存自定义专辑数据"""
    with open(CUSTOM_ALBUMS_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_learning_status() -> dict:
    """读取学习状态数据"""
    if not os.path.exists(LEARNING_STATUS_FILE):
        return {}
    with open(LEARNING_STATUS_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_learning_status(data: dict):
    """保存学习状态数据"""
    with open(LEARNING_STATUS_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_starred_status() -> dict:
    """读取星标状态数据"""
    if not os.path.exists(STARRED_STATUS_FILE):
        return {}
    with open(STARRED_STATUS_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_starred_status(data: dict):
    """保存星标状态数据"""
    with open(STARRED_STATUS_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def sanitize_filename(name: str) -> str:
    """清洗文件名，与爬虫脚本保持一致"""
    if not name:
        return "untitled"
    # 移除 Windows 文件名非法字符
    name = re.sub(r'[<>:"/\\|?*\n\r\t]', '_', name)
    # 移除前后空白和点
    name = name.strip(' .')
    # 限制长度（与爬虫脚本一致）
    return name[:80] if name else "untitled"


def scan_local_albums() -> Dict[str, List[str]]:
    """扫描本地已下载的专辑和笔记"""
    local_data = {}
    if not os.path.exists(DATA_DIR):
        return local_data
    
    for album_name in os.listdir(DATA_DIR):
        album_path = os.path.join(DATA_DIR, album_name)
        if not os.path.isdir(album_path):
            continue
        
        notes = []
        for note_folder in os.listdir(album_path):
            note_path = os.path.join(album_path, note_folder)
            metadata_path = os.path.join(note_path, "metadata.json")
            if os.path.isdir(note_path) and os.path.exists(metadata_path):
                # 从文件夹名提取笔记 ID
                parts = note_folder.rsplit('_', 1)
                if len(parts) == 2:
                    notes.append(parts[1])  # 笔记 ID
        
        local_data[album_name] = notes
    
    return local_data


def check_note_downloaded(album_name: str, note_id: str, title: str) -> bool:
    """检查笔记是否已下载"""
    safe_album = sanitize_filename(album_name)
    safe_title = sanitize_filename(title)
    note_folder = f"{safe_title}_{note_id.split('?')[0]}"
    note_path = os.path.join(DATA_DIR, safe_album, note_folder, "metadata.json")
    return os.path.exists(note_path)


def get_note_local_path(album_name: str, note_id: str, title: str) -> Optional[str]:
    """获取笔记本地路径"""
    safe_album = sanitize_filename(album_name)
    safe_title = sanitize_filename(title)
    pure_id = note_id.split('?')[0]
    note_folder = f"{safe_title}_{pure_id}"
    note_path = os.path.join(DATA_DIR, safe_album, note_folder)
    if os.path.exists(note_path):
        return note_path
    return None


def get_local_note_detail(note_path: str) -> Optional[dict]:
    """从本地读取笔记详情"""
    metadata_path = os.path.join(note_path, "metadata.json")
    if not os.path.exists(metadata_path):
        return None
    
    with open(metadata_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # 获取本地图片列表（按数字排序）
    images = []
    for file in os.listdir(note_path):
        if file.startswith('image_') and file.endswith(('.png', '.jpg', '.jpeg', '.webp', '.gif')):
            images.append(file)
    
    # 按 image_0, image_1, image_2... 排序
    images.sort(key=lambda x: int(re.search(r'image_(\d+)', x).group(1)) if re.search(r'image_(\d+)', x) else 0)
    
    # 检查视频
    video = None
    for ext in ['.mp4', '.mov', '.webm']:
        video_file = f"video{ext}"
        if os.path.exists(os.path.join(note_path, video_file)):
            video = video_file
            break
    
    return {
        "metadata": data,
        "images": images,
        "video": video,
        "path": note_path
    }


def find_note_folder(album_name: str, note_id: str, title: str = "") -> Optional[str]:
    """查找笔记文件夹，支持模糊匹配"""
    safe_album = sanitize_filename(album_name)
    album_path = os.path.join(DATA_DIR, safe_album)
    
    if not os.path.exists(album_path):
        return None
    
    # 精确匹配
    if title:
        safe_title = sanitize_filename(title)
        exact_folder = f"{safe_title}_{note_id}"
        exact_path = os.path.join(album_path, exact_folder)
        if os.path.exists(exact_path):
            return exact_path
    
    # 模糊匹配：查找以 _note_id 结尾的文件夹
    for folder in os.listdir(album_path):
        if folder.endswith(f"_{note_id}"):
            return os.path.join(album_path, folder)
    
    return None


def get_local_cover(note_path: str) -> Optional[str]:
    """获取笔记的本地封面图片（第一张图片）"""
    if not os.path.exists(note_path):
        return None
    
    # 查找图片文件
    images = []
    for file in os.listdir(note_path):
        if file.startswith('image_') and file.endswith(('.jpg', '.jpeg', '.png', '.webp', '.gif')):
            images.append(file)
    
    if not images:
        return None
    
    # 按 image_0, image_1... 排序，返回第一张
    images.sort(key=lambda x: int(re.search(r'image_(\d+)', x).group(1)) if re.search(r'image_(\d+)', x) else 0)
    
    return images[0] if images else None


# ================= API 路由 =================
@app.get("/api/albums", response_model=List[Album])
async def get_albums():
    """获取所有专辑列表（包括原始专辑和自定义专辑）"""
    data = get_source_data()
    custom_albums = get_custom_albums()
    albums = []
    
    # 计算所有笔记总数（包括自定义专辑中的笔记）
    total_count = sum(len(album.get('notes', [])) for album in data)
    for album_name, notes in custom_albums.items():
        total_count += len(notes)
    albums.append(Album(name="全部笔记", count=total_count))
    
    # 计算已下载笔记数量
    downloaded_count = 0
    for album_data in data:
        album_name = album_data.get('name', '')
        for note in album_data.get('notes', []):
            raw_id = note.get('id', '')
            note_id = raw_id.split('?')[0]
            note_title = note.get('title', '')
            note_path = find_note_folder(album_name, note_id, note_title)
            if note_path:
                downloaded_count += 1
    
    albums.append(Album(name="已下载", count=downloaded_count))
    
    # 计算星标笔记数量
    starred_status_data = get_starred_status()
    starred_count = len([note_id for note_id, is_starred in starred_status_data.items() if is_starred])
    albums.append(Album(name="星标", count=starred_count))
    
    # 添加原始专辑
    for album in data:
        albums.append(Album(
            name=album.get('name', '未知专辑'),
            count=len(album.get('notes', []))
        ))
    
    # 添加自定义专辑
    for album_name, notes in custom_albums.items():
        albums.append(Album(
            name=album_name,
            count=len(notes)
        ))
    
    return albums


@app.get("/api/notes")
async def get_notes(
    album: Optional[str] = Query(None, description="专辑名称，不传则返回全部"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    learning_status: Optional[str] = Query(None, description="学习状态筛选: learned, unlearned")
):
    """获取笔记列表（包括原始专辑和自定义专辑）"""
    data = get_source_data()
    custom_albums = get_custom_albums()
    learning_status_data = get_learning_status()
    starred_status_data = get_starred_status()
    all_notes = []
    
    # 处理原始专辑
    for album_data in data:
        album_name = album_data.get('name', '')
        
        # 筛选专辑（星标专辑在最后统一筛选）
        if album and album != "全部笔记" and album != "星标" and album_name != album:
            continue
        
        for note in album_data.get('notes', []):
            raw_id = note.get('id', '')
            note_id = raw_id.split('?')[0]
            note_title = note.get('title', '')
            
            # 查找本地文件夹
            note_path = find_note_folder(album_name, note_id, note_title)
            has_local = note_path is not None
            
            # 构建封面 URL
            cover = note.get('cover', '')
            if has_local:
                # 使用本地第一张图片作为封面
                local_cover = get_local_cover(note_path)
                if local_cover:
                    safe_album = sanitize_filename(album_name)
                    folder_name = os.path.basename(note_path)
                    cover = f"/api/media/{safe_album}/{folder_name}/{local_cover}"
            
            # 获取学习状态和星标状态
            note_id_pure = note_id
            is_learned = learning_status_data.get(note_id_pure, False)
            is_starred = starred_status_data.get(note_id_pure, False)
            
            note_info = {
                **note,
                "album": album_name,
                "hasLocal": has_local,
                "cover": cover,  # 覆盖原始封面
                "isLearned": is_learned,
                "isStarred": is_starred
            }
            all_notes.append(note_info)
    
    # 处理自定义专辑
    for album_name, notes in custom_albums.items():
        # 筛选专辑（星标专辑在最后统一筛选）
        if album and album != "全部笔记" and album != "星标" and album_name != album:
            continue
        
        for note in notes:
            raw_id = note.get('id', '')
            note_id = raw_id.split('?')[0]
            note_title = note.get('title', '')
            
            # 查找本地文件夹（可能在原始专辑中）
            note_path = None
            # 先尝试在原始专辑中查找
            for album_data in data:
                original_album_name = album_data.get('name', '')
                path = find_note_folder(original_album_name, note_id, note_title)
                if path:
                    note_path = path
                    break
            
            has_local = note_path is not None
            
            # 构建封面 URL
            cover = note.get('cover', '')
            if has_local and note_path:
                local_cover = get_local_cover(note_path)
                if local_cover:
                    # 获取原始专辑名用于构建路径
                    for album_data in data:
                        original_album_name = album_data.get('name', '')
                        path = find_note_folder(original_album_name, note_id, note_title)
                        if path:
                            safe_album = sanitize_filename(original_album_name)
                            folder_name = os.path.basename(note_path)
                            cover = f"/api/media/{safe_album}/{folder_name}/{local_cover}"
                            break
            
            # 获取学习状态和星标状态
            note_id_pure = note_id
            is_learned = learning_status_data.get(note_id_pure, False)
            is_starred = starred_status_data.get(note_id_pure, False)
            
            note_info = {
                **note,
                "album": album_name,
                "hasLocal": has_local,
                "cover": cover,
                "isLearned": is_learned,
                "isStarred": is_starred
            }
            all_notes.append(note_info)
    
    # 去重（基于笔记ID）
    seen_ids = set()
    unique_notes = []
    for note in all_notes:
        note_id = note.get('id', '').split('?')[0]
        if note_id not in seen_ids:
            seen_ids.add(note_id)
            unique_notes.append(note)
        elif album and album != "全部笔记":
            # 如果指定了专辑，允许显示（因为可能在不同专辑中）
            unique_notes.append(note)
    
    # 应用星标筛选（当album为"星标"时）
    if album == "星标":
        unique_notes = [n for n in unique_notes if n.get('isStarred', False)]
    
    # 应用学习状态筛选
    if learning_status:
        if learning_status == "learned":
            unique_notes = [n for n in unique_notes if n.get('isLearned', False)]
        elif learning_status == "unlearned":
            unique_notes = [n for n in unique_notes if not n.get('isLearned', False)]
    
    # 分页
    total = len(unique_notes)
    start = (page - 1) * page_size
    end = start + page_size
    
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "notes": unique_notes[start:end]
    }


@app.post("/api/notes/{note_id}/learning-status")
async def toggle_learning_status(note_id: str):
    """切换笔记的学习状态"""
    learning_status_data = get_learning_status()
    
    # 切换状态
    current_status = learning_status_data.get(note_id, False)
    learning_status_data[note_id] = not current_status
    save_learning_status(learning_status_data)
    
    return {
        "note_id": note_id,
        "is_learned": learning_status_data[note_id],
        "message": "已标记为已学习" if learning_status_data[note_id] else "已标记为未学习"
    }


@app.post("/api/notes/{note_id}/starred-status")
async def toggle_starred_status(note_id: str):
    """切换笔记的星标状态"""
    starred_status_data = get_starred_status()
    
    # 切换状态
    current_status = starred_status_data.get(note_id, False)
    starred_status_data[note_id] = not current_status
    save_starred_status(starred_status_data)
    
    return {
        "note_id": note_id,
        "is_starred": starred_status_data[note_id],
        "message": "已添加星标" if starred_status_data[note_id] else "已取消星标"
    }


@app.get("/api/notes/{note_id}")
async def get_note_detail(note_id: str):
    """获取笔记详情"""
    data = get_source_data()
    learning_status_data = get_learning_status()
    starred_status_data = get_starred_status()
    is_learned = learning_status_data.get(note_id, False)
    is_starred = starred_status_data.get(note_id, False)
    
    # 查找笔记
    for album_data in data:
        album_name = album_data.get('name', '')
        for note in album_data.get('notes', []):
            raw_id = note.get('id', '')
            pure_id = raw_id.split('?')[0]
            
            if pure_id == note_id:
                # 使用新的查找函数
                note_path = find_note_folder(album_name, note_id, note.get('title', ''))
                
                if note_path:
                    local_data = get_local_note_detail(note_path)
                    if local_data:
                        metadata = local_data['metadata']
                        user = metadata.get('user', {})
                        interact_info = metadata.get('interact_info', {})
                        tag_list = metadata.get('tag_list', [])
                        
                        # 获取文件夹名用于构建媒体 URL
                        folder_name = os.path.basename(note_path)
                        safe_album = sanitize_filename(album_name)
                        
                        # 处理标签：兼容字符串和字典格式
                        tags = []
                        for tag in tag_list:
                            if isinstance(tag, dict):
                                tags.append(tag.get('name', ''))
                            elif isinstance(tag, str):
                                tags.append(tag)
                        
                        return {
                            "id": note_id,
                            "title": metadata.get('title', ''),
                            "desc": metadata.get('desc', ''),
                            "author": user.get('nickname', note.get('author', '')),
                            "authorId": user.get('user_id', ''),
                            "authorAvatar": user.get('avatar', note.get('authorAvatar', '')),
                            "likes": interact_info.get('liked_count', 0),
                            "collects": interact_info.get('collected_count', 0),
                            "comments": interact_info.get('comment_count', 0),
                            "shares": interact_info.get('share_count', 0),
                            "tags": tags,
                            "images": [f"/api/media/{safe_album}/{folder_name}/{img}" 
                                      for img in local_data['images']],
                            "video": f"/api/media/{safe_album}/{folder_name}/{local_data['video']}" 
                                    if local_data['video'] else None,
                            "type": metadata.get('type', 'normal'),
                            "album": album_name,
                            "hasLocal": True,
                            "time": metadata.get('time', ''),
                            "noteUrl": metadata.get('note_url', f"https://www.xiaohongshu.com/explore/{note_id}"),
                            "isLearned": is_learned,
                            "isStarred": is_starred
                        }
                
                # 未下载到本地，返回基础信息
                return {
                    "id": note_id,
                    "title": note.get('title', ''),
                    "desc": "",
                    "author": note.get('author', ''),
                    "authorId": "",
                    "authorAvatar": note.get('authorAvatar', ''),
                    "likes": note.get('likes', 0),
                    "collects": note.get('collects', 0),
                    "comments": 0,
                    "shares": 0,
                    "tags": note.get('tags', []),
                    "images": [note.get('cover', '')] if note.get('cover') else [],
                    "video": None,
                    "type": note.get('type', 'normal'),
                    "album": album_name,
                    "hasLocal": False,
                    "noteUrl": note.get('link', f"https://www.xiaohongshu.com/explore/{note_id}"),
                    "isLearned": is_learned,
                    "isStarred": is_starred
                }
    
    raise HTTPException(status_code=404, detail="笔记不存在")


@app.get("/api/search")
async def search_notes(
    q: str = Query(..., min_length=1, description="搜索关键词"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100)
):
    """搜索笔记"""
    data = get_source_data()
    results = []
    
    keyword = q.lower()
    
    for album_data in data:
        album_name = album_data.get('name', '')
        
        for note in album_data.get('notes', []):
            title = note.get('title', '').lower()
            author = note.get('author', '').lower()
            tags = ' '.join(note.get('tags', [])).lower()
            
            # 搜索标题、作者、标签
            if keyword in title or keyword in author or keyword in tags or keyword in album_name.lower():
                raw_id = note.get('id', '')
                note_id = raw_id.split('?')[0]
                note_title = note.get('title', '')
                
                # 查找本地文件夹
                note_path = find_note_folder(album_name, note_id, note_title)
                has_local = note_path is not None
                
                # 构建封面 URL
                cover = note.get('cover', '')
                if has_local:
                    local_cover = get_local_cover(note_path)
                    if local_cover:
                        safe_album = sanitize_filename(album_name)
                        folder_name = os.path.basename(note_path)
                        cover = f"/api/media/{safe_album}/{folder_name}/{local_cover}"
                
                note_info = {
                    **note,
                    "album": album_name,
                    "hasLocal": has_local,
                    "cover": cover
                }
                results.append(note_info)
    
    # 分页
    total = len(results)
    start = (page - 1) * page_size
    end = start + page_size
    
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "keyword": q,
        "notes": results[start:end]
    }


@app.get("/api/media/{album_name}/{note_folder}/{filename}")
async def get_media(album_name: str, note_folder: str, filename: str):
    """获取媒体文件（图片/视频）"""
    # album_name 已经是安全的文件夹名
    file_path = os.path.join(DATA_DIR, album_name, note_folder, filename)
    
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="文件不存在")
    
    # 设置正确的 MIME 类型
    ext = filename.lower().split('.')[-1]
    media_types = {
        'jpg': 'image/jpeg',
        'jpeg': 'image/jpeg',
        'png': 'image/png',
        'gif': 'image/gif',
        'webp': 'image/webp',
        'mp4': 'video/mp4',
        'mov': 'video/quicktime',
        'webm': 'video/webm',
    }
    media_type = media_types.get(ext, 'application/octet-stream')
    
    return FileResponse(file_path, media_type=media_type)


@app.get("/api/stats")
async def get_stats():
    """获取统计信息"""
    data = get_source_data()
    
    total_notes = 0
    downloaded_notes = 0
    albums_count = len(data)
    
    for album_data in data:
        album_name = album_data.get('name', '')
        notes = album_data.get('notes', [])
        total_notes += len(notes)
        
        for note in notes:
            raw_id = note.get('id', '')
            note_id = raw_id.split('?')[0]
            if find_note_folder(album_name, note_id, note.get('title', '')):
                downloaded_notes += 1
    
    # 计算本地存储大小
    storage_size = 0
    if os.path.exists(DATA_DIR):
        for root, dirs, files in os.walk(DATA_DIR):
            for file in files:
                storage_size += os.path.getsize(os.path.join(root, file))
    
    return {
        "total_albums": albums_count,
        "total_notes": total_notes,
        "downloaded_notes": downloaded_notes,
        "pending_notes": total_notes - downloaded_notes,
        "download_progress": round(downloaded_notes / total_notes * 100, 1) if total_notes > 0 else 0,
        "storage_size_mb": round(storage_size / 1024 / 1024, 2)
    }


@app.get("/api/local-albums")
async def get_local_albums():
    """获取本地已下载的专辑列表（直接扫描文件系统）"""
    albums = []
    
    if not os.path.exists(DATA_DIR):
        return albums
    
    for album_name in sorted(os.listdir(DATA_DIR)):
        album_path = os.path.join(DATA_DIR, album_name)
        if not os.path.isdir(album_path):
            continue
        
        notes = []
        for note_folder in os.listdir(album_path):
            note_path = os.path.join(album_path, note_folder)
            metadata_path = os.path.join(note_path, "metadata.json")
            
            if os.path.isdir(note_path) and os.path.exists(metadata_path):
                try:
                    with open(metadata_path, 'r', encoding='utf-8') as f:
                        metadata = json.load(f)
                    
                    # 获取媒体文件
                    images = [f for f in os.listdir(note_path) 
                             if f.startswith('image_') and f.endswith(('.jpg', '.jpeg', '.png', '.webp', '.gif'))]
                    has_video = any(f.startswith('video') for f in os.listdir(note_path))
                    
                    notes.append({
                        "id": metadata.get('note_id', ''),
                        "title": metadata.get('title', ''),
                        "desc": metadata.get('desc', '')[:100] if metadata.get('desc') else '',
                        "author": metadata.get('user', {}).get('nickname', ''),
                        "authorAvatar": metadata.get('user', {}).get('avatar', ''),
                        "type": 'video' if has_video else 'normal',
                        "imageCount": len(images),
                        "hasVideo": has_video,
                        "folder": note_folder,
                        "albumFolder": album_name,
                    })
                except Exception:
                    pass
        
        if notes:
            albums.append({
                "name": album_name,
                "count": len(notes),
                "notes": notes
            })
    
    return albums


@app.post("/api/custom-albums")
async def create_custom_album(request: CreateAlbumRequest):
    """创建自定义专辑"""
    custom_albums = get_custom_albums()
    
    # 检查专辑名是否已存在
    if request.name in custom_albums:
        raise HTTPException(status_code=400, detail="专辑名称已存在")
    
    # 检查是否与原始专辑重名
    source_data = get_source_data()
    for album in source_data:
        if album.get('name') == request.name:
            raise HTTPException(status_code=400, detail="专辑名称已存在")
    
    # 创建新专辑
    custom_albums[request.name] = []
    save_custom_albums(custom_albums)
    
    return {"message": "专辑创建成功", "name": request.name}


@app.get("/api/custom-albums")
async def get_custom_albums_list():
    """获取所有自定义专辑列表"""
    custom_albums = get_custom_albums()
    return [{"name": name, "count": len(notes)} for name, notes in custom_albums.items()]


@app.post("/api/notes/{note_id}/move")
async def move_or_copy_note(note_id: str, request: MoveNoteRequest):
    """移动或复制笔记到指定专辑"""
    # 验证操作类型
    if request.operation not in ["copy", "move"]:
        raise HTTPException(status_code=400, detail="操作类型必须是 'copy' 或 'move'")
    
    # 查找笔记
    source_data = get_source_data()
    note_info = None
    source_album_name = None
    
    for album_data in source_data:
        album_name = album_data.get('name', '')
        for note in album_data.get('notes', []):
            raw_id = note.get('id', '')
            pure_id = raw_id.split('?')[0]
            
            if pure_id == note_id:
                note_info = note.copy()
                source_album_name = album_name
                break
        
        if note_info:
            break
    
    # 如果不在原始数据中，检查自定义专辑
    if not note_info:
        custom_albums = get_custom_albums()
        for album_name, notes in custom_albums.items():
            for note in notes:
                raw_id = note.get('id', '')
                pure_id = raw_id.split('?')[0]
                
                if pure_id == note_id:
                    note_info = note.copy()
                    source_album_name = album_name
                    break
            
            if note_info:
                break
    
    if not note_info:
        raise HTTPException(status_code=404, detail="笔记不存在")
    
    # 检查目标专辑是否存在
    custom_albums = get_custom_albums()
    if request.target_album not in custom_albums:
        # 检查是否是原始专辑
        is_original_album = False
        for album_data in source_data:
            if album_data.get('name') == request.target_album:
                is_original_album = True
                break
        
        if not is_original_album:
            raise HTTPException(status_code=404, detail="目标专辑不存在")
    
    # 检查目标专辑类型
    is_target_original = False
    for album_data in source_data:
        if album_data.get('name') == request.target_album:
            is_target_original = True
            break
    
    # 如果是复制操作
    if request.operation == "copy":
        if request.target_album in custom_albums:
            # 目标专辑是自定义专辑
            existing_ids = [n.get('id', '').split('?')[0] for n in custom_albums[request.target_album]]
            if note_id not in existing_ids:
                custom_albums[request.target_album].append(note_info)
                save_custom_albums(custom_albums)
            else:
                raise HTTPException(status_code=400, detail="笔记已存在于该专辑中")
        elif is_target_original:
            # 目标专辑是原始专辑，检查笔记是否已在原始专辑中
            note_in_original = False
            for album_data in source_data:
                if album_data.get('name') == request.target_album:
                    for note in album_data.get('notes', []):
                        if note.get('id', '').split('?')[0] == note_id:
                            note_in_original = True
                            break
                    break
            
            if note_in_original:
                # 笔记已在原始专辑中，创建同名自定义专辑来存储副本
                if request.target_album not in custom_albums:
                    custom_albums[request.target_album] = []
                existing_ids = [n.get('id', '').split('?')[0] for n in custom_albums[request.target_album]]
                if note_id not in existing_ids:
                    custom_albums[request.target_album].append(note_info)
                    save_custom_albums(custom_albums)
                else:
                    raise HTTPException(status_code=400, detail="笔记已存在于该专辑中")
            else:
                # 笔记不在原始专辑中，添加到同名自定义专辑
                if request.target_album not in custom_albums:
                    custom_albums[request.target_album] = []
                existing_ids = [n.get('id', '').split('?')[0] for n in custom_albums[request.target_album]]
                if note_id not in existing_ids:
                    custom_albums[request.target_album].append(note_info)
                    save_custom_albums(custom_albums)
                else:
                    raise HTTPException(status_code=400, detail="笔记已存在于该专辑中")
        else:
            raise HTTPException(status_code=404, detail="目标专辑不存在")
    
    # 如果是移动操作
    elif request.operation == "move":
        if request.target_album in custom_albums:
            # 目标专辑是自定义专辑
            # 从源专辑移除（如果源专辑是自定义专辑）
            if source_album_name in custom_albums:
                custom_albums[source_album_name] = [
                    n for n in custom_albums[source_album_name]
                    if n.get('id', '').split('?')[0] != note_id
                ]
            
            # 添加到目标专辑（如果不存在）
            existing_ids = [n.get('id', '').split('?')[0] for n in custom_albums[request.target_album]]
            if note_id not in existing_ids:
                custom_albums[request.target_album].append(note_info)
            else:
                raise HTTPException(status_code=400, detail="笔记已存在于该专辑中")
            
            save_custom_albums(custom_albums)
        elif is_target_original:
            # 目标专辑是原始专辑
            # 检查笔记是否已在原始专辑中
            note_in_original = False
            for album_data in source_data:
                if album_data.get('name') == request.target_album:
                    for note in album_data.get('notes', []):
                        if note.get('id', '').split('?')[0] == note_id:
                            note_in_original = True
                            break
                    break
            
            # 从源专辑移除（如果源专辑是自定义专辑）
            if source_album_name in custom_albums:
                custom_albums[source_album_name] = [
                    n for n in custom_albums[source_album_name]
                    if n.get('id', '').split('?')[0] != note_id
                ]
            
            if note_in_original:
                # 笔记已在原始专辑中，如果也在自定义专辑中则移除
                if request.target_album in custom_albums:
                    custom_albums[request.target_album] = [
                        n for n in custom_albums[request.target_album]
                        if n.get('id', '').split('?')[0] != note_id
                    ]
                    save_custom_albums(custom_albums)
            else:
                # 笔记不在原始专辑中，添加到同名自定义专辑
                if request.target_album not in custom_albums:
                    custom_albums[request.target_album] = []
                existing_ids = [n.get('id', '').split('?')[0] for n in custom_albums[request.target_album]]
                if note_id not in existing_ids:
                    custom_albums[request.target_album].append(note_info)
                    save_custom_albums(custom_albums)
                else:
                    raise HTTPException(status_code=400, detail="笔记已存在于该专辑中")
        else:
            raise HTTPException(status_code=404, detail="目标专辑不存在")
    
    return {
        "message": f"笔记已{'复制' if request.operation == 'copy' else '移动'}到专辑 {request.target_album}",
        "operation": request.operation,
        "target_album": request.target_album
    }


# ================= 静态文件 =================
# 确保 static 目录存在
os.makedirs(STATIC_DIR, exist_ok=True)


@app.get("/", response_class=HTMLResponse)
async def root():
    """返回首页"""
    index_path = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_path):
        with open(index_path, 'r', encoding='utf-8') as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse(content="<h1>请先创建 static/index.html</h1>")


@app.get("/view/{note_id}", response_class=HTMLResponse)
async def immersive_view(note_id: str):
    """沉浸式查看笔记页面"""
    # 获取笔记详情
    data = get_source_data()
    note_detail = None
    album_name = ""
    
    for album_data in data:
        album_name = album_data.get('name', '')
        for note in album_data.get('notes', []):
            raw_id = note.get('id', '')
            pure_id = raw_id.split('?')[0]
            
            if pure_id == note_id:
                # 查找本地文件夹
                note_path = find_note_folder(album_name, note_id, note.get('title', ''))
                
                if note_path:
                    local_data = get_local_note_detail(note_path)
                    if local_data:
                        metadata = local_data['metadata']
                        user = metadata.get('user', {})
                        interact_info = metadata.get('interact_info', {})
                        tag_list = metadata.get('tag_list', [])
                        
                        folder_name = os.path.basename(note_path)
                        safe_album = sanitize_filename(album_name)
                        
                        # 处理标签
                        tags = []
                        for tag in tag_list:
                            if isinstance(tag, dict):
                                tags.append(tag.get('name', ''))
                            elif isinstance(tag, str):
                                tags.append(tag)
                        
                        note_detail = {
                            "id": note_id,
                            "title": metadata.get('title', ''),
                            "desc": metadata.get('desc', ''),
                            "author": user.get('nickname', note.get('author', '')),
                            "authorAvatar": user.get('avatar', note.get('authorAvatar', '')),
                            "likes": interact_info.get('liked_count', 0),
                            "collects": interact_info.get('collected_count', 0),
                            "comments": interact_info.get('comment_count', 0),
                            "shares": interact_info.get('share_count', 0),
                            "tags": tags,
                            "images": [f"/api/media/{safe_album}/{folder_name}/{img}" 
                                      for img in local_data['images']],
                            "video": f"/api/media/{safe_album}/{folder_name}/{local_data['video']}" 
                                    if local_data['video'] else None,
                            "type": metadata.get('type', 'normal'),
                            "album": album_name,
                            "hasLocal": True,
                            "noteUrl": metadata.get('note_url', f"https://www.xiaohongshu.com/explore/{note_id}")
                        }
                        break
                
                if not note_detail:
                    # 未下载，使用基础信息
                    note_detail = {
                        "id": note_id,
                        "title": note.get('title', ''),
                        "desc": "",
                        "author": note.get('author', ''),
                        "authorAvatar": note.get('authorAvatar', ''),
                        "likes": note.get('likes', 0),
                        "collects": note.get('collects', 0),
                        "comments": 0,
                        "shares": 0,
                        "tags": note.get('tags', []),
                        "images": [note.get('cover', '')] if note.get('cover') else [],
                        "video": None,
                        "type": note.get('type', 'normal'),
                        "album": album_name,
                        "hasLocal": False,
                        "noteUrl": note.get('link', f"https://www.xiaohongshu.com/explore/{note_id}")
                    }
                break
    
    if not note_detail:
        return HTMLResponse(content="<h1>笔记不存在</h1>", status_code=404)
    
    # 生成沉浸式查看页面
    html_content = generate_immersive_html(note_detail)
    return HTMLResponse(content=html_content)


def generate_immersive_html(note_detail: dict) -> str:
    """生成沉浸式查看页面的 HTML"""
    # 收集所有媒体（视频优先，然后是图片）
    all_media = []
    if note_detail.get('video'):
        all_media.append({'type': 'video', 'url': note_detail['video']})
    if note_detail.get('images'):
        for img in note_detail['images']:
            all_media.append({'type': 'image', 'url': img})
    
    # 生成媒体项 HTML（只显示第一张，通过 JS 控制切换）
    media_html = ""
    if all_media:
        for idx, media in enumerate(all_media):
            display_style = "flex" if idx == 0 else "none"
            if media['type'] == 'video':
                media_html += f'<div class="media-item" data-index="{idx}" style="display: {display_style}"><video src="{media["url"]}" controls></video></div>'
            else:
                media_html += f'<div class="media-item" data-index="{idx}" style="display: {display_style}"><img src="{media["url"]}" alt="笔记图片" loading="lazy"></div>'
    else:
        media_html = '<div class="media-item"><div class="no-media">暂无媒体内容</div></div>'
    
    tags_html = ""
    if note_detail.get('tags'):
        tags_html = '<div class="tags">' + ''.join([f'<span class="tag">#{escape_html(tag)}</span>' for tag in note_detail['tags']]) + '</div>'
    
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{escape_html(note_detail.get('title', '笔记详情'))}</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            font-family: 'Noto Sans SC', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            background: #000;
            color: #fff;
            line-height: 1.6;
            overflow-x: hidden;
        }}
        
        .container {{
            max-width: 100%;
            margin: 0 auto;
            padding: 0;
        }}
        
        .header {{
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            background: linear-gradient(to bottom, rgba(0,0,0,0.8), transparent);
            padding: 20px 40px;
            z-index: 100;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        
        .back-btn {{
            background: rgba(255,255,255,0.1);
            border: 1px solid rgba(255,255,255,0.2);
            color: #fff;
            padding: 10px 20px;
            border-radius: 8px;
            text-decoration: none;
            backdrop-filter: blur(10px);
            transition: all 0.3s;
        }}
        
        .back-btn:hover {{
            background: rgba(255,255,255,0.2);
        }}
        
        .header-actions {{
            display: flex;
            gap: 12px;
        }}
        
        .action-btn {{
            background: rgba(255,255,255,0.1);
            border: 1px solid rgba(255,255,255,0.2);
            color: #fff;
            padding: 10px 20px;
            border-radius: 8px;
            text-decoration: none;
            backdrop-filter: blur(10px);
            transition: all 0.3s;
            font-size: 14px;
        }}
        
        .action-btn:hover {{
            background: rgba(255,255,255,0.2);
        }}
        
        .action-btn.primary {{
            background: #ff4757;
            border-color: #ff4757;
        }}
        
        .action-btn.primary:hover {{
            background: #ff6b7a;
        }}
        
        .content {{
            padding-top: 80px;
            display: flex;
            height: calc(100vh - 80px);
            overflow: hidden;
        }}
        
        .media-section {{
            flex: 2;
            display: flex;
            flex-direction: column;
            justify-content: center;
            align-items: center;
            background: #111;
            position: relative;
            overflow: hidden;
        }}
        
        .media-container {{
            width: 100%;
            height: 100%;
            display: flex;
            justify-content: center;
            align-items: center;
            position: relative;
        }}
        
        .media-item {{
            width: 100%;
            height: 100%;
            display: flex;
            justify-content: center;
            align-items: center;
            position: absolute;
            top: 0;
            left: 0;
        }}
        
        .media-item img {{
            max-width: 100%;
            max-height: 100%;
            object-fit: contain;
        }}
        
        .media-item video {{
            max-width: 100%;
            max-height: 100%;
        }}
        
        .no-media {{
            color: #666;
            font-size: 18px;
            text-align: center;
        }}
        
        .media-nav {{
            position: absolute;
            bottom: 30px;
            left: 50%;
            transform: translateX(-50%);
            display: flex;
            align-items: center;
            gap: 20px;
            background: rgba(0, 0, 0, 0.6);
            padding: 12px 24px;
            border-radius: 30px;
            backdrop-filter: blur(10px);
        }}
        
        .nav-btn {{
            background: rgba(255, 255, 255, 0.2);
            border: 1px solid rgba(255, 255, 255, 0.3);
            color: #fff;
            width: 40px;
            height: 40px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            cursor: pointer;
            font-size: 20px;
            transition: all 0.3s;
            user-select: none;
        }}
        
        .nav-btn:hover {{
            background: rgba(255, 255, 255, 0.3);
        }}
        
        .nav-btn:disabled {{
            opacity: 0.3;
            cursor: not-allowed;
        }}
        
        .media-indicator {{
            color: #fff;
            font-size: 14px;
            min-width: 60px;
            text-align: center;
        }}
        
        .info-section {{
            flex: 1;
            min-width: 400px;
            max-width: 800px;
            padding: 40px;
            overflow-y: auto;
            background: #0a0a0a;
        }}
        
        .author-info {{
            display: flex;
            align-items: center;
            gap: 16px;
            margin-bottom: 24px;
        }}
        
        .author-avatar {{
            width: 50px;
            height: 50px;
            border-radius: 50%;
            object-fit: cover;
        }}
        
        .author-details {{
            flex: 1;
        }}
        
        .author-name {{
            font-size: 18px;
            font-weight: 600;
            margin-bottom: 4px;
        }}
        
        .album-name {{
            font-size: 14px;
            color: #999;
        }}
        
        .title {{
            font-size: 32px;
            font-weight: 700;
            margin-bottom: 24px;
            line-height: 1.4;
        }}
        
        .desc {{
            font-size: 18px;
            line-height: 1.8;
            margin-bottom: 24px;
            white-space: pre-wrap;
            color: #e0e0e0;
        }}
        
        .tags {{
            display: flex;
            flex-wrap: wrap;
            gap: 12px;
            margin-bottom: 32px;
        }}
        
        .tag {{
            background: rgba(255, 71, 87, 0.2);
            color: #ff6b7a;
            padding: 8px 16px;
            border-radius: 20px;
            font-size: 14px;
        }}
        
        .stats {{
            display: flex;
            gap: 32px;
            padding: 24px 0;
            border-top: 1px solid rgba(255,255,255,0.1);
            border-bottom: 1px solid rgba(255,255,255,0.1);
        }}
        
        .stat-item {{
            display: flex;
            align-items: center;
            gap: 8px;
            font-size: 16px;
        }}
        
        .stat-icon {{
            font-size: 20px;
        }}
        
        @media (max-width: 1024px) {{
            .content {{
                flex-direction: column;
                height: auto;
            }}
            
            .media-section {{
                height: 60vh;
                min-height: 400px;
            }}
            
            .info-section {{
                width: 100%;
                max-height: 40vh;
            }}
        }}
        
        @media (max-width: 768px) {{
            .header {{
                padding: 16px 20px;
            }}
            
            .info-section {{
                padding: 24px 20px;
            }}
            
            .title {{
                font-size: 24px;
            }}
            
            .desc {{
                font-size: 16px;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <a href="/" class="back-btn">← 返回</a>
            <div class="header-actions">
                <a href="{note_detail.get('noteUrl', '#')}" class="action-btn primary" target="_blank">🔗 查看原文</a>
            </div>
        </div>
        
        <div class="content">
            <div class="media-section">
                <div class="media-container">
                    {media_html}
                </div>
                {('<div class="media-nav"><button class="nav-btn" id="prev-btn" onclick="changeMedia(-1)">‹</button><span class="media-indicator" id="media-indicator">1 / ' + str(len(all_media)) + '</span><button class="nav-btn" id="next-btn" onclick="changeMedia(1)">›</button></div>' if len(all_media) > 1 else '')}
            </div>
            
            <div class="info-section">
                <div class="author-info">
                    <img src="{note_detail.get('authorAvatar', '')}" alt="" class="author-avatar" onerror="this.style.display='none'">
                    <div class="author-details">
                        <div class="author-name">{escape_html(note_detail.get('author', '未知作者'))}</div>
                        <div class="album-name">{escape_html(note_detail.get('album', ''))}</div>
                    </div>
                </div>
                
                <h1 class="title">{escape_html(note_detail.get('title', '无标题'))}</h1>
                
                {('<div class="desc">' + escape_html(note_detail.get('desc', '')) + '</div>') if note_detail.get('desc') else ''}
                
                {tags_html}
                
                <div class="stats">
                    <div class="stat-item">
                        <span class="stat-icon">❤️</span>
                        <span>{format_number(note_detail.get('likes', 0))}</span>
                    </div>
                    <div class="stat-item">
                        <span class="stat-icon">⭐</span>
                        <span>{format_number(note_detail.get('collects', 0))}</span>
                    </div>
                    <div class="stat-item">
                        <span class="stat-icon">💬</span>
                        <span>{format_number(note_detail.get('comments', 0))}</span>
                    </div>
                    <div class="stat-item">
                        <span class="stat-icon">🔄</span>
                        <span>{format_number(note_detail.get('shares', 0))}</span>
                    </div>
                </div>
            </div>
        </div>
    </div>
    
    <script>
        let currentMediaIndex = 0;
        const mediaItems = document.querySelectorAll('.media-item');
        const totalMedia = mediaItems.length;
        const prevBtn = document.getElementById('prev-btn');
        const nextBtn = document.getElementById('next-btn');
        const indicator = document.getElementById('media-indicator');
        
        function updateMediaDisplay() {{
            mediaItems.forEach((item, index) => {{
                item.style.display = index === currentMediaIndex ? 'flex' : 'none';
            }});
            
            if (indicator) {{
                indicator.textContent = `${{currentMediaIndex + 1}} / ${{totalMedia}}`;
            }}
            
            if (prevBtn) {{
                prevBtn.disabled = currentMediaIndex === 0;
            }}
            if (nextBtn) {{
                nextBtn.disabled = currentMediaIndex === totalMedia - 1;
            }}
            
            // 停止之前的视频播放
            mediaItems.forEach(item => {{
                const video = item.querySelector('video');
                if (video && item.style.display === 'none') {{
                    video.pause();
                }}
            }});
        }}
        
        function changeMedia(direction) {{
            const newIndex = currentMediaIndex + direction;
            if (newIndex >= 0 && newIndex < totalMedia) {{
                currentMediaIndex = newIndex;
                updateMediaDisplay();
            }}
        }}
        
        // 键盘导航
        document.addEventListener('keydown', function(e) {{
            if (e.key === 'ArrowLeft') {{
                changeMedia(-1);
            }} else if (e.key === 'ArrowRight') {{
                changeMedia(1);
            }}
        }});
        
        // 初始化
        updateMediaDisplay();
        
        // 平滑滚动
        document.querySelectorAll('a[href^="#"]').forEach(anchor => {{
            anchor.addEventListener('click', function (e) {{
                e.preventDefault();
                const target = document.querySelector(this.getAttribute('href'));
                if (target) {{
                    target.scrollIntoView({{ behavior: 'smooth' }});
                }}
            }});
        }});
    </script>
</body>
</html>"""


def escape_html(text: str) -> str:
    """转义 HTML 特殊字符"""
    if not text:
        return ""
    return (text
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&#x27;"))


def format_number(num) -> str:
    """格式化数字"""
    if num is None:
        return "0"
    n = int(num) if isinstance(num, (int, float, str)) else 0
    if n >= 10000:
        return f"{n / 10000:.1f}w"
    if n >= 1000:
        return f"{n / 1000:.1f}k"
    return str(n)


# 挂载静态文件目录
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


# ================= 启动入口 =================
if __name__ == "__main__":
    import uvicorn
    print("🚀 启动服务器...")
    print("📝 访问地址: http://localhost:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000)

