# A 智能体源码与调用说明

负责人：李可心  
版本：A-1.2-review，2026-10-28；公共合同schema_version仍为1.0。  
状态：本地待审，尚未上传。本轮按A自身职责审查，不评价仓库中旧B版本。

## 本次内容

本目录只含A的四个包文件、测试、演示/检查脚本、说明、空密钥配置示例和最新测试证据。不包含B的数据/天气/规则源码、C的页面/存储/导出源码、历史评审、其它成员的修改方案或Git操作辅助脚本。

这是供审阅和合并的A源码集合，不是独立完整应用。运行时由团队提供下文约定的规则和天气模块。现有49项A离线测试是在本地既有运行依赖下执行，并对模型、天气和部分规划场景使用测试替身；不代表对B最终交付或完整页面的验收。

## A 的职责和调用

A负责需求提取、跨轮状态、字段校验、工具/规则编排、失败提示和输出合同。

```python
from travel_agent import TravelAgent

agent = TravelAgent(live_model=False, live_weather=False)
result = agent.turn("去成都三天，预算3000元，带一位老人")
result = agent.turn("第二天下雨，改成室内行程", result.request)
raw = result.to_dict()
```

每个会话独立保存result.request；不要在多个用户间共享previous。输入不是字符串时抛TypeError；调用方传入的previous损坏/越界时抛ValueError，页面应提示重置或修复数据。

## 团队模块接口约定

- travel_agent.rules.planner.build_chengdu_plan(request, weather)：返回itinerary, budget_items, total_cost, changes, warnings五项；金额为非负整数，分项之和等于总额。
- travel_agent.tools.weather.fetch_weather(request)：返回同一份contracts.py定义的WeatherContext；ok时逐日date完整，rain_probability为0—100有限数字或None。
- C读取统一AgentResponse.to_dict()，完整保留新增元数据。未知报价时budget_status=unverified，不能将total_cost=0占位解释为零成本。

这些是依赖约定，不是对B旧版的修改要求或完工评价。最终接入应共同复验。

## v1.2 本地修正

1. “出发日期改到2026-11-05”只修改日期，不再把2026误作预算；“预算改到2000元”仍可解析。
2. 模型返回虽类型合法，但本轮未涉及的字段会被忽略，避免重置城市、天数、人数、日期、雨天、偏好或出发地。忽略字段在extraction_status和trace中可见。本地明确字段优先。
3. 保留v1.1中性的少走路交接轨迹，直接展示规则实际返回的changes/warnings；不固定宣称已优化或未实现。
4. 预算下降后，原方案已可负担时允许费用相同；每轮仍调用规则核算并输出正确预算状态。

## 检查与证据

在具备上述依赖的项目根目录运行：

```powershell
python -B -m unittest discover -s tests -p test_agent.py -v
python -B demo_agent.py
python -B run_agent_checks.py
```

本地Python3.14.6实测：49项A离线测试通过，四轮及11个场景生成JSON。测试使用标准库unittest，不要求pytest。最新命令、退出码和源文件SHA256见docs/evidence/agent-checks-latest.json及其指向的原始日志。

## 模型与预算边界

无Key默认离线提取；启用模型但无Key时回退并说明。调用失败最多尝试2次，单次HTTP超时20秒；坏JSON、错误字段类型和范围不会直接覆盖状态。真实DeepSeek本轮未测；.env.agent.example只含变量名和空密钥。

字段提及检查是防止明显跨轮重置的启发式保护，并非完整语义证明。相对日期、所有省略/指代、预算区间、每人预算等表达仍需额外支持和实测，不能保证所有自由表述均能解析。

模型自由文本不作为价格或天气事实。成都预算是规则给出的教学估算，非成都缺报价时为unverified；是否真实满足少走路等约束取决于规则返回的实际结果，不由A凭空保证。
