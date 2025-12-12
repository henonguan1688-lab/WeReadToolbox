import asyncio
import json
import os.path
import sys
import webbrowser

import requests
from PySide6.QtCore import Qt, Slot, Signal, QTimer
from PySide6.QtGui import QPixmap, QAction, QFont
from PySide6.QtNetwork import QNetworkAccessManager
from PySide6.QtWidgets import (
    QApplication, QWidget, QLabel, QListWidget, QListWidgetItem,
    QVBoxLayout, QHBoxLayout, QAbstractItemView, QPushButton, QProgressBar, QMessageBox, QMainWindow, QProgressDialog,
    QStackedWidget, QLineEdit, QSizePolicy
)

from book_util import WereadGenerate, load_my_books, load_local_books, set_book_is_download, load_fav_books
from component import ExportDialog, BookItemWidget, DataLoadWindow, LoginAsyncWorker, AsyncDownloadWorker, \
    AsyncSearchWorker, ImageDownloader, ToastNotification
from constants import COVER_DIR, LOCAL_BOOK_SHELF_PATH, FAV_BOOK_SHELF_PATH
from shelf import login_weread, load_browser, load_search_browser


def load_image(cover=None, book=None, size=(40, 60)):
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
            content = open(os.path.join(COVER_DIR, f'{book_id}{ext}'), 'rb').read()
        else:
            r = requests.get(img_url, timeout=10)
            content = r.content

        pix = QPixmap()
        pix.loadFromData(content)
        return pix.scaled(*size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    except:
        return QPixmap()


class SearchPageWidget(QWidget):
    """
    负责显示书籍搜索界面和结果的独立 QWidget。
    """

    favorite_signal = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.max_idx = 0
        self.search_url = None
        self._setup_ui()
        self._setup_connections()

        self.cover_labels = {}  # ⚠️ 存储对 QLabel 的引用，通过 book_id 索引
        self._setup_downloader()  # 新增：设置下载器

    def _setup_ui(self):
        """初始化搜索页面的所有 UI 元素和布局"""

        main_layout = QVBoxLayout(self)

        # 页面标题
        # 注意: 修正为您提供的代码中的标题
        main_layout.addWidget(QLabel("<h4>搜索书籍</h4><hr>"))

        # --- 搜索输入框和按钮 ---
        search_box = QHBoxLayout()

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("请输入书名、作者或 ID...")
        self.search_input.setObjectName("search_input")  # 设置对象名方便样式或查找

        self.search_btn = QPushButton("搜索")
        self.search_btn.setObjectName("search_button")

        search_box.addWidget(self.search_input)
        search_box.addWidget(self.search_btn)

        # --- 搜索结果列表 ---
        self.search_results_list = QListWidget()
        self.search_results_list.addItem("搜索结果将显示在这里...")
        self.search_results_list.setSelectionMode(QAbstractItemView.NoSelection)  # 通常搜索结果不需要多选


        # --- 新增：加载更多按钮 ---
        self.load_more_button = QPushButton()
        self.load_more_button.setSizePolicy(QSizePolicy.Policy.MinimumExpanding, QSizePolicy.Policy.Fixed)
        self.load_more_button.setStyleSheet("background-color: #f0f0f0; padding: 10px;")

        # 默认情况下隐藏按钮，直到有更多结果可加载
        self.load_more_button.hide()

        # --- 组装布局 ---
        main_layout.addLayout(search_box)
        main_layout.addWidget(self.search_results_list)
        main_layout.addWidget(self.load_more_button)  # 将按钮添加到列表下方

    # ----------------------------------------------------
    # 简化版：直接利用 QNetworkAccessManager 的异步性
    # ----------------------------------------------------
    def _setup_downloader(self):
        self.network_manager = QNetworkAccessManager(self)
        self.image_downloader = ImageDownloader(self.network_manager)
        self.image_downloader.download_finished.connect(self.update_cover_image)
        # 此时，网络请求的创建和信号连接都在 UI 线程，不会有跨线程问题。

    def _setup_connections(self):
        """设置信号连接"""
        # 搜索按钮点击时触发槽函数
        self.search_btn.clicked.connect(self._handle_search)
        # 用户按 Enter 键时也触发搜索
        self.search_input.returnPressed.connect(self._handle_search)
        # ⚠️ 连接新的加载更多按钮
        self.load_more_button.clicked.connect(self.load_more_requested)

    @Slot(str, QPixmap)
    def update_cover_image(self, book_id, pixmap):
        """槽函数：接收下载完成的图片，更新 UI"""
        if book_id in self.cover_labels:
            label = self.cover_labels[book_id]
            if not pixmap.isNull():
                # 缩放图片以适应 QLabel 大小 (40x60)
                scaled_pixmap = pixmap.scaled(40, 60, Qt.AspectRatioMode.KeepAspectRatio)
                label.setPixmap(scaled_pixmap)
            else:
                # 下载失败，显示错误占位符 (可选)
                label.setText("X")

                # ⚠️ 可选：如果不再需要，可以删除引用以释放内存
            # del self.cover_labels[book_id]

    @Slot()
    def _handle_search(self):
        """实际处理搜索请求的槽函数"""
        query = self.search_input.text().strip()
        print(f"搜索请求被触发，查询内容: {query}")

        # ⚠️ 在实际应用中，您会在这里发射信号，通知主窗口执行网络/文件搜索
        # self.search_requested.emit(query)

        # 演示：清空并添加结果
        self.search_results_list.clear()
        if query:
            self.search_results_list.addItem(f"正在搜索 '{query}'...")
            self.max_idx = 0
            self.worker = AsyncSearchWorker(query)
            self.worker.results_signal.connect(self.init_search_param)
            self.worker.start()
        else:
            self.search_results_list.addItem("请输入有效的搜索关键词。")

    def init_search_param(self, url, headers, result):
        self.search_url = url
        self.headers = headers
        self.display_results(result)

    def load_more_requested(self):
        #     https://weread.qq.com/api/store/search?keyword=java&sid=1GFF2LFhA0&scope=17&maxIdx=5&count=20
        url = f'{self.search_url}&scope={self.scope}&maxIdx={self.max_idx}&count=20'
        print(url)

        resp = requests.get(url, headers=self.headers)

        data = resp.json()
        has_more = data['hasMore']
        self.display_results(data)
        self.update_ui_for_results(has_more)


    def update_ui_for_results(self, has_more_pages):
        """
        供外部调用的方法，用于根据搜索结果状态更新 '加载更多' 按钮的可见性。

        :param has_more_pages: 布尔值，指示是否有下一页结果。
        """
        if has_more_pages:
            self.load_more_button.setText(f"加载更多结果 - {self.scope_count - self.max_idx} 本")
            self.load_more_button.show()
        else:
            self.load_more_button.hide()


    def display_results(self, results):
        """供外部调用的方法，用于显示搜索结果"""
        print(results)
        parts = results.get('parts', [])
        results = results.get('results', [])

        book_info = None
        books = []
        for t in results:
            if t['title'] == '电子书':
                book_info = t

        if book_info:
            books = book_info['books']
            self.search_idx = book_info['currentCount']
            self.scope = book_info['scope']
            self.scope_count = book_info['scopeCount']
            self.search_idx = book_info['currentCount']
            self.current_count = book_info['currentCount']
            self.type = book_info['type']
            self.max_idx = self.current_count + self.max_idx

            self.update_ui_for_results(self.current_count < self.scope_count)

        if not results:
            self.search_results_list.clear()
            self.search_results_list.addItem("未找到匹配的书籍。")
        else:
            book_util = WereadGenerate()
            for number, item in enumerate(books):
                # 确保数据结构正确，提取 bookInfo
                book_info = item.get('bookInfo', {})
                book_id = book_info['bookId']
                title = book_info.get('title', '无标题')
                author = book_info.get('author', '未知作者')
                # cover_url = book_info.get('cover', '')
                rating_count = book_info.get('newRatingCount', 0)

                book_info['bookHash'] = book_util.book_hash(book_info['bookId'])

                # 2. 创建 QListWidgetItem 容器
                list_item = QListWidgetItem(self.search_results_list)

                # 3. 创建 QWidget 作为自定义内容的容器
                item_widget = QWidget()

                # 4. 配置自定义项的布局 (QHBoxLayout: 封面 | 信息 | 按钮)
                item_layout = QHBoxLayout(item_widget)
                item_layout.setContentsMargins(5, 5, 5, 5)

                cover_label = QLabel()
                cover_label.setFixedSize(40, 60)  # 设置固定尺寸
                # 1. 使用占位符图片（如灰色或加载中图标）
                placeholder_pix = QPixmap(40, 60)
                placeholder_pix.fill(Qt.GlobalColor.lightGray)
                cover_label.setPixmap(placeholder_pix)

                # 2. 存储 QLabel 引用：等待异步更新
                self.cover_labels[book_id] = cover_label
                # 3. 异步启动下载 (非阻塞)
                cover_url = book_info.get('cover', '')
                if cover_url:
                    # ⚠️ 启动下载，使用 QMetaObject.invokeMethod 确保在 UI 线程执行
                    self.image_downloader.start_download(book_id, cover_url)
                item_layout.addWidget(cover_label)

                # --- B. 书籍信息 (用 QVBoxLayout 包裹) ---
                info_widget = QWidget()
                info_layout = QVBoxLayout(info_widget)
                info_layout.setSpacing(2)
                info_layout.setContentsMargins(0, 0, 0, 0)

                title_label = QLabel(f"<b>{title}</b>")
                author_label = QLabel(f"作者: {author}")
                rating_label = QLabel(f"评分人数: {rating_count}")

                # 2. 禁用自动换行（保持不变）
                # 确保文本不会自动换行，这是省略号生效的前提。
                title_label.setWordWrap(False)
                title_label.setMinimumWidth(100)  # 示例：设置一个最小宽度，让其受布局约束
                title_label.setMaximumWidth(200)  # 示例：设置一个最大宽度

                author_label.setWordWrap(False)
                author_label.setMinimumWidth(100)  # 示例：设置一个最小宽度，让其受布局约束
                author_label.setMaximumWidth(200)  # 示例：设置一个最大宽度

                info_layout.addWidget(title_label)
                info_layout.addWidget(author_label)
                info_layout.addWidget(rating_label)

                item_layout.addWidget(info_widget)
                item_layout.addStretch()  # 推开右侧部件

                # --- C. 操作按钮 (例如：下载或查看详情) ---
                # 打开按钮
                open_btn = QPushButton("打开")
                open_btn.clicked.connect(
                    lambda checked, bid=book_info["bookHash"]:
                        webbrowser.open("https://weread.qq.com/web/reader/" + bid)
                )

                fav_button = QPushButton("收藏本地")
                # 假设连接到一个处理搜索结果下载的槽函数
                fav_button.clicked.connect(lambda checked, book=book_info, btn=fav_button: self.on_fav_click(book, btn))
                fav_button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

                item_layout.addWidget(open_btn)
                item_layout.addWidget(fav_button)

                # 5. 关键步骤：设置 QListWidgetItem 的大小
                list_item.setSizeHint(item_widget.sizeHint())

                # 6. 关键步骤：将自定义 QWidget 设置为 QListWidgetItem 的内容
                self.search_results_list.setItemWidget(list_item, item_widget)

                print(f"{book_info['title']} - {book_info['author']}")
                # self.search_results_list.addItem(item)

    def on_fav_click(self, book, btn):
        self.favorite_signal.emit(book)

        btn.setEnabled(False)
        btn.setText('⭐ 已收藏')
        btn.setStyleSheet('''
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border: none;
                border-radius: 8px;
                padding: 6px 12px;
                font-size: 15px;
            }
            QPushButton:disabled {
                background-color: #8BC34A;
                color: #EEEEEE;
            }
        ''')

class BookshelfPageWidget(QWidget):
    """
    负责显示用户的书架列表内容的独立 QWidget (对应导航 Index 0)。
    """
    # ⚠️ 可以定义信号，例如用于在点击下载按钮时通知主窗口
    download_requested = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()
        self._setup_connections()

        books = load_my_books()

        self.book_list = books

        self.update_books(books)

    def _setup_ui(self):
        """初始化书架页面的所有 UI 元素和布局"""

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)

        # 页面标题
        # 注意：这里使用 H4 标签是为了保持和您原代码一致，实际 Qt UI 中推荐使用样式
        main_layout.addWidget(QLabel("<h4>微信书架</h4><hr>"))

        # --- 书籍列表 QListWidget ---
        self.book_list_widget = QListWidget()
        self.book_list_widget.setSelectionMode(QAbstractItemView.NoSelection)
        self.book_list_widget.setObjectName("book_list_widget")  # 方便调试或样式定制

        main_layout.addWidget(self.book_list_widget)

    def _setup_connections(self):
        """设置信号连接"""
        # (如果您的 QListWidget 是标准项，这里可以连接 itemClicked 等)
        pass

    @Slot(list)
    def update_books(self, book_list):
        """
        供外部（如 WeReadWindow）调用，用于清空并重新填充书架列表。
        """
        self.book_list_widget.clear()

        if not book_list:
            self.book_list_widget.addItem("书架为空，请尝试刷新。")
            return

        self.book_list_widget.addItem(f"总计找到 {len(book_list)} 本书籍。")

        for book in book_list:
            self._add_book_item(book)

    def _add_book_item(self, book):
        """
        创建并添加一个自定义的 QListWidgetItem 来显示书籍信息。
        """
        item = QListWidgetItem(self.book_list_widget)
        item_widget = QWidget()

        # 使用 QHBoxLayout 实现横向布局：封面 | 标题/作者 | 动作按钮
        item_layout = QHBoxLayout(item_widget)
        item_layout.setContentsMargins(5, 5, 5, 5)

        # --- 封面 ---
        cover = load_image(book.get('cover', ''), size=(40, 60))
        cover_label = QLabel()
        cover_label.setPixmap(cover)
        item_layout.addWidget(cover_label)

        # --- 信息 ---
        title = book.get('title', '未知书籍')
        author = book.get('author', '未知作者')
        info_label = QLabel(f"<b>{title}</b><br>作者: {author}")
        item_layout.addWidget(info_label)
        item_layout.addStretch()  # 推开右侧部件

        # --- 动作按钮 ---
        action_btn = QPushButton("下载本地")
        # ⚠️ 连接到局部槽函数，将书籍数据作为参数传递
        action_btn.clicked.connect(lambda checked, b=book: self._handle_download_click(b))
        action_btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        item_layout.addWidget(action_btn)

        # 绑定和设置大小
        item.setSizeHint(item_widget.sizeHint())
        self.book_list_widget.setItemWidget(item, item_widget)


    @Slot(dict)
    def _handle_download_click(self, book):
        """处理下载按钮点击，并通知主窗口"""
        print(f"用户请求下载书籍: {book.get('title')}")
        # 向上发射信号，让主窗口处理实际的下载逻辑
        self.download_requested.emit(book)


