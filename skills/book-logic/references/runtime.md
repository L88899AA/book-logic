# Book Logic 0.1 运行接口

超长成果读取可能返回 `encoding: json_fragment`、`data_text` 和 `next_offset`。按偏移继续读取并拼接，不能把单个片段当完整 JSON 或完整材料。

使用已安装的 `book-logic` 命令，需要本地文件读取与 shell 权限，不依赖某个宿主工具名称。旧 `booklogic.py` 是保留的私人原型，不再是本 Skill 的入口。

## 定位与预检

先运行 `book-logic doctor`。如果只有 Skill 没有运行时，明确告知还需安装 Python 包；不自动修改环境。仓库开发环境可使用该仓库已存在的 `.venv/bin/book-logic`，不得猜测其他项目路径。

资料库由全局 `--library` 参数指定，或读取 `BOOK_LOGIC_LIBRARY`；显式参数优先。命令未指定且环境变量为空时询问资料库位置，不创建隐式默认库。所有下例的大写参数都应来自实际命令输出或已确认文件。

基础运行只需 pypdf、jsonschema 与 SQLite FTS5。MiniLM 单独通过可选依赖提供。无向量依赖不妨碍加工、阅读和关键词检索。

## 命令

全局 `--library` 放在子命令之前。路径参数用安全引用，不将文献内容拼成 shell 命令。

```sh
book-logic doctor
book-logic --library LIBRARY init
book-logic --library LIBRARY books add SOURCE_FILE
book-logic --library LIBRARY books list
book-logic --library LIBRARY books show BOOK_ID
book-logic --library LIBRARY books map BOOK_ID --file MAPPING_JSON
book-logic --library LIBRARY tasks plan BOOK_ID
book-logic --library LIBRARY tasks plan BOOK_ID --policy POLICY_JSON
book-logic --library LIBRARY tasks next RUN_ID
book-logic tasks schema
book-logic --library LIBRARY tasks submit --file SUBMISSION_JSON
book-logic --library LIBRARY tasks status RUN_ID
book-logic --library LIBRARY read --id MATERIAL_OR_ARTIFACT_OR_TASK_ID
book-logic --library LIBRARY read --book BOOK_ID --start FIRST --end LAST
book-logic --library LIBRARY search '主题问题' --keywords 'source language terms' --level material
book-logic --library LIBRARY verify
```

- JSON 输出统一为 `{schema_version, ok, result}`，错误为 `{schema_version, ok, error}`；不要只看退出码就忽略 `ok`。`--help` 和 `--version` 使用普通文本。
- `read` 对 PDF 使用从 1 开始的物理页码；TXT/Markdown 使用行号。字符偏移从 0 开始、右端不包含。不得用阅读器印刷页码代替物理页码。
- 页面读取按 `--max-chars` 限制，检查 `continuation` 并用返回的页/行及 offset 继续。任务依赖列表分页，检查 `next_offset`，用 `read --id TASK_ID --offset N` 读取后续依赖。
- `search` 默认 keyword；用 `--book` 和 `--level source|unit|material|chapter|book` 限定。返回摘要片段，不证明相关性充分，随后回读原文。
- `index build --model-path LOCAL_MODEL` 显式启用本地模型；`search --mode hybrid` 或 `semantic` 才使用向量。失效索引不会在只读查询中自动重建。
- `materials export MATERIAL_ID --format markdown` 返回 JSON 中的 Markdown 文本，不自动向外发布。

书籍元数据、目录候选和解析警告由 `books show` 提供，阅读覆盖由 `tasks status` 提供。SQL 不是正常操作接口。

## 当前重要限制

阅读单元按字符预算切分，与可选 MiniLM 的短向量片段不同。MiniLM 读取实际 max_seq_length；过长查询应拆短，不截断。语义模式只接受已有本地 safetensors 模型，不执行远程模型代码。

关键词检索采用拉丁词语与汉字字符组合；中文问题查英文书时仍应补充源语言关键词。Python CLI 不调用生成模型 API。

一次只处理一个已领取任务。向量构建在 macOS/Linux 使用单写者锁和独立 generation；无网络后台服务。书库结构或计划变化会使依赖成果失效，旧修订保留。

发布必须单独检查实际文件清单和许可，不能把“可以读这本书”当成“可以公开其加工成果”。
