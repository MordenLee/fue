# FUE Core

独立的本地资料、聊天记忆与研究服务。默认监听本机动态端口，Studio 和 Skill 通过数据目录中的实例信息连接。

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
python main.py --data-dir <已有数据目录>
# 首次初始化空目录需明确指定：
python main.py --data-dir <新数据目录> --init
# 查询不会自动创建目录：
python fue.py --data-dir <已有数据目录> status --json
# 按需启动并查询：
python fue.py --data-dir <已有数据目录> --auto-start libraries list --json
```

开发环境默认继续使用仓库的 `backend/` 数据目录；安装版继续使用原来的用户数据目录。`main.py` 是兼容启动入口，实际服务入口为 `fue_core.server`。使用 `pip install .` 可安装 `fue` 与 `fue-core` 命令。

Core 每个数据目录只允许一个实例。Studio 持有期间保持运行；无 Studio、无任务且空闲五分钟后退出。`python fue.py --data-dir <目录> core keep-alive --enabled true` 可选择常驻。

API 使用本地认证；Studio 保留旧接口，Agent 使用 [v1 外部契约](../contracts/core-v1.md)。研究任务需要显式模型和资料范围，不导入宿主历史。业务内部包名暂保留 `knowledge`、`chat`、`memory` 等，以降低迁移对原实现的影响。

测试：在仓库根目录运行 `.venv/Scripts/python -m unittest discover -s fue-core/tests -v`。独立 HTTP 检索测试为 `fue-core/scripts/smoke_core_split.py`，使用合成资料，不调用付费模型。
