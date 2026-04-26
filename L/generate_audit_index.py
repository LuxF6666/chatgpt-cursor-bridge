lines = open('l_bridge_tool_gui.py', encoding='utf-8').readlines()

keywords = [
    'pyperclip.copy',
    'pyperclip.paste',
    "hotkey('ctrl', 'v')",
    "hotkey(\"ctrl\", \"v\")",
    "press('enter')",
    "press(\"enter\")",
    'typewrite',
    'screenshot',
    'capture_screen_pil',
    'read_cv_image_unicode',
    'find_template_with_score',
    'capture_template',
    'WindowedRegionSelector',
    'one_click_send_to_coder',
    'one_click_return_to_gpt',
    'paste_to_gpt',
    'copy_coder_result',
    'execute_command',
    'safe_mode',
    'gpt_safe_mode',
    'send_button_template.png',
    'gpt_send_button.png',
    'input_box_template.png',
    'gpt_input_box.png',
    'coder_copy_button.png'
]

f = open('L_Audit/AUDIT_INDEX.txt', 'w', encoding='utf-8')
for kw in keywords:
    f.write('--- ' + kw + ' --\n')
    for i, line in enumerate(lines, 1):
        if kw in line:
            f.write('%04d: %s' % (i, line))
f.close()

print('AUDIT_INDEX.txt generated successfully')