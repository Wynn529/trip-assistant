# A 智能体源码与调用说明

负责人：李可心；2026-11-08，A-Agent团队集成接收版；公共合同schema_version仍为1.0。

已核对C交接的亲属提取增强、六城编排和Agent工具循环。完整接口、行为及限制见[智能体模块说明](docs/modules/智能体.md)。A独立交付与完整仓库有区别，运行需要团队提供的城市目录、规则和天气模块。

## 调用

```python
from travel_agent import TravelAgent

agent = TravelAgent(live_model=False, live_weather=False)
result = agent.turn("去成都三天，预算3000元，带一位老人")
result = agent.turn("第二天下雨，改成室内行程", result.request)
raw = result.to_dict()

# 可选Agent流程；需要本机配置DEEPSEEK_API_KEY。
agent = TravelAgent(live_model=True, live_weather=False, agent_mode=True)
# result = agent.turn("带着老爸老妈去上海玩三天", previous_request)
```

每个会话独立保存result.request，不在用户之间共享previous。Agent最多8次模型决策轮，工具负责计算，模型决定调用顺序及解释；失败回退固定流程，轨迹显示原因。无密钥时用固定流程，不必配置付费接口即可演示。

## 本轮接收与修复

- 接收C的agent_loop.py及llm.py/service.py改动，保留原49项A测试。
- respond()显式填写schema_version="1.0"；contracts.py字段不变。
- 修复被拦数字仍通过追问显示的问题；补充规划或最终整合异常也进入固定流程回退。
- 检查脚本覆盖全部测试与相关源码、城市JSON校验值；清单引用C的历史真实调用文件，注明来源及本轮未重放。

## 验证与证据

```powershell
python -B run_agent_checks.py
```

2026-11-08，本地Python3.14.6：87项离线测试通过（原A 49、Agent 15、C提取/偏好7、城市16），四轮演示及11个场景完成。见[最新清单](docs/evidence/agent-checks-latest.json)及其日志。

[C保存的三轮真实Agent调用](docs/evidence/agent-live-20261104-224159.json)生成于2026-11-04，天气关闭；它是历史实测材料，本轮未重放，不能声称本次代码已通过真实API复测。

## 合同与边界

成都走build_chengdu_plan；北京、上海、广州、重庆、西安走build_city_plan；未收录城市为budget_status=unverified。C消费完整AgentResponse.to_dict()，不能把total_cost=0占位当成免费。预算为课程样例估算，不含往返大交通实时报价。

固定流程的字段提及检查及本地明确值优先不适用于Agent的update_request；Agent合同校验不能保证语义正确。回复数字检查允许工具结果、用户文字、旧状态、日期及0—31，只能拦截部分词面异常，不保证所有价格、景点及天气表述真实。更详细的失败分支、测试来源与局限见模块说明。
