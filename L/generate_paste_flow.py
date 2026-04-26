def find_function(lines, func_name):
    import re
    for i, line in enumerate(lines):
        if re.match(r'^\s*def\s+' + re.escape(func_name) + '\s*\(', line):
            start = i
            indent = len(line) - len(line.lstrip())
            end = len(lines)
            for j in range(i + 1, len(lines)):
                s = lines[j]
                if s.strip() == '':
                    continue
                cur_indent = len(s) - len(s.lstrip())
                if cur_indent <= indent and (s.lstrip().startswith('def ') or s.lstrip().startswith('class ')):
                    end = j
                    break
            return start, end
    return None, None

def find_class(lines, class_name):
    import re
    for i, line in enumerate(lines):
        if re.match(r'^class\s+' + re.escape(class_name) + '\s*', line):
            start = i
            end = len(lines)
            for j in range(i + 1, len(lines)):
                s = lines[j]
                if s.strip() == '':
                    continue
                if not s.startswith(' ') and (s.startswith('class ') or s.startswith('def ')):
                    end = j
                    break
            return start, end
    return None, None

lines = open('l_bridge_tool_gui.py', encoding='utf-8').readlines()

functions = [
    'find_template_with_score',
    'execute_command',
    'one_click_send_to_coder',
    'copy_coder_result',
    'paste_to_gpt',
    'one_click_return_to_gpt',
    'capture_template',
    'read_cv_image_unicode',
    'capture_screen_pil',
    'refresh_template_status',
    'update_preview_image'
]

classes = ['WindowedRegionSelector']

f = open('L_Audit/PASTE_FLOW_EXTRACT.txt', 'w', encoding='utf-8')

for func in functions:
    start, end = find_function(lines, func)
    if start is not None:
        f.write(f'=== def {func} ===\n')
        f.write(''.join(lines[start:end]))
        f.write('\n')
    else:
        f.write(f'=== 未找到：{func} ===\n\n')

for cls in classes:
    start, end = find_class(lines, cls)
    if start is not None:
        f.write(f'=== class {cls} ===\n')
        f.write(''.join(lines[start:end]))
        f.write('\n')
    else:
        f.write(f'=== 未找到：{cls} ===\n\n')

f.close()

print('PASTE_FLOW_EXTRACT.txt generated successfully')