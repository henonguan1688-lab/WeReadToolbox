import json
import os
import platform
import shutil
import subprocess
import traceback
import zipfile
from pathlib import Path
import datetime

import hashlib

from PySide6.QtCore import QThread, Signal
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning

import requests

from constants import WKHTMLTOPDF_DIR


class BuilderThread(QThread):
    msg = Signal(str)

    end_signal = Signal(int)


    def __init__(self, book_id, path=Path('books'), out_format:str='txt'):

        super().__init__()
        if not path.exists():
            raise ''

        book_path = path / Path(f'{book_id}')

        if not book_path.exists():
            raise ''
        self.book_path = book_path
        book_info = json.load(open(book_path / Path(f'info.json'), encoding='utf8'))
        chapter_infos = json.load(open(book_path / Path(f'chapters.json'), encoding='utf8'))
        self.chapters = []
        self.book_path = book_path
        ext = '.xhtml'
        self.format = book_info['format']

        if book_info['format'] == 'txt':
            ext = '.txt'

        for i, chapter in enumerate(chapter_infos):
            cid = chapter['chapterUid']

            fp = book_path / Path(f'chapters/{cid}{ext}')

            if not fp.exists():

                self.send(f'===== skip: {fp}')

                continue

            title = chapter['title'].strip()
            if not title:
                title = f'第{i+1}章'


            self.chapters.append({
                'title': title,
                'cid': chapter['chapterUid'],
                'level': chapter.get('level', 1),
                'content': fp.open(encoding='utf8').read()
            })


        self.title = book_info['title']
        self.author = book_info['author']
        self.language = book_info['language']
        self.file_name = book_path / Path(book_info['title'] + f'-{book_info["bookHash"]}.{out_format}')

        self.book_id = str(book_info["bookHash"])

    def send(self, msg):

        self.msg.emit(msg)


