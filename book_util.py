import asyncio
import base64
import hashlib
import json
import os
import re
import time
from pathlib import Path
from random import random

import requests
from bs4 import BeautifulSoup
from playwright.async_api import BrowserContext, expect, Page

from constants import COVER_DIR, BOOK_SHELF_PATH, LOCAL_BOOK_SHELF_PATH, FAV_BOOK_SHELF_PATH


class WereadGenerate:

    def __init__(self):
        pass

    def _0x58fb1d(self, s):
        a = 0x15051505
        b = a
        length = len(s)
        i = length - 1

        while i > 0:
            a = (a ^ (ord(s[i]) << ((length - i) % 30))) & 0x7fffffff
            b = (b ^ (ord(s[i - 1]) << (i % 30))) & 0x7fffffff
            i -= 2

        return hex(a + b)[2:].lower()

    def md5_hex(self, s):
        return hashlib.md5(s.encode()).hexdigest()

    # book id、chapter id 生成算法
    def book_hash(self, s):
        # 1. 转成字符串
        s = str(s)

        # 2. MD5 哈希
        h = self.md5_hex(s)

        # 3. 前缀
        result = h[:3]

        # 4. 处理数字或字符
        if s.isdigit():
            chunks = [hex(int(s[i:i + 9]))[2:] for i in range(0, len(s), 9)]
            type_flag = '3'
        else:
            chunks = [''.join([hex(ord(c))[2:] for c in s])]
            type_flag = '4'

        result += type_flag
        result += '2' + h[-2:]

        # 5. 拼接 chunks
        for i, chunk in enumerate(chunks):
            length_hex = hex(len(chunk))[2:]
            if len(length_hex) == 1:
                length_hex = '0' + length_hex
            result += length_hex + chunk
            if i < len(chunks) - 1:
                result += 'g'

        # 6. 补齐长度到20
        if len(result) < 20:
            result += h[:20 - len(result)]

        # 7. 最终附加哈希前3位
        result += self.md5_hex(result)[:3]

        return result


class WereadParamsGenerate:

    def __init__(self, book_id, chapter_id, psvts, pclts):
        self.book_id = book_id
        self.chapter_id = chapter_id
        self.psvts = psvts
        self.pclts = pclts
        self.generate = WereadGenerate()

    def get_request_param(self, ):
        book = {
            'b': self.generate.book_hash(self.book_id),
            'c': self.generate.book_hash(self.chapter_id),
            'ct': f'{int(time.time())}',
            'pc': self.generate.book_hash(self.pclts),
            'prevChapter': 'false',
            'ps': self.psvts,
            'r': f'{int(10000 * random()) ** 2}',
            'sc': 0x0,
            'st': 0x0,
        }
        s = '&'.join([f'{k}={v}' for k, v in book.items()])

        h = self.generate._0x58fb1d(s)
        book['s'] = h
        return book


def parser_chapter_info(html, levels=[]) -> dict:
    #     document.querySelectorAll('.readerCatalog_list > li')

    soup = BeautifulSoup(html, "html.parser")

    css = 'readerCatalog_list_item_level_1'
    if levels:
        css = ','.join([ f'.readerCatalog_list_item_level_{level}' for level in levels])


    items = soup.select(css)

    chapters = []

    for li in items:
        # 1) 标题 readerCatalog_list_item_inner readerCatalog_list_item_level_1
        title_tag = li.select_one(".readerCatalog_list_item_title_text")
        title = title_tag.get_text(strip=True) if title_tag else ""

        # 2) 是否锁定（两种判断方式都可）
        is_lock = (
                "readerCatalog_list_item_disabled" in li.get("class", []) or
                li.select_one(".readerCatalog_list_item_lock") is not None
        )

        chapters.append({
            "title": title,
            "is_lock": is_lock
        })
    return chapters


def parser_script(text) -> dict:
    soup = BeautifulSoup(text, "html.parser")

    data = None
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
                    data = json.loads(json_str)

                except json.JSONDecodeError:
                    print("JSON 解析失败")
            break

    return data


async def req_book_page(page, book,):
    url = "https://weread.qq.com/web/reader/" + book['bookHash']
    # page = await context.new_page()
    resp = await page.goto(url)
    html = await resp.text()

    return html


WR_SEARCH_BAR_INPUT_SELECTOR = ".wr_index_page_search_bar_input"
WR_SEARCH_ACTION_ICON_SELECTOR = ".wr_index_page_search_bar_action_icon"
SEARCH_API_URL_PARTIAL = "/api/store/search"

async def req_goto_search_page(page, url="https://weread.qq.com"):
    """
    步骤 1: 创建新页面并导航到微信读书首页。
    """
    print(f"-> 导航到 URL: {url}")
    try:
        # page = await context.new_page()
        # 导航到指定的 URL 并等待网络空闲
        await page.goto(url, wait_until="networkidle")

        # ⚠️ 验证页面是否加载成功，确保搜索框可见
        await expect(page.locator(WR_SEARCH_BAR_INPUT_SELECTOR)).to_be_visible()
        print("-> 页面加载成功，搜索框可见。")

    except Exception as e:
        print(f"导航或页面初始化失败: {e}")
        # 如果失败，关闭页面
        if 'page' in locals() and page:
            await page.close()
        raise


