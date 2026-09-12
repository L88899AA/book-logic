# Book Logic

面向 AI 写作的书籍分层提取与证据检索工具。

Book Logic 将 PDF、TXT 和 Markdown 加工为可追溯的观点、案例、论证与写作材料。可复用的 Skill 定义阅读和复核流程，Python CLI 负责来源存储、任务管理、引文校验与检索。

## 核心能力

- **分层提取**：按阅读单元提取材料，逐级构建章节与全书导航。
- **证据追溯**：材料绑定解析版本、物理页或行号，以及精确字符位置。
- **可恢复工作流**：持久化任务状态、输入指纹和不可变成果版本。
- **模型分工与复核**：策略文件指定生成角色，复核记录绑定具体成果版本。
- **检索与导出**：内置关键词检索，可选本地语义检索，支持 JSON 和 Markdown 导出。

CLI 不调用生成模型。阅读、提取和语义复核由支持本地文件与 shell 工具的 AI 宿主执行；安装本项目不包含模型访问权限。

## 安装

要求 Python 3.11+、支持 FTS5 的 SQLite。以下命令适用于 macOS/Linux，在源码目录执行：

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install .
book-logic doctor
```

基础依赖为 `pypdf` 和 `jsonschema`，无需向量模型或 PyTorch。

将 [Book Logic Skill](skills/book-logic/SKILL.md) 注册到 AI 宿主。发行包同时将 Skill 安装到 Python 环境的 `share/book-logic/skills/book-logic`；具体注册方式由宿主决定，CLI 不修改宿主配置。

## 快速开始

### 1. 创建资料库并导入示例

`--library` 指定数据目录，也可通过 `BOOK_LOGIC_LIBRARY` 设置。初始化目标必须为空。

```sh
book-logic --library ./my-library init
book-logic --library ./my-library books add examples/harbor.md
book-logic --library ./my-library books list
```

### 2. 规划阅读任务

将 `BOOK_ID` 替换为导入结果中的书籍 ID。以下映射仅适用于仓库中的港口示例；其他文档需要先确认自己的范围映射。

```sh
book-logic --library ./my-library books map BOOK_ID --file examples/harbor-map.json
book-logic --library ./my-library tasks plan BOOK_ID --policy processing-policy.json
book-logic --library ./my-library tasks next RUN_ID
book-logic tasks schema
```

`RUN_ID` 来自 `tasks plan` 的返回值。示例策略将单元提取分配给 GPT-5.6 Luna，将协调、整合与复核分配给 GPT-6 Astra，并要求全量单元复核。宿主需要提供相应模型；CLI 只验证提交声明，不调度或认证模型。

### 3. 由 AI 宿主处理并提交

宿主依据任务输入、策略和提交 schema 生成 `submission.json`：

```sh
book-logic --library ./my-library tasks submit --file submission.json
book-logic --library ./my-library tasks status RUN_ID
book-logic --library ./my-library verify
```

重复领取尚未提交的任务会返回同一任务，支持跨会话恢复。宿主停止后，CLI 不会在后台继续生成内容。详细协议见 [运行接口](skills/book-logic/references/runtime.md) 和 [加工协议](skills/book-logic/references/processing.md)。

### 4. 检索与导出材料

```sh
book-logic --library ./my-library search '局部改善为何没有改善整体交付' --keywords 'crane gate delivery' --level material
book-logic --library ./my-library read --id MATERIAL_ID
book-logic --library ./my-library materials export MATERIAL_ID --format markdown
```

`MATERIAL_ID` 使用搜索或读取结果中的完整 ID。搜索结果是材料入口；写作前需展开材料并回读原文上下文。

## 可选语义检索

```sh
python -m pip install '.[semantic]'
book-logic --library ./my-library index build --model-path /path/to/local/model
book-logic --library ./my-library search '运输瓶颈' --mode hybrid
```

语义检索使用已有的本地 Sentence Transformers safetensors 模型，不自动下载权重。来源或模型变化后需显式重建索引。关键词检索和分层加工不依赖此功能。

## 校验边界

| 指标或状态 | 含义 |
| --- | --- |
| `accepted` | 提交通过结构、来源与依赖检查 |
| `coverage` | 纳入范围内已接受阅读单元的字符覆盖率 |
| `quality.semantic_review_coverage` | 有版本绑定审阅记录的单元字符覆盖率 |
| `verify` | 来源、证据、覆盖及成果的一致性检查 |

这些指标不认证史实、论证正确性或模型身份。复核仍须检查误归属、重要遗漏、因果跨度与限制条件。输入修订会使依赖成果及复核失效，历史版本保留。

## 限制与数据安全

- 不提供 OCR、自动下载书籍、后台生成服务或视频制作。
- 复杂表格、扫描页和解析异常需要额外检查。
- 本地存储不等于端到端离线：远程 AI 宿主可能处理提供给它的原文片段。
- 书籍、模型权重及派生材料的使用权独立于项目代码许可证。

安全边界见 [SECURITY.md](SECURITY.md)，依赖与设计来源见 [THIRD_PARTY.md](THIRD_PARTY.md)。

## 开发与文档

```sh
python -m pip install -e '.[dev]'
python -m unittest discover -s tests -p 'test_runtime*.py' -v
```

- [仓库结构](DIRECTORY.md)
- [架构与数据契约](docs/design.md)
- [测试与评估](docs/validation.md)
- [贡献指南](CONTRIBUTING.md)

## 许可证

项目代码采用 [MIT License](LICENSE)。
