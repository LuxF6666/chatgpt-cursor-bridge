import re

lines = open('l_bridge_tool_gui.py', encoding='utf-8').readlines()

f = open('L_Audit/FUNCTION_LIST.txt', 'w', encoding='utf-8')

for i, line in enumerate(lines, 1):
    line = line.strip()
    if line.startswith('class '):
        match = re.match(r'class\s+(\w+)', line)
        if match:
            class_name = match.group(1)
            f.write(f'class {class_name}: {i}\n')
    elif line.startswith('def '):
        match = re.match(r'def\s+(\w+)', line)
        if match:
            func_name = match.group(1)
            f.write(f'def {func_name}: {i}\n')

f.close()

print('FUNCTION_LIST.txt generated successfully')