async def req_search_books(keyword, page: Page):
    """
    步骤 2: 输入关键词、点击搜索，并监听 API 响应。
    """
    if not page or page.is_closed():
        raise RuntimeError("提供的 Page 对象无效或已关闭。")

    print(f"-> 开始搜索关键词: '{keyword}'")


    # ⚠️ 确保点击操作可以触发 API 请求
    # 注意：必须明确指定事件名称 'response'
    search_response_future = page.wait_for_event(
        "response",  # 明确指定等待的事件类型
        lambda response: SEARCH_API_URL_PARTIAL in response.url
    )

    search_request_future = page.wait_for_event(
        "request",  # 明确指定等待的事件类型
        lambda request: SEARCH_API_URL_PARTIAL in request.url
    )


    # 1. 定位并输入关键词
    search_input = page.locator(WR_SEARCH_BAR_INPUT_SELECTOR)
    await search_input.fill(keyword)

    # 2. 定位并点击搜索图标
    search_icon = page.locator(WR_SEARCH_ACTION_ICON_SELECTOR)

    await search_icon.click()

    print("-> UI 操作完成，等待 API 响应...")


    # ----------------------------------------------------
    # C. 获取 API 响应并返回数据
    # ----------------------------------------------------
    try:
        search_request = await search_request_future

        # 等待之前设置的 Response Listener 完成
        search_response = await search_response_future
        # 检查响应状态码
        if search_response.status != 200:
            print(f"API 响应失败，状态码: {search_response.status}")
            return None

        # 解析 JSON 响应体
        search_results = await search_response.json()
        url = search_response.url
        headers = {
            'sec-ch-ua-platform': search_request.headers['sec-ch-ua-platform'],
            'referer': search_request.headers['referer'],
            'user-agent': search_request.headers['user-agent'],
            'accept': '*/*',
            'accept-encoding': 'gzip, deflate, br, zstd',
            'accept-language': 'zh-CN,zh;q=0.9,en;q=0.8,zh-HK;q=0.7',
        }
        print(f"-> 成功捕获并解析搜索结果 API 响应。{url}")
        return url, headers, search_results

    except asyncio.TimeoutError:
        print("错误: 等待搜索 API 响应超时。")
        return None, None, None
    except Exception as e:
        print(f"处理 API 响应时发生错误: {e}")
        return None, None, None


async def req_book_chapters(page, book):
    # 使用 page.request.post 创建请求对象
    request = page.request
    headers = {
        "Content-Type": "application/json;charset=UTF-8",
        "accept": "application/json, text/plain, */*"
    }
    book_id = book['bookId']
    payload = {"bookIds": [f'{book_id}']}

    url = 'https://weread.qq.com/web/book/chapterInfos'
    # url = 'https://weread.qq.com/web/book/publicchapterInfos'
    response = await request.post(url, data=json.dumps(payload), headers=headers)

    if response.ok:
        data = await response.json()

        return data['data'][0]['updated']
    else:
        print("请求失败:", response.status)


async def req_book_chapters_content(page, book, chapter_id, psvts, pclts):
    # 请求接口
    book_type = book['format']
    book_id = book['bookId']

    gen = WereadParamsGenerate(book_id, chapter_id, psvts, pclts)

    if book_type == 'epub':
        urls = [
            "https://weread.qq.com/web/book/chapter/e_0",
            "https://weread.qq.com/web/book/chapter/e_1",
            "https://weread.qq.com/web/book/chapter/e_2",
            "https://weread.qq.com/web/book/chapter/e_3",
        ]
    else:
        urls = [
            "https://weread.qq.com/web/book/chapter/t_0",
            "https://weread.qq.com/web/book/chapter/t_1",
        ]

    payload = gen.get_request_param()

    # 使用 page.request.post 创建请求对象
    request = page.request
    headers = {
        "Content-Type": "application/json;charset=UTF-8",
        "accept": "application/json, text/plain, */*"
    }

    print("请求体：", payload)
    texts = []
    for url in urls:
        retry = 0
        while True:
            response = await request.post(url, data=json.dumps(payload), headers=headers, )

            if response.ok:
                text = await response.text()
                texts.append(text)
                break
            else:
                print("请求失败:", response.status)
                retry = retry + 1

                if retry > 3:
                    raise Exception(r'网络请求失败，稍后再试。')

    return texts

async def req_add_book_shelf():

    '''

    https://weread.qq.com/mp/shelf/addToShelf   POST

    {"bookIds":["3300150309"]}

    content-type: application/json;charset=UTF-8
    accept: application/json, text/plain, */*

    :return:
    '''

def resolve_content(texts, book, ):
    t = book['format']

    if t == 'epub':
        content = _resolve_content([texts[0], texts[1], texts[3]])
        css = _resolve_content([texts[2]])
        return content, css
    else:

        return _resolve_content(texts), None


