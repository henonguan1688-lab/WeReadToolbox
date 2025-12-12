import asyncio
import json
import math
import os.path
import re
import time
import traceback

import aiohttp
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

from book_util import WereadGenerate
from constants import BOOK_SHELF_PATH, STORAGE, COVER_DIR, CHROME_DIR

# if not os.path.exists(STORAGE):
#     raise 'weread_state.json can found。'

# BASE_HEADERS_KEYS = ['sec-ch-ua-platform', 'referer', 'sec-ch-ua', 'sec-ch-ua-mobile', 'user-agent']

user_data = {}
shelfIndexes = []



async def download_image(url, filename):
    try:
        async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=False)) as session:
            async with session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.read()
                    with open(filename, "wb") as f:
                        f.write(data)
                    print("已保存:", filename)
                else:
                    print("下载失败:", url)
    except Exception as e:
        print("下载异常:", e, url)


def parser_shelf(text):
    # 2. 用 BeautifulSoup 解析
    soup = BeautifulSoup(text, "html.parser")

    # 遍历所有 <script> 标签
    for script in soup.find_all("script"):
        # 有的 script 标签是空的
        if not script.string:
            continue
        # print(script.string)
        # 检查是否包含关键字
        if "window.__INITIAL_STATE__" in script.string:
            print("找到 __INITIAL_STATE__ 脚本内容:")
            # 提取 JSON
            match = re.search(r"window\.__INITIAL_STATE__=(\{.*});", script.string, re.DOTALL)
            if match:
                json_str = match.group(1)
                try:
                    data = json.loads(json_str)['shelf']
                    # booksAndArchives = data['booksAndArchives']

                    shelfIndexes[:] = data['shelfIndexes']

                except json.JSONDecodeError:
                    print("JSON 解析失败")
            break


async def handle_response(response):
    text = None
    try:
        text = await response.text()
    except:
        return

    if "https://weread.qq.com/web/user?" in response.url:
        try:
            data = json.loads(text)
            user_data.clear()
            user_data.update(data)
            print("捕获用户数据：", user_data)
        except:
            traceback.print_exc()

    if "https://weread.qq.com/web/shelf" in response.url:
        try:
            parser_shelf(text)
        except:
            traceback.print_exc()

    if 'weread.qq.com/web/shelf/syncBook' in response.url:
        data = await response.json()
        print("请求 URL:", response.url)
        print("数据:", json.dumps(data, ensure_ascii=False))
        print("请求 headers:", response.headers)


async def load_browser():

    p = await async_playwright().start()  # 不使用 async with

    browser = await p.chromium.launch(headless=False, executable_path=CHROME_DIR)  # 可改 True

    # 如果已经有会话文件，加载它
    try:
        context = await browser.new_context(storage_state=STORAGE, )
        print("加载已有会话:", STORAGE)
    except Exception:
        traceback.print_exc()
        context = await browser.new_context()
        print("创建新会话")

    return p, browser, context

async def load_search_browser():

    p = await async_playwright().start()  # 不使用 async with

    browser = await p.chromium.launch(headless=True, executable_path=CHROME_DIR)  # 可改 True

    # 如果已经有会话文件，加载它
    try:
        context = await browser.new_context()
    except Exception:
        traceback.print_exc()
        context = await browser.new_context()
        print("创建新会话")

    return p, browser, context


