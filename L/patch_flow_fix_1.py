from pathlib import Path
import re

p = Path(r"c:\Users\Lu\Desktop\新建文件夹 (5)\l_bridge_tool_gui.py")
s = p.read_text(encoding="utf-8", errors="replace")
backup = p.with_suffix(".py.bak_flow_fix_1")
backup.write_text(s, encoding="utf-8")

def replace_method(src, name, body):
    m = re.search(rf"^    def {re.escape(name)}\b[\s\S]*?(?=^    def |\nclass |\Z)", src, re.M)
    if not m:
        raise RuntimeError(f"找不到方法: {name}")
    return src[:m.start()] + body.rstrip() + "\n\n" + src[m.end():]

one_click = r'''
    def one_click_send_to_coder(self):
        cmd = self.command_input.toPlainText().strip()
        if not cmd:
            self.log("错误: 输入指令为空，请先输入提示词")
            self.set_error("输入指令为空")
            return

        profile_dir = profile_manager.get_profile_dir()
        if not profile_dir:
            self.log("错误: 当前配置目录不存在")
            self.set_error("当前配置目录不存在")
            return

        input_template = profile_dir / "input_box_template.png"
        if not input_template.exists():
            self.log("错误: 请先采集编程工具输入框模板")
            self.set_error("输入框模板未采集")
            return

        if not self.safe_mode_checkbox.isChecked():
            if not self.confirm_real_execution("真实发送内容到编程工具"):
                return
            self.log("真实执行模式: 会粘贴并发送")
        else:
            self.log("安全模式: 只粘贴，不发送，但仍会执行粘贴流程")

        wrapped_cmd = self.auto_wrap(cmd)
        self.get_current_queue().put(wrapped_cmd)

        display_text = wrapped_cmd[:80] + "..." if len(wrapped_cmd) > 80 else wrapped_cmd
        self.queue_view.addItem(f"[待执行] {display_text}")
        self.log(f"已加入队列: {display_text}")

        if not self.running:
            self.start_execution()
        else:
            self.log("队列已在执行中，本条任务会按顺序处理")

        self.update_task_status_display()
'''

s = replace_method(s, "one_click_send_to_coder", one_click)

fix_methods = {
"capture_input_box_template": '    def capture_input_box_template(self):\n        self.capture_template("input")\n',
"capture_send_button_template": '    def capture_send_button_template(self):\n        self.capture_template("send")\n',
"capture_coder_copy_button_template": '    def capture_coder_copy_button_template(self):\n        self.capture_template("coder_copy")\n',
"capture_gpt_input_box_template": '    def capture_gpt_input_box_template(self):\n        self.capture_template("gpt_input")\n',
"capture_gpt_send_button_template": '    def capture_gpt_send_button_template(self):\n        self.capture_template("gpt_send")\n',
}

for name, body in fix_methods.items():
    if re.search(rf"^    def {re.escape(name)}\b", s, re.M):
        s = replace_method(s, name, body)

p.write_text(s, encoding="utf-8")
print("patch_flow_fix_1 完成")
print("备份:", backup)
