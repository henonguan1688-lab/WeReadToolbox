import asyncio
import json
import os
import sys
import time
import traceback
from pathlib import Path
from typing import Dict, Any

from PySide6.QtCore import QUrl, QThread, Signal, Slot, QObject, QPoint, QTimer
from PySide6.QtCore import Qt
from PySide6.QtGui import QDesktopServices
from PySide6.QtGui import QPixmap, QColor
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply
from PySide6.QtWidgets import (
    QApplication
)
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QGroupBox, QHBoxLayout,
    QButtonGroup, QRadioButton, QPlainTextEdit, QPushButton, QMessageBox
)
from PySide6.QtWidgets import (
    QWidget,
    QLabel,
    QProgressBar,
)

from text_to_epub import EpubBuilder, MarkdownBuilder, PdfBuilder
from book_util import set_book_is_download, req_book_page, req_book_chapters, parser_script, parser_chapter_info, \
    req_book_chapters_content, resolve_content, load_my_books, req_goto_search_page, req_search_books
from shelf import login_weread, load_browser, load_search_browser
from constants import DOWNLOAD_DELAY, BOOK_DIR, STORAGE


class ExportDialog(QDialog):

    def __init__(self, parent=None, book_id=None):
        super().__init__(parent)
        self.setWindowTitle("导出文件")
        self.resize(900, 500)
        self.is_start = False
        self.book_id = book_id
        self.builder = None  # 保存当前导出任务
        layout = QVBoxLayout(self)

        # === 导出类型单选 ===
        type_box = QGroupBox("导出类型")
        type_layout = QHBoxLayout()

        self.radio_group = QButtonGroup(self)
        self.radio_pdf = QRadioButton("PDF")
        self.radio_md = QRadioButton("MD")
        self.radio_txt = QRadioButton("TXT")
        self.radio_epub = QRadioButton("EPUB")

        self.radio_group.addButton(self.radio_pdf)
        self.radio_group.addButton(self.radio_md)
        self.radio_group.addButton(self.radio_txt)
        self.radio_group.addButton(self.radio_epub)

        self.radio_pdf.setChecked(True)

        for radio in [self.radio_pdf, self.radio_md, self.radio_txt, self.radio_epub]:
            type_layout.addWidget(radio)

        type_box.setLayout(type_layout)
        layout.addWidget(type_box)

        # === 日志窗口 ===
        self.log_area = QPlainTextEdit()
        self.log_area.setReadOnly(True)
        self.log_area.setPlaceholderText("下载资源日志...")
        layout.addWidget(self.log_area)

        # === 按钮区域 ===
        btn_layout = QHBoxLayout()
        self.open_folder_btn = QPushButton("打开输出文件夹")
        self.start_export_btn = QPushButton("开始导出")
        self.stop_export_btn = QPushButton("停止")
        self.close_btn = QPushButton("关闭窗口")  # 新增关闭按钮
        self.close_btn.setStyleSheet("background-color: red; color: white;")

        self.stop_export_btn.setEnabled(False)

        btn_layout.addWidget(self.open_folder_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(self.start_export_btn)
        btn_layout.addWidget(self.stop_export_btn)
        btn_layout.addWidget(self.close_btn)

        layout.addLayout(btn_layout)

        # 信号绑定
        self.open_folder_btn.clicked.connect(self.open_output_folder)
        self.start_export_btn.clicked.connect(self.start_export)
        self.stop_export_btn.clicked.connect(self.stop_export)
        self.close_btn.clicked.connect(self.close_dialog)

        # 默认输出目录
        self.output_dir = os.path.join(os.getcwd(), f"books/{book_id}")
        os.makedirs(self.output_dir, exist_ok=True)

        # 禁用窗口右上角关闭按钮
        self.setWindowFlag(Qt.WindowCloseButtonHint, False)



    def open_output_folder(self):

        if hasattr(self, 'file_path'):

            file_path = self.output_file  # 你生成的 epub 路径
        else:
            file_path = os.path.join(self.output_dir, "chapters")
        if not os.path.exists(file_path):
            return

        # Windows 上打开文件所在目录并选中该文件
        QDesktopServices.openUrl(
            QUrl.fromLocalFile(os.path.dirname(file_path))
        )

    def closeEvent(self, event):
        """
        禁用右上角关闭
        """
        # 阻止窗口关闭

        event.ignore()
        QMessageBox.information(self, "提示", "请点击“关闭窗口”按钮退出")

    def close_dialog(self):
        """
        用户点击自定义关闭按钮
        """
        if self.builder and self.builder.isRunning():
            QMessageBox.information(self, "提示", "导出任务还没完成")

        else:
            self.accept()  # 关闭对话框

    def stop_export(self):
        """
        用户点击自定义关闭按钮
        """
        if self.builder and self.builder.isRunning():
            # 创建自定义 QMessageBox
            msg_box = QMessageBox(self)
            msg_box.setWindowTitle("任务进行中")
            msg_box.setText("确定终止吗？")
            msg_box.setIcon(QMessageBox.Warning)

            # 添加按钮
            yes_btn = msg_box.addButton("是，终止任务", QMessageBox.YesRole)
            no_btn = msg_box.addButton("继续任务", QMessageBox.NoRole)

            # 设置红色样式
            yes_btn.setStyleSheet("background-color: red; color: white;")

            # 显示对话框并等待用户选择
            msg_box.exec()

            if msg_box.clickedButton() == no_btn:
                # self.log_area.appendPlainText("取消任务...")
                return
            else:
                self.log_area.appendPlainText("开始终止任务...")
                self.builder.terminate()
                self.builder.wait()
                self.log_area.appendPlainText("终止任务完成")
                self.update_btns_star(0)


    def start_export(self):
        export_type = self.get_export_type()
        self.log_area.appendPlainText(f"开始导出: {export_type}")

        self.builder = None
        if export_type == 'epub':
            self.builder = EpubBuilder(book_id=self.book_id)
        elif export_type == 'md':
            self.builder = MarkdownBuilder(book_id=self.book_id)
        elif export_type == 'txt':
            return
        elif export_type == 'pdf':
            self.builder = PdfBuilder(book_id=self.book_id)
        else:
            raise ValueError("未知导出类型")

        self.start_export_btn.setEnabled(False)
        self.stop_export_btn.setEnabled(True)
        self.close_btn.setEnabled(False)
        self.close_btn.setStyleSheet("background-color: gray; color: white;")

        self.builder.end_signal.connect(self.update_btns_star)

        if self.builder:
            self.output_file = self.builder.file_name
            self.builder.msg.connect(self.log_area.appendPlainText)
            self.builder.start()


    def update_btns_star(self, signal):
        self.start_export_btn.setEnabled(True)
        self.stop_export_btn.setEnabled(False)
        self.close_btn.setEnabled(True)
        self.close_btn.setStyleSheet("background-color: red; color: white;")


    def get_export_type(self):
        if self.radio_pdf.isChecked():
            return "pdf"
        if self.radio_md.isChecked():
            return "md"
        if self.radio_txt.isChecked():
            return "txt"
        if self.radio_epub.isChecked():
            return "epub"
        return "txt"


class ToastNotification(QWidget):
    """
    一个无边框、半透明、自动消失的浮动通知组件。

    def __init__():
        # ⚠️ 确保通知实例可以被复用或存储，以避免频繁创建和内存泄漏
        self.toast = ToastNotification("", self)
        self.toast.hide()  # 默认隐藏

    def trigger_toast(self):
        self.toast.setText("操作已完成，文件已保存到本地。")
        self.toast.show_notification(duration_ms=1500)
    """

    def __init__(self, message: str, parent: QWidget = None):
        super().__init__(parent)

        # --- A. 窗口设置：实现无边框和透明背景 ---
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |  # 移除标题栏和边框
            Qt.WindowType.ToolTip |  # 确保它浮在其他窗口之上
            Qt.WindowType.BypassWindowManagerHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        # --- B. UI 布局和样式 ---
        layout = QVBoxLayout(self)

        self.label = QLabel(message)
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # 设置样式：圆角、背景色、内边距
        self.label.setStyleSheet("""
            QLabel {
                background-color: rgba(50, 50, 50, 220); /* 深灰色半透明背景 */
                color: white;
                padding: 10px 20px;
                border-radius: 8px; /* 圆角 */
                font-size: 14px;
            }
        """)

        layout.addWidget(self.label)
        self.setLayout(layout)

        # --- C. 动画和定时器 ---
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.hide_notification)

    def show_notification(self, duration_ms: int = 1500):
        """显示通知并启动定时器，使用全局坐标系精确居中定位。"""

        parent = self.parentWidget()
        if parent:
            # 1. 强制调整自身尺寸
            self.adjustSize()

            # 2. 获取父窗口的屏幕绝对位置 (主窗口左上角)
            # mapToGlobal(QPoint(0, 0)) 给出的是父窗口内容区的左上角在屏幕上的坐标
            parent_global_pos: QPoint = parent.mapToGlobal(QPoint(0, 0))

            # 3. 获取父窗口的几何信息 (使用 size() 获取内容区宽度)
            parent_width = parent.size().width()

            # 4. 计算 Toast 的目标屏幕绝对坐标 (关键修正)

            # X 坐标: 父窗口全局X + (父窗口内容宽度 - 自身宽度) / 2
            # 这是为了实现水平居中
            target_x = parent_global_pos.x() + (parent_width - self.width()) // 2

            # Y 坐标: 父窗口全局Y + 顶部偏移量
            # 我们需要考虑主窗口的标题栏高度 (约 30px)
            # ⚠️ QMainWindow的标题栏高度大约是30px，这里使用 30 作为偏移基础
            TITLE_BAR_OFFSET = 10
            TOP_PADDING = 10

            target_y = parent_global_pos.y() + TITLE_BAR_OFFSET + TOP_PADDING

            # 5. 移动通知到计算出的屏幕绝对位置 (使用绝对坐标)
            # -----------------------------------------------------------
            # ⚠️ 关键修正：直接使用 target_x 和 target_y
            self.move(target_x, target_y)
            # -----------------------------------------------------------

        # 6. 显示并启动定时器
        self.show()
        self.timer.start(duration_ms)

    def hide_notification(self):
        """关闭通知"""
        self.close()

    def setText(self, message: str):
        """外部接口：设置文本"""
        self.label.setText(message)
        self.adjustSize()  # 调整大小以适应新文本