class EpubBuilder(BuilderThread):

    def __init__(self, book_id, path=Path('books'), ):

        super().__init__(book_id, path, 'epub')
        if not path.exists():
            raise ''

        self.resources = {}      # 静态资源：filename -> bytes



    # ---------------------
    # 添加静态资源（CSS、JS、图片）
    # ---------------------
    def add_resource(self, filename: str, data: bytes):
        self.resources[filename] = data

    # ---------------------
    # 添加章节
    # ---------------------
    def add_chapter(self, title: str, filename: str, content: str):
        # self.chapters.append({
        #     "title": title,
        #     "filename": filename,
        #     "content": content
        # })
        pass

    # ---------------------
    # 生成 container.xml
    # ---------------------
    @staticmethod
    def _container_xml():
        return """<?xml version="1.0"?>
<container version="1.0"
    xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf"
        media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>
"""

    # ---------------------
    # 生成章节 XHTML
    # ---------------------
    def _chapter_template(self, content):
        if self.format == 'txt':
            return f"""<?xml version="1.0" encoding="utf-8"?>
    <html xmlns="http://www.w3.org/1999/xhtml" lang="{self.language}">
    <head>
    <meta charset="utf-8"/>
    </head>
    <body>
    {content}
    </body>
    </html>
    """
        else:
            return content

    # ---------------------
    # 生成 toc.ncx
    # ---------------------
    def _build_ncx(self):
        nav_points = ""
        for i, ch in enumerate(self.chapters, 1):
            nav_points += f"""
<navPoint id="navPoint-{i}" playOrder="{i}">
    <navLabel><text>{ch["title"]}</text></navLabel>
    <content src="{ch['filename']}"/>
</navPoint>
"""

        return f"""<?xml version="1.0" encoding="UTF-8"?>
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">
  <head>
    <meta name="dtb:uid" content="{self.book_id}"/>
    <meta name="dtb:depth" content="1"/>
    <meta name="dtb:totalPageCount" content="0"/>
    <meta name="dtb:maxPageNumber" content="0"/>
  </head>
  <docTitle><text>{self.title}</text></docTitle>

  <navMap>
    {nav_points}
  </navMap>
</ncx>
"""

    # ---------------------
    # 生成 content.opf
    # ---------------------
    def _build_opf(self):
        manifest_items = ""
        spine_items = ""

        # 章节
        for i, ch in enumerate(self.chapters, 1):
            manifest_items += f"""
    <item id="chap{i}" href="{ch['filename']}" media-type="application/xhtml+xml"/>"""
            spine_items += f"""
    <itemref idref="chap{i}"/>"""

        # 静态资源
        for filename in self.resources:
            mime = self._guess_mime(filename)
            manifest_items += f"""
    <item id="{filename}" href="{filename}" media-type="{mime}"/>"""

        return f"""<?xml version="1.0" encoding="utf-8"?>
<package unique-identifier="BookId" version="2.0"
    xmlns="http://www.idpf.org/2007/opf">

  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:title>{self.title}</dc:title>
    <dc:creator>{self.author}</dc:creator>
    <dc:language>{self.language}</dc:language>
    <dc:identifier id="BookId">{self.book_id}</dc:identifier>
    <dc:date>{datetime.date.today()}</dc:date>
  </metadata>

  <manifest>
    <item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>
    {manifest_items}
  </manifest>

  <spine toc="ncx">
    {spine_items}
  </spine>

</package>
"""

    # ---------------------
    # 静态资源 MIME 推断
    # ---------------------
    @staticmethod
    def _guess_mime(filename):
        if filename.endswith(".css"): return "text/css"
        if filename.endswith(".js"): return "application/javascript"
        if filename.endswith(".png"): return "image/png"
        if filename.endswith(".jpg") or filename.endswith(".jpeg"): return "image/jpeg"
        if filename.endswith(".gif"): return "image/gif"
        return "application/octet-stream"

    # ---------------------
    # 主流程：生成 EPUB
    # ---------------------
    def generate(self):
        self.send(f"生成 EPUB：{self.file_name}")

        with zipfile.ZipFile(self.file_name, "w", compression=zipfile.ZIP_DEFLATED) as z:

            # ===================================
            # 1. 必须放在 ZIP 第一条，无压缩
            # ===================================
            z.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)

            # ===================================
            # 2. META-INF/container.xml
            # ===================================
            z.writestr("META-INF/container.xml", self._container_xml())

            # ===================================
            # 3. 章节 XHTML 写入 OEBPS/
            # ===================================
            for ch in self.chapters:
                xhtml = self._chapter_template(ch["content"])
                z.writestr(f"OEBPS/{ch['filename']}", xhtml)

            # ===================================
            # 4. 静态资源写入
            # ===================================
            for filename, data in self.resources.items():
                z.writestr(f"OEBPS/{filename}", data)

            # ===================================
            # 5. OPF & NCX
            # ===================================
            z.writestr("OEBPS/toc.ncx", self._build_ncx())
            z.writestr("OEBPS/content.opf", self._build_opf())

        self.send("EPUB 生成成功！")


    def run(self):

        output_dir = self.book_path / Path('images')

        output_dir.mkdir(exist_ok=True, parents=True)

        for i, chapter in enumerate(self.chapters):
            if self.format == 'epub':
                pass

            chapter['filename'] = f"chapter{i}.xhtml",

            images, new_xhtml = process_xhtml(chapter['content'])

            if images:
                chapter['content'] = new_xhtml
                for img in images:
                    filename = img['filename']
                    link = img['link']

                    file_path = output_dir / Path(f'{filename}')

                    if file_path.exists():
                        self.add_resource(f"images/{filename}", file_path.open("rb").read())
                        continue

                    if link == '../Images/note.png':
                        self.send(f'skip file: {link}')
                        continue
                    if link.startswith('../'):
                        self.send(f'skip file: {link}')
                        continue

                    resp = requests.get(link, headers={
                        'hose': 'https://weread.qq.com/',
                        'referer': 'https://weread.qq.com/',
                        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36',
                    })

                    b = resp.content
                    open(file_path, 'wb', ).write(b)

                    self.send(f'下载资源：{link}')

                    self.add_resource(f"images/{filename}", file_path.open("rb").read())

             # 添加 CSS / 图片（所有静态资源都会自动打包）
        # self.add_resource("css/style.css", open("css/style.css", "rb").read())
        # self.add_resource("images/logo.png", open("images/logo.png", "rb").read())
        # self.add_resource("images/img.png", open("images/img.png", "rb").read())
        # self.add_resource("images/device_phone_frontcover.jpg", open("images/device_phone_frontcover.jpg", "rb").read())

        try:
            self.generate()
            self.end_signal.emit(0)
        except:
            self.end_signal.emit(1)

