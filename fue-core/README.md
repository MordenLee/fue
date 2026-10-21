# Python 后端

基于 **FastAPI** 的后端服务，监听 `http://127.0.0.1:8000`。

## 安装依赖

1. 安装 Python 3.11+（推荐从 [python.org](https://www.python.org/downloads/) 下载，**不要用 Microsoft Store 版本**）
2. 创建并激活虚拟环境：

```bash
python -m venv venv
# Windows
.\venv\Scripts\Activate.ps1
# macOS/Linux
source venv/bin/activate
```

3. 安装依赖：

```bash
pip install -r requirements.txt
```

## 运行

```bash
python main.py
```

API 文档：`http://127.0.0.1:8000/docs`