class LoginAsyncWorker(QThread):

    books_signal = Signal(list)

    def run(self):
        """在工作线程中执行阻塞的 asyncio.run"""
        # 注意：虽然这一行会阻塞这个 QThread，但它不会阻塞 UI 主线程
        try:
            # 实际调用您的异步函数
            asyncio.run(login_weread())

            # 如果 login_weread 返回数据，可以在这里保存到 self.result 并通过 Signal 传递
            books = load_my_books()

            set_book_is_download(books)

            self.books_signal.emit(books)

        except Exception as e:
            traceback.print_exc()
            print(f"异步任务执行失败: {e}")
            # 可以在这里发射一个带有错误信息的信号


# =========================================
# ★ 下载线程（不阻塞 UI）
# =========================================
class AsyncDownloadWorker(QThread):
    '''
    :param progress
            -1 失败，1成功， 0 开始下载，2暂停
    '''
    progress = Signal(int, str, int, int, dict)
    chapterTotal = Signal(int, int, dict)
    status = Signal(str, dict)
    show_progress = Signal(int, dict)
    update_book_signal = Signal(dict, )

    def __init__(self, ):
        super().__init__()
        self.book = None
        self.paused = True
        self.running = False
        self.book_ids = set()
        self.tasks = []

    async def task(self):

        p, b, context = await load_browser()
        while True:
            if not self.tasks:
                time.sleep(2)
            else:
                book = self.tasks.pop(0)

                self.running = True
                self.paused = False

                page = await context.new_page()
                total = 0
                curr_index = 0
                try:
                    self.progress.emit(0, "开始下载...", 0, 0, book)

                    book_id = book['bookId']

                    html = await req_book_page(page, book)

                    chapter_infos = await req_book_chapters(page, book)
                    levels = list(set([c.get('level', 1) for c in chapter_infos]))

                    book_info = parser_script(html)
                    chapters = parser_chapter_info(html, levels)

                    if not book.get('format'):
                        new_book = book_info['reader']['bookInfo']
                        book['format'] = new_book['format']
                        book['language'] = new_book['language']
                        self.update_book_signal.emit(book,)

                    book_info_path = BOOK_DIR / Path(f'{book_id}/info.json')
                    chapter_infos_path = BOOK_DIR / Path(f'{book_id}/chapters.json')
                    chapter_dir = Path(BOOK_DIR / Path(f'{book_id}')) / Path('chapters')

                    Path(BOOK_DIR / Path(f'{book_id}')).mkdir(exist_ok=True, parents=True)
                    chapter_dir.mkdir(exist_ok=True, parents=True)

                    Path(BOOK_DIR / Path(f'{book_id}/{book["title"]}')).open('w', encoding='utf8').write('')

                    psvts = book_info['reader']['psvts']
                    pclts = f'{int(time.time())}'

                    total = len(chapter_infos)

                    self.chapterTotal.emit(0, total, book)

                    json.dump(book, book_info_path.open('w', encoding='utf8'), ensure_ascii=False, indent=4)
                    json.dump(chapter_infos, chapter_infos_path.open('w', encoding='utf8'), ensure_ascii=False,
                              indent=4)

                    for i, chapter in enumerate(chapter_infos):
                        if not self.running:
                            break

                        curr_index = i

                        if chapters[max(i - 1, 0)]['is_lock']:
                            raise Exception(f'下载失败 - 没有阅读权限...')

                        chapter_id = chapter["chapterUid"]

                        ext = '.xhtml' if book['format'] == 'epub' else '.txt'
                        chapter_path = chapter_dir / Path(f'{chapter_id}{ext}')
                        if not chapter_path.exists():
                            texts = await req_book_chapters_content(
                                page,
                                book,
                                chapter_id,
                                psvts,
                                pclts
                            )
                            content, css = resolve_content(texts, book, )

                            if content:
                                chapter_path.open('w', encoding='utf8').write(content)
                                # print(f'保存章节：{chapter_path}')

                        success = 1 if (i + 1) == total else 0
                        self.progress.emit(success, '', min(i + 1, total), total, book)

                        # 暂停逻辑
                        while self.paused:
                            self.progress.emit(2, f"暂停中…", i + 1, total, book)
                            await asyncio.sleep(1)

                        await asyncio.sleep(DOWNLOAD_DELAY)
                except Exception as e:
                    self.progress.emit(-1, f'{e}', curr_index + 1, total, book)
                    traceback.print_exc()
                finally:
                    # 保存会话到文件
                    await context.storage_state(path=STORAGE)
                    await page.close()

    def run(self):

        asyncio.run(self.task())


    def add_task(self, book):
        book_id = book['bookId']
        if book_id not in self.book_ids:
            self.book_ids.add(book_id)

            if not book.get('is_download'):
                self.tasks.append(book)


    # --- 暂停与继续 ---
    def pause(self):
        self.paused = True
        self.status.emit("已暂停", self.book)

    def resume(self):
        self.paused = False
        self.status.emit("继续下载...", self.book)

    def stop(self):
        self.running = False
        self.status.emit("停止", self.book)


