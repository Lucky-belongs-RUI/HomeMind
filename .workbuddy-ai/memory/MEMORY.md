# ZHJJ 项目长期约定

## 环境与工具（重要，避免重复摸索）

- **conda 环境**：`langGraph` → `C:\sofeware\Anaconda3\envs\langGraph\python.exe`（Python 3.13.14）
- `conda run -n langGraph python -c "多行代码"` **会失败**（conda 不支持含换行的参数）→ 直接用环境内 python.exe 绝对路径
- **ruff**：在 PATH 上（`C:\sofeware\Anaconda3\Scripts\ruff`），可直接 `ruff check .` / `ruff format .`
- **mypy**：同样在 PATH（1.10.0），但 langgraph 等库缺类型存根，会报大量 `import-not-found`
- **pytest-asyncio 未安装** → 异步测试一律用 `asyncio.run()` 包裹场景函数；不要写 `async def test_*`（会被静默跳过，全绿但没跑）

## 代码规范

- **不建 `pyproject.toml`**：`langgraph.json` 的 `dependencies: ["."]` 会让 langgraph-cli 从本目录依赖定义文件安装；一旦出现 pyproject.toml 就会改从它装（而依赖清单在 requirements.txt），`langgraph dev` 会起不来。工具配置用 `ruff.toml` / `mypy.ini` / `pytest.ini`
- **分层**：SQL 只允许出现在 `homemind/repositories/`；service 层通过 `unit_of_work()` 拿仓库，只写业务规则与事务边界
- **异常**：service 层抛 `homemind/core/exceptions.py` 的领域异常，API 层不写 try/except 转译，由全局 handler 统一处理
- **prompt**：全部集中在 `homemind/prompts/`，带 id/version，用 `.render()`
- **改动前先跑验证**：`pytest` + `python -m evals.runner` + `ruff check .`，三者全绿才算完成

## 编辑经验

- **对含大量中文标点（直引号/全角引号混用）的文件，优先整文件重写，不要用局部 Edit**——精确匹配反复失败，且曾因误删 docstring 首行造成语法错误
- 批量 sed 替换后必须复查残留引用，并立即跑导入冒烟

## 已知待办

- `mypy` 63 项未清理（需先在 mypy.ini 按模块声明 `ignore_missing_imports`）
- 3 个被 git 跟踪但工作区缺失的文件需用户决定：`Agent模块详细设计.md`、`backend/_rag_test.py`、`智能家居大模型体验平台开发文档.md`
- B-8 token 成本计量：用户明确不做
