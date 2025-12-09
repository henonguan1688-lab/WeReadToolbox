import asyncio
import json
import os.path
import sys
import time
import traceback
import webbrowser
from pathlib import Path

import requests
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QApplication, QWidget, QLabel, QListWidget, QListWidgetItem,
    QVBoxLayout, QHBoxLayout, QAbstractItemView, QPushButton, QProgressBar
)

from book_util import WereadGenerate, req_book_page, req_book_chapters_content, req_book_chapters, resolve_content, \
    set_book_is_download, parser_chapter_info, parser_script
from component import ExportDialog
from shelf import login_weread, load_browser

DOWNLOAD_DELAY = 0.1
SAVE_DIR = "images/cover"
BOOK_DIR = Path("books")

BOOK_DIR.mkdir(exist_ok=True, parents=True)

def load_image(cover=None, book=None, size=(80, 120)):
    """下载封面图并转换为 QPixmap"""
    try:
        book_id = None
        if book:
            img_url = book["cover"]
            book_id = book['bookHash']
        else:
            img_url = cover

        ext = os.path.splitext(img_url)[1].split("?")[0]  # 保留 jpg/png
        if ext.lower() not in [".jpg", ".jpeg", ".png"]:
            ext = ".jpg"  # 默认 jpg

        if book_id:
            content = open(os.path.join(SAVE_DIR, f'{book_id}{ext}'), 'rb').read()
        else:
            r = requests.get(img_url, timeout=10)
            content = r.content

        pix = QPixmap()
        pix.loadFromData(content)
        return pix.scaled(*size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    except:
        return QPixmap()

# =========================================
# ★ 下载线程（不阻塞 UI）
# =========================================

class AsyncDownloadWorker(QThread):
    '''
    :param progress
            -1 失败，1成功， 0 开始下载，2暂停
    '''
    progress = Signal(int, str, int, int,)
    chapterTotal = Signal(int, int)
    status = Signal(str)
    show_progress = Signal(int)
    # finished = Signal(bool)

    def __init__(self, book, context):
        super().__init__()
        self.book = book
        self.context = context
        self.paused = True
        self.running = False

    def run(self):
        async def task():
            self.running = True
            self.paused = False

            p, b, context = await load_browser()

            page = await context.new_page()
            total = 0
            curr_index = 0
            try:
                self.progress.emit(0, "开始下载...", 0, 0)

                book_id = self.book['bookId']



                html = await req_book_page(page, self.book)

                chapter_infos = await req_book_chapters(page, self.book)
                levels = list(set([c['level'] for c in chapter_infos]))

                book_info = parser_script(html)
                chapters = parser_chapter_info(html, levels)


                book_info_path = BOOK_DIR / Path(f'{book_id}/info.json')
                chapter_infos_path = BOOK_DIR / Path(f'{book_id}/chapters.json')
                chapter_dir = Path(BOOK_DIR / Path(f'{book_id}')) / Path('chapters')

                Path(BOOK_DIR / Path(f'{book_id}')).mkdir(exist_ok=True, parents=True)
                chapter_dir.mkdir(exist_ok=True, parents=True)

                Path(BOOK_DIR / Path(f'{book_id}/{self.book["title"]}')).open('w', encoding='utf8').write('')

                psvts = book_info['reader']['psvts']
                pclts = f'{int(time.time())}'

                total = len(chapter_infos)

                self.chapterTotal.emit(0, total)

                json.dump(self.book, book_info_path.open('w', encoding='utf8'), ensure_ascii=False, indent=4)
                json.dump(chapter_infos, chapter_infos_path.open('w', encoding='utf8'), ensure_ascii=False, indent=4)


                for i, chapter in enumerate(chapter_infos):
                    if not self.running:
                        break

                    curr_index = i

                    if chapters[max(i - 1, 0)]['is_lock']:
                        raise Exception(f'下载失败 - 没有阅读权限...')

                    chapter_id = chapter["chapterUid"]

                    ext = '.xhtml' if self.book['format'] == 'epub' else '.txt'
                    chapter_path = chapter_dir / Path(f'{chapter_id}{ext}')
                    if not chapter_path.exists():
                        texts = await req_book_chapters_content(
                            page, self.book,
                            chapter_id,
                            psvts,
                            pclts
                        )
                        content, css = resolve_content(texts, self.book, )

                        if content:
                            chapter_path.open('w', encoding='utf8').write(content)
                            print(f'保存章节：{chapter_path}')

                    success = 1 if (i + 1) == total else 0
                    self.progress.emit(success, '', min(i + 1, total), total, )

                    # 暂停逻辑
                    while self.paused:
                        self.progress.emit(2, f"暂停中…", i + 1, total)
                        await asyncio.sleep(1)

                    await asyncio.sleep(DOWNLOAD_DELAY)
            except Exception as e:
                self.progress.emit(-1, f'{e}', curr_index + 1, total)
                traceback.print_exc()
            finally:
                await page.close()
                await b.close()

        asyncio.run(task())

    # --- 暂停与继续 ---
    def pause(self):
        self.paused = True
        self.status.emit("已暂停")

    def resume(self):
        self.paused = False
        self.status.emit("继续下载...")

    def stop(self):
        self.running = False
        self.status.emit("停止")


# =========================================
# 主窗口
# =========================================
class WeReadWindow(QWidget):
    def __init__(self, browser, context, user_data, book_list):
        super().__init__()

        self.book_util = WereadGenerate()

        self.tasks = {}

        self.browser = browser
        self.context = context

        self.setWindowTitle("WeRead 书架")
        self.resize(800, 800)

        self.layout = QVBoxLayout(self)

        # ======================
        # 用户信息区域
        # ======================
        user_box = QHBoxLayout()

        avatar = load_image(user_data.get("avatar", ''), size=(80, 80))
        avatar_label = QLabel()
        avatar_label.setPixmap(avatar)

        info_label = QLabel(
            f"<b>{user_data.get('name')}</b><br>"
            f"UserVid: {user_data.get('userVid')}<br>"
        )
        info_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        user_box.addWidget(avatar_label)
        user_box.addWidget(info_label)
        self.layout.addLayout(user_box)

        # ======================
        # 书籍列表
        # ======================
        self.list_widget = QListWidget()
        self.list_widget.setSelectionMode(QAbstractItemView.NoSelection)

        self.display_books(book_list, self.list_widget)

        self.layout.addWidget(self.list_widget)

    def display_books(self, book_list, list_widget):

        for book in book_list:
            is_download = book.get('is_download')
            pix = load_image(book=book)

            item = QListWidgetItem()
            item_widget = QWidget()
            item_layout = QVBoxLayout(item_widget)

            # 上排 = 图片 + 标题 + 按钮区
            # row = QHBoxLayout()
            img_label = QLabel()
            img_label.setPixmap(pix)

            title_label = QLabel(book["title"])
            title_label.setWordWrap(True)
            title_label.setStyleSheet("font-size: 14px; font-weight: bold;")

            # 打开按钮
            open_btn = QPushButton("打开")
            open_btn.clicked.connect(
                lambda _, book_hash=book["bookHash"]:
                webbrowser.open("https://weread.qq.com/web/reader/" + book_hash)
            )
            open_btn.setMaximumWidth(50)

            # 下载按钮
            download_btn = QPushButton("下载")
            download_btn.setMaximumWidth(50)

            pause_btn = QPushButton("暂停")
            pause_btn.setEnabled(False)
            pause_btn.setMaximumWidth(50)

            export_btn = QPushButton("导出")
            export_btn.setEnabled(False)
            export_btn.setMaximumWidth(50)
            # 点击导出 → 弹 dialog
            # export_btn.clicked.connect(self.open_export_dialog)
            export_btn.clicked.connect(lambda _, bid=book["bookId"]: self.open_export_dialog(bid))

            # 状态文字
            status_label = QLabel("")
            status_label.setStyleSheet("color: gray; font-size: 12px;")

            # 进度条
            progress = QProgressBar()
            progress.setFormat("%p%")  # 显示百分比文本
            progress.setTextVisible(True)

            is_download = book.get('is_download')
            if is_download:
                # 确保最大值合法（避免 0）
                chapter_size = book.get('chapter_size') or 0
                max_val = max(1, int(chapter_size))
                progress.setRange(0, max_val)
                progress.setValue(max_val)
                progress.setVisible(True)

                self.update_bar_status(progress, 1)

                status_label.setText('完成')
                status_label.setStyleSheet("color: green; font-size: 12px;")
                export_btn.setEnabled(True)
            else:
                download_progress = book.get('progress', 0)
                if download_progress > 0:
                    chapter_size = book.get('chapter_size') or 0
                    max_val = max(1, int(chapter_size))
                    progress.setRange(0, max_val)
                    progress.setValue(download_progress)
                    progress.setVisible(True)
                    self.update_bar_status(progress, 2)

                    status_label.setText(f'{download_progress} / {max_val} 暂停...')
                    status_label.setStyleSheet("color: orange; font-size: 12px;")

                    download_btn.setEnabled(False)
                    pause_btn.setEnabled(True)
                    pause_btn.setText('继续')

                    self.bind_download(download_btn, pause_btn, export_btn, progress, status_label, book, invoke=False)()
                else:
                    # progress.setValue(0)
                    progress.setVisible(False)

            download_btn.clicked.connect(
                self.bind_download(download_btn, pause_btn, export_btn, progress, status_label, book)
            )

            # 上排 = 图片 + 标题 + 按钮区
            row = QHBoxLayout()

            img_label = QLabel()
            img_label.setPixmap(pix)

            title_label = QLabel(book["title"])
            title_label.setWordWrap(True)

            # 按钮竖排布局
            btn_column = QVBoxLayout()
            btn_column.addWidget(open_btn)
            btn_column.addWidget(download_btn)
            btn_column.addWidget(pause_btn)
            btn_column.addWidget(export_btn)
            btn_column.addStretch()

            row.addWidget(img_label)
            row.addWidget(title_label)

            # 把按钮竖排添加进去
            row.addLayout(btn_column)

            item_layout.addLayout(row)
            item_layout.addWidget(progress)
            item_layout.addWidget(status_label)

            item.setSizeHint(item_widget.sizeHint())
            list_widget.addItem(item)
            list_widget.setItemWidget(item, item_widget)



    def bind_download(self, download_btn, pauseBtn, export_btn, pbar, slabel, book, invoke=True):

        def start_download():
            download_btn.setEnabled(False)
            pbar.setVisible(True)
            pauseBtn.setEnabled(True)

            worker = AsyncDownloadWorker(book, self.context)
            if invoke:
                # 🚀 创建真正的异步下载任务
                worker.start()
                worker.paused = True

            self.tasks.update({
                book['bookId']: worker
            })

            # 暂停按钮
            pauseBtn.clicked.connect(lambda: self.toggle_pause(worker, pauseBtn))

            # 状态文本（用于 开始下载 / 完成 / 暂停 / 失败）
            def on_done(success):
                download_btn.setEnabled(True)
                pauseBtn.setEnabled(False)
                if success:
                    export_btn.setEnabled(True)

            # 设置总章节数
            worker.chapterTotal.connect(pbar.setRange)

            # 设置当前进度
            worker.progress.connect(
                lambda status, msg, curr, total, :
                self.update_progress(download_btn, pauseBtn, export_btn, pbar, slabel, status, msg, curr, total)
            )
            worker.show_progress.connect(pbar.setValue)

        return start_download

    # 更新进度条
    def update_progress(self, download_btn, pauseBtn,
                        export_btn, pbar, slabel,
                        status: int, msg: str, offset, total):

        if status == 1:
            slabel.setText(f'完成')
            slabel.setStyleSheet("color: green;")
            pbar.setValue(total)
            self.update_bar_status(pbar, 1)

            download_btn.setEnabled(True)
            export_btn.setEnabled(True)
            pauseBtn.setEnabled(False)

        elif status == 0:
            pbar.setValue(offset)
            slabel.setText(f'{offset} / {total}')
            slabel.setStyleSheet("color: gray; font-size: 12px;")
            self.update_bar_status(pbar, 0)

        elif status == 2:
            slabel.setText(f'{offset} / {total} - {msg}')
            slabel.setStyleSheet("color: orange;")
            self.update_bar_status(pbar, 2)

        else:
            pbar.setValue(offset)
            slabel.setText(f'{offset} / {total} - {msg}')
            slabel.setStyleSheet("color: red;")
            download_btn.setEnabled(True)
            pauseBtn.setEnabled(False)
            self.update_bar_status(pbar, -1)

    def update_bar_status(self, bar, status, ):
        # bar.setValue(value)

        if status == 1:  # 下载成功
            color = "#22c55e"
        elif status == 2:  # 暂停
            color = "#fbbf24"
        elif status == -1:  # 失败
            color = "#ef4444"
        else:    # 下载中
            color = "gray"

        bar.setStyleSheet(f"""
            QProgressBar {{
                text-align: center;   /* 文本水平居中 */
                border: 2px solid #555;      /* 边框颜色 */
                border-radius: 6px;          /* 圆角 */
                background-color: #eeeeee;   /* 背景色 */
                text-align: center;          /* 百分比文本居中 */
                padding: 1px;                /* 内边距 */
            }}
    
            QProgressBar::chunk {{
                background-color: {color};
            }}
        """)


    def toggle_pause(self, worker: AsyncDownloadWorker, pauseBtn, ):
        if not worker.paused:
            # 暂停
            worker.pause()
            pauseBtn.setText("继续")
        else:
            pauseBtn.setText("暂停")
            # 继续
            worker.resume()

            if not worker.running:
                # 🚀 创建真正的异步下载任务
                worker.start()


    def open_export_dialog(self, book_id):
        dlg = ExportDialog(self, book_id=book_id)
        dlg.exec()

    def closeEvent(self, event):
        asyncio.get_event_loop().create_task(self.cleanup())
        event.accept()

    async def cleanup(self):
        try:
            if self.browser:
                await self.browser.close()
                print("浏览器已安全关闭")
        except Exception as e:
            print("关闭浏览器时异常:", e)


def init_async():
    print("starting login...")
    user_data = {}
    user_data = asyncio.run(login_weread())  # 如果需要

    books = json.load(open('books.json', encoding='utf8'))
    set_book_is_download(books)

    window = WeReadWindow(None, None, user_data, books)
    window.show()


def main():
    app = QApplication(sys.argv)

    init_async()

    sys.exit(app.exec())

    # 创建 qasync loop
    # loop = qasync.QEventLoop(app)

    # asyncio.set_event_loop(loop)

    # 初始化你的异步 setup
    # loop.create_task(init_async())

    # with loop:
    #     loop.run_forever()


if __name__ == '__main__':
    print("init loop")
    main()
