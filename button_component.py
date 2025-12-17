import sys
from PySide6.QtWidgets import QApplication, QWidget, QVBoxLayout, QPushButton
from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor
from PySide6.QtCore import QSize, Qt


class BootstrapButton(QPushButton):
    def __init__(self, text="", icon_path=None, variant="primary", outline=False, parent=None):
        super().__init__(text, parent)

        self.variant = variant
        self.outline = outline
        self.icon_path = icon_path

        # 颜色定义
        self.colors = {
            "primary":   ("#0d6efd", "#0b5ed7", "#0a58ca"),
            "secondary": ("#6c757d", "#5c636a", "#565e64"),
            "success":   ("#198754", "#157347", "#146c43"),
            "info":      ("#0dcaf0", "#31d2f2", "#2dc9ee"),
            "warning":   ("#ffc107", "#ffca2c", "#ffb300"),
            "danger":    ("#dc3545", "#bb2d3b", "#b02a37"),
            "light":     ("#f8f9fa", "#f9fafb", "#f2f2f2"),
            "dark":      ("#212529", "#1c1f23", "#191c1f"),
        }

        bg, hover_bg, pressed_bg = self.colors.get(self.variant, self.colors["primary"])

        # 根据变体决定默认图标颜色
        if self.outline:
            default_icon_color = bg  # outline 时图标跟随主题色
        else:
            default_icon_color = "white"  # 实心按钮默认白色图标

        # 设置图标（如果提供路径）
        if icon_path:
            tinted_icon = self.tint_svg_icon(icon_path, default_icon_color)
            self.setIcon(tinted_icon)
            self.setIconSize(QSize(16, 16))

        # 应用样式
        self.apply_style()

    def tint_svg_icon(self, svg_path: str, color_str: str) -> QIcon:
        """将 SVG 图标染成指定颜色"""
        pixmap = QPixmap(svg_path)
        if pixmap.isNull():
            return QIcon()

        # 创建同大小的可编辑 pixmap
        tinted = QPixmap(pixmap.size())
        tinted.fill(Qt.GlobalColor.transparent)

        painter = QPainter(tinted)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        painter.drawPixmap(0, 0, pixmap)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
        painter.fillRect(tinted.rect(), QColor(color_str))
        painter.end()

        return QIcon(tinted)

    def apply_style(self):
        bg, hover_bg, pressed_bg = self.colors.get(self.variant, self.colors["primary"])

        if self.outline:
            stylesheet = f"""
                QPushButton {{
                    background-color: transparent;
                    color: {bg};
                    border: 0.5px solid {bg};
                    border-radius: 6px;
                    padding: .2em .3em;
                    font-weight: 500;
                }}
                QPushButton:hover {{
                    background-color: {bg};
                    color: white;
                }}
                QPushButton:pressed {{
                    background-color: {pressed_bg};
                    color: white;
                    border-color: {pressed_bg};
                }}
                QPushButton:disabled {{
                    color: #6c757d;
                    border-color: #6c757d;
                    background-color: transparent;
                }}
            """
        else:
            stylesheet = f"""
                QPushButton {{
                    background-color: {bg};
                    color: white;
                    border: none;
                    border-radius: 6px;
                    padding: .5em .7em;
                    font-weight: 500;
                }}
                QPushButton:hover {{
                    background-color: {hover_bg};
                }}
                QPushButton:pressed {{
                    background-color: {pressed_bg};
                }}
                QPushButton:disabled {{
                    background-color: {pressed_bg};     /* 主题色的最深变体 */
                    color: rgba(255, 255, 255, 0.75);
                    opacity: 0.9;
                }}
            """

        self.setStyleSheet(stylesheet)

        # 动态更新图标颜色（尤其是 outline + hover）
        if self.icon_path:
            if self.outline and self.underMouse():  # hover 时
                icon_color = "white"
            elif self.outline:
                icon_color = bg
            else:
                icon_color = "white"

            tinted_icon = self.tint_svg_icon(self.icon_path, icon_color)
            self.setIcon(tinted_icon)

    # ========== 新增切换图标方法 ==========
    def toggle_icon(self, new_icon_path=None, variant=None, toggle_visibility=None):
        """
        切换按钮图标
        :param new_icon_path: 新图标路径（可选），不传则切换当前图标的显示/隐藏状态
        :param toggle_visibility: 强制设置图标可见性（True/False），优先级高于自动切换
        """
        # 1. 如果传入新图标路径，更新图标
        if new_icon_path is not None:
            self.icon_path = new_icon_path
            self._original_icon_path = new_icon_path
            self._icon_visible = True  # 更换图标时默认显示
        # 2. 控制图标可见性
        if toggle_visibility is not None:
            self._icon_visible = toggle_visibility
        else:
            # 未指定则自动切换显示/隐藏状态
            if self.icon_path:
                self._icon_visible = not self._icon_visible

        if variant:
            self.variant = variant

        # 3. 更新图标显示
        self.apply_style()

    def enterEvent(self, event):
        super().enterEvent(event)
        self.apply_style()  # hover 时更新图标颜色（outline 变体）

    def leaveEvent(self, event):
        super().leaveEvent(event)
        self.apply_style()  # 离开时恢复

if __name__ == '__main__':

# 示例应用
    app = QApplication(sys.argv)

    window = QWidget()
    window.setWindowTitle("自定义 Bootstrap 风格按钮示例")
    layout = QVBoxLayout(window)

    # 各种按钮示例（假设你有图标文件，如 save.svg, delete.svg 等）
    layout.addWidget(BootstrapButton("Primary 按钮", "icons/save.svg", variant="primary"))

    b2 = BootstrapButton("Primary 按钮", "icons/save.svg", variant="primary")
    b2.setEnabled(False)
    layout.addWidget(b2)

    b3 = BootstrapButton("warning 按钮", "icons/save.svg", variant="warning")
    layout.addWidget(b3)

    b4 = BootstrapButton("warning 按钮", "icons/save.svg", variant="warning")
    b4.setEnabled(False)
    layout.addWidget(b4)

    def a(p, btn:BootstrapButton):
        print('btn clicked.')
        btn.toggle_icon(p)


    b5 = BootstrapButton("warning 按钮", "icons/pause.svg", variant="warning", outline=True)
    b5.clicked.connect(lambda b, p='icons/play.svg', btn=b5: a(p, btn))
    layout.addWidget(b5)

    b6 = BootstrapButton("warning 按钮", "icons/pause.svg", variant="warning", outline=True)
    b6.setEnabled(False)
    layout.addWidget(b6)

    layout.addWidget(BootstrapButton("Success 按钮", "icons/check.svg", variant="success"))
    layout.addWidget(BootstrapButton("Danger 按钮", "icons/trash.svg", variant="danger"))


    layout.addWidget(BootstrapButton("Outline Primary", "icons/pencil-square.svg", variant="primary", outline=True))

    o1 = BootstrapButton("Outline Primary", "icons/pencil-square.svg", variant="primary", outline=True)
    layout.addWidget(o1)

    o2 = BootstrapButton("Outline Primary", "icons/pencil-square.svg", variant="primary", outline=True)
    o2.setEnabled(False)
    layout.addWidget(o2)

    layout.addWidget(BootstrapButton("", "icons/house.svg", variant="secondary"))

    window.show()
    sys.exit(app.exec())