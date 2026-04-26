from pathlib import Path
import re

p = Path(r"c:\Users\Lu\Desktop\新建文件夹 (5)\l_bridge_tool_gui.py")
s = p.read_text(encoding="utf-8", errors="replace")

def replace_class(src, name, new):
    m = re.search(rf"^class {name}\b[\s\S]*?(?=^class |\Z)", src, re.M)
    if not m:
        raise RuntimeError(f"找不到 class {name}")
    return src[:m.start()] + new.rstrip() + "\n\n" + src[m.end():]

def replace_method(src, name, new):
    m = re.search(rf"^    def {name}\b[\s\S]*?(?=^    def |\nclass |\Z)", src, re.M)
    if not m:
        raise RuntimeError(f"找不到 def {name}")
    return src[:m.start()] + new.rstrip() + "\n\n" + src[m.end():]

new_capture_template = r'''
    def capture_template(self, template_type):
        template_map = {
            "input": ("input_box_template.png", "编程工具输入框"),
            "send": ("send_button_template.png", "编程工具发送按钮"),
            "delete": ("delete_popup.png", "删除/确认按钮"),
            "sandbox": ("sandbox_button.png", "后台沙箱按钮"),
            "coder_copy": ("coder_copy_button.png", "编程工具复制结果按钮"),
            "gpt_input": ("gpt_input_box.png", "ChatGPT 输入框"),
            "gpt_send": ("gpt_send_button.png", "ChatGPT 发送按钮"),
        }
        if template_type not in template_map:
            self.log(f"未知模板类型: {template_type}")
            self.set_error(f"未知模板类型: {template_type}")
            return

        template_name, label = template_map[template_type]
        try:
            reply = QtWidgets.QMessageBox.question(
                self, "采集模板",
                f"准备采集：{label}\n\n确认后 L 会隐藏并截图，然后在截图窗口里框选区域。",
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No
            )
            if reply != QtWidgets.QMessageBox.Yes:
                self.log(f"采集已取消: {label}")
                return

            self.log(f"准备采集 {template_name}，当前配置: {profile_manager.current_profile}")
            self.hide()
            QtWidgets.QApplication.processEvents()
            time.sleep(0.8)

            screenshot = capture_screen_pil(self.log if hasattr(self, "log") else None)

            self.show()
            self.raise_()
            self.activateWindow()
            QtWidgets.QApplication.processEvents()

            if screenshot is None:
                self.log("采集失败: 截图返回 None")
                self.set_error("采集失败: 截图失败")
                self.refresh_template_status()
                self.update_next_step_hint()
                return

            self.log(f"截图成功，原图尺寸: {screenshot.size[0]}x{screenshot.size[1]}")
            selector = WindowedRegionSelector(screenshot, self)
            result = selector.exec_()

            if result != QtWidgets.QMessageBox.Accepted:
                self.log(f"采集已取消: {template_name}")
                self.refresh_template_status()
                self.update_next_step_hint()
                return

            cropped = selector.get_cropped_image()
            if cropped is None:
                self.log("采集失败: 没有有效选区")
                self.set_error("采集失败: 没有有效选区")
                self.refresh_template_status()
                self.update_next_step_hint()
                return

            template_path = profile_manager.get_template_path(template_name)
            if template_path is None:
                self.log("采集失败: 无法获取当前配置模板路径")
                self.set_error("采集失败: 无法获取当前配置模板路径")
                return

            template_path.parent.mkdir(parents=True, exist_ok=True)
            cropped.save(str(template_path))

            exists = template_path.exists()
            size = template_path.stat().st_size if exists else 0
            self.log(f"保存成功: {template_path}")
            self.log(f"文件存在: {exists}，文件大小: {size} bytes")

            if not exists or size <= 0:
                self.set_error(f"采集失败: 保存后文件不存在或为空: {template_path}")
            else:
                self.set_error("")
            self.refresh_template_status()
            self.update_next_step_hint()

        except Exception as e:
            try:
                self.show()
                self.raise_()
                self.activateWindow()
            except Exception:
                pass
            self.log(f"采集异常: {e}")
            self.set_error(f"采集异常: {e}")
            try:
                self.refresh_template_status()
                self.update_next_step_hint()
            except Exception:
                pass
'''

