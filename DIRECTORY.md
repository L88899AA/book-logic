# 仓库结构

## 源码与工程文件

| 路径 | 职责 |
| --- | --- |
| `src/book_logic/` | CLI、来源解析、任务状态、持久化、校验与检索 |
| `src/book_logic/schemas/` | 提交数据的 JSON Schema |
| `skills/book-logic/` | AI 宿主的工作规范与参考协议 |
| `processing-policy.json` | 模型角色及语义复核策略示例 |
| `tests/` | 运行时与可选语义检索的自动化测试 |
| `examples/` | 合成文档、映射、回放成果与评估样本 |
| `tools/` | 检索评估与发行包检查工具 |
| `docs/` | 架构、数据契约及验证流程 |
| `.github/workflows/` | 持续集成配置 |
| `pyproject.toml` | 包元数据、依赖、命令入口与安装资源 |
| `MANIFEST.in` | 源码发行包的包含与排除规则 |

运行时与 Skill 分别负责确定性处理和 AI 工作流程。修改任一侧的数据契约时，应同步检查另一侧及相关测试。

## 数据与生成物

资料库通过 `--library` 或 `BOOK_LOGIC_LIBRARY` 显式指定，不要求位于仓库内。

以下目录名保留用于开发工作，不随仓库或发行包分发：

| 路径 | 约定用途 |
| --- | --- |
| `workspace/` | 用户数据、资料库与加工输出 |
| `archive/` | 不参与构建的历史资料 |
| `.cache/` | 可重建的测试与构建输出 |
| `.venv/` | Python 虚拟环境 |

构建工具生成的 `build/`、`dist/`、`*.egg-info/`，以及 Python 的 `__pycache__/` 均属于生成物。Git 忽略规则见 [.gitignore](.gitignore)，发行包排除规则见 [MANIFEST.in](MANIFEST.in)。

## 持久化边界

- SQLite 保存任务状态、成果版本及证据关系。
- 原文副本和解析版本用于校验与回溯。
- 向量索引可以重建，不替代原文与成果。
- JSON 提交文件和 Markdown 导出不是独立的状态源；是否通过处理与复核，以资料库记录为准。

对外提交应包含源码、公开文档和具有分发许可的测试样本，不包含用户资料库、模型权重或执行日志。
