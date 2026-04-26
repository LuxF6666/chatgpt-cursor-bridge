import sys
import time
import os
import threading
import json
import re
from pathlib import Path
from queue import Queue
from PyQt5 import QtWidgets, QtGui, QtCore
import pyautogui
import cv2
import numpy as np

APP_VERSION = "0.1.0"

try:
    from PIL import Image, ImageGrab
    PIL_AVAILABLE = True
except Exception:
    Image = None
    ImageGrab = None
    PIL_AVAILABLE = False

try:
    from mss import mss as _mss
    MSS_AVAILABLE = True
except Exception:
    _mss = None
    MSS_AVAILABLE = False

LAST_SCREENSHOT_BACKEND = None  # "mss" | "imagegrab" | "pyautogui" | None

def capture_screen_pil(log_fn=None):
    """
    统一截图函数：优先 mss > PIL.ImageGrab > pyautogui.screenshot
    返回：PIL RGB Image；全部失败返回 None
    """
    global LAST_SCREENSHOT_BACKEND

    def _log(msg):
        try:
            if callable(log_fn):
                log_fn(msg)
            else:
                print(msg)
        except Exception:
            try:
                print(msg)
            except Exception:
                pass

    last_err = None

    # 1) mss
    try:
        if MSS_AVAILABLE and _mss and PIL_AVAILABLE and Image:
            with _mss() as sct:
                monitor = sct.monitors[0]
                img = sct.grab(monitor)  # BGRA
                pil_img = Image.frombytes("RGB", img.size, img.bgra, "raw", "BGRX")
                LAST_SCREENSHOT_BACKEND = "mss"
                return pil_img.convert("RGB")
        else:
            if not MSS_AVAILABLE:
                _log("截图后端: mss 不可用")
    except Exception as e:
        last_err = e
        _log(f"截图后端 mss 失败: {str(e)}")

    # 2) PIL.ImageGrab
    try:
        if PIL_AVAILABLE and ImageGrab:
            pil_img = ImageGrab.grab(all_screens=True)
            LAST_SCREENSHOT_BACKEND = "imagegrab"
            return pil_img.convert("RGB")
        else:
            _log("截图后端: PIL.ImageGrab 不可用")
    except Exception as e:
        last_err = e
        _log(f"截图后端 ImageGrab 失败: {str(e)}")

    # 3) pyautogui.screenshot
    try:
        pil_img = pyautogui.screenshot()
        LAST_SCREENSHOT_BACKEND = "pyautogui"
        try:
            return pil_img.convert("RGB")
        except Exception:
            return pil_img
    except Exception as e:
        last_err = e
        _log(f"截图后端 pyautogui 失败: {str(e)}")

    LAST_SCREENSHOT_BACKEND = None
    _log(f"截图失败: {str(last_err) if last_err else '未知错误'}")
    return None

def pil_image_to_qpixmap(pil_img, log_fn=None):
    """
    PIL Image -> QPixmap
    优先走内存转换；失败则落盘到临时文件再加载，保证稳定。
    """
    def _log(msg):
        try:
            if callable(log_fn):
                log_fn(msg)
            else:
                print(msg)
        except Exception:
            pass

    if pil_img is None:
        return QtGui.QPixmap()

    try:
        rgb = pil_img.convert("RGB")
        w, h = rgb.size
        data = rgb.tobytes("raw", "RGB")
        qimg = QtGui.QImage(data, w, h, 3 * w, QtGui.QImage.Format_RGB888)
        return QtGui.QPixmap.fromImage(qimg)
    except Exception as e:
        _log(f"PIL->QPixmap 内存转换失败，尝试临时文件: {str(e)}")
        try:
            import tempfile
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
            tmp_path = tmp.name
            tmp.close()
            pil_img.save(tmp_path, format="PNG")
            pm = QtGui.QPixmap(tmp_path)
            try:
                os.unlink(tmp_path)
            except Exception:
                pass
            return pm
        except Exception as e2:
            _log(f"PIL->QPixmap 临时文件转换失败: {str(e2)}")
            return QtGui.QPixmap()

try:
    import pyperclip
except ImportError:
    pyperclip = None

try:
    from pywinauto import Desktop
    PYWINAUTO_AVAILABLE = True
except Exception:
    Desktop = None
    PYWINAUTO_AVAILABLE = False

running = False
pending_execution = False
stop_current_task = False
stop_event = threading.Event()

BASE_DIR = Path(__file__).parent
PROFILES_DIR = BASE_DIR / "profiles"

DEFAULT_PROFILES = ["左侧项目", "右侧项目"]

class ProfileManager:
    def __init__(self):
        self.current_profile = None
        self.profiles = {}
        self.profile_queues = {}
        self.ensure_default_profiles()
        if self.profiles:
            self.current_profile = list(self.profiles.keys())[0]
        self.load_profile_config(self.current_profile)

    def ensure_default_profiles(self):
        try:
            PROFILES_DIR.mkdir(exist_ok=True)
            for profile_name in DEFAULT_PROFILES:
                profile_path = PROFILES_DIR / profile_name
                if not profile_path.exists():
                    profile_path.mkdir(parents=True, exist_ok=True)
                if profile_name not in self.profiles:
                    self.profiles[profile_name] = profile_path
                if profile_name not in self.profile_queues:
                    self.profile_queues[profile_name] = Queue()
        except Exception as e:
            print(f"创建默认配置失败: {e}")

    def get_template_path(self, template_name):
        if not self.current_profile:
            return None
        return self.profiles.get(self.current_profile) / template_name

    def get_profile_dir(self):
        if not self.current_profile:
            return None
        return self.profiles.get(self.current_profile)

    def create_profile(self, name):
        try:
            if not name or not name.strip():
                return False, "配置名称不能为空"
            illegal_chars = r'[<>:"/\\|?*]'
            if re.search(illegal_chars, name):
                return False, "配置名称包含非法字符"
            name = name.strip()
            if name in self.profiles:
                return False, "配置名称已存在"
            profile_path = PROFILES_DIR / name
            profile_path.mkdir(parents=True, exist_ok=True)
            self.profiles[name] = profile_path
            self.profile_queues[name] = Queue()
            self.save_profile_config(name)
            return True, f"配置 '{name}' 创建成功"
        except Exception as e:
            return False, f"创建配置失败: {str(e)}"

    def delete_profile(self, name):
        try:
            if len(self.profiles) <= 1:
                return False, "至少保留一个配置"
            if name not in self.profiles:
                return False, "配置不存在"
            if name == self.current_profile:
                return False, "不能删除当前配置"
            profile_path = self.profiles[name]
            try:
                import shutil
                shutil.rmtree(profile_path)
            except:
                pass
            del self.profiles[name]
            del self.profile_queues[name]
            return True, f"配置 '{name}' 已删除"
        except Exception as e:
            return False, f"删除配置失败: {str(e)}"

    def switch_profile(self, name):
        try:
            if name not in self.profiles:
                return False, "配置不存在"
            self.current_profile = name
            self.load_profile_config(name)
            return True, f"已切换到配置 '{name}'"
        except Exception as e:
            return False, f"切换配置失败: {str(e)}"

    def get_config_path(self, name=None):
        if not name:
            name = self.current_profile
        if name and name in self.profiles:
            return self.profiles[name] / "config.json"
        return None

    def load_profile_config(self, name):
        try:
            config_path = self.get_config_path(name)
            if config_path and config_path.exists():
                with open(config_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            return {"safe_mode": True, "gpt_safe_mode": True}
        except Exception as e:
            return {"safe_mode": True, "gpt_safe_mode": True}

    def save_profile_config(self, name=None, delete_keywords=None, sandbox_keywords=None):
        try:
            if not name:
                name = self.current_profile
            config_path = self.get_config_path(name)
            if not config_path:
                return
            config = {
                "safe_mode": getattr(self, 'safe_mode', True),
                "gpt_safe_mode": getattr(self, 'gpt_safe_mode', True)
            }
            if delete_keywords is not None:
                config["delete_keywords"] = delete_keywords
            if sandbox_keywords is not None:
                config["sandbox_keywords"] = sandbox_keywords
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"保存配置失败: {e}")

    def get_queue(self, name=None):
        if not name:
            name = self.current_profile
        if name not in self.profile_queues:
            self.profile_queues[name] = Queue()
        return self.profile_queues[name]

profile_manager = ProfileManager()

class QueueUpdateSignal(QtCore.QObject):
    update_signal = QtCore.pyqtSignal(str, str)


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

class RegionSelector(QtWidgets.QWidget):
    def __init__(self, screenshot, screenshot_pil=None, log_fn=None):
        super().__init__()
        self.screenshot = screenshot
        self.screenshot_pil = screenshot_pil
        self.start_point = None
        self.end_point = None
        self.is_selecting = False
        self.log_fn = log_fn

        screen = QtWidgets.QApplication.primaryScreen()
        self.setGeometry(screen.geometry())
        self.setWindowFlags(QtCore.Qt.FramelessWindowHint | QtCore.Qt.WindowStaysOnTopHint)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)

        self.pixmap = self.convert_screenshot_to_pixmap()
        self.selection_rect = QtCore.QRect()
        self.cancelled = False

    def convert_screenshot_to_pixmap(self):
        if self.screenshot_pil is not None:
            pm = pil_image_to_qpixmap(self.screenshot_pil, log_fn=self.log_fn)
            if not pm.isNull():
                return pm
        screenshot_rgb = cv2.cvtColor(self.screenshot, cv2.COLOR_BGR2RGB)
        height, width, channel = screenshot_rgb.shape
        bytes_per_line = 3 * width
        q_image = QtGui.QImage(screenshot_rgb.data, width, height, bytes_per_line, QtGui.QImage.Format_RGB888)
        return QtGui.QPixmap.fromImage(q_image)

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.drawPixmap(self.rect(), self.pixmap)

        if self.is_selecting and self.start_point and self.end_point:
            painter.setPen(QtGui.QPen(QtGui.QColor(0, 255, 0), 2))
            rect = QtCore.QRect(self.start_point, self.end_point).normalized()
            painter.drawRect(rect)

            brush = QtGui.QBrush(QtGui.QColor(0, 255, 0, 50))
            painter.setBrush(brush)
            painter.drawRect(rect)

            painter.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255), 1))
            text = f"选择区域: {rect.width()} x {rect.height()}"
            painter.drawText(rect.topLeft() + QtCore.QPoint(10, 20), text)

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            self.start_point = event.pos()
            self.end_point = event.pos()
            self.is_selecting = True
            self.update()

    def mouseMoveEvent(self, event):
        if self.is_selecting:
            self.end_point = event.pos()
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            self.is_selecting = False
            self.end_point = event.pos()
            self.selection_rect = QtCore.QRect(self.start_point, self.end_point).normalized()
            if self.selection_rect.width() < 10 or self.selection_rect.height() < 10:
                self.cancelled = True
            self.close()

    def keyPressEvent(self, event):
        if event.key() == QtCore.Qt.Key_Escape:
            self.cancelled = True
            self.close()


