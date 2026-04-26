# L 工具核心原型 - 第一部分
import sys
import time
import threading
from queue import Queue
from PyQt5 import QtWidgets, QtGui, QtCore
import pyautogui
import cv2
import numpy as np

# 指令队列和状态管理
command_queue = Queue()
execution_status = {}  # {'id': 'pending/running/done/waiting'}

# GUI 框架
class BridgeGUI(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("L 桥梁工具")
        self.setGeometry(200, 200, 800, 600)
        self.layout = QtWidgets.QVBoxLayout()

        # 指令队列显示
        self.queue_view = QtWidgets.QListWidget()
        self.layout.addWidget(QtWidgets.QLabel("指令队列状态"))
        self.layout.addWidget(self.queue_view)

        # 日志显示
        self.log_view = QtWidgets.QTextEdit()
        self.log_view.setReadOnly(True)
        self.layout.addWidget(QtWidgets.QLabel("操作日志"))
        self.layout.addWidget(self.log_view)

        # 人工干预提示
        self.intervene_label = QtWidgets.QLabel("人工干预提示：无")
        self.layout.addWidget(self.intervene_label)

        self.setLayout(self.layout)

    def log(self, message):
        self.log_view.append(message)

    def update_queue(self):
        self.queue_view.clear()
        for idx, cmd in enumerate(list(command_queue.queue)):
            status = execution_status.get(idx, 'pending')
            self.queue_view.addItem(f"{idx}: {cmd[:50]}... [{status}]")

# 指令识别函数
def is_prompt_command(text):
    return text.startswith("<<PROMPT>>") and text.endswith("<<END>>")

def clean_command_markers(text):
    return text.replace("<<PROMPT>>", "").replace("<<END>>", "").strip()

# 输入框定位与复制粘贴
def find_input_box(screenshot=None, template_path=None):
    if screenshot is None:
        screenshot = pyautogui.screenshot()
        screenshot = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)
    template = cv2.imread(template_path, cv2.IMREAD_COLOR)
    res = cv2.matchTemplate(screenshot, template, cv2.TM_CCOEFF_NORMED)
    min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)
    if max_val > 0.8:
        return max_loc
    return None

# 自动复制粘贴执行指令
def execute_command(cmd_text):
    clean_text = clean_command_markers(cmd_text)
    # 找到输入框位置
    input_pos = find_input_box(template_path='input_box_template.png')  # 模板文件需准备
    if input_pos:
        pyautogui.click(input_pos[0]+5, input_pos[1]+5)
        pyautogui.typewrite(clean_text)
        pyautogui.press('enter')
    else:
        print("未找到输入框，等待下一次尝试")
    # 模拟等待执行
    start_time = time.time()
    while True:
        # 检查输出框是否生成结果
        output_found = True  # TODO: 可用 find_output_box 判断
        if output_found:
            # 复制输出结果
            pyautogui.hotkey('ctrl', 'a')
            pyautogui.hotkey('ctrl', 'c')
            # 返回结果给 ChatGPT
            return
        # 超过60秒无输出 -> 点击后台沙箱按钮
        if time.time() - start_time > 60:
            sandbox_button = find_input_box(template_path='sandbox_button.png')
            if sandbox_button:
                pyautogui.click(sandbox_button[0]+5, sandbox_button[1]+5)
                start_time = time.time()
            else:
                time.sleep(1)
        time.sleep(0.5)

# 弹窗处理（默认删除）
def handle_popup():
    popup_pos = find_input_box(template_path='delete_popup.png')
    if popup_pos:
        pyautogui.click(popup_pos[0]+5, popup_pos[1]+5)

# 队列处理线程
def process_queue(gui):
    idx = 0
    while True:
        if not command_queue.empty():
            cmd = command_queue.get()
            execution_status[idx] = 'running'
            gui.update_queue()
            if is_prompt_command(cmd):
                execute_command(cmd)
                handle_popup()
            execution_status[idx] = 'done'
            gui.update_queue()
            idx += 1
        else:
            time.sleep(1)

# 启动 GUI 和队列线程
if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    gui = BridgeGUI()
    gui.show()
    threading.Thread(target=process_queue, args=(gui,), daemon=True).start()
    sys.exit(app.exec_())