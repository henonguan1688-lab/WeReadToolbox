import os
from pathlib import Path

LIB_DIR = Path('lib')

CHROME_DIR = LIB_DIR / Path(r'chromium-1200/chrome-win64/chrome.exe')
WKHTMLTOPDF_DIR = LIB_DIR / Path(r'wkhtmltox/bin/wkhtmltopdf.exe')

STORAGE = "weread_state.json"

DOWNLOAD_DELAY = 0.1
COVER_DIR = "images/cover"
BOOK_DIR = Path("books")

os.makedirs(COVER_DIR, exist_ok=True)
BOOK_DIR.mkdir(exist_ok=True, parents=True)

BOOK_SHELF_PATH = 'book_shelf.json'    # 微信书架电子书保存目录
LOCAL_BOOK_SHELF_PATH = 'local_book_shelf.json'    # 本地下载保存目录
FAV_BOOK_SHELF_PATH = 'fav_book_shelf.json'    # 本地收藏的保存目录
