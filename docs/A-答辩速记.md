# A 智能体答辩速记

当前交付版本：A-1.1，公共合同v1保持不变。

负责人：A（姓名待补）  
基线：文斓前期代码；当前本地合同v1，无Git提交号  
更新时间：2026-10-28（北京时间）  
AI辅助用途：依据代码和实测结果整理讲解稿；本人应运行并理解，不将AI执行说作本人已亲自核验。

## 可以现场展示的过程

运行 python -B demo_agent.py；四轮输入依次为成都3天3000元带老人、第二天下雨、预算2500、少走路。估算为2790、2830、2070、2070。

第一轮给出基础行程；第二轮第2天替换成室内活动；第三轮规则切换经济型方案；第四轮保留成都、3天、老人、2500元和第2天雨天，并记录少走路。本包第四轮尚无真实步行路线变化；A-1.1只记录中性交接轨迹，具体调整/未满足约束由规则的changes/warnings说明，不能把去掉旧警告说成路线已优化。

运行 python -B run_agent_checks.py 可展示44个离线测试方法和原始日志；模型、天气与新增规则接入测试使用测试替身，真实接口与外部B整合仍未验收。

## 六个常见问题

1. 上一轮状态在哪里？调用 agent.turn(text, previous) 的 previous 就是上一轮 result.request。A复制并合并，没有修改的字段保留；新一轮不会改掉旧列表。
2. 大模型做什么？只做可选的需求增量提取，不负责报价格或预报天气。输出JSON先查形状、键、类型和范围，明确本地字段优先。
3. 没Key或模型坏了怎么办？无Key不调用模型；异常最多尝试2次，然后回退本地提取。用户能在extraction_status、warnings和trace看到原因。
4. 天气什么时候查？在需求提取之后、规划规则之前。provider异常由A转为error，daily为空；仍可用用户给的模拟雨天生成行程。
5. 预算由谁算？B的planner计算分项和总额；A检查总额一致性并标预算状态。非成都缺报价时为unverified，total_cost=0只是旧接口占位。
6. 你新增了什么？在文斓已有基线上补了默认确认标记、严格校验、异常隔离、明确预算状态、离线测试和证据。前期价格表、原有四轮基础能力与页面不算A新增。

## 现场指出代码的位置

- contracts.py：TripRequest、assumed_fields、normalized()、AgentResponse新增字段。
- llm.py：_local_extract本地提取、_merge独立副本合并、parse模型校验和重试回退。
- service.py：turn编排；_weather隔离工具异常；调用build_chengdu_plan；生成budget_status和警告。
- tests/test_agent.py：test_four_rounds_retain_state_and_budget、test_bad_json_falls_back、test_weather_exception_does_not_interrupt。

不应宣称：真实API已成功、少走路路线已优化、报价实时、页面完整验收、已完成真实预订/付款/推送，或者团队尚未签收的内容已经签收。
