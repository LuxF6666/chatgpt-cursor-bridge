# chatgpt-cursor-bridge
一个连接 ChatGPT 和 Cursor 的免 API 密钥中间件桥梁工具。
# 🌉 ChatGPT-Cursor-Bridge

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Version](https://img.shields.io/badge/version-1.0.0-green.svg)

## 📖 项目简介

`ChatGPT-Cursor-Bridge` 是一个轻量级的本地中间件/代理服务。它的核心目标是：**打破 API 密钥的限制，让开发者能够以零 API 成本在 Cursor 编程工具中无缝调用 ChatGPT 的强大能力。**

传统的 Cursor 工作流往往依赖昂贵的官方 API，而本工具通过特定的桥接技术（如 Web 代理或无头浏览器模拟等），在本地建立一个兼容 OpenAI API 格式的服务器，直接将 Cursor 的请求转发至 ChatGPT 网页端/逆向服务端，并将结果回传给 Cursor 进行代码生成与自动化操控。

## ✨ 核心特性

- **🆓 完全免 API Key**：直接利用已有账号的网页对话能力，无需购买或配置官方 API 密钥。
- **🔌 协议完美兼容**：在本地模拟标准的 OpenAI API 接口 (`/v1/chat/completions`)，骗过 Cursor 的接口检查。
- **🤖 自动化代码操控**：完美支持 Cursor 的 `Ctrl+K` (代码生成) 和 `Ctrl+L` (对话聊天) 等核心交互功能。
- **⚡ 极速本地部署**：轻量级架构，支持多环境快速启动，占用本地资源极小。

## 🛠️ 工作原理

1. 启动本程序后，将在本地（例如 `http://127.0.0.1:8000`）开启一个监听服务。
2. 在 Cursor 中将大语言模型的接口地址（Base URL）修改为本地地址。
3. Cursor 发出的所有代码解析和生成请求，都会被本工具拦截，并转化为针对 ChatGPT 的免 API 访问请求。
4. 获取到 ChatGPT 的响应后，本工具将其包装回标准格式，返回给 Cursor。

---

## 🚀 安装与运行指南

### 1. 环境准备
确保你的本地环境已安装以下依赖：
- Python 3.8 或以上版本 (推荐使用 Miniconda/Anaconda 管理环境)
- Git

### 2. 克隆项目到本地
```bash
git clone [https://github.com/你的用户名/chatgpt-cursor-bridge.git](https://github.com/你的用户名/chatgpt-cursor-bridge.git)
cd chatgpt-cursor-bridge
