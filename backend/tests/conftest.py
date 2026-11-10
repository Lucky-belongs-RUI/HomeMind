"""pytest 公共配置。

**设计原则：测试必须零外部依赖。**

不需要 MySQL、不需要 LLM API Key、不需要网络。因此这里只测两类东西：

1. **纯函数**——规则解析、链路计算、密码哈希、限流、reducer 语义；
2. **结构约束**——Agent 图结构、状态字段的 reducer 声明、prompt 注册表。

需要数据库的节点逻辑（意图识别、任务规划、工具执行）由 `evals/` 覆盖，
那里用标准家庭 + 规则引擎做端到端行为验证，不需要真库。
"""

import sys
from pathlib import Path

# 把 backend/ 加入 sys.path，保证 `import homemind.*` 与 `import evals.*` 可用
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
