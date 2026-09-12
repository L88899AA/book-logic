# 测试与评估

测试分为运行时检查、协议回放、检索回归与语义质量评估。结果应关联具体提交、依赖版本与执行环境。

## 安装开发依赖

从源码目录执行，以下命令假定虚拟环境已激活：

```sh
python -m pip install -e '.[dev]'
```

## 运行时测试

```sh
python -W error::ResourceWarning -m unittest discover -s tests -p 'test_runtime*.py' -v
```

测试覆盖来源副本、范围映射、引文定位、任务恢复、版本失效、模型声明、审阅范围及返工限制。测试使用合成文档，不需要用户书库。

可选语义索引测试使用 NumPy 和测试编码器，不下载真实模型：

```sh
python -m pip install numpy
python -m unittest discover -s tests -p 'test_runtime_semantic.py' -v
```

没有 NumPy 时，这组测试会显式跳过。跳过不计为通过，测试编码器的结果也不代表真实模型质量。

## 协议回放与检索回归

目标目录必须为空。重复执行时选择新的目录，避免覆盖上一次结果。

```sh
python examples/replay.py --library .cache/protocol-replay
book-logic --library .cache/protocol-replay verify
python tools/evaluate.py --library .cache/protocol-replay
```

回放使用 [合成港口文档](../examples/harbor.md) 和预先编写的成果，验证任务协议与存储流程，不调用模型生成内容。

[检索回归集](../examples/evaluation.json) 包含查询、人工扩展关键词与预期材料。评估结果仅用于该固定样本上的检索回归，不应解释为跨书泛化准确率或写作质量。

## 语义质量评估

[内容评估样本](../examples/quality-evaluation.json) 提供过度推论、否定遗漏、归属错误及关键内容遗漏等案例。样本包含预期判定，但没有内置的自动模型评审器。

对真实提取流程的评估应分别检查：

1. **证据支持**：引用是否支持主张的全部实质内容。
2. **信息保留**：关键机制、反例、否定与适用条件是否遗漏。
3. **归属准确**：来源陈述、作者解释、引述观点和编辑推论是否区分。
4. **复核有效性**：审阅是否绑定正确版本并覆盖指定原文范围。
5. **总体成本**：包括初提、审阅和返工，而非只记录单次生成成本。

评估报告应记录语料来源、样本选择方式、模型与提示版本、评审标准和人工校准方法。用于调整提示的样本应与最终评估样本区分。

## 发行包验证

```sh
python -m build
python tools/check_distribution.py dist
```

检查器验证包内路径、敏感目录排除，以及 Skill、提交 schema 和策略文件的存在。还应在独立环境中安装 wheel 和 sdist，验证源码目录之外的导入、`book-logic doctor` 和 schema 加载。

发行包检查不覆盖 Git 暂存区、提交历史或额外 release 附件，这些内容需要单独审查。

## 持续集成

[CI 配置](../.github/workflows/ci.yml) 定义 Ubuntu/macOS 与 Python 3.11/3.13 的测试矩阵，执行基础测试、协议回放、关键词评估、打包检查及可选索引测试。平台支持判断以对应提交的执行结果为准，而非仅以配置中存在某个平台为准。