class FavoriteBookPageWidget(QWidget):
    """
    本地收藏的书架
    """
    # ⚠️ 可以定义信号，例如用于在点击下载按钮时通知主窗口
    download_requested = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()
        self._setup_connections()

        books = load_fav_books()

        self.book_list = books

        self.book_ids = set()

        self.update_books(books)

        self.toast = ToastNotification("", self)
        self.toast.hide()  # 默认隐藏

    def _setup_ui(self):
        """初始化书架页面的所有 UI 元素和布局"""

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)

        # 页面标题
        # 注意：这里使用 H4 标签是为了保持和您原代码一致，实际 Qt UI 中推荐使用样式
        main_layout.addWidget(QLabel("<h4>本地收藏</h4><hr>"))

        # --- 书籍列表 QListWidget ---
        self.book_list_widget = QListWidget()
        self.book_list_widget.setSelectionMode(QAbstractItemView.NoSelection)
        self.book_list_widget.setObjectName("book_list_widget")  # 方便调试或样式定制

        main_layout.addWidget(self.book_list_widget)

    def _setup_connections(self):
        """设置信号连接"""
        # (如果您的 QListWidget 是标准项，这里可以连接 itemClicked 等)
        pass

    @Slot(list)
    def update_books(self, book_list):
        """
        供外部（如 WeReadWindow）调用，用于清空并重新填充书架列表。
        """
        self.book_list_widget.clear()

        if not book_list:
            self.book_list_widget.addItem("书架为空，请尝试刷新。")
            return

        self.book_list_widget.addItem(f"总计找到 {len(book_list)} 本书籍。")

        for book in book_list:
            self._add_book_item(book)

    def _add_book_item(self, book):
        self.book_ids.add(book['bookId'])
        """
        创建并添加一个自定义的 QListWidgetItem 来显示书籍信息。
        """
        item = QListWidgetItem(self.book_list_widget)
        item_widget = QWidget()

        # 使用 QHBoxLayout 实现横向布局：封面 | 标题/作者 | 动作按钮
        item_layout = QHBoxLayout(item_widget)
        item_layout.setContentsMargins(5, 5, 5, 5)

        # --- 封面 ---
        cover = load_image(book.get('cover', ''), size=(40, 60))
        cover_label = QLabel()
        cover_label.setPixmap(cover)
        item_layout.addWidget(cover_label)

        # --- 信息 ---
        title = book.get('title', '未知书籍')
        author = book.get('author', '未知作者')
        info_label = QLabel(f"<b>{title}</b><br>作者: {author}")
        item_layout.addWidget(info_label)
        item_layout.addStretch()  # 推开右侧部件

        # --- 动作按钮 ---
        action_btn = QPushButton("加入下载")
        # ⚠️ 连接到局部槽函数，将书籍数据作为参数传递
        action_btn.clicked.connect(lambda checked, b=book, btn=action_btn: self._handle_download_click(b, btn))
        action_btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        item_layout.addWidget(action_btn)

        # 绑定和设置大小
        item.setSizeHint(item_widget.sizeHint())
        self.book_list_widget.setItemWidget(item, item_widget)


    @Slot(dict)
    def _handle_download_click(self, book, download_btn: "QPushButton"):
        """处理下载按钮点击，并通知主窗口"""
        print(f"用户请求下载书籍: {book.get('title')}")
        # 向上发射信号，让主窗口处理实际的下载逻辑
        self.download_requested.emit(book)
        download_btn.setEnabled(False)
        download_btn.setText('✅ 已添加')
        download_btn.setStyleSheet('''
            QPushButton {
                background-color: #4CAF50; 
                color: white; 
                border: 2px solid #4CAF50;
                border-radius: 5px; 
                padding: 5px 10px;
            }
            QPushButton:disabled {
                background-color: #f3ffee;
                color: #666666; 
                border: 2px solid #A5D6A7;
            }
        ''')

    @Slot(dict)
    def show_favorite_message(self, msg):
        self.toast.setText(msg)
        self.toast.show_notification(duration_ms=1500)

    def add_book(self, book):
        book_id = book['bookId']
        if not book_id in self.book_ids:
            self.show_favorite_message(f"已收藏《{book['title']}》")
            self.book_list.append(book)
            self._add_book_item(book)
            open(FAV_BOOK_SHELF_PATH, 'w', encoding='utf8').write(json.dumps(self.book_list, indent=4, ensure_ascii=False))
        else:
            self.show_favorite_message(f"❌ 已经收藏过")