class BridgeGUI(QtWidgets.QWidget):
    log_signal = QtCore.pyqtSignal(str)
    status_signal = QtCore.pyqtSignal(str)
    queue_update_signal = QtCore.pyqtSignal(str, str)
    status_update_signal = QtCore.pyqtSignal(str, str, str, str)

    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"L 桥梁工具 v{APP_VERSION}")
        
        # 获取屏幕可用区域
        screen = QtWidgets.QApplication.primaryScreen()
        available_geometry = screen.availableGeometry()
        screen_width = available_geometry.width()
        screen_height = available_geometry.height()
        
        # 计算窗口大小：最大为屏幕的90%
        window_width = min(1200, int(screen_width * 0.9))
        window_height = min(850, int(screen_height * 0.9))
        
        # 设置窗口位置和大小
        self.setGeometry(
            (screen_width - window_width) // 2,
            (screen_height - window_height) // 2,
            window_width,
            window_height
        )
        
        # 设置最小尺寸
        self.setMinimumSize(900, 620)

        self.log_signal.connect(self.on_log_signal)
        self.status_signal.connect(self.on_status_signal)
        self.queue_update_signal.connect(self.on_queue_update_signal)
        self.status_update_signal.connect(self.on_status_update_signal)

        self.current_mode = "安全模式"
        self.current_task_summary = "无"
        self.last_template_result = "无"
        self.last_error = "无"

        self.safe_mode = True
        self.gpt_safe_mode = True

        self.向导_step = 1
        self.向导_skipped = False
        self.向导_safety_drill_done = False

        # 创建主布局
        main_layout = QtWidgets.QVBoxLayout()

        # 创建顶部按钮布局（保持在滚动区域外）
        self.top_buttons_layout = QtWidgets.QHBoxLayout()
        self.open_readme_btn = QtWidgets.QPushButton("打开使用说明")
        self.open_program_dir_btn = QtWidgets.QPushButton("打开程序目录")
        self.open_profile_dir_btn = QtWidgets.QPushButton("打开当前配置目录")
        self.system_check_btn = QtWidgets.QPushButton("系统自检")
        self.save_report_btn = QtWidgets.QPushButton("保存诊断报告")
        self.backup_btn = QtWidgets.QPushButton("创建版本备份")
        self.zoom_label = QtWidgets.QLabel("界面缩放:")
        self.zoom_small_btn = QtWidgets.QPushButton("小")
        self.zoom_medium_btn = QtWidgets.QPushButton("中")
        self.zoom_large_btn = QtWidgets.QPushButton("大")
        self.zoom_small_btn.setMinimumSize(40, 34)
        self.zoom_medium_btn.setMinimumSize(40, 34)
        self.zoom_large_btn.setMinimumSize(40, 34)
        self.top_buttons_layout.addWidget(self.open_readme_btn)
        self.top_buttons_layout.addWidget(self.open_program_dir_btn)
        self.top_buttons_layout.addWidget(self.open_profile_dir_btn)
        self.top_buttons_layout.addWidget(self.system_check_btn)
        self.top_buttons_layout.addWidget(self.save_report_btn)
        self.top_buttons_layout.addWidget(self.backup_btn)
        self.top_buttons_layout.addWidget(self.zoom_label)
        self.top_buttons_layout.addWidget(self.zoom_small_btn)
        self.top_buttons_layout.addWidget(self.zoom_medium_btn)
        self.top_buttons_layout.addWidget(self.zoom_large_btn)
        self.top_buttons_layout.addStretch()
        main_layout.addLayout(self.top_buttons_layout)

        # 创建滚动区域
        scroll_area = QtWidgets.QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_content = QtWidgets.QWidget()
        self.layout = QtWidgets.QVBoxLayout(scroll_content)
        scroll_area.setWidget(scroll_content)
        main_layout.addWidget(scroll_area)

        self.project区 = QtWidgets.QGroupBox("项目配置区")
        self.project_layout = QtWidgets.QHBoxLayout()

        self.profile_combo = QtWidgets.QComboBox()
        self.new_profile_btn = QtWidgets.QPushButton("新建配置")
        self.delete_profile_btn = QtWidgets.QPushButton("删除配置")
        self.open_profile_dir_btn2 = QtWidgets.QPushButton("打开当前配置目录")

        self.project_layout.addWidget(QtWidgets.QLabel("当前项目:"))
        self.project_layout.addWidget(self.profile_combo)
        self.project_layout.addWidget(self.new_profile_btn)
        self.project_layout.addWidget(self.delete_profile_btn)
        self.project_layout.addWidget(self.open_profile_dir_btn2)
        self.project区.setLayout(self.project_layout)
        self.layout.addWidget(self.project区)

        self.instruction_label = QtWidgets.QLabel(
            "<b>使用说明：</b><br>"
            "第一步：选择或新建项目配置<br>"
            "第二步：在当前配置下采集模板<br>"
            "第三步：把要发给编程工具的提示词粘贴到下面输入框<br>"
            "第四步：点击「加入队列」，再点「开始执行」<br>"
            "--- 双向桥梁 ---<br>"
            "第五步：使用回传区将编程工具结果发送到 ChatGPT"
        )
        self.instruction_label.setStyleSheet("background-color: #f0f0f0; padding: 10px; border-radius: 5px;")
        self.instruction_label.setWordWrap(True)
        self.layout.addWidget(self.instruction_label)

        self.input_layout = QtWidgets.QHBoxLayout()
        self.command_input = QtWidgets.QTextEdit()
        self.command_input.setPlaceholderText("在此输入指令...")
        self.wrap_button = QtWidgets.QPushButton("自动包裹标记")
        self.add_button = QtWidgets.QPushButton("加入队列")
        self.clear_queue_button = QtWidgets.QPushButton("清空队列")
        self.clear_log_button = QtWidgets.QPushButton("清空日志")
        self.start_button = QtWidgets.QPushButton("开始执行")
        self.stop_button = QtWidgets.QPushButton("停止执行")
        self.execute_one_button = QtWidgets.QPushButton("只执行一条")
        self.input_layout.addWidget(QtWidgets.QLabel("指令输入:"))
        self.input_layout.addWidget(self.command_input)
        self.input_layout.addWidget(self.wrap_button)
        self.input_layout.addWidget(self.add_button)
        self.input_layout.addWidget(self.clear_queue_button)
        self.input_layout.addWidget(self.clear_log_button)
        self.input_layout.addWidget(self.start_button)
        self.input_layout.addWidget(self.execute_one_button)
        self.input_layout.addWidget(self.stop_button)
        self.layout.addLayout(self.input_layout)

        self.option_layout = QtWidgets.QHBoxLayout()
        self.safe_mode_checkbox = QtWidgets.QCheckBox("安全模式（只粘贴，不发送）")
        self.safe_mode_checkbox.setChecked(True)
        self.on_top_checkbox = QtWidgets.QCheckBox("窗口置顶")
        self.on_top_checkbox.setChecked(False)
        self.option_layout.addWidget(self.safe_mode_checkbox)
        self.option_layout.addWidget(self.on_top_checkbox)
        self.option_layout.addWidget(QtWidgets.QLabel(""))
        self.layout.addLayout(self.option_layout)

        self.workflow区 = QtWidgets.QGroupBox("工作流控制区")
        self.workflow_layout = QtWidgets.QHBoxLayout()

        self.one_click_send_btn = QtWidgets.QPushButton("一键发送到编程工具")
        self.one_click_send_btn.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold;")
        self.one_click_return_btn = QtWidgets.QPushButton("一键回传到 ChatGPT")
        self.one_click_return_btn.setStyleSheet("background-color: #2196F3; color: white; font-weight: bold;")
        self.one_click_drill_btn = QtWidgets.QPushButton("一键安全演练")
        self.one_click_drill_btn.setStyleSheet("background-color: #FF9800; color: white; font-weight: bold;")
        self.reset_workflow_btn = QtWidgets.QPushButton("重置当前流程")
        self.reset_workflow_btn.setStyleSheet("background-color: #f44336; color: white; font-weight: bold;")

        self.workflow_layout.addWidget(self.one_click_send_btn)
        self.workflow_layout.addWidget(self.one_click_return_btn)
        self.workflow_layout.addWidget(self.one_click_drill_btn)
        self.workflow_layout.addWidget(self.reset_workflow_btn)
        self.workflow区.setLayout(self.workflow_layout)
        self.layout.addWidget(self.workflow区)

        self.向导区 = QtWidgets.QGroupBox("首次使用向导")
        self.向导_layout = QtWidgets.QVBoxLayout()

        self.向导_step_label = QtWidgets.QLabel("当前步骤: 准备开始")
        self.向导_step_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        self.向导_desc_label = QtWidgets.QLabel("请按照向导步骤完成设置")
        self.向导_desc_label.setWordWrap(True)

        self.向导_buttons_layout = QtWidgets.QHBoxLayout()
        self.向导_prev_btn = QtWidgets.QPushButton("上一步")
        self.向导_next_btn = QtWidgets.QPushButton("下一步")
        self.向导_execute_btn = QtWidgets.QPushButton("执行当前步骤")
        self.向导_execute_btn.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold;")
        self.向导_skip_btn = QtWidgets.QPushButton("跳过向导")

        self.向导_buttons_layout.addWidget(self.向导_prev_btn)
        self.向导_buttons_layout.addWidget(self.向导_next_btn)
        self.向导_buttons_layout.addWidget(self.向导_execute_btn)
        self.向导_buttons_layout.addWidget(self.向导_skip_btn)

        self.向导_layout.addWidget(self.向导_step_label)
        self.向导_layout.addWidget(self.向导_desc_label)
        self.向导_layout.addLayout(self.向导_buttons_layout)
        self.向导区.setLayout(self.向导_layout)
        self.layout.addWidget(self.向导区)

        self.next_step_label = QtWidgets.QLabel("下一步：请选择或新建项目配置")
        self.next_step_label.setStyleSheet("background-color: #E3F2FD; padding: 10px; border-radius: 5px; font-weight: bold;")
        self.next_step_label.setWordWrap(True)
        self.layout.addWidget(self.next_step_label)

        self.关键词设置区 = QtWidgets.QGroupBox("关键词识别设置区")
        self.关键词_layout = QtWidgets.QHBoxLayout()

        self.delete_keywords_label = QtWidgets.QLabel("删除/确认关键词:")
        self.delete_keywords_input = QtWidgets.QLineEdit()
        self.delete_keywords_input.setPlaceholderText("删除,确认,Yes,OK")
        self.delete_keywords_input.setText("删除,确认,Yes,OK")

        self.sandbox_keywords_label = QtWidgets.QLabel("后台沙箱关键词:")
        self.sandbox_keywords_input = QtWidgets.QLineEdit()
        self.sandbox_keywords_input.setPlaceholderText("后台,沙箱,后台运行,Run in background")
        self.sandbox_keywords_input.setText("后台,沙箱,后台运行,Run in background")

        self.save_keywords_btn = QtWidgets.QPushButton("保存关键词设置")

        self.关键词_layout.addWidget(self.delete_keywords_label)
        self.关键词_layout.addWidget(self.delete_keywords_input)
        self.关键词_layout.addWidget(self.sandbox_keywords_label)
        self.关键词_layout.addWidget(self.sandbox_keywords_input)
        self.关键词_layout.addWidget(self.save_keywords_btn)
        self.关键词设置区.setLayout(self.关键词_layout)
        self.layout.addWidget(self.关键词设置区)

        # 采集模式选择区
        self.采集模式区 = QtWidgets.QGroupBox("采集模式选择")
        self.采集模式_layout = QtWidgets.QHBoxLayout()
        self.capture_mode_combo = QtWidgets.QComboBox()
        self.capture_mode_combo.addItem("窗口化截图采集", "window")
        self.capture_mode_combo.addItem("全屏透明采集", "fullscreen")
        self.capture_mode_combo.setCurrentIndex(0)  # 默认选择窗口化采集
        self.capture_help_btn = QtWidgets.QPushButton("采集测试说明")
        self.采集模式_layout.addWidget(QtWidgets.QLabel("采集模式:"))
        self.采集模式_layout.addWidget(self.capture_mode_combo)
        self.采集模式_layout.addWidget(self.capture_help_btn)
        self.采集模式区.setLayout(self.采集模式_layout)
        self.layout.addWidget(self.采集模式区)

        self.template采集区 = QtWidgets.QGroupBox("模板采集区")
        self.template采集_layout = QtWidgets.QHBoxLayout()

        self.capture_input_btn = QtWidgets.QPushButton("采集编程工具输入框")
        self.capture_send_btn = QtWidgets.QPushButton("采集发送按钮")
        self.capture_delete_btn = QtWidgets.QPushButton("采集删除/确认按钮")
        self.capture_sandbox_btn = QtWidgets.QPushButton("采集后台沙箱按钮")
        self.capture_coder_copy_btn = QtWidgets.QPushButton("采集编程工具复制按钮")
        self.capture_gpt_input_btn = QtWidgets.QPushButton("采集ChatGPT输入框")
        self.capture_gpt_send_btn = QtWidgets.QPushButton("采集ChatGPT发送按钮")
        self.refresh_template_btn = QtWidgets.QPushButton("刷新模板状态")

        self.template采集_layout.addWidget(self.capture_input_btn)
        self.template采集_layout.addWidget(self.capture_send_btn)
        self.template采集_layout.addWidget(self.capture_delete_btn)
        self.template采集_layout.addWidget(self.capture_sandbox_btn)
        self.template采集_layout.addWidget(self.capture_coder_copy_btn)
        self.template采集_layout.addWidget(self.capture_gpt_input_btn)
        self.template采集_layout.addWidget(self.capture_gpt_send_btn)
        self.template采集_layout.addWidget(self.refresh_template_btn)
        self.template采集区.setLayout(self.template采集_layout)
        self.layout.addWidget(self.template采集区)

        self.template_status_layout = QtWidgets.QHBoxLayout()
        self.template_status_layout.addWidget(QtWidgets.QLabel("模板状态:"))

        self.input_status_label = QtWidgets.QLabel("输入框: 未采集")
        self.send_status_label = QtWidgets.QLabel("发送按钮: 未采集")
        self.delete_status_label = QtWidgets.QLabel("删除/确认: 未采集")
        self.sandbox_status_label = QtWidgets.QLabel("沙箱按钮: 未采集")
        self.coder_copy_status_label = QtWidgets.QLabel("编程复制: 未采集")
        self.gpt_input_status_label = QtWidgets.QLabel("GPT输入: 未采集")
        self.gpt_send_status_label = QtWidgets.QLabel("GPT发送: 未采集")

        self.input_status_label.setStyleSheet("color: red;")
        self.send_status_label.setStyleSheet("color: orange;")
        self.delete_status_label.setStyleSheet("color: orange;")
        self.sandbox_status_label.setStyleSheet("color: orange;")
        self.coder_copy_status_label.setStyleSheet("color: orange;")
        self.gpt_input_status_label.setStyleSheet("color: orange;")
        self.gpt_send_status_label.setStyleSheet("color: orange;")

        self.template_status_layout.addWidget(self.input_status_label)
        self.template_status_layout.addWidget(self.send_status_label)
        self.template_status_layout.addWidget(self.delete_status_label)
        self.template_status_layout.addWidget(self.sandbox_status_label)
        self.template_status_layout.addWidget(self.coder_copy_status_label)
        self.template_status_layout.addWidget(self.gpt_input_status_label)
        self.template_status_layout.addWidget(self.gpt_send_status_label)
        self.layout.addLayout(self.template_status_layout)

        self.preview_layout = QtWidgets.QHBoxLayout()
        self.preview_layout.addWidget(QtWidgets.QLabel("模板预览:"))

        self.input_preview_label = QtWidgets.QLabel()
        self.input_preview_label.setFixedSize(60, 25)
        self.input_preview_label.setStyleSheet("border: 1px solid gray; background-color: #ddd;")
        self.send_preview_label = QtWidgets.QLabel()
        self.send_preview_label.setFixedSize(60, 25)
        self.send_preview_label.setStyleSheet("border: 1px solid gray; background-color: #ddd;")
        self.delete_preview_label = QtWidgets.QLabel()
        self.delete_preview_label.setFixedSize(60, 25)
        self.delete_preview_label.setStyleSheet("border: 1px solid gray; background-color: #ddd;")
        self.sandbox_preview_label = QtWidgets.QLabel()
        self.sandbox_preview_label.setFixedSize(60, 25)
        self.sandbox_preview_label.setStyleSheet("border: 1px solid gray; background-color: #ddd;")
        self.coder_copy_preview_label = QtWidgets.QLabel()
        self.coder_copy_preview_label.setFixedSize(60, 25)
        self.coder_copy_preview_label.setStyleSheet("border: 1px solid gray; background-color: #ddd;")
        self.gpt_input_preview_label = QtWidgets.QLabel()
        self.gpt_input_preview_label.setFixedSize(60, 25)
        self.gpt_input_preview_label.setStyleSheet("border: 1px solid gray; background-color: #ddd;")
        self.gpt_send_preview_label = QtWidgets.QLabel()
        self.gpt_send_preview_label.setFixedSize(60, 25)
        self.gpt_send_preview_label.setStyleSheet("border: 1px solid gray; background-color: #ddd;")

        self.preview_layout.addWidget(self.input_preview_label)
        self.preview_layout.addWidget(self.send_preview_label)
        self.preview_layout.addWidget(self.delete_preview_label)
        self.preview_layout.addWidget(self.sandbox_preview_label)
        self.preview_layout.addWidget(self.coder_copy_preview_label)
        self.preview_layout.addWidget(self.gpt_input_preview_label)
        self.preview_layout.addWidget(self.gpt_send_preview_label)
        self.layout.addLayout(self.preview_layout)

        self.calibration区 = QtWidgets.QGroupBox("校准测试区")
        self.calibration_layout = QtWidgets.QHBoxLayout()

        self.test_input_btn = QtWidgets.QPushButton("测试识别输入框")
        self.test_send_btn = QtWidgets.QPushButton("测试识别发送按钮")
        self.test_delete_btn = QtWidgets.QPushButton("测试识别删除/确认")
        self.test_sandbox_btn = QtWidgets.QPushButton("测试识别沙箱按钮")
        self.test_coder_copy_btn = QtWidgets.QPushButton("测试识别编程复制")
        self.test_gpt_input_btn = QtWidgets.QPushButton("测试识别GPT输入")
        self.test_gpt_send_btn = QtWidgets.QPushButton("测试识别GPT发送")
        self.test_paste_btn = QtWidgets.QPushButton("安全测试粘贴")
        self.open_dir_btn = QtWidgets.QPushButton("打开模板目录")

        self.calibration_layout.addWidget(self.test_input_btn)
        self.calibration_layout.addWidget(self.test_send_btn)
        self.calibration_layout.addWidget(self.test_delete_btn)
        self.calibration_layout.addWidget(self.test_sandbox_btn)
        self.calibration_layout.addWidget(self.test_coder_copy_btn)
        self.calibration_layout.addWidget(self.test_gpt_input_btn)
        self.calibration_layout.addWidget(self.test_gpt_send_btn)
        self.calibration_layout.addWidget(self.test_paste_btn)
        self.calibration_layout.addWidget(self.open_dir_btn)
        self.calibration区.setLayout(self.calibration_layout)
        self.layout.addWidget(self.calibration区)

        self.回传区 = QtWidgets.QGroupBox("回传区 (编程工具 → ChatGPT)")
        self.回传_layout = QtWidgets.QHBoxLayout()

        self.copy_coder_btn = QtWidgets.QPushButton("复制编程工具结果")
        self.paste_gpt_btn = QtWidgets.QPushButton("粘贴到ChatGPT")
        self.copy_paste_gpt_btn = QtWidgets.QPushButton("复制并粘贴到ChatGPT")
        self.gpt_safe_mode_checkbox = QtWidgets.QCheckBox("回传安全模式（只粘贴，不发送）")
        self.gpt_safe_mode_checkbox.setChecked(True)

        self.回传_layout.addWidget(self.copy_coder_btn)
        self.回传_layout.addWidget(self.paste_gpt_btn)
        self.回传_layout.addWidget(self.copy_paste_gpt_btn)
        self.回传_layout.addWidget(self.gpt_safe_mode_checkbox)
        self.回传区.setLayout(self.回传_layout)
        self.layout.addWidget(self.回传区)

        self.task_status区 = QtWidgets.QGroupBox("任务运行状态")
        self.task_status_layout = QtWidgets.QVBoxLayout()

        self.profile_label = QtWidgets.QLabel("当前配置: 无")
        self.profile_dir_label = QtWidgets.QLabel("配置目录: 无")
        self.mode_label = QtWidgets.QLabel("当前模式: 安全模式")
        self.queue_count_label = QtWidgets.QLabel("当前队列数量: 0")
        self.task_label = QtWidgets.QLabel("当前任务: 无")
        self.template_result_label = QtWidgets.QLabel("最后模板识别: 无")
        self.error_label = QtWidgets.QLabel("最后错误: 无")
        self.error_label.setStyleSheet("color: red;")

        self.task_status_layout.addWidget(self.profile_label)
        self.task_status_layout.addWidget(self.profile_dir_label)
        self.task_status_layout.addWidget(self.mode_label)
        self.task_status_layout.addWidget(self.queue_count_label)
        self.task_status_layout.addWidget(self.task_label)
        self.task_status_layout.addWidget(self.template_result_label)
        self.task_status_layout.addWidget(self.error_label)
        self.task_status区.setLayout(self.task_status_layout)
        self.layout.addWidget(self.task_status区)

        self.queue_view = QtWidgets.QListWidget()
        self.layout.addWidget(QtWidgets.QLabel("指令队列状态"))
        self.layout.addWidget(self.queue_view)

        self.log_view = QtWidgets.QTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setStyleSheet("""
            QTextEdit {
                background-color: #2b2b2b;
                color: #d4d4d4;
                border: 1px solid #3e3e3e;
                padding: 8px;
                font-family: Consolas, 微软雅黑;
                font-size: 13px;
                line-height: 1.5;
            }
        """)
        self.layout.addWidget(QtWidgets.QLabel("操作日志"))
        self.layout.addWidget(self.log_view)

        self.status_label = QtWidgets.QLabel("状态: 等待中")
        self.layout.addWidget(self.status_label)

        self.setLayout(main_layout)

        self.profile_combo.currentTextChanged.connect(self.on_profile_changed)
        self.new_profile_btn.clicked.connect(self.on_new_profile)
        self.delete_profile_btn.clicked.connect(self.on_delete_profile)
        self.open_profile_dir_btn.clicked.connect(self.on_open_profile_dir)

        self.wrap_button.clicked.connect(self.wrap_command)
        self.add_button.clicked.connect(self.add_command)
        self.clear_queue_button.clicked.connect(self.clear_queue)
        self.clear_log_button.clicked.connect(self.clear_log)
        self.start_button.clicked.connect(self.start_execution)
        self.stop_button.clicked.connect(self.stop_execution)
        self.execute_one_button.clicked.connect(self.execute_single)

        self.safe_mode_checkbox.stateChanged.connect(self.on_safe_mode_changed)
        self.on_top_checkbox.stateChanged.connect(self.on_top_changed)

        self.capture_input_btn.clicked.connect(lambda: self.capture_template("input"))
        self.capture_send_btn.clicked.connect(lambda: self.capture_template("send"))
        self.capture_delete_btn.clicked.connect(lambda: self.capture_template("delete"))
        self.capture_sandbox_btn.clicked.connect(lambda: self.capture_template("sandbox"))
        self.capture_coder_copy_btn.clicked.connect(lambda: self.capture_template("coder_copy"))
        self.capture_gpt_input_btn.clicked.connect(lambda: self.capture_template("gpt_input"))
        self.capture_gpt_send_btn.clicked.connect(lambda: self.capture_template("gpt_send"))
        self.refresh_template_btn.clicked.connect(self.refresh_template_status)
        self.capture_help_btn.clicked.connect(self.show_capture_help)

        self.test_input_btn.clicked.connect(lambda: self.test_template("input"))
        self.test_send_btn.clicked.connect(lambda: self.test_template("send"))
        self.test_delete_btn.clicked.connect(lambda: self.test_template("delete"))
        self.test_sandbox_btn.clicked.connect(lambda: self.test_template("sandbox"))
        self.test_coder_copy_btn.clicked.connect(lambda: self.test_template("coder_copy"))
        self.test_gpt_input_btn.clicked.connect(lambda: self.test_template("gpt_input"))
        self.test_gpt_send_btn.clicked.connect(lambda: self.test_template("gpt_send"))
        self.test_paste_btn.clicked.connect(self.safe_test_paste)
        self.open_dir_btn.clicked.connect(self.open_template_directory)

        self.copy_coder_btn.clicked.connect(self.copy_coder_result)
        self.paste_gpt_btn.clicked.connect(self.paste_to_gpt)
        self.copy_paste_gpt_btn.clicked.connect(self.copy_and_paste_to_gpt)

        self.gpt_safe_mode_checkbox.stateChanged.connect(self.on_gpt_safe_mode_changed)

        self.one_click_send_btn.clicked.connect(self.one_click_send_to_coder)
        self.one_click_return_btn.clicked.connect(self.one_click_return_to_gpt)
        self.one_click_drill_btn.clicked.connect(self.one_click_safety_drill)
        self.reset_workflow_btn.clicked.connect(self.reset_workflow)

        self.open_readme_btn.clicked.connect(self.open_readme)
        self.open_program_dir_btn.clicked.connect(self.open_program_directory)
        self.open_profile_dir_btn2.clicked.connect(self.on_open_profile_dir)
        self.system_check_btn.clicked.connect(self.run_system_check)
        self.save_report_btn.clicked.connect(self.save_diagnostic_report)
        self.backup_btn.clicked.connect(self.create_version_backup)
        self.save_keywords_btn.clicked.connect(self.save_keywords_settings)
        self.zoom_small_btn.clicked.connect(lambda: self.set_ui_scale("small"))
        self.zoom_medium_btn.clicked.connect(lambda: self.set_ui_scale("medium"))
        self.zoom_large_btn.clicked.connect(lambda: self.set_ui_scale("large"))

        self.向导_prev_btn.clicked.connect(self.wizard_prev)
        self.向导_next_btn.clicked.connect(self.wizard_next)
        self.向导_execute_btn.clicked.connect(self.wizard_execute)
        self.向导_skip_btn.clicked.connect(self.wizard_skip)

        self.init_profile_combo()
        self.refresh_template_status()
        self.init_ui_scale()
        self.wizard_init()

        self.log(f"L 桥梁工具 v{APP_VERSION} 已启动")
        self.log(f"配置目录: {PROFILES_DIR}")
        self.log(f"当前配置: {profile_manager.current_profile}")
        profile_dir = profile_manager.get_profile_dir()
        if profile_dir:
            self.log(f"当前配置模板目录: {profile_dir}")
        self.log(f"安全模式: {'开启' if self.safe_mode else '关闭'}")
        self.log(f"回传安全模式: {'开启' if self.gpt_safe_mode else '关闭'}")
        if pyperclip is None:
            self.log("警告: pyperclip 未安装，文本粘贴将使用 pyautogui.typewrite（不支持中文）")

    def init_profile_combo(self):
        self.profile_combo.blockSignals(True)
        self.profile_combo.clear()
        for name in profile_manager.profiles.keys():
            self.profile_combo.addItem(name)
        if profile_manager.current_profile:
            idx = self.profile_combo.findText(profile_manager.current_profile)
            if idx >= 0:
                self.profile_combo.setCurrentIndex(idx)
        self.profile_combo.blockSignals(False)
        self.update_profile_display()

    def update_profile_display(self):
        self.profile_label.setText(f"当前配置: {profile_manager.current_profile}")
        profile_dir = profile_manager.get_profile_dir()
        self.profile_dir_label.setText(f"配置目录: {profile_dir}")

    def on_profile_changed(self, profile_name):
        try:
            if not profile_name or profile_name == profile_manager.current_profile:
                return
            success, msg = profile_manager.switch_profile(profile_name)
            if success:
                self.load_profile_settings()
                self.refresh_template_status()
                self.clear_queue_display()
                self.init_ui_scale()
                self.wizard_init()
                self.log(msg)
            else:
                self.set_error(msg)
                idx = self.profile_combo.findText(profile_manager.current_profile)
                if idx >= 0:
                    self.profile_combo.blockSignals(True)
                    self.profile_combo.setCurrentIndex(idx)
                    self.profile_combo.blockSignals(False)
        except Exception as e:
            self.set_error(f"切换配置异常: {str(e)}")
            self.log(f"切换配置异常: {str(e)}")

    def load_profile_settings(self):
        try:
            config = profile_manager.load_profile_config(profile_manager.current_profile)
            self.safe_mode = config.get("safe_mode", True)
            self.gpt_safe_mode = config.get("gpt_safe_mode", True)
            self.safe_mode_checkbox.blockSignals(True)
            self.safe_mode_checkbox.setChecked(self.safe_mode)
            self.safe_mode_checkbox.blockSignals(False)
            self.gpt_safe_mode_checkbox.blockSignals(True)
            self.gpt_safe_mode_checkbox.setChecked(self.gpt_safe_mode)
            self.gpt_safe_mode_checkbox.blockSignals(False)
            self.update_mode_display()

            delete_keywords = config.get("delete_keywords", "删除,确认,Yes,OK")
            sandbox_keywords = config.get("sandbox_keywords", "后台,沙箱,后台运行,Run in background")
            self.delete_keywords_input.blockSignals(True)
            self.delete_keywords_input.setText(delete_keywords)
            self.delete_keywords_input.blockSignals(False)
            self.sandbox_keywords_input.blockSignals(True)
            self.sandbox_keywords_input.setText(sandbox_keywords)
            self.sandbox_keywords_input.blockSignals(False)
        except Exception as e:
            self.log(f"加载配置设置失败: {str(e)}")

    def save_profile_settings(self):
        try:
            self.safe_mode = self.safe_mode_checkbox.isChecked()
            self.gpt_safe_mode = self.gpt_safe_mode_checkbox.isChecked()
            profile_manager.safe_mode = self.safe_mode
            profile_manager.gpt_safe_mode = self.gpt_safe_mode
            profile_manager.save_profile_config()
        except Exception as e:
            self.log(f"保存配置设置失败: {str(e)}")

    def save_keywords_settings(self):
        try:
            delete_keywords = self.delete_keywords_input.text().strip()
            sandbox_keywords = self.sandbox_keywords_input.text().strip()
            profile_manager.save_profile_config(
                delete_keywords=delete_keywords,
                sandbox_keywords=sandbox_keywords
            )
            self.log(f"关键词设置已保存")
            self.log(f"删除/确认关键词: {delete_keywords}")
            self.log(f"后台沙箱关键词: {sandbox_keywords}")
        except Exception as e:
            self.log(f"保存关键词设置失败: {str(e)}")
            self.set_error(f"保存关键词设置失败: {str(e)}")

    def on_new_profile(self):
        text, ok = QtWidgets.QInputDialog.getText(
            self, "新建配置", "请输入配置名称:\n(不能包含特殊字符: < > : \" / \\ | ? *)"
        )
        if not ok or not text:
            self.log("新建配置已取消")
            return

        success, msg = profile_manager.create_profile(text)
        if success:
            self.init_profile_combo()
            idx = self.profile_combo.findText(text)
            if idx >= 0:
                self.profile_combo.setCurrentIndex(idx)
            self.load_profile_settings()
            self.refresh_template_status()
            self.clear_queue_display()
        else:
            self.set_error(msg)
        self.log(msg)

    def on_delete_profile(self):
        if len(profile_manager.profiles) <= 1:
            self.log("至少保留一个配置，无法删除")
            self.set_error("至少保留一个配置")
            return

        current = profile_manager.current_profile
        reply = QtWidgets.QMessageBox.question(
            self, "删除配置确认",
            f"确定要删除配置 '{current}' 吗？\n该操作不可恢复。",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No
        )

        if reply != QtWidgets.QMessageBox.Yes:
            self.log("删除配置已取消")
            return

        success, msg = profile_manager.delete_profile(current)
        if success:
            first_profile = list(profile_manager.profiles.keys())[0]
            profile_manager.switch_profile(first_profile)
            self.init_profile_combo()
            self.load_profile_settings()
            self.refresh_template_status()
            self.clear_queue_display()
        else:
            self.set_error(msg)
        self.log(msg)

    def on_open_profile_dir(self):
        try:
            profile_dir = profile_manager.get_profile_dir()
            if profile_dir and profile_dir.exists():
                os.startfile(str(profile_dir))
                self.log(f"已打开配置目录: {profile_dir}")
            else:
                self.log("配置目录不存在")
                self.set_error("配置目录不存在")
        except Exception as e:
            self.log(f"打开配置目录失败: {str(e)}")
            self.set_error(f"打开目录失败: {str(e)}")

    def clear_queue_display(self):
        self.queue_view.clear()

    def get_current_queue(self):
        return profile_manager.get_queue()

    @QtCore.pyqtSlot(str)
    def on_log_signal(self, message):
        self.log(message)

    @QtCore.pyqtSlot(str)
    def on_status_signal(self, message):
        self.status_label.setText(message)

    @QtCore.pyqtSlot(str, str)
    def on_queue_update_signal(self, cmd, status):
        self.update_queue_item(cmd, status)

    @QtCore.pyqtSlot(str, str, str, str)
    def on_status_update_signal(self, mode, task, template_result, error):
        self.current_mode = mode
        self.current_task_summary = task
        self.last_template_result = template_result
        self.last_error = error
        self.update_task_status_display()

    def update_task_status_display(self):
        self.mode_label.setText(f"当前模式: {self.current_mode}")
        self.queue_count_label.setText(f"当前队列数量: {self.get_current_queue().qsize()}")
        self.task_label.setText(f"当前任务: {self.current_task_summary[:30]}...")
        self.template_result_label.setText(f"最后模板识别: {self.last_template_result}")
        self.error_label.setText(f"最后错误: {self.last_error}")
        if self.last_error and self.last_error != "无":
            self.error_label.setStyleSheet("color: red;")
        else:
            self.error_label.setStyleSheet("color: green;")

    def update_mode_display(self):
        if self.safe_mode_checkbox.isChecked():
            self.current_mode = "安全模式"
        else:
            self.current_mode = "真实执行模式"
        self.update_task_status_display()

    def on_safe_mode_changed(self):
        self.safe_mode = self.safe_mode_checkbox.isChecked()
        self.update_mode_display()
        self.log(f"模式切换: {self.current_mode}")
        self.save_profile_settings()

    def on_gpt_safe_mode_changed(self):
        self.gpt_safe_mode = self.gpt_safe_mode_checkbox.isChecked()
        mode_str = "安全模式" if self.gpt_safe_mode else "真实执行模式"
        self.log(f"回传模式切换: {mode_str}")
        self.save_profile_settings()

    def on_top_changed(self):
        if self.on_top_checkbox.isChecked():
            self.setWindowFlags(self.windowFlags() | QtCore.Qt.WindowStaysOnTopHint)
            self.log("窗口已置顶")
        else:
            self.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowStaysOnTopHint)
            self.log("窗口已取消置顶")
        self.show()

    def set_error(self, error_msg):
        self.last_error = error_msg
        self.error_label.setText(f"最后错误: {error_msg}")
        self.error_label.setStyleSheet("color: red;")

    def clear_error(self):
        self.last_error = "无"
        self.error_label.setText("最后错误: 无")
        self.error_label.setStyleSheet("color: green;")

    def log(self, message):
        timestamp = time.strftime("%H:%M:%S")
        self.log_view.append(f"[{timestamp}] {message}")
        self.log_view.verticalScrollBar().setValue(self.log_view.verticalScrollBar().maximum())

    def wrap_command(self):
        cmd = self.command_input.toPlainText().strip()
        if not cmd:
            self.log("警告: 输入指令为空，无法包裹")
            return

        if "<<PROMPT>>" in cmd and "<<END>>" in cmd:
            self.log("指令已包含标记，无需重复包裹")
            return

        wrapped = f"<<PROMPT>>\n{cmd}\n<<END>>"
        self.command_input.setPlainText(wrapped)
        self.log("已自动包裹提示词标记")

    def auto_wrap(self, cmd):
        if "<<PROMPT>>" not in cmd or "<<END>>" not in cmd:
            return f"<<PROMPT>>\n{cmd}\n<<END>>"
        return cmd

    def add_command(self):
        cmd = self.command_input.toPlainText().strip()
        if cmd:
            wrapped_cmd = self.auto_wrap(cmd)
            self.get_current_queue().put(wrapped_cmd)

            display_text = wrapped_cmd[:80] + "..." if len(wrapped_cmd) > 80 else wrapped_cmd
            self.queue_view.addItem(f"[待执行] {display_text}")
            self.log(f"已加入队列: {display_text}")
            self.command_input.clear()
            self.update_task_status_display()
        else:
            self.log("警告: 输入指令为空")

    def clear_queue(self):
        q = self.get_current_queue()
        while not q.empty():
            try:
                q.get_nowait()
            except:
                break
        self.queue_view.clear()
        self.log("已清空待执行队列")
        self.update_task_status_display()

    def clear_log(self):
        self.log_view.clear()
        self.log("已清空日志")

    def update_queue_item(self, original_cmd, status):
        for i in range(self.queue_view.count()):
            item = self.queue_view.item(i)
            text = item.text()
            if original_cmd[:80] in text or original_cmd[:40] in text:
                display_text = original_cmd[:80] + "..." if len(original_cmd) > 80 else original_cmd
                item.setText(f"[{status}] {display_text}")
                break

    def get_template_path(self, template_name):
        return profile_manager.get_template_path(template_name)

    def refresh_template_status(self):
        self.clear_error()
        profile_dir = profile_manager.get_profile_dir()

        templates_status = [
            ("input_box_template.png", self.input_status_label, self.input_preview_label),
            ("send_button_template.png", self.send_status_label, self.send_preview_label),
            ("delete_popup.png", self.delete_status_label, self.delete_preview_label),
            ("sandbox_button.png", self.sandbox_status_label, self.sandbox_preview_label),
            ("coder_copy_button.png", self.coder_copy_status_label, self.coder_copy_preview_label),
            ("gpt_input_box.png", self.gpt_input_status_label, self.gpt_input_preview_label),
            ("gpt_send_button.png", self.gpt_send_status_label, self.gpt_send_preview_label),
        ]

        for template_name, status_label, preview_label in templates_status:
            if profile_dir:
                template_path = profile_dir / template_name
            else:
                template_path = None

            if template_path and template_path.exists():
                status_label.setText(f"{template_name.split('_')[0]}: 已采集")
                status_label.setStyleSheet("color: green;")
                self.update_preview_image(preview_label, template_path)
            else:
                short_name = template_name.split('_')[0]
                status_label.setText(f"{short_name}: 未采集")
                status_label.setStyleSheet("color: orange;")
                preview_label.setText("未采集")
                preview_label.setAlignment(QtCore.Qt.AlignCenter)

        self.update_profile_display()
        self.wizard_update_display()
        self.update_next_step_hint()

    def update_preview_image(self, label, template_path):
        try:
            img = cv2.imread(str(template_path))
            if img is not None:
                h, w = img.shape[:2]
                aspect = w / h if h > 0 else 1
                label_w = 60
                label_h = int(label_w / aspect)
                if label_h > 25:
                    label_h = 25
                    label_w = int(label_h * aspect)
                if label_w < 10:
                    label_w = 10
                if label_h < 10:
                    label_h = 10
                img_resized = cv2.resize(img, (label_w, label_h))
                img_rgb = cv2.cvtColor(img_resized, cv2.COLOR_BGR2RGB)
                h, w = img_rgb.shape[:2]
                bytes_per_line = 3 * w
                q_image = QtGui.QImage(img_rgb.data, w, h, bytes_per_line, QtGui.QImage.Format_RGB888)
                pixmap = QtGui.QPixmap.fromImage(q_image)
                label.setPixmap(pixmap)
                label.setAlignment(QtCore.Qt.AlignCenter)
            else:
                label.setText("读取失败")
        except Exception as e:
            label.setText("预览失败")

    def show_capture_help(self):
        try:
            help_text = """如果全屏采集异常，请使用默认的窗口化截图采集。\n\n窗口化采集会先截图，再在截图窗口里框选，更稳定。\n\n操作步骤：\n1. 选择窗口化截图采集模式\n2. 点击采集按钮\n3. 切到目标界面后点击确定\n4. 在截图窗口里框选目标区域\n5. 按 Enter 确认或 ESC 取消\n\n全屏透明采集作为备用模式，适合快速采集。"""
            QtWidgets.QMessageBox.information(self, "采集测试说明", help_text)
        except Exception as e:
            self.log(f"显示采集说明失败: {str(e)}")


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

    def take_screenshot(self):
        try:
            pil_img = capture_screen_pil(log_fn=self.log)
            if pil_img is None:
                raise RuntimeError("capture_screen_pil 返回 None")
            rgb = np.array(pil_img.convert("RGB"))
            return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
        except Exception as e:
            self.set_error(f"截图失败: {str(e)}")
            raise

    def find_template_with_score(self, template_name, threshold=0.75):
        template_path = self.get_template_path(template_name)
        if not template_path:
            return {"found": False, "center_x": None, "center_y": None, "score": 0}

        try:
            if not template_path.exists():
                return {"found": False, "center_x": None, "center_y": None, "score": 0}

            try:
                screenshot = self.take_screenshot()
            except Exception as e:
                self.log(f"截图失败: {str(e)}")
                return {"found": False, "center_x": None, "center_y": None, "score": 0}

            try:
                template = cv2.imread(str(template_path), cv2.IMREAD_COLOR)
            except Exception as e:
                self.log(f"读取模板失败: {str(e)}")
                return {"found": False, "center_x": None, "center_y": None, "score": 0}

            if template is None:
                return {"found": False, "center_x": None, "center_y": None, "score": 0}

            res = cv2.matchTemplate(screenshot, template, cv2.TM_CCOEFF_NORMED)
            min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)

            if max_val > threshold:
                h, w = template.shape[:2]
                center_x = max_loc[0] + w // 2
                center_y = max_loc[1] + h // 2
                return {"found": True, "center_x": center_x, "center_y": center_y, "score": max_val}

            return {"found": False, "center_x": None, "center_y": None, "score": max_val}
        except Exception as e:
            self.log(f"模板匹配异常: {str(e)}")
            self.set_error(f"模板匹配异常: {str(e)}")
            return {"found": False, "center_x": None, "center_y": None, "score": 0}

    def find_template_center(self, template_name, threshold=0.75):
        result = self.find_template_with_score(template_name, threshold)
        if result["found"]:
            return (result["center_x"], result["center_y"])
        return None

    def test_template(self, template_type):
        template_map = {
            "input": "input_box_template.png",
            "send": "send_button_template.png",
            "delete": "delete_popup.png",
            "sandbox": "sandbox_button.png",
            "coder_copy": "coder_copy_button.png",
            "gpt_input": "gpt_input_box.png",
            "gpt_send": "gpt_send_button.png"
        }

        template_name = template_map.get(template_type)
        if not template_name:
            self.log(f"未知的模板类型: {template_type}")
            return

        template_path = self.get_template_path(template_name)
        if not template_path or not template_path.exists():
            self.log(f"测试识别 {template_name}: 模板文件不存在")
            self.set_error(f"模板不存在: {template_name}")
            return

        self.log(f"开始测试识别: {template_name}")
        self.clear_error()
        result = self.find_template_with_score(template_name)

        if result["found"]:
            result_str = f"是 (分数:{result['score']:.4f} 坐标:({result['center_x']},{result['center_y']}))"
            self.last_template_result = result_str
            self.log(f"  模板名: {template_name}")
            self.log(f"  是否找到: 是")
            self.log(f"  匹配分数: {result['score']:.4f}")
            self.log(f"  中心坐标: ({result['center_x']}, {result['center_y']})")
            try:
                pyautogui.moveTo(result['center_x'], result['center_y'])
                self.log(f"  鼠标已移动到中心点（未点击）")
            except Exception as e:
                self.log(f"  鼠标移动失败: {str(e)}")
                self.set_error(f"鼠标移动失败: {str(e)}")
        else:
            result_str = f"否 (最高分数:{result['score']:.4f})"
            self.last_template_result = result_str
            self.log(f"  模板名: {template_name}")
            self.log(f"  是否找到: 否")
            self.log(f"  最高匹配分数: {result['score']:.4f}")
            self.log(f"  提示: 分数低于阈值 {0.75}，请检查模板质量")

        self.update_task_status_display()

    def safe_test_paste(self):
        template_path = self.get_template_path("input_box_template.png")
        if not template_path or not template_path.exists():
            self.log("安全测试失败: 输入框模板不存在")
            self.set_error("输入框模板不存在")
            return

        reply = QtWidgets.QMessageBox.question(
            self,
            "安全测试粘贴确认",
            "是否开始安全测试粘贴？\n测试文本将粘贴到输入框，但不会点击发送。",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No
        )

        if reply != QtWidgets.QMessageBox.Yes:
            self.log("安全测试已取消")
            return

        self.log("开始安全测试粘贴...")
        self.clear_error()

        result = self.find_template_with_score("input_box_template.png")
        if not result["found"]:
            self.log("安全测试失败: 未找到输入框")
            self.set_error("未找到输入框")
            return

        input_pos = (result["center_x"], result["center_y"])
        self.log(f"步骤1: 找到输入框，位置: {input_pos}，分数: {result['score']:.4f}")

        try:
            pyautogui.click(input_pos[0], input_pos[1])
            self.log("步骤2: 已点击输入框")
        except Exception as e:
            self.log(f"点击输入框失败: {str(e)}")
            self.set_error(f"点击失败: {str(e)}")
            return

        time.sleep(0.3)

        test_text = "L工具安全测试：如果看到这句话，说明中文粘贴正常。"
        self.log(f"步骤3: 准备粘贴测试文本")

        try:
            if pyperclip:
                pyperclip.copy(test_text)
                self.log("步骤4: 已复制到剪贴板 (pyperclip)")
                pyautogui.hotkey('ctrl', 'v')
                self.log("步骤5: 已使用 Ctrl+V 粘贴")
            else:
                pyautogui.typewrite(test_text)
                self.log("步骤4: 已使用 pyautogui.typewrite 粘贴（不支持中文）")
        except Exception as e:
            self.log(f"粘贴失败: {str(e)}")
            self.set_error(f"粘贴失败: {str(e)}")
            return

        self.log("安全测试完成：文本已粘贴，未点击发送")

    def open_template_directory(self):
        try:
            profile_dir = profile_manager.get_profile_dir()
            if profile_dir and profile_dir.exists():
                os.startfile(str(profile_dir))
                self.log(f"已打开模板目录: {profile_dir}")
            else:
                self.log("模板目录不存在")
                self.set_error("模板目录不存在")
        except Exception as e:
            self.log(f"打开模板目录失败: {str(e)}")
            self.set_error(f"打开目录失败: {str(e)}")

    def click_position(self, pos, offset=0):
        try:
            if pos:
                pyautogui.click(pos[0] + offset, pos[1] + offset)
                return True
        except Exception as e:
            self.log(f"点击位置失败: {str(e)}")
            self.set_error(f"点击失败: {str(e)}")
        return False

    def handle_popup(self):
        result = self.find_template_with_score("delete_popup.png")
        if result["found"]:
            popup_pos = (result["center_x"], result["center_y"])
            if self.click_position(popup_pos):
                self.log("弹窗已自动处理: 点击删除/确认按钮（模板方式）")
                return True

        self.log("模板方式未找到弹窗，尝试关键词方式...")
        keywords_str = self.delete_keywords_input.text().strip()
        if keywords_str:
            keywords = [k.strip() for k in keywords_str.split(",") if k.strip()]
            button_obj = self.find_button_by_keywords(keywords)
            if button_obj:
                try:
                    button_obj.click()
                    self.log(f"弹窗已自动处理: 点击按钮（关键词方式）")
                    return True
                except Exception as e:
                    self.log(f"关键词方式点击失败: {str(e)}")
        else:
            self.log("关键词为空，跳过关键词方式")
        return False

    def find_button_by_keywords(self, keywords):
        if not PYWINAUTO_AVAILABLE:
            self.log("pywinauto 不可用，无法使用关键词识别")
            return None

        try:
            desktop = Desktop(backend="uia")
            windows = desktop.windows()
            for window in windows:
                try:
                    window_title = window.window_text()
                    if window_title:
                        pass
                    buttons = window.children(control_type="Button")
                    for button in buttons:
                        try:
                            button_name = button.window_text()
                            if button_name:
                                for keyword in keywords:
                                    if keyword.lower() in button_name.lower():
                                        self.log(f"找到匹配按钮: '{button_name}' (匹配关键词: '{keyword}')")
                                        return button
                        except Exception:
                            continue
                except Exception:
                    continue
            self.log("未找到匹配关键词的按钮")
            return None
        except Exception as e:
            self.log(f"关键词识别失败: {str(e)}")
            return None

    def copy_coder_result(self):
        self.log("开始复制编程工具结果...")
        self.clear_error()

        template_path = self.get_template_path("coder_copy_button.png")
        if not template_path or not template_path.exists():
            self.log("复制失败: coder_copy_button.png 模板不存在")
            self.set_error("编程复制按钮模板不存在")
            return False

        result = self.find_template_with_score("coder_copy_button.png")
        if not result["found"]:
            self.log(f"复制失败: 未找到编程复制按钮 (最高分数: {result['score']:.4f})")
            self.set_error("未找到编程复制按钮")
            return False

        copy_pos = (result["center_x"], result["center_y"])
        self.log(f"找到编程复制按钮，位置: {copy_pos}，分数: {result['score']:.4f}")

        try:
            pyautogui.click(copy_pos[0], copy_pos[1])
            self.log("已点击编程复制按钮")
        except Exception as e:
            self.log(f"点击编程复制按钮失败: {str(e)}")
            self.set_error(f"点击失败: {str(e)}")
            return False

        time.sleep(0.5)

        try:
            if pyperclip:
                clipboard_text = pyperclip.paste()
                if clipboard_text:
                    preview = clipboard_text[:120] + "..." if len(clipboard_text) > 120 else clipboard_text
                    preview = preview.replace("\n", " ")
                    self.log(f"复制成功！剪贴板内容前120字: {preview}")
                    self.last_template_result = f"复制成功 ({len(clipboard_text)}字符)"
                else:
                    self.log("复制成功，但剪贴板为空")
                    self.last_template_result = "复制成功 (剪贴板空)"
            else:
                self.log("复制成功（无法读取剪贴板，pyperclip未安装）")
                self.last_template_result = "复制成功"
        except Exception as e:
            self.log(f"读取剪贴板失败: {str(e)}")
            self.set_error(f"读取剪贴板失败: {str(e)}")
            return False

        self.update_task_status_display()
        return True

    def paste_to_gpt(self):
        safe_mode = self.gpt_safe_mode_checkbox.isChecked()
        mode_str = "安全模式" if safe_mode else "真实执行模式"
        self.log(f"开始粘贴到ChatGPT... [{mode_str}]")
        self.clear_error()

        template_path = self.get_template_path("gpt_input_box.png")
        if not template_path or not template_path.exists():
            self.log("粘贴失败: gpt_input_box.png 模板不存在")
            self.set_error("ChatGPT输入框模板不存在")
            return False

        result = self.find_template_with_score("gpt_input_box.png")
        if not result["found"]:
            self.log(f"粘贴失败: 未找到ChatGPT输入框 (最高分数: {result['score']:.4f})")
            self.set_error("未找到ChatGPT输入框")
            return False

        gpt_input_pos = (result["center_x"], result["center_y"])
        self.log(f"找到ChatGPT输入框，位置: {gpt_input_pos}，分数: {result['score']:.4f}")

        try:
            pyautogui.click(gpt_input_pos[0], gpt_input_pos[1])
            self.log("已点击ChatGPT输入框")
        except Exception as e:
            self.log(f"点击ChatGPT输入框失败: {str(e)}")
            self.set_error(f"点击失败: {str(e)}")
            return False

        time.sleep(0.3)

        try:
            if pyperclip:
                pyautogui.hotkey('ctrl', 'v')
                self.log("已使用 Ctrl+V 粘贴")
            else:
                pyautogui.typewrite("")
                self.log("已使用 pyautogui.typewrite 粘贴（不支持中文）")
        except Exception as e:
            self.log(f"粘贴失败: {str(e)}")
            self.set_error(f"粘贴失败: {str(e)}")
            return False

        time.sleep(0.2)

        if safe_mode:
            self.log("回传安全模式: 跳过发送（不点击发送，不按Enter）")
        else:
            gpt_send_path = self.get_template_path("gpt_send_button.png")
            if gpt_send_path and gpt_send_path.exists():
                gpt_send_result = self.find_template_with_score("gpt_send_button.png")
                if gpt_send_result["found"]:
                    gpt_send_pos = (gpt_send_result['center_x'], gpt_send_result['center_y'])
                    self.log(f"点击ChatGPT发送按钮，位置: {gpt_send_pos}，分数: {gpt_send_result['score']:.4f}")
                    self.click_position(gpt_send_pos)
                else:
                    self.log("未找到ChatGPT发送按钮，使用 Enter 键")
                    pyautogui.press('enter')
            else:
                self.log("ChatGPT发送按钮模板不存在，使用 Enter 键")
                pyautogui.press('enter')
            self.log("已完成粘贴并发送")

        return True

    def copy_and_paste_to_gpt(self):
        self.log("开始复制并粘贴到ChatGPT...")

        if not self.copy_coder_result():
            self.log("复制步骤失败，停止回传")
            return False

        time.sleep(0.3)

        if not self.paste_to_gpt():
            self.log("粘贴步骤失败")
            return False

        self.log("复制并粘贴到ChatGPT完成")
        return True

    def execute_command(self, cmd):
        global stop_current_task
        stop_current_task = False

        safe_mode = self.safe_mode_checkbox.isChecked()
        mode_str = "安全模式" if safe_mode else "真实执行模式"
        self.current_task_summary = cmd[:50]
        self.update_task_status_display()

        self.log_signal.emit(f"开始执行: {cmd[:80]}... [{mode_str}]")
        self.status_signal.emit(f"状态: 执行中 - {cmd[:30]}...")

        result = self.find_template_with_score("input_box_template.png")
        if not result["found"]:
            self.log_signal.emit("错误: 未找到输入框，无法执行")
            self.set_error("未找到输入框")
            return

        input_pos = (result["center_x"], result["center_y"])
        self.log_signal.emit(f"找到输入框，位置: {input_pos}，分数: {result['score']:.4f}")

        if not self.click_position(input_pos):
            self.set_error("点击输入框失败")
            return

        time.sleep(0.3)

        clean_text = cmd.replace("<<PROMPT>>", "").replace("<<END>>", "").strip()
        self.log_signal.emit("步骤1: 清理指令文本")

        self.log_signal.emit("步骤2: 复制文本到剪贴板")
        try:
            if pyperclip:
                pyperclip.copy(clean_text)
                self.log_signal.emit("步骤3: 使用剪贴板粘贴 (pyperclip)")
                pyautogui.hotkey('ctrl', 'v')
            else:
                self.log_signal.emit("步骤3: 使用 pyautogui 粘贴 (不支持中文)")
                pyautogui.typewrite(clean_text)
        except Exception as e:
            self.log_signal.emit(f"粘贴失败: {str(e)}")
            self.set_error(f"粘贴失败: {str(e)}")
            return

        time.sleep(0.2)

        if safe_mode:
            self.log_signal.emit("步骤4: 安全模式，跳过发送（不点击发送，不按Enter）")
        else:
            send_result = self.find_template_with_score("send_button_template.png")
            if send_result["found"]:
                self.log_signal.emit(f"步骤4: 点击发送按钮，位置: ({send_result['center_x']}, {send_result['center_y']})，分数: {send_result['score']:.4f}")
                self.click_position((send_result['center_x'], send_result['center_y']))
            else:
                self.log_signal.emit("步骤4: 未找到发送按钮，使用 Enter 键")
                pyautogui.press('enter')
            self.log_signal.emit("指令已输入并发送")

        start_time = time.time()
        while running and not stop_current_task:
            self.handle_popup()

            elapsed = time.time() - start_time
            if elapsed > 60:
                sandbox_path = self.get_template_path("sandbox_button.png")
                if sandbox_path and sandbox_path.exists():
                    self.log_signal.emit("执行超时 (60秒)，尝试点击沙箱按钮（模板方式）...")
                    sandbox_result = self.find_template_with_score("sandbox_button.png")
                    if sandbox_result["found"]:
                        self.click_position((sandbox_result['center_x'], sandbox_result['center_y']))
                        self.log_signal.emit(f"已点击沙箱按钮（模板方式），重新开始计时，分数: {sandbox_result['score']:.4f}")
                        start_time = time.time()
                    else:
                        self.log_signal.emit("模板方式未找到沙箱按钮，尝试关键词方式...")
                        keywords_str = self.sandbox_keywords_input.text().strip()
                        if keywords_str:
                            keywords = [k.strip() for k in keywords_str.split(",") if k.strip()]
                            button_obj = self.find_button_by_keywords(keywords)
                            if button_obj:
                                try:
                                    button_obj.click()
                                    self.log_signal.emit("已点击沙箱按钮（关键词方式），重新开始计时")
                                    start_time = time.time()
                                except Exception as e:
                                    self.log_signal.emit(f"关键词方式点击沙箱按钮失败: {str(e)}，继续等待")
                                    time.sleep(1)
                                    start_time = time.time()
                            else:
                                self.log_signal.emit("未找到匹配关键词的沙箱按钮，继续等待")
                                time.sleep(1)
                                start_time = time.time()
                        else:
                            self.log_signal.emit("沙箱关键词为空，跳过关键词方式")
                            time.sleep(1)
                            start_time = time.time()
                else:
                    self.log_signal.emit("超时 60秒，沙箱按钮未采集，跳过")
                    break

            time.sleep(0.5)

        self.log_signal.emit(f"完成执行: {cmd[:80]}...")
        self.status_signal.emit("状态: 等待中")
        self.current_task_summary = "无"
        self.update_task_status_display()

    def process_queue(self):
        global running, pending_execution

        if pending_execution:
            pending_execution = False
            return

        idx = 0
        q = self.get_current_queue()
        while running:
            if not q.empty():
                try:
                    cmd = q.get_nowait()
                except:
                    break
                execution_status[idx] = 'running'
                self.queue_update_signal.emit(cmd, "执行中")
                self.update_task_status_display()

                try:
                    if cmd.startswith("<<PROMPT>>") and cmd.endswith("<<END>>"):
                        self.execute_command(cmd)
                    else:
                        self.log_signal.emit(f"非标准指令，跳过: {cmd[:50]}")
                except Exception as e:
                    self.log_signal.emit(f"执行异常: {str(e)}")
                    self.set_error(f"执行异常: {str(e)}")

                execution_status[idx] = 'done'
                self.queue_update_signal.emit(cmd, "已完成")
                idx += 1
                self.update_task_status_display()
            else:
                time.sleep(0.1)

        self.log_signal.emit("队列处理线程已停止")

    def start_execution(self):
        global running, pending_execution

        template_path = self.get_template_path("input_box_template.png")
        if not template_path or not template_path.exists():
            self.log("错误: 请先采集编程工具输入框模板 (input_box_template.png)")
            self.set_error("输入框模板未采集")
            return

        if running:
            self.log("队列已在执行中")
            return

        self.log("执行前倒计时: 3...")
        self.status_label.setText("状态: 倒计时中")

        for i in [3, 2, 1]:
            if not running:
                self.log("倒计时中断")
                self.status_label.setText("状态: 已停止")
                pending_execution = True
                return
            time.sleep(1)
            self.log(f"执行前倒计时: {i}...")

        self.log("执行前倒计时: 开始！")

        running = True
        stop_event.clear()
        self.thread = threading.Thread(target=self.process_queue)
        self.thread.start()
        self.log("队列执行已启动")
        self.status_signal.emit("状态: 执行中")

    def execute_single(self):
        global running, pending_execution

        template_path = self.get_template_path("input_box_template.png")
        if not template_path or not template_path.exists():
            self.log("错误: 请先采集编程工具输入框模板 (input_box_template.png)")
            self.set_error("输入框模板未采集")
            return

        if running:
            self.log("队列已在执行中")
            return

        q = self.get_current_queue()
        if q.empty():
            self.log("队列为空，无法执行")
            return

        self.log("只执行一条模式")
        pending_execution = False

        self.log("执行前倒计时: 3...")
        self.status_label.setText("状态: 倒计时中")

        for i in [3, 2, 1]:
            if running:
                self.log("倒计时中断")
                self.status_label.setText("状态: 已停止")
                return
            time.sleep(1)
            self.log(f"执行前倒计时: {i}...")

        self.log("执行前倒计时: 开始！")

        running = True
        pending_execution = True
        stop_event.clear()

        def run_single():
            global running
            q = self.get_current_queue()
            if not q.empty():
                try:
                    cmd = q.get_nowait()
                except:
                    running = False
                    pending_execution = False
                    return
                self.queue_update_signal.emit(cmd, "执行中")
                self.update_task_status_display()
                try:
                    self.execute_command(cmd)
                except Exception as e:
                    self.log_signal.emit(f"执行异常: {str(e)}")
                    self.set_error(f"执行异常: {str(e)}")
                self.queue_update_signal.emit(cmd, "已完成")
                self.update_task_status_display()
            running = False
            pending_execution = False
            self.log_signal.emit("只执行一条完成")
            self.status_signal.emit("状态: 等待中")

        self.thread = threading.Thread(target=run_single)
        self.thread.start()
        self.log("单条执行已启动")
        self.status_signal.emit("状态: 执行中")

    def stop_execution(self):
        global running, stop_current_task

        if running:
            running = False
            stop_current_task = True
            self.log("已请求停止当前任务和后续队列")
            self.status_signal.emit("状态: 已停止")
            self.current_task_summary = "已停止"
            self.update_task_status_display()
            self.queue_update_signal.emit("", "已停止")

    def confirm_real_execution(self, action):
        if self.safe_mode_checkbox.isChecked():
            return True

        reply = QtWidgets.QMessageBox.question(
            self,
            "真实执行确认",
            f"当前将{action}，是否继续？",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No
        )

        if reply == QtWidgets.QMessageBox.Yes:
            return True
        else:
            self.log(f"{action}已取消")
            return False

    def one_click_send_to_coder(self):
        cmd = self.command_input.toPlainText().strip()
        if not cmd:
            self.log("错误: 输入指令为空，请先输入提示词")
            self.set_error("输入指令为空")
            return

        profile_dir = profile_manager.get_profile_dir()
        input_template = profile_dir / "input_box_template.png"
        if not input_template.exists():
            self.log("错误: 请先采集编程工具输入框模板")
            self.set_error("输入框模板未采集")
            return

        if not self.confirm_real_execution("真实发送内容到编程工具"):
            return

        wrapped_cmd = self.auto_wrap(cmd)
        self.get_current_queue().put(wrapped_cmd)

        display_text = wrapped_cmd[:80] + "..." if len(wrapped_cmd) > 80 else wrapped_cmd
        self.queue_view.addItem(f"[待执行] {display_text}")
        self.log(f"已加入队列: {display_text}")

        if self.safe_mode_checkbox.isChecked():
            self.log("安全模式: 只粘贴，不发送")
            self.log("请手动检查粘贴内容")
        else:
            self.log("真实执行模式: 准备发送")
            self.start_execution()

        self.update_task_status_display()

    def one_click_return_to_gpt(self):
        profile_dir = profile_manager.get_profile_dir()
        coder_copy_template = profile_dir / "coder_copy_button.png"
        gpt_input_template = profile_dir / "gpt_input_box.png"

        missing_templates = []
        if not coder_copy_template.exists():
            missing_templates.append("编程工具复制按钮")
        if not gpt_input_template.exists():
            missing_templates.append("ChatGPT 输入框")

        if missing_templates:
            self.log(f"错误: 缺少模板: {', '.join(missing_templates)}")
            self.set_error(f"缺少模板: {', '.join(missing_templates)}")
            return

        if not self.confirm_real_execution("回传结果到 ChatGPT"):
            return

        self.copy_and_paste_to_gpt()

    def one_click_safety_drill(self):
        self.log("开始一键安全演练...")
        self.clear_error()

        profile_dir = profile_manager.get_profile_dir()
        key_templates = [
            ("input_box_template.png", "编程工具输入框"),
            ("coder_copy_button.png", "编程工具复制按钮"),
            ("gpt_input_box.png", "ChatGPT 输入框")
        ]

        missing_templates = []
        for template_name, template_desc in key_templates:
            template_path = profile_dir / template_name
            if not template_path.exists():
                missing_templates.append(template_desc)

        if missing_templates:
            self.log(f"演练失败: 缺少关键模板: {', '.join(missing_templates)}")
            self.set_error(f"缺少模板: {', '.join(missing_templates)}")
            return

        self.log("步骤1: 测试识别编程工具输入框")
        self.test_template("input")

        self.log("步骤2: 测试识别编程工具复制按钮")
        self.test_template("coder_copy")

        self.log("步骤3: 测试识别 ChatGPT 输入框")
        self.test_template("gpt_input")

        self.log("步骤4: 执行安全测试粘贴")
        self.safe_test_paste()

        self.log("安全演练完成！")
        self.log("- 已测试模板识别")
        self.log("- 已执行安全粘贴")
        self.log("- 未执行任何危险操作")

    def reset_workflow(self):
        self.log("开始重置当前流程...")

        if running:
            self.stop_execution()

        self.clear_queue()
        self.current_task_summary = "无"
        self.clear_error()

        self.log("当前流程已重置")
        self.update_task_status_display()

    def open_readme(self):
        try:
            readme_path = BASE_DIR / "README_L工具使用说明.txt"
            if readme_path.exists():
                os.startfile(str(readme_path))
                self.log(f"已打开使用说明: {readme_path}")
            else:
                self.log("使用说明文件不存在")
                self.set_error("使用说明文件不存在")
        except Exception as e:
            self.log(f"打开使用说明失败: {str(e)}")
            self.set_error(f"打开使用说明失败: {str(e)}")

    def open_program_directory(self):
        try:
            os.startfile(str(BASE_DIR))
            self.log(f"已打开程序目录: {BASE_DIR}")
        except Exception as e:
            self.log(f"打开程序目录失败: {str(e)}")
            self.set_error(f"打开程序目录失败: {str(e)}")

    def run_system_check(self):
        self.log("=====================================")
        self.log("开始系统自检...")
        self.log("=====================================")
        
        checks = []
        issues = []
        self.diagnostic_data = []
        
        # 检查 Python 版本
        try:
            import sys
            python_version = f"Python {sys.version}"
            self.log(f"✓ Python 版本: {python_version}")
            self.diagnostic_data.append(f"Python 版本: {python_version}")
            checks.append(True)
        except Exception as e:
            self.log(f"✗ Python 版本检查失败: {str(e)}")
            self.diagnostic_data.append(f"Python 版本: 检查失败 - {str(e)}")
            issues.append("Python 版本检查失败")
            checks.append(False)
        
        # 检查当前程序目录
        try:
            program_dir = str(BASE_DIR)
            self.log(f"✓ 当前程序目录: {program_dir}")
            self.diagnostic_data.append(f"当前程序目录: {program_dir}")
            checks.append(True)
        except Exception as e:
            self.log(f"✗ 当前程序目录检查失败: {str(e)}")
            self.diagnostic_data.append(f"当前程序目录: 检查失败 - {str(e)}")
            issues.append("当前程序目录检查失败")
            checks.append(False)
        
        # 检查当前配置
        try:
            profile_name = profile_manager.current_profile
            self.log(f"✓ 当前配置名称: {profile_name}")
            self.diagnostic_data.append(f"当前配置名称: {profile_name}")
            checks.append(True)
        except Exception as e:
            self.log(f"✗ 当前配置检查失败: {str(e)}")
            self.diagnostic_data.append(f"当前配置名称: 检查失败 - {str(e)}")
            issues.append("当前配置检查失败")
            checks.append(False)
        
        # 检查配置目录
        try:
            profile_dir = profile_manager.get_profile_dir()
            if profile_dir:
                self.log(f"✓ 当前配置模板目录: {profile_dir}")
                self.diagnostic_data.append(f"当前配置模板目录: {profile_dir}")
            else:
                self.log("✗ 当前配置模板目录: 未找到")
                self.diagnostic_data.append("当前配置模板目录: 未找到")
                issues.append("当前配置模板目录未找到")
            checks.append(True)
        except Exception as e:
            self.log(f"✗ 当前配置模板目录检查失败: {str(e)}")
            self.diagnostic_data.append(f"当前配置模板目录: 检查失败 - {str(e)}")
            issues.append("当前配置模板目录检查失败")
            checks.append(False)
        
        # 检查 profiles 目录
        try:
            if PROFILES_DIR.exists():
                self.log(f"✓ profiles 目录: 存在 ({PROFILES_DIR})")
                self.diagnostic_data.append(f"profiles 目录: 存在 ({PROFILES_DIR})")
            else:
                self.log(f"✗ profiles 目录: 不存在 ({PROFILES_DIR})")
                self.diagnostic_data.append(f"profiles 目录: 不存在 ({PROFILES_DIR})")
                issues.append("profiles 目录不存在")
            checks.append(True)
        except Exception as e:
            self.log(f"✗ profiles 目录检查失败: {str(e)}")
            self.diagnostic_data.append(f"profiles 目录: 检查失败 - {str(e)}")
            issues.append("profiles 目录检查失败")
            checks.append(False)
        
        # 检查 config.json
        try:
            config_path = profile_manager.get_config_path()
            if config_path:
                if config_path.exists():
                    self.log(f"✓ config.json: 存在 ({config_path})")
                    # 测试读写
                    try:
                        with open(config_path, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                        self.log("✓ config.json: 可读")
                        # 测试写入
                        try:
                            with open(config_path, 'w', encoding='utf-8') as f:
                                json.dump(data, f, ensure_ascii=False, indent=2)
                            self.log("✓ config.json: 可写")
                            self.diagnostic_data.append(f"config.json: 存在且可读写 ({config_path})")
                        except Exception as e:
                            self.log(f"✗ config.json: 可写测试失败: {str(e)}")
                            self.diagnostic_data.append(f"config.json: 可读但不可写 - {str(e)}")
                            issues.append("config.json 不可写")
                    except Exception as e:
                        self.log(f"✗ config.json: 可读测试失败: {str(e)}")
                        self.diagnostic_data.append(f"config.json: 存在但不可读 - {str(e)}")
                        issues.append("config.json 不可读")
                else:
                    self.log(f"✗ config.json: 不存在 ({config_path})")
                    self.diagnostic_data.append(f"config.json: 不存在 ({config_path})")
                    issues.append("config.json 不存在")
            else:
                self.log("✗ config.json: 无法获取路径")
                self.diagnostic_data.append("config.json: 无法获取路径")
                issues.append("config.json 路径获取失败")
            checks.append(True)
        except Exception as e:
            self.log(f"✗ config.json 检查失败: {str(e)}")
            self.diagnostic_data.append(f"config.json: 检查失败 - {str(e)}")
            issues.append("config.json 检查失败")
            checks.append(False)
        
        # 检查依赖
        dependencies = [
            ('PyQt5', 'from PyQt5 import QtWidgets'),
            ('pyautogui', 'import pyautogui'),
            ('OpenCV', 'import cv2'),
            ('numpy', 'import numpy'),
            ('pyperclip', 'import pyperclip'),
            ('pywinauto', 'from pywinauto import Desktop'),
            ('mss', 'from mss import mss'),
            ('Pillow', 'from PIL import Image')
        ]
        
        for name, import_stmt in dependencies:
            try:
                exec(import_stmt)
                self.log(f"✓ {name}: 可用")
                self.diagnostic_data.append(f"{name}: 可用")
                checks.append(True)
            except Exception as e:
                self.log(f"✗ {name}: 不可用 - {str(e)}")
                self.diagnostic_data.append(f"{name}: 不可用 - {str(e)}")
                issues.append(f"{name} 不可用")
                checks.append(False)
        
        # 检查截图能力（mss > ImageGrab > pyautogui）
        try:
            self.log(f"✓ 截图后端可用性: mss={'可用' if MSS_AVAILABLE else '不可用'}; ImageGrab={'可用' if (PIL_AVAILABLE and ImageGrab is not None) else '不可用'}")
            self.diagnostic_data.append(f"截图后端可用性: mss={'可用' if MSS_AVAILABLE else '不可用'}; ImageGrab={'可用' if (PIL_AVAILABLE and ImageGrab is not None) else '不可用'}")

            screenshot_pil = capture_screen_pil(log_fn=self.log)
            if screenshot_pil is None:
                raise RuntimeError("capture_screen_pil 返回 None")
            self.log(f"✓ 屏幕截图: 成功 ({screenshot_pil.size}) 使用后端: {LAST_SCREENSHOT_BACKEND}")
            self.diagnostic_data.append(f"屏幕截图: 成功 ({screenshot_pil.size}) 使用后端: {LAST_SCREENSHOT_BACKEND}")
            checks.append(True)
        except Exception as e:
            self.log(f"✗ 屏幕截图: 失败 - {str(e)} (后端: {LAST_SCREENSHOT_BACKEND})")
            self.diagnostic_data.append(f"屏幕截图: 失败 - {str(e)} (后端: {LAST_SCREENSHOT_BACKEND})")
            issues.append("屏幕截图失败")
            checks.append(False)
        
        # 检查剪贴板
        try:
            test_text = "L工具剪贴板测试"
            pyperclip.copy(test_text)
            clipboard_content = pyperclip.paste()
            if clipboard_content == test_text:
                self.log("✓ 剪贴板: 可读写")
                self.diagnostic_data.append("剪贴板: 可读写")
            else:
                self.log(f"✗ 剪贴板: 内容不匹配 - 期望: '{test_text}', 实际: '{clipboard_content}'")
                self.diagnostic_data.append(f"剪贴板: 内容不匹配")
                issues.append("剪贴板内容不匹配")
            checks.append(True)
        except Exception as e:
            self.log(f"✗ 剪贴板: 测试失败 - {str(e)}")
            self.diagnostic_data.append(f"剪贴板: 测试失败 - {str(e)}")
            issues.append("剪贴板测试失败")
            checks.append(False)
        
        # 检查模板
        templates = [
            "input_box_template.png",
            "send_button_template.png",
            "delete_popup.png",
            "sandbox_button.png",
            "coder_copy_button.png",
            "gpt_input_box.png",
            "gpt_send_button.png"
        ]
        
        template_status = []
        for template in templates:
            try:
                template_path = profile_manager.get_template_path(template)
                if template_path and template_path.exists():
                    self.log(f"✓ 模板 {template}: 已采集")
                    template_status.append(f"{template}: 已采集")
                else:
                    self.log(f"✗ 模板 {template}: 未采集")
                    template_status.append(f"{template}: 未采集")
                    issues.append(f"模板 {template} 未采集")
            except Exception as e:
                self.log(f"✗ 模板 {template}: 检查失败 - {str(e)}")
                template_status.append(f"{template}: 检查失败 - {str(e)}")
                issues.append(f"模板 {template} 检查失败")
        self.diagnostic_data.extend(template_status)
        checks.append(True)
        
        # 检查队列
        try:
            queue_size = self.get_current_queue().qsize()
            self.log(f"✓ 当前队列数量: {queue_size}")
            self.diagnostic_data.append(f"当前队列数量: {queue_size}")
            checks.append(True)
        except Exception as e:
            self.log(f"✗ 队列检查失败: {str(e)}")
            self.diagnostic_data.append(f"当前队列数量: 检查失败 - {str(e)}")
            issues.append("队列检查失败")
            checks.append(False)
        
        # 检查安全模式
        try:
            safe_mode = self.safe_mode_checkbox.isChecked()
            gpt_safe_mode = self.gpt_safe_mode_checkbox.isChecked()
            self.log(f"✓ 安全模式: {'开启' if safe_mode else '关闭'}")
            self.log(f"✓ 回传安全模式: {'开启' if gpt_safe_mode else '关闭'}")
            self.diagnostic_data.append(f"安全模式: {'开启' if safe_mode else '关闭'}")
            self.diagnostic_data.append(f"回传安全模式: {'开启' if gpt_safe_mode else '关闭'}")
            checks.append(True)
        except Exception as e:
            self.log(f"✗ 安全模式检查失败: {str(e)}")
            self.diagnostic_data.append(f"安全模式: 检查失败 - {str(e)}")
            issues.append("安全模式检查失败")
            checks.append(False)

        # 检查关键词设置
        try:
            delete_keywords = self.delete_keywords_input.text().strip()
            sandbox_keywords = self.sandbox_keywords_input.text().strip()
            self.log(f"✓ 删除/确认关键词: {delete_keywords}")
            self.log(f"✓ 后台沙箱关键词: {sandbox_keywords}")
            self.diagnostic_data.append(f"删除/确认关键词: {delete_keywords}")
            self.diagnostic_data.append(f"后台沙箱关键词: {sandbox_keywords}")
            checks.append(True)
        except Exception as e:
            self.log(f"✗ 关键词设置检查失败: {str(e)}")
            self.diagnostic_data.append(f"关键词设置: 检查失败 - {str(e)}")
            issues.append("关键词设置检查失败")
            checks.append(False)

        # 汇总
        self.log("=====================================")
        if issues:
            self.log(f"系统自检发现 {len(issues)} 个问题:")
            for issue in issues:
                self.log(f"  - {issue}")
            self.log("系统自检发现问题，请查看上方详细日志")
            self.set_error(f"系统自检发现 {len(issues)} 个问题")
        else:
            self.log("系统自检通过，可以开始使用")
            self.clear_error()
        self.log("=====================================")

    def save_diagnostic_report(self):
        if not hasattr(self, 'diagnostic_data') or not self.diagnostic_data:
            self.log("错误: 请先执行系统自检")
            self.set_error("请先执行系统自检")
            return
        
        try:
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            report_filename = f"L诊断报告_{timestamp}.txt"
            report_path = BASE_DIR / report_filename
            
            with open(report_path, 'w', encoding='utf-8') as f:
                f.write("L 桥梁工具 - 诊断报告\n")
                f.write("=====================================\n")
                f.write(f"生成时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"L 工具版本: {APP_VERSION}\n")
                f.write("=====================================\n\n")
                
                for item in self.diagnostic_data:
                    f.write(f"{item}\n")
                
                f.write("\n=====================================\n")
                f.write("诊断报告已保存\n")
            
            self.log(f"已保存诊断报告: {report_path}")
            
            # 尝试打开目录
            try:
                os.startfile(str(BASE_DIR))
                self.log(f"已打开报告所在目录: {BASE_DIR}")
            except Exception as e:
                self.log(f"无法打开目录: {str(e)}")
                
        except Exception as e:
            self.log(f"保存诊断报告失败: {str(e)}")
            self.set_error(f"保存诊断报告失败: {str(e)}")

    def create_version_backup(self):
        try:
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            backup_dir = BASE_DIR / "backups"
            
            if not backup_dir.exists():
                backup_dir.mkdir(parents=True, exist_ok=True)
                self.log(f"已创建备份目录: {backup_dir}")
            
            backup_filename = f"l_bridge_tool_gui_{timestamp}.py"
            backup_path = backup_dir / backup_filename
            
            source_path = Path("c:/Users/Lu/Desktop/新建文件夹 (5)/l_bridge_tool_gui.py")
            
            import shutil
            shutil.copy2(source_path, backup_path)
            
            self.log(f"已创建版本备份: {backup_path}")
            
            try:
                os.startfile(str(backup_dir))
                self.log(f"已打开备份目录: {backup_dir}")
            except Exception as e:
                self.log(f"无法打开备份目录: {str(e)}")
                
        except Exception as e:
            self.log(f"创建版本备份失败: {str(e)}")
            self.set_error(f"创建版本备份失败: {str(e)}")

    def init_ui_scale(self):
        try:
            config = profile_manager.load_profile_config(profile_manager.current_profile)
            self.ui_scale = config.get("ui_scale", "medium")
            self.apply_ui_scale()
        except Exception as e:
            self.ui_scale = "medium"
            self.apply_ui_scale()

    def set_ui_scale(self, scale):
        try:
            self.ui_scale = scale
            self.apply_ui_scale()
            config = profile_manager.load_profile_config(profile_manager.current_profile)
            config["ui_scale"] = scale
            config_path = profile_manager.get_config_path(profile_manager.current_profile)
            if config_path:
                with open(config_path, 'w', encoding='utf-8') as f:
                    json.dump(config, f, ensure_ascii=False, indent=2)
            self.log(f"界面缩放已切换为: {scale}")
        except Exception as e:
            self.log(f"切换缩放失败: {str(e)}")

    def apply_ui_scale(self):
        scale_fonts = {
            "small": {"general": 10, "log": 10, "input": 11, "button": 10},
            "medium": {"general": 12, "log": 12, "input": 13, "button": 12},
            "large": {"general": 14, "log": 13, "input": 14, "button": 13}
        }
        fonts = scale_fonts.get(self.ui_scale, scale_fonts["large"])

        general_font = QtGui.QFont("微软雅黑", fonts["general"])
        log_font = QtGui.QFont("Consolas", fonts["log"])
        input_font = QtGui.QFont("微软雅黑", fonts["input"])
        button_font = QtGui.QFont("微软雅黑", fonts["button"])

        QtWidgets.QApplication.instance().setFont(general_font)

        if hasattr(self, 'log_view'):
            self.log_view.setFont(log_font)
        if hasattr(self, 'queue_view'):
            self.queue_view.setFont(general_font)
        if hasattr(self, 'instruction_input'):
            self.instruction_input.setFont(input_font)
        if hasattr(self, 'next_step_label'):
            self.next_step_label.setFont(general_font)

        for widget in QtWidgets.QApplication.instance().allWidgets():
            if isinstance(widget, QtWidgets.QPushButton):
                widget.setFont(button_font)
                if "发送" in widget.text() or "执行" in widget.text() or "演练" in widget.text():
                    widget.setMinimumHeight(38)
                else:
                    widget.setMinimumHeight(34)

        self.update_zoom_button_styles()

    def update_zoom_button_styles(self):
        styles = {
            "small": """
                QPushButton { background-color: #e0e0e0; border: 1px solid #999; padding: 4px 8px; }
                QPushButton:pressed { background-color: #c0c0c0; }
            """,
            "medium": """
                QPushButton { background-color: #d0d0d0; border: 1px solid #888; padding: 5px 10px; }
                QPushButton:pressed { background-color: #b0b0b0; }
            """,
            "large": """
                QPushButton { background-color: #3498db; color: white; border: 2px solid #2980b9; padding: 6px 12px; font-weight: bold; }
                QPushButton:pressed { background-color: #2980b9; }
            """
        }
        style = styles.get(self.ui_scale, styles["large"])
        self.zoom_small_btn.setStyleSheet(style if self.ui_scale == "small" else "")
        self.zoom_medium_btn.setStyleSheet(style if self.ui_scale == "medium" else "")
        self.zoom_large_btn.setStyleSheet(style if self.ui_scale == "large" else "")

    def wizard_init(self):
        try:
            config = profile_manager.load_profile_config(profile_manager.current_profile)
            self.向导_step = config.get("wizard_step", 1)
            self.向导_skipped = config.get("wizard_skipped", False)
            self.向导_safety_drill_done = config.get("wizard_safety_drill_done", False)
            self.wizard_update_display()
            self.update_next_step_hint()
        except Exception as e:
            self.log(f"向导初始化失败: {str(e)}")
            self.向导_step = 1
            self.向导_skipped = False
            self.向导_safety_drill_done = False

    def wizard_steps(self):
        return [
            {
                "step": 1,
                "title": "选择项目配置",
                "description": "请确认当前项目配置，或创建新配置",
                "required": True,
                "completed": True  # 总是完成，因为配置总是存在
            },
            {
                "step": 2,
                "title": "采集编程工具输入框",
                "description": "请点击'执行当前步骤'，然后选择编程工具的输入框",
                "required": True,
                "template": "input_box_template.png"
            },
            {
                "step": 3,
                "title": "采集发送按钮",
                "description": "请点击'执行当前步骤'，然后选择编程工具的发送按钮（可跳过）",
                "required": False,
                "template": "send_button_template.png"
            },
            {
                "step": 4,
                "title": "采集编程工具复制结果按钮",
                "description": "请点击'执行当前步骤'，然后选择编程工具的复制结果按钮",
                "required": True,
                "template": "coder_copy_button.png"
            },
            {
                "step": 5,
                "title": "采集 ChatGPT 输入框",
                "description": "请点击'执行当前步骤'，然后选择 ChatGPT 的输入框",
                "required": True,
                "template": "gpt_input_box.png"
            },
            {
                "step": 6,
                "title": "采集 ChatGPT 发送按钮",
                "description": "请点击'执行当前步骤'，然后选择 ChatGPT 的发送按钮（可跳过）",
                "required": False,
                "template": "gpt_send_button.png"
            },
            {
                "step": 7,
                "title": "执行安全演练",
                "description": "请点击'执行当前步骤'，系统将自动测试所有模板",
                "required": True,
                "safety_drill": True
            },
            {
                "step": 8,
                "title": "完成",
                "description": "向导已完成！现在可以输入提示词并点击一键发送到编程工具",
                "required": True,
                "completed": True  # 最后一步总是完成
            }
        ]

    def wizard_update_display(self):
        try:
            steps = self.wizard_steps()
            if 1 <= self.向导_step <= len(steps):
                step_info = steps[self.向导_step - 1]
                self.向导_step_label.setText(f"当前步骤: {self.向导_step}/{len(steps)} - {step_info['title']}")
                status = "已完成" if self.wizard_step_completed(step_info) else "未完成"
                required = "必须完成" if step_info['required'] else "可跳过"
                self.向导_desc_label.setText(f"{step_info['description']}\n状态: {status} | {required}")
            else:
                self.向导_step_label.setText("向导已完成")
                self.向导_desc_label.setText("您已经完成了所有向导步骤")
        except Exception as e:
            self.log(f"向导更新显示失败: {str(e)}")

    def wizard_step_completed(self, step_info):
        try:
            if 'completed' in step_info and step_info['completed']:
                return True
            if 'template' in step_info:
                template_path = profile_manager.get_template_path(step_info['template'])
                return template_path and template_path.exists()
            if 'safety_drill' in step_info:
                return self.向导_safety_drill_done
            return False
        except Exception:
            return False

    def wizard_prev(self):
        try:
            steps = self.wizard_steps()
            if self.向导_step > 1:
                self.向导_step -= 1
                self.wizard_update_display()
                self.update_next_step_hint()
                self.log(f"向导步骤: {self.向导_step}")
        except Exception as e:
            self.log(f"向导上一步失败: {str(e)}")

    def wizard_next(self):
        try:
            steps = self.wizard_steps()
            if self.向导_step < len(steps):
                current_step = steps[self.向导_step - 1]
                if current_step['required'] and not self.wizard_step_completed(current_step):
                    self.log(f"错误: 第 {self.向导_step} 步是必须完成的")
                    self.set_error(f"请先完成当前步骤")
                    return
                self.向导_step += 1
                self.wizard_update_display()
                self.update_next_step_hint()
                self.wizard_save_status()
                self.log(f"向导步骤: {self.向导_step}")
        except Exception as e:
            self.log(f"向导下一步失败: {str(e)}")

    def wizard_execute(self):
        try:
            steps = self.wizard_steps()
            if 1 <= self.向导_step <= len(steps):
                step_info = steps[self.向导_step - 1]
                
                if self.wizard_step_completed(step_info):
                    self.log(f"第 {self.向导_step} 步已经完成")
                    self.wizard_next()
                    return
                
                if 'template' in step_info:
                    template_name = step_info['template']
                    self.log(f"开始采集模板: {template_name}")
                    # 调用现有的模板采集逻辑
                    if template_name == "input_box_template.png":
                        self.capture_input_box_template()
                    elif template_name == "send_button_template.png":
                        self.capture_send_button_template()
                    elif template_name == "coder_copy_button.png":
                        self.capture_coder_copy_button_template()
                    elif template_name == "gpt_input_box.png":
                        self.capture_gpt_input_box_template()
                    elif template_name == "gpt_send_button.png":
                        self.capture_gpt_send_button_template()
                    
                    # 检查是否完成
                    if self.wizard_step_completed(step_info):
                        self.log(f"模板采集成功: {template_name}")
                        self.wizard_next()
                    else:
                        self.log(f"模板采集失败: {template_name}")
                
                elif 'safety_drill' in step_info:
                    self.log("开始执行安全演练")
                    self.one_click_safety_drill()
                    self.向导_safety_drill_done = True
                    self.wizard_save_status()
                    self.wizard_next()
        except Exception as e:
            self.log(f"向导执行当前步骤失败: {str(e)}")
            self.set_error(f"执行步骤失败: {str(e)}")

    def wizard_skip(self):
        try:
            self.向导_skipped = True
            self.wizard_save_status()
            self.向导_step = len(self.wizard_steps())
            self.wizard_update_display()
            self.update_next_step_hint()
            self.log("向导已跳过")
        except Exception as e:
            self.log(f"向导跳过失败: {str(e)}")

    def wizard_save_status(self):
        try:
            profile_manager.save_profile_config(
                delete_keywords=self.delete_keywords_input.text().strip(),
                sandbox_keywords=self.sandbox_keywords_input.text().strip()
            )
            # 额外保存向导状态
            config_path = profile_manager.get_config_path()
            if config_path:
                config = profile_manager.load_profile_config(profile_manager.current_profile)
                config["wizard_step"] = self.向导_step
                config["wizard_skipped"] = self.向导_skipped
                config["wizard_safety_drill_done"] = self.向导_safety_drill_done
                with open(config_path, 'w', encoding='utf-8') as f:
                    json.dump(config, f, ensure_ascii=False, indent=2)
        except Exception as e:
            self.log(f"向导保存状态失败: {str(e)}")

    def capture_input_box_template(self):
        try:
            self.capture_template("input_box_template.png", "请选择编程工具的输入框")
        except Exception as e:
            self.log(f"采集输入框模板失败: {str(e)}")

    def capture_send_button_template(self):
        try:
            self.capture_template("send_button_template.png", "请选择编程工具的发送按钮")
        except Exception as e:
            self.log(f"采集发送按钮模板失败: {str(e)}")

    def capture_coder_copy_button_template(self):
        try:
            self.capture_template("coder_copy_button.png", "请选择编程工具的复制结果按钮")
        except Exception as e:
            self.log(f"采集编程复制按钮模板失败: {str(e)}")

    def capture_gpt_input_box_template(self):
        try:
            self.capture_template("gpt_input_box.png", "请选择 ChatGPT 的输入框")
        except Exception as e:
            self.log(f"采集GPT输入框模板失败: {str(e)}")

    def capture_gpt_send_button_template(self):
        try:
            self.capture_template("gpt_send_button.png", "请选择 ChatGPT 的发送按钮")
        except Exception as e:
            self.log(f"采集GPT发送按钮模板失败: {str(e)}")

    def update_next_step_hint(self):
        try:
            if not self.向导_skipped and self.向导_step < len(self.wizard_steps()):
                steps = self.wizard_steps()
                step_info = steps[self.向导_step - 1]
                self.next_step_label.setText(f"向导下一步: {step_info['title']} - {step_info['description']}")
                self.next_step_label.setStyleSheet("background-color: #FFF3E0; padding: 10px; border-radius: 5px; font-weight: bold;")
            else:
                # 原来的下一步提示逻辑
                profile_dir = profile_manager.get_profile_dir()
                if not profile_dir:
                    self.next_step_label.setText("下一步：请选择或新建项目配置")
                    self.next_step_label.setStyleSheet("background-color: #E3F2FD; padding: 10px; border-radius: 5px; font-weight: bold;")
                    return

                input_template = profile_dir / "input_box_template.png"
                send_template = profile_dir / "send_button_template.png"
                coder_copy_template = profile_dir / "coder_copy_button.png"
                gpt_input_template = profile_dir / "gpt_input_box.png"

                if not input_template.exists():
                    self.next_step_label.setText("下一步：采集编程工具输入框")
                elif not coder_copy_template.exists():
                    self.next_step_label.setText("下一步：采集编程工具复制结果按钮")
                elif not gpt_input_template.exists():
                    self.next_step_label.setText("下一步：采集 ChatGPT 输入框")
                elif not send_template.exists():
                    self.next_step_label.setText("下一步：建议采集发送按钮，或保持 Enter 发送")
                else:
                    self.next_step_label.setText("下一步：输入提示词，然后点击一键发送到编程工具")
                self.next_step_label.setStyleSheet("background-color: #E3F2FD; padding: 10px; border-radius: 5px; font-weight: bold;")
        except Exception as e:
            self.log(f"更新下一步提示失败: {str(e)}")

if __name__ == "__main__":
    # 设置高 DPI 支持
    QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_EnableHighDpiScaling, True)
    QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_UseHighDpiPixmaps, True)
    
    app = QtWidgets.QApplication(sys.argv)
    gui = BridgeGUI()
    gui.show()
    sys.exit(app.exec_())