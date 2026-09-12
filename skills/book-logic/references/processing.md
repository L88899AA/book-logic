# 分层加工协议

## 范围和阅读预算

`books add` 只解析与复制来源，不表示已精读。用 `books show` 检查目录、版本、解析警告，必要时查看原 PDF。准备 mapping JSON 数组，每项含 `title/start/end/kind`；kind 可为 body、preface、conclusion、notes、bibliography、index、blank、other。范围必须按序覆盖每一页或行且不重叠；排除项必须有 reason。

默认纳入 body/preface/conclusion。注释按论证需要跟读，并以原文引用关联材料。不要把疑似扫描的正文标成 blank；修复来源前应报告无法覆盖。TXT 空行只是正常文本分隔，不是扫描警告。

确认映射后运行 `tasks plan`。默认每单元主体最多 8000 Unicode 字符、前后边界上下文各最多 800 字符，不是固定 token 数。可通过 `--unit-chars`/`--context-chars` 调整。改变映射或计划配置会使旧运行和依赖成果失效，但保留历史；不要在只读查询中重新规划。

先报告任务数量与加工范围。不硬编码美元费用，不承诺一次对话完成长书。已经获准的范围按预算持续处理，不每单元重复请求许可。

## 领取与提交

1. `tasks next RUN_ID` 领取一个任务；未提交任务会被重新返回。只以数据库状态作为进度依据。
2. 首次提交前读取 `tasks schema`，使用 schema_version=1。阅读单元输入来自 payload.spans，边界上下文不重复计覆盖。
3. 按任务 kind 处理，保存提交草稿 JSON：`schema_version/task_id/input_hash/result`。input_hash 原样使用，不能自行更改。
4. `tasks submit --file FILE` 执行结构、来源及依赖校验。相同结果重复提交是幂等操作；不同内容需 `tasks reopen TASK_ID` 后提交新修订。
5. 校验错误第一次出现后最多修正两次；第三次失败任务转为 blocked。检查具体错误，不通过删除证据或标成背景绕过失败。需要修复时用 reopen 恢复，遇到不可读来源用 `tasks block TASK_ID --reason ...` 记录。

CLI 不自动写草稿，也不运行生成模型。宿主 AI 停止时任务暂停。上下文紧张时保存当前成果和 run_id，下一会话继续 next，不用记忆补造处理进度。

## 各层任务

### unit：保留可复用内容

逐个处理主体 span。每个 span 必须在 coverage 中出现一次，并标为 extracted 或 background，附理由。unreadable 会阻止接受，不能计为完成。

提取事实、主张、事件、案例、数字、定义、反例，保留成立条件与作者保留意见，不只筛选精彩材料。历史叙述不要强行转成作者命名的决策方法。材料结构见 cards.md。

每项证据用来源中的精确字符位置及短引；表格和数字必要时查看原 PDF。相关尾注可用 read 读取同一本书的其他页，再加入 evidence。无法定位的注释、指代和跨节论证放入 open_questions，不编造答案。

### chapter：整合而非再次压缩

任务输入为所有已接受 unit 成果的索引。完整翻页读取 inputs，再用 read 按 ID 展开需要的内容。输出 input_ids 必须包括所有当前输入 artifact ID。

恢复本章问题、主张、原因、证据与后果；合并重复材料但保留引用，矛盾与反例不得删除。每条 claims、topics 使用真实完整 material ID。input 的 open_questions 必须通过 resolved_questions（task_id/question/answer/material_ids）解释，或明确保留在 unresolved。

### review：回原文检查

检查 required_review_tasks 列出的目标整合任务和阅读单元。有 processing_policy 的首版运行全量复核；无策略的 legacy 运行保持自动数字风险、AI 风险和未解决问题全部复核，其他单元固定种子抽样 10%、每章至少一项。模型分配、审阅版本与质量状态见 quality.md。

将原文与成果对照，检查重要遗漏、数字范围、归属、反例、因果跨度，不把格式校验当语义审阅。reviewed_task_ids 只写真正复核过的任务。

发现问题时 decision=revise，findings 指向需要修正的任务并描述问题；该复核阻塞且之后扩大为全章复核。先 reopen 出问题的下层任务并修订，再重新生成失效的整合和复核成果。只 reopen review 而不修正其输入不能解决来源问题。

decision=pass 必须没有未解决 findings，目标整合也不能仍有 unresolved。通过表示这次宿主 AI 的复核，不是假装获得独立人工或跨书事实审查。

### book：构建导航

全部章节复核通过后，按章节索引逐步读取，整合全书主线、主题入口和章节关系。input_ids 使用 chapter artifact ID（不是 review ID）。重要概括通过 claims/material_ids 回到材料；topics 用术语和材料 ID 建立入口。不要抹掉底层成果。

全书整合之后还需一次 book review。中间状态可以用于有边界的写作，但不得称为全书已完成。

## 完成报告

报告 `tasks status` 的处理覆盖率、阻塞项、排除范围和 `verify` 结果。说明本次 AI 实际复核范围；coverage=1 只说明主体范围的任务已接受，run complete 才说明整合及规定复核完成，二者都不保证知识无损提取。