class DownloadPageWidget(QWidget):
    """
    负责显示当前下载任务列表和进度的独立 QWidget。
    """

    def __init__(self, parent=None, ):
        super().__init__(parent)
        self.tasks = {}
        self.book_ids = set()
        self.books = load_local_books()

        set_book_is_download(self.books)

        self.item_layout_list = {}

        self.worker = AsyncDownloadWorker()
        self.worker.paused = True
        self.worker.start()

        self._setup_connections()

        self.toast = ToastNotification("", self)
        self.toast.hide()  # 默认隐藏

        self._setup_ui()

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.addWidget(QLabel("<h2>下载列表</h2><hr>"))

        # 任务列表
        self.list_widget = QListWidget()
        main_layout.addWidget(self.list_widget)

        self.display_books(self.books)

    def _setup_connections(self):
        """设置信号连接"""

        '''
            progress = Signal(int, str, int, int, dict)
            chapterTotal = Signal(int, int, dict)
            status = Signal(str, dict)
            show_progress = Signal(int, dict)
            update_book_signal = Signal(dict, )
        '''
        self.worker.progress.connect(self.update_progress)
        self.worker.chapterTotal.connect(self._update_bar_range)  # pbar.setRange
        # self.worker.status.connect()
        self.worker.show_progress.connect(self._update_bar_value)
        self.worker.update_book_signal.connect(self.update_books)

    def _update_bar_value(self, value, book):
        book_id = book['bookId']
        obj = self.item_layout_list[book_id]

        bar = obj['bar']
        bar.setValue(value)

    def _update_bar_range(self, start, value, book):
        book_id = book['bookId']
        obj = self.item_layout_list[book_id]

        bar:"QProgressBar" = obj['bar']
        bar.setVisible(True)
        bar.setRange(start, value)

        pause_btn: "QPushButton" = obj['pause_btn']
        pause_btn.setEnabled(True)
        pause_btn.setText('暂停')

    @Slot(str, int, int)
    def update_task_progress(self, task_id, current, total):
        """
        供外部信号连接，用于更新特定任务的进度。
        (实际应用中，您可能需要更复杂的 QListWidgetItem 来嵌入 QProgressBar)
        """
        # 演示：只更新 QListWidget 的一个普通项
        print(f"更新任务 {task_id}: {current}/{total}")
        # 实际代码会涉及遍历 self.task_list 找到对应项并更新
        pass

    # 更新进度条
    def update_progress(self, status: int, msg: str, offset, total, book):
        item_layout = self.item_layout_list[book["bookId"]]
        # 获取进度条
        bar = item_layout['bar']
        # 获取暂停按钮
        pause_btn = item_layout['pause_btn']
        # 获取导出按钮
        export_btn = item_layout['export_btn']
        # 获取状态标签
        status_label = item_layout['status_label']

        if status == 1:
            status_label.setText(f'完成')
            status_label.setStyleSheet("color: green;")
            bar.setValue(total)
            self._update_bar_status(bar, 1)

            export_btn.setEnabled(True)
            pause_btn.setEnabled(False)

        elif status == 0:
            bar.setValue(offset)
            status_label.setText(f'{offset} / {total}')
            status_label.setStyleSheet("color: gray; font-size: 12px;")
            self._update_bar_status(bar, 0)

        elif status == 2:
            status_label.setText(f'{offset} / {total} - {msg}')
            status_label.setStyleSheet("color: orange;")
            self._update_bar_status(bar, 2)

        else:
            bar.setValue(offset)
            status_label.setText(f'{offset} / {total} - {msg}')
            status_label.setStyleSheet("color: red;")
            # download_btn.setEnabled(True)
            pause_btn.setEnabled(False)
            self._update_bar_status(bar, -1)

    def _update_bar_status(self, bar, status, ):
        if status == 1:  # 下载成功
            color = "#22c55e"
        elif status == 2:  # 暂停
            color = "#fbbf24"
        elif status == -1:  # 失败
            color = "#ef4444"
        else:  # 下载中
            color = "#2371ed"

        bar.setStyleSheet(f"""
            QProgressBar {{
                text-align: center;   /* 文本水平居中 */
                border: 0.8px solid #dcdcdc;      /* 边框颜色 */
                border-radius: 4px;          /* 圆角 */
                background-color: #dcdcdc;   /* 背景色 */
                text-align: center;          /* 百分比文本居中 */
                max-height: 10px;
            }}

            QProgressBar::chunk {{
                background-color: {color};
            }}
        """)

    def add_book(self, book):
        if book['bookId'] not in self.book_ids:
            self.show_favorite_message(f'添加到下载队列')
            self.books.append(book)
            self.book_ids.add(book['bookId'])

            set_book_is_download(self.books)
            self._save_to_json()
            self._add_item(book, len(self.books))

        else:
            self.show_favorite_message(f'❌ 已添加过')

    def show_favorite_message(self, msg):
        self.toast.setText(msg)
        self.toast.show_notification(duration_ms=1500)

    def _save_to_json(self):
        open(LOCAL_BOOK_SHELF_PATH, 'w', encoding='utf8').write(json.dumps(self.books, ensure_ascii=False, indent=4))

    def display_books(self, book_list,):

        # 1. 清空现有的所有列表项 (QListWidgetItem)
        self.list_widget.clear()

        if not book_list:
            self.list_widget.addItem("书架为空，请尝试刷新。")
            return

        if self.tasks:
            self.tasks.clear()

        # 添加总数提示
        self.list_widget.addItem(f"下载列队 {len(book_list)} 本书籍。")

        for number, book in enumerate(book_list):
            self._add_item(book, number)

    def _add_item(self, book, number):
        book_id = book["bookId"]
        self.book_ids.add(book_id)
        pix = load_image(book=book)
        item = QListWidgetItem()
        item_widget = QWidget()
        item_layout = QVBoxLayout(item_widget)
        # 上排 = 图片 + 标题 + 按钮区
        img_label = QLabel()
        img_label.setPixmap(pix)
        title_label = QLabel(book["title"])
        title_label.setWordWrap(True)
        title_label.setStyleSheet("font-size: 14px; font-weight: bold;")

        pause_btn = QPushButton("暂停")
        pause_btn.setEnabled(False)
        pause_btn.setMaximumWidth(50)
        pause_btn.clicked.connect(lambda btn=pause_btn: self.toggle_pause(pause_btn))

        export_btn = QPushButton("导出")
        export_btn.setEnabled(False)
        export_btn.setMaximumWidth(50)
        # 点击导出 → 弹 dialog
        export_btn.clicked.connect(lambda b, bid=book["bookId"]: self.open_export_dialog(bid))

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

            self._update_bar_status(progress, 1)

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
                self._update_bar_status(progress, 2)

                status_label.setText(f'{download_progress} / {max_val} 暂停...')
                status_label.setStyleSheet("color: orange; font-size: 12px;")

                pause_btn.setEnabled(True)
                pause_btn.setText('继续')

                # self.update_progress(book,)
            else:
                progress.setVisible(False)

        # 上排 = 图片 + 标题 + 按钮区
        row = QHBoxLayout()
        img_label = QLabel()
        img_label.setPixmap(pix)
        title_label = QLabel(book["title"])
        title_label.setWordWrap(True)
        # 按钮竖排布局
        btn_column = QHBoxLayout()
        # btn_column.addWidget(open_btn)
        # btn_column.addWidget(download_btn)
        btn_column.addWidget(pause_btn)
        btn_column.addWidget(export_btn)
        btn_column.addStretch()

        number_label = QLabel(f'{number + 1}. ')
        row.addWidget(number_label, 0)
        row.addWidget(img_label, 0)
        row.addWidget(title_label, 10)
        # 把按钮竖排添加进去
        row.addLayout(btn_column, 0)
        status_row = QHBoxLayout()
        status_row.addWidget(status_label, 0)
        status_row.addWidget(progress, 10)
        item_layout.addLayout(row)
        item_layout.addLayout(status_row)
        item.setSizeHint(item_widget.sizeHint())
        self.list_widget.addItem(item)
        self.list_widget.setItemWidget(item, item_widget)

        self.item_layout_list[book_id] = {
            'bar': progress, 'pause_btn': pause_btn, 'export_btn': export_btn, 'status_label': status_label
        }
        self.worker.add_task(book)

    def bind_download(self, download_btn, pause_btn, export_btn, pbar, slabel, book, invoke=True):

        def start_download():
            download_btn.setEnabled(False)
            pbar.setVisible(True)
            pause_btn.setEnabled(True)

            worker = AsyncDownloadWorker(book, )
            if invoke:
                # 🚀 创建真正的异步下载任务
                worker.start()
                worker.paused = True

            self.tasks.update({
                book['bookId']: worker
            })

            # 暂停按钮
            pause_btn.clicked.connect(lambda: self.toggle_pause(worker, pause_btn))

            # 状态文本（用于 开始下载 / 完成 / 暂停 / 失败）
            def on_done(success):
                download_btn.setEnabled(True)
                pause_btn.setEnabled(False)
                if success:
                    export_btn.setEnabled(True)

            # 设置总章节数
            worker.chapterTotal.connect(pbar.setRange)

            # 设置当前进度
            worker.progress.connect(
                lambda status, msg, curr, total, :
                self.update_progress(download_btn, pause_btn, export_btn, pbar, slabel, status, msg, curr, total)
            )
            worker.show_progress.connect(pbar.setValue)

            worker.update_book_signal.connect(self.update_books)

        return start_download

    def toggle_pause(self, pause_btn,):

        if not self.worker.paused:
            # 暂停
            self.worker.pause()
            pause_btn.setText("继续")
        else:
            pause_btn.setText("暂停")
            # 继续
            self.worker.resume()


    def update_books(self, book):
        self._save_to_json()


    def open_export_dialog(self, book_id):
        dlg = ExportDialog(self, book_id=book_id)
        dlg.exec()


