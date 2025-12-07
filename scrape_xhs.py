import asyncio
import json
import os
from playwright.async_api import async_playwright

# 目标数据文件
OUTPUT_FILE = "my_xhs_data.json"


def load_existing_data():
    """读取现有的 JSON 文件，如果不存在返回空列表"""
    if os.path.exists(OUTPUT_FILE):
        try:
            with open(OUTPUT_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"⚠️ 读取旧文件失败，将创建新文件: {e}")
            return []
    return []


async def extract_single_note_element(el, index):
    """提取单个 DOM 元素的数据"""
    try:
        # 1. 提取链接 (关键：用于获取 ID)
        link_el = await el.query_selector('a.cover')
        if not link_el:
            link_el = await el.query_selector('a[href^="/explore/"]')

        href = await link_el.get_attribute('href') if link_el else ""
        if not href:
            return None  # 没有链接通常是无效元素

        note_id = href.split('/')[-1]
        full_link = f"https://www.xiaohongshu.com{href}"

        # 2. 提取标题
        title_el = await el.query_selector('.footer .title span')
        title = await title_el.inner_text() if title_el else "无标题"

        # 3. 提取封面
        img_el = await el.query_selector('.cover img')
        cover_url = await img_el.get_attribute('src') if img_el else ""

        # 4. 提取作者
        author_el = await el.query_selector('.author-wrapper .name')
        author = await author_el.inner_text() if author_el else "未知作者"

        # 5. 提取头像
        avatar_el = await el.query_selector('.author-wrapper img')
        avatar = await avatar_el.get_attribute('src') if avatar_el else ""

        # 6. 提取点赞
        like_el = await el.query_selector('.like-wrapper .count')
        likes = await like_el.inner_text() if like_el else "0"

        is_video = await el.query_selector('.play-icon') is not None

        return {
            "id": note_id,
            "title": title,
            "cover": cover_url,
            "author": author,
            "authorAvatar": avatar,
            "type": "video" if is_video else "normal",
            "likes": likes,
            "collects": 0,
            "link": full_link,
            "tags": []
        }
    except Exception as e:
        # 某些特殊广告位或无效元素可能会报错，忽略即可
        return None


async def scrape_album_incrementally(page, album_name, existing_album_notes):
    """
    边滚动边抓取，并与旧数据合并
    """
    # 将旧笔记转为字典，Key 为 ID，方便快速查找和更新
    # 结构: { "note_id_1": {data...}, "note_id_2": {data...} }
    notes_map = {note['id']: note for note in existing_album_notes}

    print(f">>> 开始抓取专辑 '{album_name}'...")
    print(f"    当前已有存档笔记: {len(notes_map)} 篇")

    # 滚动控制变量
    no_change_count = 0
    max_no_change = 5  # 连续5次高度不变则认为到底
    previous_height = 0

    scraped_count_session = 0

    while True:
        # 1. --- 抓取当前视口内的所有笔记 ---
        # 注意：这里会包含之前抓过的，也会包含新加载的
        elements = await page.query_selector_all('section.note-item')

        for idx, el in enumerate(elements):
            note_data = await extract_single_note_element(el, idx)
            if note_data:
                # 【增量更新逻辑】
                # 无论 ID 是否存在，都用新抓取的数据覆盖（保证点赞数、标题是最新的）
                # 或者如果你想保留旧数据的某些字段，可以在这里加判断
                if note_data['id'] not in notes_map:
                    scraped_count_session += 1

                notes_map[note_data['id']] = note_data

        # 2. --- 滚动页面 ---
        # 每次向下滚动约 800px (模拟用户行为)
        await page.evaluate("window.scrollBy(0, 800)")
        await page.wait_for_timeout(1000)  # 等待加载

        # 3. --- 检查是否到底 ---
        current_height = await page.evaluate("document.body.scrollHeight")
        current_scroll_y = await page.evaluate("window.scrollY")
        viewport_height = await page.evaluate("window.innerHeight")

        # 如果当前滚动位置 + 视口高度 接近 总高度，或者高度不再变化
        if current_height == previous_height:
            no_change_count += 1
            print(f"    页面高度未变化 ({no_change_count}/{max_no_change})...")
        else:
            no_change_count = 0
            previous_height = current_height
            print(f"    正在加载... (库中当前共 {len(notes_map)} 篇)")

        if no_change_count >= max_no_change:
            print(">>> 判定已到达底部。")
            break

    print(f"✅ 专辑 '{album_name}' 处理完毕。本次新增/更新: {scraped_count_session} 篇 (总计: {len(notes_map)} 篇)")

    # 将字典转回列表返回
    return list(notes_map.values())


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(
            viewport={'width': 1280, 'height': 800},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        # 读取现有的 JSON 数据
        all_data = load_existing_data()

        print("正在打开小红书...")
        await page.goto("https://www.xiaohongshu.com/explore")

        print("\n" + "=" * 50)
        print("【操作指引】")
        print("1. 请扫码登录。")
        print("2. 进入个人中心 -> 点击【我的收藏】。")
        print("3. 点击进入具体的专辑。")
        print("=" * 50 + "\n")

        while True:
            album_name = input("\n请输入当前专辑名称 (输入 q 保存并退出): ").strip()
            if album_name.lower() == 'q':
                break

            # 查找该专辑之前的旧数据
            existing_album_index = -1
            existing_album_notes = []

            for idx, album in enumerate(all_data):
                if album['name'] == album_name:
                    existing_album_index = idx
                    existing_album_notes = album['notes']
                    break

            # 执行增量抓取
            updated_notes = await scrape_album_incrementally(page, album_name, existing_album_notes)

            # 更新总数据结构
            new_album_data = {
                "name": album_name,
                "notes": updated_notes
            }

            if existing_album_index != -1:
                all_data[existing_album_index] = new_album_data
            else:
                all_data.append(new_album_data)

            # 为了安全起见，每爬完一个专辑就保存一次文件
            # 这样如果中途报错，前面的数据不会丢
            with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
                json.dump(all_data, f, ensure_ascii=False, indent=2)

            print(f"💾 数据已自动保存至 {OUTPUT_FILE}")

            print(">>> 请切换到下一个专辑，然后继续...")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())