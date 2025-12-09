import os
import sys

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QPushButton, QDialog,
    QRadioButton, QGroupBox, QHBoxLayout, QPlainTextEdit,
    QButtonGroup
)

from text_to_epub import EpubBuilder, MarkdownBuilder, PdfBuilder


# class ExportDialog(QDialog):
#
#     def __init__(self, parent=None, book_id=None):
#         super().__init__(parent)
#         self.setWindowTitle("导出文件")
#         self.resize(900, 500)
#         self.book_id = book_id
#         layout = QVBoxLayout(self)
#
#         # === 导出类型单选区域 ===
#         type_box = QGroupBox("导出类型")
#         type_layout = QHBoxLayout()
#
#         self.radio_group = QButtonGroup(self)
#         self.radio_pdf = QRadioButton("PDF")
#         self.radio_md = QRadioButton("MD")
#         self.radio_txt = QRadioButton("TXT")
#         self.radio_epub = QRadioButton("EPUB")
#
#         self.radio_group.addButton(self.radio_pdf)
#         self.radio_group.addButton(self.radio_md)
#         self.radio_group.addButton(self.radio_txt)
#         self.radio_group.addButton(self.radio_epub)
#
#         self.radio_pdf.setChecked(True)
#
#         type_layout.addWidget(self.radio_pdf)
#         type_layout.addWidget(self.radio_md)
#         type_layout.addWidget(self.radio_txt)
#         type_layout.addWidget(self.radio_epub)
#
#         type_box.setLayout(type_layout)
#         layout.addWidget(type_box)
#
#         # === 日志窗口 ===
#         self.log_area = QPlainTextEdit()
#         self.log_area.setReadOnly(True)
#         self.log_area.setPlaceholderText("下载资源日志...")
#         layout.addWidget(self.log_area)
#
#         # === 按钮区域 ===
#         btn_layout = QHBoxLayout()
#
#         self.open_folder_btn = QPushButton("打开输出文件夹")
#         self.start_export_btn = QPushButton("开始导出")
#
#         btn_layout.addWidget(self.open_folder_btn)
#         btn_layout.addStretch()
#         btn_layout.addWidget(self.start_export_btn)
#
#         layout.addLayout(btn_layout)
#
#         # 信号绑定
#         self.open_folder_btn.clicked.connect(self.open_output_folder)
#         self.start_export_btn.clicked.connect(self.start_export)
#
#         # 默认输出目录
#         self.output_dir = os.path.join(os.getcwd(), f"books/{book_id}")
#         os.makedirs(self.output_dir, exist_ok=True)
#
#     def open_output_folder(self):
#
#         if hasattr(self, 'file_path'):
#
#             file_path = self.output_file  # 你生成的 epub 路径
#         else:
#             file_path = os.path.join(self.output_dir, "chapters")
#         if not os.path.exists(file_path):
#             return
#
#         # Windows 上打开文件所在目录并选中该文件
#         QDesktopServices.openUrl(
#             QUrl.fromLocalFile(os.path.dirname(file_path))
#         )
#
#
#     def start_export(self):
#         export_type = self.get_export_type()
#         self.log_area.appendPlainText(f"开始导出: {export_type}")
#
#         self.builder = None
#         if export_type == 'epub':
#             self.builder = EpubBuilder(book_id=self.book_id, )
#
#         elif export_type == 'md':
#             self.builder = MarkdownBuilder(book_id=self.book_id, )
#
#         elif export_type == 'txt':
#             pass
#
#         elif export_type == 'pdf':
#             self.builder = PdfBuilder(book_id=self.book_id, )
#
#         else:
#             raise ''
#
#         self.output_file = self.builder.file_name
#         self.builder.msg.connect(self.log_area.appendPlainText)
#         self.builder.start()
#
#
#
#     def get_export_type(self):
#         if self.radio_pdf.isChecked():
#             return "pdf"
#         if self.radio_md.isChecked():
#             return "md"
#         if self.radio_txt.isChecked():
#             return "txt"
#         if self.radio_epub.isChecked():
#             return "epub"
#         return "txt"

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QGroupBox, QHBoxLayout,
    QButtonGroup, QRadioButton, QPlainTextEdit, QPushButton, QMessageBox
)
from PySide6.QtCore import Qt

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
            pass
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