class AsyncSearchWorker(QThread):

    results_signal = Signal(str, dict, dict)

    def __init__(self, query, /):
        super().__init__()
        self.browser = None
        self.query = query

    def run(self):
        async def task():
            p, browser, context = await load_search_browser()
            self.browser = (p, browser, context)
            page = await context.new_page()
            await req_goto_search_page(page)

            url, headers, results = await req_search_books(self.query, page, )
            if results:
                self.results_signal.emit(url, headers, results)

            await browser.close()

        asyncio.run(task())


class ImageDownloader(QObject):
    """在 QThread 中运行，负责从 URL 下载图片"""
    # 信号签名: (book_id, pixmap) - 包含书籍ID和下载好的图片
    download_finished = Signal(str, QPixmap)

    # ⚠️ 必须在主线程创建 QNetworkAccessManager
    def __init__(self, manager: QNetworkAccessManager, parent=None):
        super().__init__(parent)
        self.manager = manager
        self.request_queue = []
        self.is_busy = False

    Slot(str, str)

    def start_download(self, book_id: str, url: str):
        """接收下载请求"""
        if not url:
            self.download_finished.emit(book_id, QPixmap())
            return

        request = QNetworkRequest(QUrl(url))

        # -----------------------------------------------------------------
        # ⚠️ 关键修正：直接使用 QNetworkRequest.Attribute 访问属性
        # -----------------------------------------------------------------

        # 1. 设置 CustomVerbAttribute (间接确保使用标准方法)
        request.setAttribute(
            QNetworkRequest.Attribute.CustomVerbAttribute,
            "GET"
        )

        # 2. 关键修正：禁用 HTTP/2 Pipelining 来提高兼容性
        request.setAttribute(
            QNetworkRequest.Attribute.HttpPipeliningAllowedAttribute,
            False
        )

        # 3. 设置 User-Agent (可选，推荐：模拟浏览器，提高成功率)
        request.setRawHeader(
            b"User-Agent",
            b"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/100.0.0.0 Safari/537.36"
        )

        reply: QNetworkReply = self.manager.get(request)

        # ⚠️ 将 replyFinished 信号连接到处理槽
        reply.finished.connect(lambda r=reply, bid=book_id: self._handle_finished(r, bid))

    def _handle_finished(self, reply: QNetworkReply, book_id):
        """处理网络响应"""
        # 检查是否有错误，特别是协议错误
        if reply.error() != QNetworkReply.NetworkError.NoError:
            # 捕获并打印错误详情
            error_str = reply.errorString()
            print(f"图片下载失败 ({reply.error()}): {error_str}")

            # 检查是否为 HTTP/2 错误
            if "protocol error" in error_str.lower():
                print("  -> 可能是 HTTP/2 兼容性问题。")

            pixmap = QPixmap()  # 返回空 QPixmap
        else:
            # ... (成功处理代码不变) ...
            data = reply.readAll()
            pixmap = QPixmap()
            pixmap.loadFromData(data)

        self.download_finished.emit(book_id, pixmap)
        reply.deleteLater()


