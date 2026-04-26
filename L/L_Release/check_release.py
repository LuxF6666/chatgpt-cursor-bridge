#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
L 工具发布检查脚本
检查发布目录的完整性和可用性
"""

import os
import sys
import py_compile


def check_file_exists(file_path):
    """检查文件是否存在"""
    return os.path.exists(file_path)


def check_python_available():
    """检查 Python 是否可用"""
    try:
        import sys
        version = f"Python {sys.version.split()[0]}"
        return True, version
    except Exception as e:
        return False, str(e)


def check_compile_python_file(file_path):
    """检查 Python 文件是否能编译通过"""
    try:
        py_compile.compile(file_path, doraise=True)
        return True, "编译通过"
    except Exception as e:
        return False, str(e)


def main():
    """主检查函数"""
    print("=" * 50)
    print("L 工具发布检查")
    print("=" * 50)
    
    # 检查当前目录
    current_dir = os.getcwd()
    print(f"当前检查目录: {current_dir}")
    
    # 检查必要文件
    files_to_check = [
        "l_bridge_tool_gui.py",
        "requirements.txt",
        "start_L.bat",
        "README_L工具使用说明.txt",
        "README_先看我.txt"
    ]
    
    print("\n1. 检查必要文件:")
    all_files_exist = True
    for file in files_to_check:
        exists = check_file_exists(file)
        status = "✓" if exists else "✗"
        print(f"  {status} {file}: {'存在' if exists else '缺失'}")
        if not exists:
            all_files_exist = False
    
    # 检查 Python 可用性
    print("\n2. 检查 Python 可用性:")
    python_available, python_info = check_python_available()
    status = "✓" if python_available else "✗"
    print(f"  {status} Python: {python_info}")
    
    # 检查 requirements.txt
    print("\n3. 检查 requirements.txt:")
    if check_file_exists("requirements.txt"):
        print("  ✓ requirements.txt: 存在")
    else:
        print("  ✗ requirements.txt: 缺失")
    
    # 检查 l_bridge_tool_gui.py 编译
    print("\n4. 检查 l_bridge_tool_gui.py 编译:")
    if check_file_exists("l_bridge_tool_gui.py"):
        compile_ok, compile_info = check_compile_python_file("l_bridge_tool_gui.py")
        status = "✓" if compile_ok else "✗"
        print(f"  {status} 编译: {compile_info}")
    else:
        print("  ✗ l_bridge_tool_gui.py: 缺失，无法编译")
    
    # 检查 profiles 目录
    print("\n5. 检查 profiles 目录:")
    if os.path.exists("profiles"):
        print("  ✓ profiles 目录: 存在")
        # 检查左侧项目和右侧项目
        if os.path.exists("profiles\左侧项目"):
            print("    ✓ 左侧项目: 存在")
        else:
            print("    ✗ 左侧项目: 缺失")
        if os.path.exists("profiles\右侧项目"):
            print("    ✓ 右侧项目: 存在")
        else:
            print("    ✗ 右侧项目: 缺失")
    else:
        print("  ✗ profiles 目录: 缺失")
    
    print("\n" + "=" * 50)
    if all_files_exist and python_available:
        print("🎉 检查通过！L 工具发布包完整可用")
    else:
        print("⚠️  检查未通过，存在缺失或错误")
    print("=" * 50)


if __name__ == "__main__":
    main()