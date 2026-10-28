# A 智能体交付说明 v1.1

版本：A-1.1  
日期：2026-10-28（北京时间）  
负责人：沿用README-A.md中的A负责人  
公共合同：schema_version=1.0，字段、类、函数签名保持不变  
AI辅助用途：Codex辅助修改、运行离线回归、整理说明与打包；团队签收、实际B联调和真实接口仍待验证。

## 本次修改

| 文件 | 实际变化 |
|---|---|
| travel_agent/service.py | 移除固定的“B尚未实现少走路”警告；使用中性交接轨迹，原样保留规则返回的changes/warnings；非成都明确未执行成都规则 |
| tests/test_agent.py | 不再强制出现旧警告或预算下降必须降价；保留状态/预算一致性断言，增加4项规则接入回归 |
| demo_agent.py | 证据标记delivery_version=A-1.1、contract_schema_version=1.0 |
| run_agent_checks.py | 最新检查清单记录交付版本与合同版本，继续保存日志和源代码SHA256 |
| README-A.md及A模块/进度/答辩/交接文档 | 更新版本、测试数量和提示说明，保留真实限制与前期归属 |
| 给B的修改与联调方案.md | 注明A侧调整已完成，B无需重复修改A文件，剩余B功能和验收待做 |

本次未改contracts.py和llm.py；B/C基线目录data/、rules/、tools/、storage/、ui/没有因本次更新而修改。原压缩包保留，不覆盖旧交付包。

## 验证与证据

44项A离线测试通过；其中新增4项用规则替身验证：

1. B兼容规则返回少走路活动变化后，A保留结果，不再追加过时的未实现警告。
2. 规则报告约束未满足时，A不隐藏警告，也不固定宣称优化成功。
3. 1390元的同一合理方案可以同时满足3000和2500预算；每轮重新调用规则并验证预算状态，无需人为降价。
4. 非成都不会调用成都规划函数，偏好轨迹不会声称执行了该规则。

这些是A兼容行为测试，不代表实际B交付已经完成。最新运行日志、源代码哈希和结果见docs/evidence/agent-checks-latest.json及其log路径；44项测试包含原有40项回归和新增4项。

## 运行方式

在解压后的项目根目录执行：

```powershell
python -B demo_agent.py
python -B run_agent_checks.py
```

无需API密钥或第三方测试依赖。交互聊天：python -B demo_agent.py --interactive。

## 给 B/C 的合并说明

已有A旧版的团队项目：优先合并本次修改的service.py、tests/test_agent.py、demo_agent.py、run_agent_checks.py及更新后的说明文件；公共合同无需改变。B直接按包内《给B的修改与联调方案》提供统一规划/天气接口。

尚未引入A的项目：按README-A.md引入A的contracts.py、llm.py、service.py及TravelAgent导出入口，接入自己的正式B模块；测试和脚本一同引入。

完整运行包中的data/、rules/、tools/、storage/、ui/是用于独立离线运行的前期基线，不是本次B/C新版实现。不要整体覆盖组员已经修改的同名目录。C继续消费统一AgentResponse，按budget_status显示预算，保存完整元数据。

## 未完成与真实性边界

本包自带前期规则仍没有少走路的实际路线优化；去掉固定警告不等于实现了路线变化。B应在自己规则里返回真实changes或未满足的warnings，再联合验收。

实际B交付的calc_budget/get_weather仍需按方案适配；本次没有把它们合并进运行包。真实DeepSeek、真实天气、C页面、保存/导出和团队签收均未以本次更新宣称通过。

不要求B凑旧金额；以其最终数据、方案和复算为准。A已有对模型/天气失败、默认值未确认、非成都未知预算的处理继续保留。
