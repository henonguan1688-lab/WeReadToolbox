import asyncio
import sys
import time
import random

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import QApplication, QWidget, QVBoxLayout, QProgressBar


async def task(worker):
    worker.a.emit(random.Random().randint(0, 15))
    await asyncio.sleep(.5)

    return random.Random().random()

class A(QThread):

    a = Signal(int)  # 注意这里要写成 tuple
    init_bar = Signal(int, int,)

    def __init__(self, ):
        super().__init__()
        self.running = True

    def stop(self):
        self.running = False

    def run(self):
        # i = 1
        self.init_bar.emit(0, 15)

        while self.running:

            r = asyncio.run(task(self,))
            print(f'信号：{r}')
            # i += 1

            # self.a.emit(i)


class Demo(QWidget):
    def __init__(self):
        super().__init__()
        print('init...')
        self.setWindowTitle("ProgressBar Demo")

        self.layout = QVBoxLayout(self)


        self.bars = []
        self.workers = []
        for i in range(10):

            pbar = QProgressBar()
            pbar.setFormat("%p%")          # 显示百分比文本
            pbar.setTextVisible(True)

            worker = A()
            worker.a.connect(pbar.setValue)
            worker.init_bar.connect(pbar.setRange)
            worker.start()
            print(f'启动线程-{i}')

            self.layout.addWidget(pbar)

            self.bars.append(pbar)
            self.workers.append(worker)

        # self.pbar2 = QProgressBar()
        # self.pbar2.setFormat("%p%")          # 显示百分比文本
        # self.pbar2.setTextVisible(True)
        #
        # self.layout.addWidget(self.pbar2)
        #
        #
        # self.worker2 = A()
        # self.worker2.a.connect(self.pbar2.setValue)
        # self.worker2.init_bar.connect(self.pbar2.setRange)
        # self.worker2.start()
        # print('启动线程2')

    def closeEvent(self, event):
        """窗口关闭时停止所有线程"""
        print("停止所有线程...")
        for w in self.workers:
            w.stop()
            w.wait()
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = Demo()
    w.show()
    sys.exit(app.exec())
