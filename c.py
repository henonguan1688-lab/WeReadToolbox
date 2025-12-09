import platform
import hashlib
import json
import os.path
import re
import subprocess
import requests
from pathlib import Path
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning


# ----------------------------
# 下载图片
# ----------------------------
def download_image(url, img_path):
    # filename = url.split("/")[-1]
    # img_path = img_dir / filename
    #
    # 已存在直接返回
    if img_path.exists():
        print(f'skip: {url}')
        return

    print("下载图片：", url)

    headers = {
        "User-Agent": "Mozilla/5.0",
        "Referer": "https://weread.qq.com/"
    }

    r = requests.get(url, headers=headers, timeout=10)
    if r.status_code == 200:
        img_path.write_bytes(r.content)
    else:
        print("下载失败：", url, r.status_code)


# ----------------------------
# 基础路径
# ----------------------------
book_id = 3300107269

book_dir = Path(f'books/{book_id}')
img_dir = book_dir / "images"
img_dir.mkdir(exist_ok=True)


chapters = json.load(Path(f'books/{book_id}/chapters.json').open('r', encoding='utf8'))
book_info = json.load(Path(f'books/{book_id}/info.json').open('r', encoding='utf8'))
book_name = book_info['title']

output_pdf = book_dir / f"{book_name}.pdf"

print(f"{book_name} - {book_id}")

# ----------------------------
# 处理每个章节
# ----------------------------
import warnings

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

contents = []
for chapter in chapters:
    cp = book_dir / f'chapters/{chapter["chapterUid"]}.xhtml'
    print("处理章节：", cp)

    html = cp.read_text("utf-8")
    soup = BeautifulSoup(html, "lxml")

    # 下载并替换图片资源
    for img in soup.find_all("img"):
        src = img.get("src")
        if not src:
            continue

        if src.startswith('../'):
            print(f'sikp: {src}')
            continue

        ext = os.path.splitext(src)[1].lower().replace('.', '')

        if ext not in ['jpg', 'png', 'jpeg']:
            ext = 'jpg'

        img_hash = hashlib.md5(src.encode("utf-8")).hexdigest() + f".{ext}"
        img_path = Path(f'books/{book_id}/images')
        img_path.mkdir(parents=True, exist_ok=True)
        img_path = img_path / Path(img_hash)
        img["src"] = f'images/{img_hash}'

        download_image(src, img_path=img_path)

    fixed_html = soup.prettify()
    contents.append(fixed_html)


# ----------------------------
# 合并 HTML
# ----------------------------
print("正在合并 HTML...")

merged_html = (
    "<html><head><meta charset='utf-8'></head><body>"
    + "<div style='page-break-after: always'></div>".join(contents)
    + "</body></html>"
)




# ----------------------------
# 使用 wkhtmltopdf 生成 PDF
# ----------------------------
print("正在生成 PDF...")




system = platform.system()

if system == "Windows":
    merged_file = book_dir / "merged.html"
    merged_file.write_text(merged_html, "utf-8")

    WKHTML_PATH = r"lib/wkhtmltox/bin/wkhtmltopdf.exe"
    cmd = [
        WKHTML_PATH,
        "--enable-local-file-access",  # 允许读取本地图片
        str(merged_file),
        str(output_pdf)
    ]

    print("检测到 Windows，执行 wkhtmltopdf 命令行...")

    try:
        subprocess.run(cmd, check=True)
        print("转换完成！")

        # ---- 删除 merged.html ----
        if merged_file.exists():
            merged_file.unlink()
            print("清理中间文件:", merged_file)
    except subprocess.CalledProcessError as e:
        print("wkhtmltopdf 执行失败！", e)
else:
    print(f"当前系统 {system} 不执行 wkhtmltopdf。")