new_class = r'''
class WindowedRegionSelector(QtWidgets.QDialog):
    def __init__(self, pil_image, parent=None):
        super().__init__(parent)
        self.setWindowTitle("请选择模板区域")
        self.original_image = pil_image.convert("RGB")
        self.orig_w, self.orig_h = self.original_image.size
        self.start_pos = None
        self.end_pos = None
        self.crop_box = None

        raw = self.original_image.tobytes("raw", "RGB")
        self._raw = raw
        qimg = QtGui.QImage(raw, self.orig_w, self.orig_h, self.orig_w * 3, QtGui.QImage.Format_RGB888)
        self.base_pixmap = QtGui.QPixmap.fromImage(qimg)

        screen = QtWidgets.QApplication.primaryScreen().availableGeometry()
        max_w = int(screen.width() * 0.88)
        max_h = int(screen.height() * 0.72)
        self.scale = min(max_w / self.orig_w, max_h / self.orig_h, 1.0)
        self.disp_w = max(1, int(self.orig_w * self.scale))
        self.disp_h = max(1, int(self.orig_h * self.scale))
        self.display_pixmap = self.base_pixmap.scaled(
            self.disp_w, self.disp_h,
            QtCore.Qt.KeepAspectRatio,
            QtCore.Qt.SmoothTransformation
        )

        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(QtWidgets.QLabel("拖拽选择区域，然后点击“保存选区”。ESC 或取消可退出。"))

        self.info = QtWidgets.QLabel("当前选区：无")
        layout.addWidget(self.info)

        self.image_label = QtWidgets.QLabel()
        self.image_label.setPixmap(self.display_pixmap)
        self.image_label.setFixedSize(self.disp_w, self.disp_h)
        self.image_label.installEventFilter(self)
        self.image_label.setCursor(QtCore.Qt.CrossCursor)
        layout.addWidget(self.image_label)

        row = QtWidgets.QHBoxLayout()
        self.save_btn = QtWidgets.QPushButton("保存选区")
        self.cancel_btn = QtWidgets.QPushButton("取消")
        self.save_btn.setMinimumHeight(36)
        self.cancel_btn.setMinimumHeight(36)
        row.addWidget(self.save_btn)
        row.addWidget(self.cancel_btn)
        layout.addLayout(row)

        self.save_btn.clicked.connect(self.save_selection)
        self.cancel_btn.clicked.connect(self.reject)

        self.resize(min(self.disp_w + 40, max_w), min(self.disp_h + 130, max_h + 140))

    def eventFilter(self, obj, event):
        if obj is self.image_label:
            if event.type() == QtCore.QEvent.MouseButtonPress and event.button() == QtCore.Qt.LeftButton:
                self.start_pos = event.pos()
                self.end_pos = event.pos()
                self.update_overlay()
                return True

            if event.type() == QtCore.QEvent.MouseMove and self.start_pos is not None:
                self.end_pos = event.pos()
                self.update_overlay()
                return True

            if event.type() == QtCore.QEvent.MouseButtonRelease and self.start_pos is not None:
                self.end_pos = event.pos()
                self.update_overlay()
                return True

        return super().eventFilter(obj, event)

    def _rect_display(self):
        if self.start_pos is None or self.end_pos is None:
            return None

        x1, y1 = self.start_pos.x(), self.start_pos.y()
        x2, y2 = self.end_pos.x(), self.end_pos.y()

        x = max(0, min(x1, x2))
        y = max(0, min(y1, y2))
        w = abs(x2 - x1)
        h = abs(y2 - y1)

        x = min(x, self.disp_w - 1)
        y = min(y, self.disp_h - 1)
        w = min(w, self.disp_w - x)
        h = min(h, self.disp_h - y)

        return QtCore.QRect(x, y, w, h)

    def _crop_from_display(self, rect):
        x = int(rect.x() / self.scale)
        y = int(rect.y() / self.scale)
        w = int(rect.width() / self.scale)
        h = int(rect.height() / self.scale)

        x = max(0, min(x, self.orig_w - 1))
        y = max(0, min(y, self.orig_h - 1))
        w = max(0, min(w, self.orig_w - x))
        h = max(0, min(h, self.orig_h - y))

        return x, y, w, h

    def update_overlay(self):
        pix = QtGui.QPixmap(self.display_pixmap)
        rect = self._rect_display()

        if rect:
            painter = QtGui.QPainter(pix)
            painter.fillRect(rect, QtGui.QColor(255, 0, 0, 70))
            painter.setPen(QtGui.QPen(QtGui.QColor(255, 0, 0), 2))
            painter.drawRect(rect)
            painter.end()

            cx, cy, cw, ch = self._crop_from_display(rect)
            self.info.setText(
                f"当前选区：显示({rect.x()},{rect.y()},{rect.width()},{rect.height()})  "
                f"裁剪({cx},{cy},{cw},{ch})"
            )

        self.image_label.setPixmap(pix)

    def save_selection(self):
        rect = self._rect_display()

        if not rect or rect.width() < 10 or rect.height() < 10:
            QtWidgets.QMessageBox.warning(self, "选区太小", "请先拖拽选择至少 10x10 的区域。")
            return

        crop_box = self._crop_from_display(rect)

        if crop_box[2] < 10 or crop_box[3] < 10:
            QtWidgets.QMessageBox.warning(self, "选区太小", "换算后的裁剪区域太小，请重新选择。")
            return

        self.crop_box = crop_box
        self.accept()

    def keyPressEvent(self, event):
        if event.key() == QtCore.Qt.Key_Escape:
            self.reject()
            return

        if event.key() in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter):
            self.save_selection()
            return

        super().keyPressEvent(event)

    def get_cropped_image(self):
        if not self.crop_box:
            return None

        x, y, w, h = self.crop_box
        return self.original_image.crop((x, y, x + w, y + h))
'''

backup = p.with_suffix(".py.bak_capture_save")
backup.write_text(s, encoding="utf-8")

s2 = replace_class(s, "WindowedRegionSelector", new_class)
s2 = replace_method(s2, "capture_template", new_capture_template)

p.write_text(s2, encoding="utf-8")
print("补丁完成")
print("备份文件:", backup)
print("目标文件:", p)
