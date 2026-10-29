# 03 · 测试、实际结果与限制

## 复现入口

查看 [真实模型报告](../examples/live/report.json)、[离线报告](../examples/mock/report.json)、[后端 JUnit](../examples/test-results/pytest.xml)、[浏览器报告](../examples/test-results/playwright.json)。真实模型报告中的时间为 UTC；本次最终验证日期为北京时间 2026-10-29。

运行命令、模型配置和环境见 README。评估脚本不加 `--force` 会复核已有记录；加该参数才重新运行。真实输出来自 DeepSeek `deepseek-v4-pro`；每条模型事件记录供应商响应 ID、模型字段和用量（如供应商提供）。

## 题目验收结果

| 场景 | 预期 | 实际材料 |
|---|---|---|
| 正常问题 | 30 天，引用 D01 | [输入](../examples/live/normal/input.json) / [输出](../examples/live/normal/output.json) / [Trace](../examples/live/normal/trace.jsonl) |
| 文档冲突 | 30/15 双方引用，冲突未解决并追问 | [输出](../examples/live/conflict/output.json) / [Trace](../examples/live/conflict/trace.jsonl) |
| 资料外问题 | 不编造年终奖政策 | [输出](../examples/live/outside/output.json) / [Trace](../examples/live/outside/trace.jsonl) |
| 改写问法 | 与正常回答一致 | [输出](../examples/live/paraphrase/output.json) / [Trace](../examples/live/paraphrase/trace.jsonl) |
| 上下文追问 | 正确回答报销材料 | [前置运行](../examples/live/context/prelude.json) / [输入](../examples/live/context/input.json) / [输出](../examples/live/context/output.json) / [Trace](../examples/live/context/trace.jsonl) |
| 检索失败 | incomplete，说明故障，不伪造文档 | [输出](../examples/live/search_failure/output.json) / [Trace](../examples/live/search_failure/trace.jsonl) |
| 读取失败 | 不拿摘要冒充原文 | [输出](../examples/live/read_failure/output.json) / [Trace](../examples/live/read_failure/trace.jsonl) |
| 替换 D01 | 回答随内容改为 45 天 | [快照](../examples/live/changed/snapshot.json) / [输出](../examples/live/changed/output.json) / [Trace](../examples/live/changed/trace.jsonl) |
| 步数上限 | 明确 BUDGET_EXHAUSTED | [输出](../examples/live/budget/output.json) / [Trace](../examples/live/budget/trace.jsonl) |
| 范围不足 | 不套用正式员工远程额度 | [输出](../examples/live/scope/output.json) / [Trace](../examples/live/scope/trace.jsonl) |

最终真实场景自动断言 10/10，Mock 场景 10/10。自动断言覆盖状态、原文一致、目标文档、关键数值、冲突双方、故障观察和预算边界；不把这些有限断言称为所有问题的正确率。

后端测试覆盖 26 个用例（参数化场景计入）：引用伪造/未读/版本/索引、资料替换、工具错误反馈、审核错误上下文、校验后的重新决策、审核拒绝、模型失败不降级、超时、检索冲突保留、非法路径、API 会话/事件/快照、服务重启、并发活跃运行限制。

浏览器测试覆盖正常回答与原文高亮、追问及会话重载、Trace 下载入口、冲突双方、工具失败、手机知识库布局。页面截图为 Mock 运行，不作为真实模型效果证据。

## 动态路径证据

正常路径：检索命中 D01 → 模型读取 D01 → 模型结束 → 审核。

冲突路径：检索命中 D01/D02 → 模型分别读取 → 根据相互矛盾结果输出冲突及追问。没有在执行器中硬编码哪个制度获胜。

资料外路径：模型观察无足够结果后补充/改写查询，仍无资料后报告不足。请以对应 Trace 中的实际参数及动作序列为准。

工具失败路径：本地业务工具故意返回结构化 TOOL_UNAVAILABLE，真实模型看到错误后决定重试/停止，最终提供未完成状态。自动评估额外要求失败路径不能仅靠预算耗尽或总超时“碰巧通过”。

## 开发中发现并修复的问题

1. 短查询“报销”只有一个独立词项，原先的固定至少两项门槛导致 Mock 和接口测试失败。改为按查询词项数设最小命中数，保留回归测试。
2. 初始审核器只接收已读证据，未收到工具错误，误判“工具故障”缺少依据，造成反复修正直到预算耗尽。补充 tool_observations 后重跑真实场景；同时强化评估断言，禁止预算兜底掩盖此错误。
3. 浏览器测试最初点击 Ant Design Select 的透明输入层，被展示文字拦截。改为点击可见选中项，并补充导航可访问名称。
4. 小屏执行记录原在隐藏的侧栏内，增加全宽抽屉入口，引用仍可从回答直接打开。

## 限制

- 样例小、领域窄；没有独立大规模人工标注集，也没有多次随机重复统计。
- 改写召回依赖词项重叠与模型换词；未验证完全无词面交集的所有同义问法。
- 不保留无限会话历史；长会话可能丢失早期信息，必要时需要用户重述。
- 同模型审核存在相关误差，真实 API 有费用、延迟和可用性变化。
- 业务工具是本地实现；故障由场景配置注入，不代表测试过真实企业检索服务的所有故障类型。
- GitHub CI 与本地验证分别记录；没有看到远程运行完成前，不宣称远程 CI 成功。
