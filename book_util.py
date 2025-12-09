import base64
import hashlib
import json
import re
import time
from pathlib import Path
from random import random

from bs4 import BeautifulSoup


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

    # data = parser_script(html)

    # chapters = parser_chapter_info(html, levels)

    # return data, chapters


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

def set_book_is_download(books):
    # local_path = Path('books')
    for book in books:

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