# --- 1. 定义工作线程 (执行耗时任务) ---
class DataLoadWorker(QThread):

    def __init__(self, books, /):
        super().__init__()
        self.books = books
        print("--- DataLoadWindow __init__ 被调用 ---")  # 👈 添加这个

    def run(self):
        """模拟一个耗时的数据加载任务"""
        print("Worker: 正在开始加载数据...")

        set_book_is_download(self.books)
        print("Worker: 数据加载完成。")


class DataLoadWindow(QWidget):

    loaded_signal = Signal(bool)

    def __init__(self, is_init=True):
        super().__init__()
        self.books = []
        self.resize(250, 100)
        self.setWindowTitle("数据加载中")

        self.layout = QVBoxLayout(self)
        self.layout.addWidget(QLabel("正在等待数据加载..."))

        bar = QProgressBar()
        bar.setValue(0)
        bar.setMaximum(0)
        bar.setVisible(True)

        self.layout.addWidget(bar)

        self.show()
        # asyncio.run(login_weread())  # 如果需要
        if is_init:
            self.login_worker = LoginAsyncWorker()
            self.login_worker.books_signal.connect(self.init_async)
            self.login_worker.start()
        else:
            self.init_async(self.books)


    def init_async(self, books):
        """
        开始异步任务，并显示加载弹框。
        """
        self.books = books
        self.worker = DataLoadWorker(self.books)
        # 链接工作线程的完成信号到主线程的槽函数
        self.worker.finished.connect(self.on_data_load_finished)

        print("--- init_async 被调用，启动 Worker ---")  # 👈 添加这个
        self.worker.start()  # 启动工作线程

    def on_data_load_finished(self):
        """
        数据加载完成时调用的槽函数。
        """
        print("主线程: 接收到完成信号。")

        self.close()

        self.loaded_signal.emit(True)