class MarkdownBuilder(BuilderThread):

    def __init__(self, book_id, path=Path('books')):
        super().__init__(book_id, path, 'md')

    def run(self):

        try:
            for chapter in self.chapters:
                content = chapter['content']
                if self.format == 'epub':
                    content = self.xhtml_to_markdown(content)

                title = chapter['title']
                self.send(f'转换-章节：{title}')

                chapter.update({
                    'content': content
                })

            self.output()

            self.end_signal.emit(0)
        except Exception as e:
            traceback.print_exc()

            self.end_signal.emit(1)

    def output(self):
        try:
            css_temp = '---\nid: "my-id"\n---\n@import "css/style.less"\n\n'
            with open(self.file_name, 'w', encoding='utf8') as fp:
                fp.write(css_temp)
                for chapter in self.chapters:
                    if self.format == 'txt':
                        title = '# ' + chapter['title']
                        # level = max(1, int(chapter.get('level', '0')))
                        # title_level = ''.join(['#' for i in range(level)]) + ' ' + chapter['title'].strip()
                        fp.write(f"{title}\n\n{chapter['content']}\n\n")
                    else:
                        fp.write(f"{chapter['content']}\n\n")

            css_path = self.book_path / Path("css")
            css_path.mkdir(exist_ok=True, parents=True)
            shutil.copyfile("css/style.less", self.book_path / Path("css/style.less"))

        except Exception as e:
            traceback.print_exc()

        self.send(f'转换完成：{self.file_name}')

    # 适配 vscode 的 markdown-preview-enhanced (MPE) 插件
    # MPE 支持 Pandoc/extended syntax：
    # ![封面](url){.content-image-class}
    @staticmethod
    def normalize_classes(raw):
        """
        规范化 class 属性：
        - None → []
        - "a b c" → ["a", "b", "c"]
        - ["a", "b"] → ["a", "b"]
        - 其他类型 → []
        """
        if raw is None:
            return []

        if isinstance(raw, list):
            return raw

        if isinstance(raw, str):
            return raw.strip().split()

        return []

    def xhtml_to_markdown(self, xhtml: str) -> str:
        soup = BeautifulSoup(xhtml, "lxml-xml")

        md_lines = []

        def handle_inline(el):
            if el.name is None:
                return el.string or ""

            # italic span
            if el.name == "span" and "italic" in self.normalize_classes(el.get("class")):
                return f"*{''.join(handle_inline(c) for c in el.children)}*"

            # img inline
            if el.name == "img":
                src = el.get("src", "")
                classes = self.normalize_classes(el.get("class"))
                if classes:
                    cls = ".".join(classes)
                    return f"![]({src}){{.{cls}}}"
                return f"![]({src})"

            # 默认递归
            return "".join(handle_inline(c) for c in el.children)

        # --- 关键修复：只遍历 body.children，避免嵌套混乱 ---
        for tag in soup.body.children:
            if getattr(tag, "name", None) is None:
                continue

            if tag.name == "h1":
                md_lines.append(f"# {handle_inline(tag)}\n")
            elif tag.name == "h2":
                md_lines.append(f"## {handle_inline(tag)}\n")
            elif tag.name == "h3":
                md_lines.append(f"### {handle_inline(tag)}\n")
            elif tag.name == "p":
                text = handle_inline(tag).strip()
                if text:
                    md_lines.append(text + "\n")

            elif tag.name == "div":
                imgs = tag.find_all("img", recursive=False)
                if len(imgs) == 1:
                    img = imgs[0]
                    src = img.get("src", "")
                    classes = self.normalize_classes(img.get("class"))
                    if classes:
                        cls = ".".join(classes)
                        md_lines.append(f"![]({src}){{.{cls}}}\n")
                    else:
                        md_lines.append(f"![]({src})\n")

        return "\n".join(md_lines).strip()