def _resolve_content(texts):
    t = "".join(s[32:] for s in texts)
    t = t[1:]

    def a(s: str):
        length = len(s)
        if length < 4:
            return []
        if length < 11:
            return [0, 2]

        n = min(4, -(-length // 10))  # ceil(length / 10)
        tmp = ""
        for i in range(length - 1, length - 1 - n, -1):
            tmp += str(int(bin(ord(s[i]))[2:], 4))

        arr = []
        m = length - n - 2
        step = len(str(m))

        i = 0
        while len(arr) < 10 and i + step < len(tmp):
            v = int(tmp[i:i + step])
            arr.append(v % m)
            v2 = int(tmp[i + 1:i + 1 + step])
            arr.append(v2 % m)
            i += step
        return arr

    def b(s: str, arr):
        chars = list(s)
        for i in range(len(arr) - 1, -1, -2):
            for k in (1, 0):
                idx1 = arr[i] + k
                idx2 = arr[i - 1] + k
                chars[idx1], chars[idx2] = chars[idx2], chars[idx1]
        return "".join(chars)

    # def base64_url_to_base64(s: str):
    #     s = s.replace("-", "+").replace("_", "/")
    #     return re.sub(r"[^A-Za-z0-9+/]", "", s)

    def replace_utf8(m: re.Match):
        chunk = m.group(0)
        l = len(chunk)
        if l == 4:
            val = ((ord(chunk[0]) & 0x7) << 18) | ((ord(chunk[1]) & 0x3F) << 12) | ((ord(chunk[2]) & 0x3F) << 6) | (
                    ord(chunk[3]) & 0x3F)
            val -= 0x10000
            return chr(0xD800 + (val >> 10)) + chr(0xDC00 + (val & 0x3FF))
        elif l == 3:
            return chr(((ord(chunk[0]) & 0xF) << 12) | ((ord(chunk[1]) & 0x3F) << 6) | (ord(chunk[2]) & 0x3F))
        else:
            return chr(((ord(chunk[0]) & 0x1F) << 6) | (ord(chunk[1]) & 0x3F))

    # === 执行 ===
    arr = a(t)
    encodeStr = b(t, arr)

    # Base64 解码
    decoded_bytes = base64.b64decode(encodeStr)
    text = decoded_bytes.decode(errors="ignore")

    # 进一步修复 UTF-8 编码
    pattern = re.compile(r'[\xC0-\xDF][\x80-\xBF]|[\xE0-\xEF][\x80-\xBF]{2}|[\xF0-\xF7][\x80-\xBF]{3}')
    text = pattern.sub(replace_utf8, text)

    # print(text)
    return text

def load_my_books():
    '''
    加载微信书架信息
    :return:
    '''

    if os.path.exists(BOOK_SHELF_PATH):
        books = json.load(open(BOOK_SHELF_PATH, encoding='utf8'))
    else:
        books = []
    # free_books = json.load(open('free_books.json', encoding='utf8'))
    # books = books + free_books
    #

    return books

def load_local_books():
    '''
    加载本地书架信息
    :return:
    '''
    if os.path.exists(LOCAL_BOOK_SHELF_PATH):
        t = open(LOCAL_BOOK_SHELF_PATH, encoding='utf8').read()
        if t:
            books = json.loads(t)
            return books
    return []

def load_fav_books():
    '''
    加载本地收藏的电子书信息
    :return:
    '''
    if os.path.exists(FAV_BOOK_SHELF_PATH):
        t = open(FAV_BOOK_SHELF_PATH, encoding='utf8').read()
        if t:
            books = json.loads(t)
            return books
    return []

def download_img(book):
    img_url = book["cover"]
    if not img_url:
        return

    ext = os.path.splitext(img_url)[1].split("?")[0]  # 保留 jpg/png
    if ext.lower() not in [".jpg", ".jpeg", ".png"]:
        ext = ".jpg"  # 默认 jpg

    filename = os.path.join(COVER_DIR, f'{book["bookHash"]}{ext}')
    if not os.path.exists(filename):
        # tasks.append(download_image(img_url, filename))

        try:
            resp = requests.get(img_url)
            if resp.status_code == 200:
                data = resp.content
                with open(filename, "wb") as f:
                    f.write(data)
                print("已保存:", filename)
            else:
                print("下载失败:", img_url)
        except Exception as e:
            print("下载异常:", e, img_url)


def set_book_is_download(books):
    # local_path = Path('books')
    book_util = WereadGenerate()
    for book in books:

        if not book.get('bookHash'):
            book['bookHash'] = book_util.book_hash(book['bookId'])

        download_img(book)


        bp = Path(f'books/{book["bookId"]}')

        chapter_path = bp / Path(f'chapters')
        chapter_info_path = bp / Path(f'chapters.json')

        if chapter_path.exists() and chapter_info_path.exists():
            chapter_infos = json.load(chapter_info_path.open('r', encoding='utf8'))
            size = len(chapter_infos)
            chapter_size = len(list(chapter_path.iterdir()))
            book['progress'] = chapter_size
            book['is_download'] = size == chapter_size
            book['chapter_size'] = size



if __name__ == '__main__':
    books = json.load(open('books.json', 'r', encoding='utf8'))

    set_book_is_download(books)

    print([b.get('is_download') for b in books])