class ClickableLabel(QLabel):

    clicked = Signal()  # 自定义点击信号

    def __init__(self, tip_text='', parent=None, ):
        super().__init__(parent)
        self.tip_text = tip_text

        # 初始样式：没有边框
        self.setStyleSheet("border: 1px solid transparent;")
        # 鼠标悬停才会触发 enterEvent / leaveEvent
        self.setMouseTracking(True)

        # 设置提示文字（Qt 会自动在 hover 时显示）
        self.setToolTip(self.tip_text)

    # 点击事件
    def mousePressEvent(self, event):
        self.clicked.emit()
        super().mousePressEvent(event)

    # 鼠标进入事件
    def enterEvent(self, event):
        # 高亮边框，比如蓝色
        self.setStyleSheet("border: 1px solid gray;")
        super().enterEvent(event)

    # 鼠标离开事件
    def leaveEvent(self, event):
        # 恢复原始样式
        self.setStyleSheet("border: 1px solid transparent;")
        super().leaveEvent(event)


# 假设这些是外部定义的函数或方法，您需要在实际环境中提供它们的实现
# 1. load_image: 根据 book 数据加载 QPixmap
# 2. self.update_bar_status: 更新进度条样式
# 3. self.open_export_dialog: 打开导出对话框
# 4. self.bind_download: 绑定下载/继续逻辑
# 注意：为了让代码可运行，我将假设 load_image 在这里简单地返回一个 QPixmap。
def load_image(book: Dict[str, Any]) -> QPixmap:
    # 示例实现：实际中您需要根据 book 数据加载图片
    # 这里我们返回一个小的占位 QPixmap
    pixmap = QPixmap(50, 75)
    # 使用 QColor 来创建颜色并填充 (在 PySide6/Qt6 中推荐使用 QColor)
    pixmap.fill(QColor(0xEEEEEE))
    return pixmap


class BookItemWidget(QWidget):
    pass


if __name__ == "__main__":

    def test():
        class MainWindow(QWidget):
            def __init__(self):
                super().__init__()
                self.setWindowTitle("主窗口")

                layout = QVBoxLayout(self)

                # 导出按钮
                self.export_btn = QPushButton("导出")
                self.export_btn.setEnabled(True)  # 你可以自己控制什么时候可用
                self.export_btn.setMaximumWidth(50)

                layout.addWidget(self.export_btn)
                layout.addStretch()

                # 点击导出 → 弹 dialog
                self.export_btn.clicked.connect(self.open_export_dialog)

            def open_export_dialog(self):
                dlg = ExportDialog(self, book_id='28416137')
                dlg.exec()


        app = QApplication(sys.argv)
        w = MainWindow()
        w.resize(300, 150)
        w.show()
        sys.exit(app.exec())

    test()