class PdfBuilder(BuilderThread):


    def __init__(self, book_id, path=Path('books')):
        super().__init__(book_id, path, 'pdf')

    def run(self, /) -> None:

        # ----------------------------
        # 处理每个章节
        # ----------------------------
        import warnings

        warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)
        # 定义要统一添加的 CSS 链接
        UNIFIED_CSS_LINK = f'<link href="style.css" rel="stylesheet" type="text/css" />'
        for chapter in self.chapters:
            html = chapter['content']
            soup = BeautifulSoup(html, "lxml")

            # for link in soup.find_all("link", rel="stylesheet"):
            #     link.decompose()
            #
            # head = soup.find('head')
            # new_link_soup = BeautifulSoup(UNIFIED_CSS_LINK, "html.parser")
            # new_link_tag = new_link_soup.find('link')
            #
            # if head:
            #     head.append(new_link_tag)
            # else:
            #     first_tag = soup.find()
            #     if first_tag:
            #         first_tag.insert_before(new_link_tag)
            #     else:
            #         soup.insert(0, new_link_tag)

            # 下载并替换图片资源
            for img in soup.find_all("img"):
                src = img.get("src")
                if not src:
                    continue

                if src.startswith('../'):
                    self.send(f'sikp download: {src}')
                    img["src"] = src.replace('../Images/note.png', f'note.png')
                else:

                    ext = os.path.splitext(src)[1].lower().replace('.', '')

                    if ext not in ['jpg', 'png', 'jpeg']:
                        ext = 'jpg'

                    img_hash = hashlib.md5(src.encode("utf-8")).hexdigest() + f".{ext}"
                    img_dir = self.book_path / Path(f'images')

                    img_dir.mkdir(parents=True, exist_ok=True)
                    img_file_path = img_dir / Path(img_hash)
                    img["src"] = f'images/{img_hash}'

                    self.download_image(src, img_path=img_file_path)

            # 查找 body 标签
            body_tag = soup.find('body')

            if body_tag:
                # 只提取 body 标签内部的内容
                # .decode_contents() 返回 body 标签内所有元素的字符串形式，不包含 body 标签本身。
                fixed_html = body_tag.decode_contents()
            else:
                # 如果文档片段中没有 body 标签，则返回整个 prettify() 后的内容，
                # 或者根据您的需求，返回 soup 的 prettify() 结果。
                # 如果您确认输入始终是完整的 HTML 文档，则不会进入此分支。
                # 如果是片段，这里可以返回整个 soup.prettify() 的结果，或者其他处理。
                fixed_html = soup.prettify()

            chapter['content'] = fixed_html
        try:
            self.output()
        except Exception as e:
            traceback.print_exc()

            self.send(f'下载失败：{e}')

        self.end_signal.emit(0)

    def output(self):
        # ----------------------------
        # 合并 HTML
        # ----------------------------
        self.send("正在合并 HTML...")
        contents = [c['content'] for c in self.chapters]
        merged_html = (
                "<html><head><meta charset='utf-8'>"
                + "<link rel='stylesheet' href='style.css'/>"
                + "</head><body>"
                + contents[0]
                + "<div style='page-break-after: always'></div>".join(contents[1:])
                + "</body></html>"
        )

        # ----------------------------
        # 使用 wkhtmltopdf 生成 PDF
        # ----------------------------
        self.send("正在生成 PDF...")

        system = platform.system()

        shutil.copyfile('images/note.png', self.book_path / 'note.png')
        shutil.copyfile('css/style.css', self.book_path / 'style.css')
        self.send(f"正在复制资源： {self.book_path}/note.png")

        if system == "Windows":
            merged_file = self.book_path / "merged.html"
            merged_file.write_text(merged_html, "utf-8")

            # 定义 PDF 格式和全局样式选项
            pdf_options = [
                "--enable-local-file-access",  # 允许读取本地图片 (保持)
                "--page-size", "A4",  # 纸张大小 A4
                "--margin-top", "20mm",  # 顶部边距 20mm
                "--margin-bottom", "20mm",  # 底部边距 20mm
                "--margin-left", "15mm",  # 左边距 15mm
                "--margin-right", "15mm",  # 右边距 15mm
                "--encoding", "utf-8",  # 确保输入编码正确
                # "--dpi", "300",             # 可选：提高图像分辨率
            ]


            if not os.path.exists(WKHTMLTOPDF_DIR):
                raise f'not found: {WKHTMLTOPDF_DIR}'

            cmd = [
                WKHTMLTOPDF_DIR,
                *pdf_options,  # 允许读取本地图片
                str(merged_file),
                str(self.file_name)
            ]

            self.send("检测到 Windows，执行 wkhtmltopdf 命令行...")

            try:
                subprocess.run(cmd, check=True)
                self.send("转换完成！")

                # ---- 删除 merged.html ----
                # if merged_file.exists():
                #     merged_file.unlink()
                #     self.send(f"清理中间文件: {merged_file}", )

            except subprocess.CalledProcessError as e:
                traceback.print_exc()
                self.send("wkhtmltopdf 执行失败！", )
        else:
            self.send(f"当前系统 {system} 不能执行 wkhtmltopdf。")

    # ----------------------------
    # 下载图片
    # ----------------------------
    def download_image(self, url, img_path):
        # filename = url.split("/")[-1]
        # img_path = img_dir / filename
        #
        # 已存在直接返回
        if img_path.exists():
            self.send(f'skip: {url}')
            return

        self.send(f"下载图片：{url}", )

        headers = {
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://weread.qq.com/"
        }
        while True:
            try:
                r = requests.get(url, headers=headers, timeout=10)
                if r.status_code == 200:
                    img_path.write_bytes(r.content)
                    break
                else:
                    self.send(f"下载失败：{url}  {r.status_code}  ",)

            except:
                traceback.print_exc()
                self.send(f"下载失败-重试：{url}",)

