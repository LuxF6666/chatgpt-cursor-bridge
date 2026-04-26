# 测试 L 桥梁工具
from l_bridge_tool import command_queue

# 添加测试指令到队列
print("添加测试指令到队列...")
command_queue.put("<<PROMPT>> 测试指令1 <<END>>")
command_queue.put("<<PROMPT>> 测试指令2 <<END>>")
print("测试指令已添加到队列")
print(f"队列中当前指令数: {command_queue.qsize()}")
