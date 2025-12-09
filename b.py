import sys
import webbrowser
from PySide6.QtWidgets import (
    QApplication, QWidget, QListWidget, QListWidgetItem,
    QLabel, QPushButton, QVBoxLayout, QHBoxLayout,
    QProgressBar
)
from PySide6.QtGui import QPixmap
from PySide6.QtCore import Qt


def load_image(book):
    pix = QPixmap(80, 100)
    pix.fill(Qt.lightGray)
    return pix


class BookListDemo(QWidget):

    def __init__(self, book_list):
        super().__init__()

        self.setWindowTitle("PySide6 Book List Demo")
        self.resize(700, 500)

        layout = QVBoxLayout(self)

        self.list_widget = QListWidget()
        layout.addWidget(self.list_widget)

        for book in book_list:
            self.add_book_item(book)

    def add_book_item(self, book):

        item = QListWidgetItem()
        item_widget = QWidget()

        # ⭐ 最外层竖向布局：上内容行 + 下状态行
        outer = QVBoxLayout(item_widget)
        outer.setContentsMargins(10, 10, 10, 10)
        outer.setSpacing(6)

        # ==================================================
        # 第一行：左图 | 中间（标题+进度条） | 右按钮列
        # ==================================================
        content_row = QHBoxLayout()
        content_row.setSpacing(12)

        # 左侧封面
        pix = load_image(book)
        img_label = QLabel()
        img_label.setPixmap(pix)
        img_label.setAlignment(Qt.AlignCenter)
        content_row.addWidget(img_label)

        # 中间布局：标题 + 进度条
        # mid_layout = QVBoxLayout()
        # mid_layout.setSpacing(5)

        title_label = QLabel(book["title"])
        title_label.setWordWrap(True)
        title_label.setStyleSheet("font-size: 14px; font-weight: bold;")
        # mid_layout.addWidget(title_label)

        progress = QProgressBar()
        progress.setFormat("%p%")
        progress.setValue(50)
        progress.setStyleSheet(f"""
               QProgressBar::chunk {{
                   background-color: blue;
               }}
               """)
        # mid_layout.addWidget(progress)

        # mid_layout.addStretch()
        content_row.addWidget(title_label, stretch=1)

        # 右侧按钮竖排
        btn_col = QVBoxLayout()
        btn_col.setSpacing(6)

        open_btn = QPushButton("打开")
        open_btn.clicked.connect(
            lambda _, bh=book["bookHash"]:
            webbrowser.open("https://weread.qq.com/web/reader/" + bh)
        )
        btn_col.addWidget(open_btn)

        download_btn = QPushButton("下载")
        download_btn.clicked.connect(lambda _, b=book: self.download_book(b))
        btn_col.addWidget(download_btn)

        pause_btn = QPushButton("暂停")
        pause_btn.setEnabled(False)
        btn_col.addWidget(pause_btn)

        export_btn = QPushButton("导出")
        export_btn.setEnabled(False)
        export_btn.clicked.connect(
            lambda _, bid=book["bookId"]: self.open_export_dialog(bid)
        )
        btn_col.addWidget(export_btn)

        btn_col.addStretch()
        content_row.addLayout(btn_col)

        # 添加第一行（主要内容）
        outer.addLayout(content_row)

        # ==================================================
        # 第二行：状态（单独占一整行）
        # ==================================================



        status_label = QLabel("未下载")
        status_label.setStyleSheet("color: #666; font-size: 12px;")
        outer.addWidget(progress)
        outer.addWidget(status_label)

        # 设置列表项
        item.setSizeHint(item_widget.sizeHint())
        self.list_widget.addItem(item)
        self.list_widget.setItemWidget(item, item_widget)

    def download_book(self, book):
        print("开始下载:", book["title"])

    def open_export_dialog(self, book_id):
        print("打开导出对话框，bookId =", book_id)


# 运行示例
if __name__ == "__main__":

    fake_books = [
        {"title": "三体", "bookId": "1001", "bookHash": "hash_001"},
        {"title": "雪中悍刀行", "bookId": "1002", "bookHash": "hash_002"},
        {"title": "人类简史", "bookId": "1003", "bookHash": "hash_003"},
    ]

    app = QApplication(sys.argv)
    w = BookListDemo(fake_books)
    w.show()
    sys.exit(app.exec())