def process_xhtml(xhtml: str):
    soup = BeautifulSoup(xhtml, "lxml-xml")

    results = []

    for img in soup.find_all("img"):
        link = img.get("src")
        if not link:
            continue

        # 生成 hash 文件名（用 URL 作为唯一标识）
        ext = os.path.splitext(link)[1].lower().replace('.', '')

        if ext not in ['jpg', 'png', 'jpeg']:
            ext = 'jpg'

        filename = hashlib.md5(link.encode("utf-8")).hexdigest() + f".{ext}"

        # 替换 src => images/<filename>
        img["src"] = f"images/{filename}"

        # 保存记录
        results.append({
            "link": link,
            "filename": filename,
            "content": str(img)      # img 标签本身
        })

    # 最终修改后的 XHTML
    new_xhtml = str(soup)

    return results, new_xhtml



if __name__ == '__main__':

    def a():
        xhtml = '''
        <p class="calibre_5">
          <img alt="" class="calibre_6"
               src="https://res.weread.qq.com/wrepub/CB_3300006549_00038.jpg"
               data-w="340px" data-ratio="0.862" data-w-new="293px" />
        </p>
        '''

        images, new_xhtml = process_xhtml(xhtml)

        print(images)
        print(new_xhtml)

        book_id = 3300006549
        epub = EpubBuilder(book_id)

        epub.output()

    def b(xhtml):

        def normalize_classes(raw):
            """
            规范化 class 属性：
            - None → []
            - "a b c" → ["a", "b", "c"]
            - ["a", "b"] → ["a", "b"]
            - 其他类型 → []
            """
            if raw is None:
                return []

            if isinstance(raw, list):
                return raw

            if isinstance(raw, str):
                return raw.strip().split()

            return []

        def xhtml_to_markdown(xhtml: str) -> str:
            soup = BeautifulSoup(xhtml, "lxml-xml")

            md_lines = []

            def handle_inline(el):
                if el.name is None:
                    return el.string or ""

                # italic span
                if el.name == "span" and "italic" in normalize_classes(el.get("class")):
                    return f"*{''.join(handle_inline(c) for c in el.children)}*"

                # img inline
                if el.name == "img":
                    src = el.get("src", "")
                    classes = normalize_classes(el.get("class"))
                    if classes:
                        cls = ".".join(classes)
                        return f"![]({src}){{.{cls}}}"
                    return f"![]({src})"

                # 默认递归
                return "".join(handle_inline(c) for c in el.children)

            # --- 关键修复：只遍历 body.children，避免嵌套混乱 ---
            for tag in soup.body.children:
                if getattr(tag, "name", None) is None:
                    continue

                if tag.name == "h1":
                    md_lines.append(f"# {handle_inline(tag)}\n")
                elif tag.name == "h2":
                    md_lines.append(f"## {handle_inline(tag)}\n")
                elif tag.name == "h3":
                    md_lines.append(f"### {handle_inline(tag)}\n")
                elif tag.name == "p":
                    text = handle_inline(tag).strip()
                    if text:
                        md_lines.append(text + "\n")

                elif tag.name == "div":
                    imgs = tag.find_all("img", recursive=False)
                    if len(imgs) == 1:
                        img = imgs[0]
                        src = img.get("src", "")
                        classes = normalize_classes(img.get("class"))
                        if classes:
                            cls = ".".join(classes)
                            md_lines.append(f"![]({src}){{.{cls}}}\n")
                        else:
                            md_lines.append(f"![]({src})\n")

            return "\n".join(md_lines).strip()
        return xhtml_to_markdown(xhtml)

    h = b(open(r"C:\Users\80651\PycharmProjects\good-job\tootls\weread\weread_client\books\36703570\chapters\10.xhtml",
               'r', encoding='utf8').read())

    print(h)