async def login_weread():
    p, browser, context = await load_browser()

    print("已点击登录按钮")

    page = await context.new_page()

    # 拦截 network response
    page.on("response", handle_response)

    # 监听所有请求
    async def log_request(req):
        if 'weread.qq.com/web/shelf/syncBook' in req.url:
            print("请求 URL:", req.url)
            print("请求方法:", req.method)
            print("完整请求头:", json.dumps(req.headers, indent=2))
            if req.post_data:
                print("请求体:", req.post_data)

    page.on("request", log_request)

    await page.goto("https://weread.qq.com/")

    # 等待整个 action 区域出现（最稳）
    await page.wait_for_selector(".wr_index_page_top_section_header_action")

    # 获取所有链接元素
    links = await page.query_selector_all("a.wr_index_page_top_section_header_action_link")
    login_btn = None
    for link in links:
        text = (await link.text_content() or "").strip()
        if text == "登录":
            print("发现登录按钮")
            login_btn = link
            break
    else:
        print("未发现登录按钮")

    # 如果是“登录”，才点击
    if login_btn:
        await login_btn.click()
        print("检测到未登录，已点击登录按钮，请扫码登录…")

        # 等待用户扫码
        while True:
            try:
                # 等待头像元素出现（登录成功的标志）
                # document.querySelectorAll('img.wr_avatar_img')
                await page.wait_for_selector("img.wr_avatar_img", timeout=180000)
                print("登录成功！")
                break
            except Exception as e:
                traceback.print_exc()

    # 保存会话到文件
    await context.storage_state(path=STORAGE)
    print("会话已保存:", STORAGE)

    # 打开我的书架：<div class="wr_index_page_top_section_header_action_link"> 我的书架 </div>
    # 或者 https://weread.qq.com/web/shelf
    # 已登录 → 进入我的书架
    print("检测到已登录，不需要点击登录按钮。打开我的书架。")


    # 直接进入书架页面
    shelf_resp = await page.goto("https://weread.qq.com/web/shelf")

    # 等待书架列表加载
    await page.wait_for_selector("div.shelf_list a.shelfBook", timeout=60 * 1000)

    print("已经进入：我的书架")

    # 获取所有书籍元素
    # books = await page.query_selector_all("div.shelf_list a.shelfBook")

    '''
    <div class="wr_avatar navBar_avatar">
    
    <img src="https://thirdwx.qlogo.cn/mmopen/vi_32/PiajxSqBRaELQbc5uHoC9GnyIq3q9JeGue2EjEM4wv07PlzFAnYmgcnoDjwfakd5djIlCqvSoicXn21rINZiam04NuO86Aj4TwkfW5vloGjt1nXgTOU30C7IA/46" 
    
    class="wr_avatar_img">
    
    </div>
    '''

    while not user_data.get('userVid'):
        await asyncio.sleep(2)
        if not user_data.get('userVid'):
            await page.reload(wait_until="networkidle")

    books = []
    offset = 0
    limit = 50
    print(f'shelfIndexes size: {len(shelfIndexes)}')

    for i in range(1, math.ceil(len(shelfIndexes) / limit) + 1):

        book_ids = [f'{book["bookId"]}' for book in shelfIndexes[offset: offset + limit]]

        if not book_ids:
            break

        # 请求接口
        url = "https://weread.qq.com/web/shelf/syncBook"
        payload = {
            "bookIds": book_ids,
            "count": limit,
            "isArchive": None,
            "currentArchiveId": None,
            "loadMore": True
        }

        offset += limit

        # 使用 page.request.post 创建请求对象
        request = page.request
        headers = {
            "Content-Type": "application/json;charset=UTF-8",
            "accept": "application/json, text/plain, */*"
        }

        print("请求体：", payload)

        while True:

            response = await request.post(url, data=json.dumps(payload), headers=headers)

            if response.ok:
                data = await response.json()
                books = books + data.get('books', [])

                book_titles = [b['title'] for b in data.get('books', [])]

                print("书籍数据:", json.dumps(book_titles, ensure_ascii=False, ))

                if books:
                    break

            else:
                print("请求失败:", response.status)

    print(f'book shelf size: {len(books)}')

    # 遍历书架，下载图片
    book_util = WereadGenerate()
    tasks = []
    for book in books:
        img_url = book["cover"]
        if not img_url:
            continue

        book['bookHash'] = book_util.book_hash(book['bookId'])

        ext = os.path.splitext(img_url)[1].split("?")[0]  # 保留 jpg/png
        if ext.lower() not in [".jpg", ".jpeg", ".png"]:
            ext = ".jpg"  # 默认 jpg

        filename = os.path.join(COVER_DIR, f'{book["bookHash"]}{ext}')
        if not os.path.exists(filename):
            tasks.append(download_image(img_url, filename))

    if books:
        open(BOOK_SHELF_PATH, 'w', encoding='utf8').write(json.dumps(books, ensure_ascii=False, indent=4))

    if tasks:
        await asyncio.gather(*tasks)


    # 清理顺序不能修改，否则报错
    await context.close()
    await browser.close()
    await p.stop()

    if user_data:
        open('user_info.json', 'w', encoding='utf8')\
            .write(json.dumps(user_data, ensure_ascii=False, indent=4))

    return user_data, books

if __name__ == '__main__':

    def a():
        asyncio.run(login_weread())
        # asyncio.get_event_loop().run_until_complete(login_weread())


    a()



