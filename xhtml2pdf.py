import json
from pathlib import Path

from bs4 import BeautifulSoup
from weasyprint import HTML

import mimetypes
import requests
from weasyprint import HTML, default_url_fetcher

def my_url_fetcher(url):
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Referer": "https://weread.qq.com/",
    }

    # 如果是 Http/Https 外网地址，用 requests 下载
    if url.startswith("http://") or url.startswith("https://"):
        r = requests.get(url, headers=headers, timeout=10)
        r.raise_for_status()

        # WeasyPrint 需要返回 dict
        return {
            "string": r.content,
            "mime_type": r.headers.get("Content-Type", mimetypes.guess_type(url)[0]),
            "encoding": None,
            "redirected_url": url,
        }

    # 否则交给默认处理（文件 / data URI 等）
    return default_url_fetcher(url)


book_dir = Path('books/3300098798/chapters')  # 傲慢与偏见
chapters = json.load(Path('books/3300098798/chapters.json').open('r', encoding='utf8'))  # 傲慢与偏见

# 读取所有 XHTML
contents = []
for chapter in chapters:

    cp = book_dir / Path(f'{chapter["chapterUid"]}.xhtml')


    print(cp)

    xhtml = cp.read_text(encoding="utf-8")
    soup = BeautifulSoup(xhtml, "lxml")

    fixed_html = soup.prettify()
    contents.append(f"<!-- Page {cp} -->\n{fixed_html}\n")

print('正在转换。。。')
# 合并成一个 HTML 文档
merged_html = (
    "<html><head>"
    "<meta charset='utf-8'>"
    "</head><body>"
    + "\n<div style='page-break-after: always'></div>\n".join(contents)
    + "</body></html>"
)

# 输出 PDF
HTML(string=merged_html, url_fetcher=my_url_fetcher, base_url=str(book_dir)).write_pdf(
    book_dir / "Transformer自然语言处理实战：使用Hugging Face Transformers库构建NLP应用.pdf"
)

print('转换完成')