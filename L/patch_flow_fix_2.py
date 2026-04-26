from pathlib import Path
import re

p = Path(r"c:\Users\Lu\Desktop\新建文件夹 (5)\l_bridge_tool_gui.py")
s = p.read_text(encoding="utf-8", errors="replace")
backup = p.with_suffix(".py.bak_flow_fix_2")
backup.write_text(s, encoding="utf-8")

s = s.replace("QtWidgets.QMessageBox.Accepted", "QtWidgets.QDialog.Accepted")

def replace_method(src, name, body):
    m = re.search(rf"^    def {re.escape(name)}\b[\s\S]*?(?=^    def |\nclass |\Z)", src, re.M)
    if not m:
        raise RuntimeError(f"找不到方法: {name}")
    return src[:m.start()] + body.rstrip() + "\n\n" + src[m.end():]

one_click_return = r'''
    def one_click_return_to_gpt(self):
        profile_dir = profile_manager.get_profile_dir()
        if not profile_dir:
            self.log("错误: 当前配置目录不存在")
            self.set_error("当前配置目录不存在")
            return

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

        if self.gpt_safe_mode_checkbox.isChecked():
            self.log("回传安全模式: 只粘贴到 ChatGPT，不自动发送")
        else:
            reply = QtWidgets.QMessageBox.question(
                self,
                "真实回传确认",
                "当前将把内容真实发送给 ChatGPT，是否继续？",
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No
            )
            if reply != QtWidgets.QMessageBox.Yes:
                self.log("用户取消真实回传")
                return
            self.log("真实回传模式: 会粘贴并发送给 ChatGPT")

        self.copy_and_paste_to_gpt()
'''

s = replace_method(s, "one_click_return_to_gpt", one_click_return)

p.write_text(s, encoding="utf-8")
print("patch_flow_fix_2 完成")
print("备份:", backup)
