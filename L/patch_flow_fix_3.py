from pathlib import Path
import re

p = Path(r"c:\Users\Lu\Desktop\新建文件夹 (5)\l_bridge_tool_gui.py")
s = p.read_text(encoding="utf-8", errors="replace")
backup = p.with_suffix(".py.bak_flow_fix_3")
backup.write_text(s, encoding="utf-8")

def replace_method(src, name, body):
    m = re.search(rf"^    def {re.escape(name)}\b[\s\S]*?(?=^    def |\nclass |\Z)", src, re.M)
    if not m:
        raise RuntimeError(f"找不到方法: {name}")
    return src[:m.start()] + body.rstrip() + "\n\n" + src[m.end():]

execute_command = r'''
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
            self.log_signal.emit(f"错误: 未找到输入框，最高分数: {result.get('score', 0):.4f}")
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

        if not pyperclip:
            self.log_signal.emit("粘贴失败: pyperclip 不可用，中文粘贴无法保证，请安装 pyperclip")
            self.set_error("pyperclip 不可用")
            return

        try:
            self.log_signal.emit("步骤2: 清空当前输入框")
            pyautogui.hotkey('ctrl', 'a')
            time.sleep(0.1)
            pyautogui.press('backspace')
            time.sleep(0.1)

            self.log_signal.emit("步骤3: 复制文本到剪贴板")
            pyperclip.copy(clean_text)
            time.sleep(0.1)

            self.log_signal.emit("步骤4: 使用 Ctrl+V 粘贴")
            pyautogui.hotkey('ctrl', 'v')
        except Exception as e:
            self.log_signal.emit(f"粘贴失败: {str(e)}")
            self.set_error(f"粘贴失败: {str(e)}")
            return

        time.sleep(0.2)

        if safe_mode:
            self.log_signal.emit("安全模式完成: 已粘贴，不发送，不进入等待循环")
            self.status_signal.emit("状态: 等待中")
            self.current_task_summary = "无"
            self.update_task_status_display()
            return

        send_result = self.find_template_with_score("send_button_template.png")
        if send_result["found"]:
            self.log_signal.emit(f"步骤5: 点击发送按钮，位置: ({send_result['center_x']}, {send_result['center_y']})，分数: {send_result['score']:.4f}")
            self.click_position((send_result['center_x'], send_result['center_y']))
        else:
            self.log_signal.emit(f"步骤5: 未找到发送按钮，最高分数: {send_result.get('score', 0):.4f}，使用 Enter 键")
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
                                    start_time = time.time()
                            else:
                                self.log_signal.emit("未找到匹配关键词的沙箱按钮，继续等待")
                                start_time = time.time()
                        else:
                            self.log_signal.emit("沙箱关键词为空，跳过关键词方式")
                            start_time = time.time()
                else:
                    self.log_signal.emit("超时 60秒，沙箱按钮未采集，结束本次等待")
                    break

            time.sleep(0.5)

        self.log_signal.emit(f"完成执行: {cmd[:80]}...")
        self.status_signal.emit("状态: 等待中")
        self.current_task_summary = "无"
        self.update_task_status_display()
'''

paste_to_gpt = r'''
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

        if not pyperclip:
            self.log("粘贴失败: pyperclip 不可用，无法可靠粘贴中文")
            self.set_error("pyperclip 不可用")
            return False

        try:
            self.log("清空 ChatGPT 输入框")
            pyautogui.hotkey('ctrl', 'a')
            time.sleep(0.1)
            pyautogui.press('backspace')
            time.sleep(0.1)

            pyautogui.hotkey('ctrl', 'v')
            self.log("已使用 Ctrl+V 粘贴")
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
                    self.log(f"未找到ChatGPT发送按钮，最高分数: {gpt_send_result.get('score', 0):.4f}，使用 Enter 键")
                    pyautogui.press('enter')
            else:
                self.log("ChatGPT发送按钮模板不存在，使用 Enter 键")
                pyautogui.press('enter')
            self.log("已完成粘贴并发送")

        return True
'''

s = replace_method(s, "execute_command", execute_command)
s = replace_method(s, "paste_to_gpt", paste_to_gpt)

p.write_text(s, encoding="utf-8")
print("patch_flow_fix_3 完成")
print("备份:", backup)