# =========================================
# 主窗口
# =========================================
class WeReadWindow(QMainWindow):

    def __init__(self, user_data):
        super().__init__()
        self.user_data = user_data
        self.book_util = WereadGenerate()
        # self.book_list = book_list
        self.tasks = {}
        self.loading_dialog = None

        self.setWindowTitle("WeRead 书架-试用版 - beat")
        self.resize(800, 800)

        # ----------------------------------
        # 1. 创建菜单栏
        # ----------------------------------
        self._create_menu_bar()

        # 2. 设置中心部件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # 3. 创建主水平布局 (新的顶层布局：左侧导航 | 右侧内容)
        main_hbox = QHBoxLayout(central_widget)
        main_hbox.setContentsMargins(0, 0, 0, 0)

        # ----------------------------------
        # A. 左侧：导航栏 (Navigation Pane)
        # ----------------------------------
        self._create_navigation_pane(main_hbox)

        # ----------------------------------
        # B. 右侧：堆叠内容区 (Stacked Content)
        # ----------------------------------
        self.stacked_widget = QStackedWidget()
        main_hbox.addWidget(self.stacked_widget)

        #  搜索页面 (Index 2) -> 使用独立类
        self.search_page = SearchPageWidget()
        # ⚠️ 可选：将搜索请求信号连接到主窗口的处理方法
        self.search_page.favorite_signal.connect(self.handle_global_favorite)
        self.stacked_widget.addWidget(self.search_page)

        # 我的书架
        bookshelf_page = BookshelfPageWidget()
        self.stacked_widget.addWidget(bookshelf_page)  # Index 2

        self.favorite_page = FavoriteBookPageWidget()
        self.stacked_widget.addWidget(self.favorite_page)  # Index 3

        # 下载列表页面 (Index 1) -> 使用独立类
        self.download_page = DownloadPageWidget()
        self.stacked_widget.addWidget(self.download_page)

        bookshelf_page.download_requested.connect(self.download_page.add_book)
        self.favorite_page.download_requested.connect(self.download_page.add_book)

        # 4. 初始化和连接导航
        self._setup_navigation_connection()

    def _create_menu_bar(self):
        """创建和配置菜单栏"""
        menu_bar = self.menuBar()  # 获取 QMainWindow 的菜单栏

        # --- 文件菜单 (File Menu) ---
        file_menu = menu_bar.addMenu("文件(&F)")  # &F 表示 Alt+F 快捷键

        # 退出动作
        exit_action = QAction("退出(&X)", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.setStatusTip("退出应用程序")
        exit_action.triggered.connect(self.close)  # 连接到窗口关闭方法

        file_menu.addAction(exit_action)

        # --- 设置菜单 (Settings Menu) ---
        settings_menu = menu_bar.addMenu("设置(&S)")

        # 登录信息动作
        info_action = QAction("查看登录信息", self)
        info_action.triggered.connect(self.show_login_info)

        settings_menu.addAction(info_action)

        # ----------------------------------
        # --- 新增：工具菜单 (Tools Menu) ---
        # ----------------------------------
        tools_menu = menu_bar.addMenu("工具(&T)")

        # 刷新书架动作
        refresh_action = QAction("刷新书架", self)
        refresh_action.setShortcut("F5")
        refresh_action.setStatusTip("重新从微信读书加载书架数据")
        # ⚠️ 连接到 WeReadWindow 中的刷新槽函数
        refresh_action.triggered.connect(self.refresh_bookshelf)

        tools_menu.addAction(refresh_action)
        # ----------------------------------

        # --- 帮助菜单 (Help Menu) ---
        help_menu = menu_bar.addMenu("帮助(&H)")

        about_action = QAction("关于...", self)
        about_action.triggered.connect(self.show_about_dialog)

        help_menu.addAction(about_action)

    def _create_navigation_pane(self, parent_layout):
        """创建左侧导航栏：用户区 + 导航列表"""

        nav_widget = QWidget()
        nav_widget.setMaximumWidth(150)  # 稍微加宽
        nav_layout = QVBoxLayout(nav_widget)
        nav_layout.setContentsMargins(10, 10, 10, 10)

        # --- 用户信息区域 ---
        user_box = QHBoxLayout()
        avatar = load_image(self.user_data.get("avatar", ''), size=(40, 40))
        avatar_label = QLabel()
        avatar_label.setPixmap(avatar)

        info_label = QLabel(
            f"<b>{self.user_data.get('name', 'N/A')}</b><br>"
            # f"<small>UserVid: {self.user_data.get('userVid', 'N/A')}</small>"
        )
        user_box.addWidget(avatar_label)
        user_box.addWidget(info_label)
        nav_layout.addLayout(user_box)
        nav_layout.addSpacing(15)

        # --- 导航列表 ---
        self.nav_list = QListWidget()
        self.nav_list.setFont(QFont('Arial', 12))
        self.nav_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.nav_list.setMinimumHeight(120)

        # 导航项 (与 QStackedWidget 索引对应)
        self.nav_list.addItem("🔍 搜索")  # Index 0
        self.nav_list.addItem("📚 我的书架")  # Index 1
        self.nav_list.addItem("💾 本地收藏")  # Index 2
        self.nav_list.addItem("⬇️ 下载列表")  # Index 3

        self.nav_list.setCurrentRow(0)

        nav_layout.addWidget(self.nav_list)
        nav_layout.addStretch()

        parent_layout.addWidget(nav_widget)

    def _setup_navigation_connection(self):
        """连接导航列表和堆叠内容区"""
        self.nav_list.currentRowChanged.connect(self.stacked_widget.setCurrentIndex)

    def handle_global_favorite(self, book):
        print(book)
        self.favorite_page.add_book(book)

    def show_login_info(self):
        """显示登录信息的槽函数"""
        info = (
            f"用户名: {self.user_data.get('name')}\n"
            f"UserVid: {self.user_data.get('userVid')}\n"
            "您已成功登录。"
        )
        QMessageBox.information(self, "登录信息", info)

    def show_about_dialog(self):
        """显示关于对话框的槽函数"""
        QMessageBox.about(
            self,
            "关于 WeRead 书架",
            "这是一个基于 PySide6 的微信读书书架管理工具。"
        )

    def refresh_bookshelf(self):
        """
                触发重新加载书架数据的逻辑，并在 QThread 中执行
                """
        print("--- 刷新书架动作被触发 ---")

        # 1. 创建并配置加载对话框 (QProgressDialog 适合加载)
        self.loading_dialog = QProgressDialog(
            "正在重新加载书架数据，请稍候...",
            None,  # 不显示取消按钮文本
            0, 0,  # 设置为不确定进度条
            self
        )
        self.loading_dialog.setWindowTitle("刷新中")
        self.loading_dialog.setWindowModality(Qt.ApplicationModal)
        self.loading_dialog.setMinimumDuration(0)

        # 禁用关闭按钮 (X)，并自定义窗口边框
        self.loading_dialog.setWindowFlags(
            self.loading_dialog.windowFlags() & ~Qt.WindowCloseButtonHint
            | Qt.CustomizeWindowHint
        )
        self.loading_dialog.show()

        # 2. 创建并启动异步工作线程
        self.async_worker = LoginAsyncWorker()
        self.async_worker.finished.connect(self.on_refresh_finished)
        self.async_worker.books_signal.connect(self.display_books)
        self.async_worker.start()

    def on_refresh_finished(self):
        """
        异步任务完成时，在主线程中执行的槽函数
        """
        # 1. 自动关闭加载对话框
        if self.loading_dialog:
            self.loading_dialog.close()
            self.loading_dialog = None

        # 2. 启用刷新按钮
        # self.findChild(QAction, "refresh_action").setEnabled(True)

        # 3. 显示结果和更新 UI
        QMessageBox.information(self, "完成", "书架数据已成功刷新！")


    def closeEvent(self, event):
        # asyncio.get_event_loop().create_task(self.cleanup())
        # event.accept()
        pass


def load_user_info():
    if os.path.exists('user_info.json'):
        t = open('user_info.json', 'r', encoding='utf8').read()
        if t:
            return json.loads(t)

    return {}

def weread_main():
    app = QApplication(sys.argv)  # pyside6

    print("starting login...")

    window = None
    user_data = asyncio.run(login_weread())  # 如果需要

    user_data = load_user_info()

    def start_app(r):
        nonlocal window
        print('start app..')
        if r:
            window = WeReadWindow(user_data, )
            window.show()
        else:
            QMessageBox.warning(None, "完成", "数据加载失败！关闭程序。")

    # 实例化主窗口，加载过程会自动开始
    main_window = DataLoadWindow([])

    main_window.loaded_signal.connect(start_app)

    sys.exit(app.exec())


if __name__ == '__main__':
    print("init loop")
    weread_main()
