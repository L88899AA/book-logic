# 材料与写作约定

## L1 材料
每条材料包含 id/type/title/text/attribution/reasoning/conditions/counterpoints/terms/evidence。
id 只需在本次提交内唯一，使用字母、数字、下划线和短横线；入库后完整 ID 为 artifact_id:local_id。上层和写作引用必须使用完整 ID。

type 为 claim、fact、event、case、statistic、definition、counterexample。
attribution 为 source_statement、author_interpretation、quoted_opinion、editor_inference。
不要把来源中的叙述升级为已独立验证的事实。

每个 evidence 项包含 extraction_id/page/start/end/quote/supports：
- PDF page 为物理页，TXT/Markdown page 为行号。
- start/end 是保存的原文中从 0 开始、右端不含的字符范围。
- quote 必须与该范围完全一致，不能自行去换行或修正拼写。
- supports 说明支持哪个陈述；引用相符仍不证明语义蕴含。

reasoning 是对象数组：每步有 text、attribution、evidence_indices，索引从 0 开始指向该材料的 evidence。材料没有显式推理时使用空数组，不强造因果。
conditions、counterpoints 和 terms 是字符串数组。它们属于材料的一部分，也必须在复核时对照证据。

完整 JSON Schema 以 `book-logic tasks schema` 输出为准，不手工修改 schema 或数据库来绕过校验。现有来源不支持的编辑推论也要引用促成推论的上下文，并明确为 editor_inference。

## 从资料到写作
1. 把写作请求拆成论点、案例、数字、反例和背景需求。
2. 先查 book/chapter/material 层，再通过 read 展开材料和原页。明确检索范围和未加工部分。
3. 对照证据判断可用性；一个最相似的结果也可能不相关。需要时改变源语言关键词。
4. 跨书比较逐个核查来源、时代与概念，一书引述另一书不构成独立佐证。
5. 使用 materials export 导出选定材料，并由宿主 AI 组织材料包或文章。

材料包至少说明：写作问题、可支持论点、案例、反例和限制、原文定位、待补证项及编辑建议的讲述顺序。
正式写作保持事实陈述与编辑分析分界；正文中的重要主张引用具体材料版本和页/行。摘要不是原话，不用引号包装转述。

## 选材判断
先看机制是否完整、证据是否充分，再看是否具体可讲、是否有合理的反直觉张力、能否交代边界。
以文字说明取舍，不用向量分数或预测流量作为质量评分。反直觉不等于新发现，不能未经研究声称首次揭示。
本 Skill 可以按用户要求辅助写文章或脚本，不生成视频、不下载书籍、不自动公开任何资料。
