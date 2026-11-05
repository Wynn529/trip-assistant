# C → A 交接：智能体模块改动说明

交接人：C　接收人：A　日期：2026-11-05（北京时间）  
基线：A v1.2（PR #4，提交 `527033d`）　当前：main 最新提交（推送后由 C 填写：`______`）

本文件说明 C 在 A 负责的 `travel_agent/llm.py`、`travel_agent/service.py` 上做的改动，以及新增的 `travel_agent/agent_loop.py`。所有改动处在代码中以 `# C 补充` / `# C 修改` / `C 新增` 注释标出。**合同字段（`contracts.py`）没有任何改动。**

## 1. 需要 A 做的事（按优先级）

| # | 事项 | 原因 |
|---|---|---|
| 1 | 阅读 `travel_agent/agent_loop.py` 开头说明与本文第 3 节，确认 Agent 模式设计 | 答辩时“哪里用了 Agent”由智能体模块回答 |
| 2 | 重跑 `python -B run_agent_checks.py` 并提交新的 `agent-checks-latest.json` | 现有清单记录的 `llm.py`、`service.py` 校验值是 11-02 20:42 的版本，已过期 |
| 3 | 更新 `docs/modules/智能体.md`：版本、日期、第 2 节改动、Agent 模式流程、失败分支、测试数 | 文档仍停在 10-28，写着“未上传新提交” |
| 4 | 清单中 `real_model_test` 改为引用真实调用证据（见第 5 节） | 真实 DeepSeek 调用已实测成功 |
| 5 | 决定是否在 `respond()` 中填写 `schema_version`（目前页面显示默认值 1.0） | 与 A v1.2 的提交说明不一致 |

## 2. `llm.py` 改动（本地规则提取 + 模型防护）

| 改动 | 作用 | 例子 |
|---|---|---|
| `KNOWN_CITIES` 城市兜底 | 句中没有“去/到”时也能识别目的地；“X出发”的 X 不当目的地；同时提到多城不猜并提示 | “成都，4天” → 成都 |
| 无“预算”字样金额 | 句中只有一个“X元/块”且不是人均、门票、每晚时按预算 | “2500元” → 预算 2500 |
| 列出同行人时不再默认加老人 | 本轮明确了成人/儿童、没提老人、老人仍是默认值 → 老人 0 | “一个大人一个小孩” → 2 人 |
| 总人数 | “我自己/一个人/两个人/3人”按成人计，老人、儿童归 0 | “我自己一个人” → 1 人 |
| 亲属称呼 | 爸妈/父母/爷爷奶奶等计老人；老婆/老公等成人 2；娃/宝宝/儿子/女儿计儿童；“不带爸妈”老人 0 | “带着老爸老妈” → 成人 1、老人 2 |
| `_chinese_number` 省略末位单位 | “两千五”=2500、“一万二”=12000、“三百五”=350；“两千零五”仍为 2005 | — |
| `_field_mentioned` 词表扩充 | 模型理解对的亲属、口语、相对日期不再被防护丢弃；未提到的字段仍然拦截 | “国庆带爸妈……别太累” |
| 老人数随成人/儿童一起采纳 | 模型明确了成人或儿童、老人仍是默认值时，采纳模型给的老人数 | “我跟老婆再带个娃” |

保持不变：规则与模型冲突时以本地规则为准；模型改未提及字段一律忽略；坏 JSON/超时重试 2 次后回退。

## 3. `service.py` 改动

| 改动 | 说明 |
|---|---|
| 按城市数据目录分派 | `find_city(request.city)` 有数据即规划；成都仍调用 `build_chengdu_plan`，其他城市调用 `build_city_plan`；无数据走“未收录城市，未核实”分支（原“非成都”文案改为“未收录城市”） |
| `turn()` 拆分 | `turn()` → `pipeline_turn()`（解析需求）+ `respond(user_text, request, extraction_status, weather=None)`（天气、规划、预算、回复）。**原逻辑逐行保留**，A 的 49 个测试未改动且全部通过 |
| 新参数 `agent_mode=False` | 默认关闭，行为与原版完全一致；为 True 且有密钥时先走 `AgentLoop`，失败返回 None 再走固定流程，并在轨迹首行写“Agent 回退（错误类型）” |

调用方式：

```python
from travel_agent import TravelAgent
agent = TravelAgent(live_model=True, live_weather=False, agent_mode=True)  # 页面中由开关控制
result = agent.turn("带着老爸老妈去上海玩三天", previous_request)
```

## 4. Agent 模式（`agent_loop.py`，C 新增）

**定位**：DeepSeek 负责决策和解释，工具负责计算。价格、天气、行程都由原有代码算出，可复算。

**工具**（OpenAI 兼容 function calling，`tool_choice=auto`，`thinking` 关闭）：

| 工具 | 背后实现 | 返回 |
|---|---|---|
| `update_request` | `llm._merge`（含全部字段校验） | 新需求；非法值返回错误让模型自行改正 |
| `list_cities` | `catalog.supported_cities()` | 收录城市 |
| `get_weather` | `TravelAgent._weather()` | 天气状态与逐日数据 |
| `plan_trip` | `TravelAgent.respond()` | 行程、预算分项、预算状态、超出/剩余金额、调整说明、提示 |
| `try_plan` | `_merge` + `respond()`，不改当前需求 | 试算方案的总价与预算状态 |
| `finish` | — | 回复正文 + 最多 2 条追问 |

**保护与回退**

- 最多 8 步；超过则按当前结果结束（轨迹“Agent 终止”）。
- 模型未调用 `plan_trip`，或规划后又改了需求：系统按最终需求补一次规划（轨迹“Agent 补充”）。
- **回复校验**：回复中出现工具结果、用户原话、日期之外的数字 → 丢弃回复，改用规则模板（轨迹“回复校验”）。
- 网络、HTTP、JSON、工具参数异常 → 返回 None，`TravelAgent` 回退固定流程。
- 不修改传入的 `previous`。

**轨迹格式**（页面“执行轨迹”页签）：`Agent 第N步：调用 工具（参数）→ 结果摘要`，随后是 `回复校验`，再接固定流程原有的约束记忆、天气、数据查询等步骤。`extraction_status` 为 `DeepSeek <模型> Agent 模式：N 次工具调用`。

## 5. 测试与证据

| 项目 | 命令 / 文件 | 结果 |
|---|---|---|
| 全部离线测试 | `python -B -m unittest discover -s tests` | 84 个通过（A 的 49 个 + C 的 35 个） |
| Agent 离线测试 | `tests/test_agent_loop.py`（脚本化假模型） | 12 个：工具驱动、超预算重规划、试算、编造数字拦截、非法参数自纠、忘记规划、失败回退、步数上限、不改 previous、无密钥不调用、默认关闭 |
| 真实调用检查 | `python -B agent_live_check.py --save` | 三轮真实 Agent 调用 |
| 真实调用证据（修复前） | `docs/evidence/agent-live-20261104-214619.json` | 暴露跨天重复、差额被拦两个问题 |
| 真实调用证据（修复后） | `docs/evidence/agent-live-20261104-224159.json` | 第 3 轮：改预算 → 规划超出 460 → 试算 2 天 1560 → 给出方案让用户选；回复校验通过 |

## 6. 已知限制（建议写进智能体.md）

- 关闭 Agent 模式时，模型只做需求提取，回复为规则模板。
- 固定流程中 `generic_ideas`（非收录城市方向建议）仍被丢弃；Agent 模式下由模型在回复中给出。
- Agent 每轮 3–4 次模型调用，实测 3.5–4.5 秒。
- 模型回复偶有错字（实测出现“改成成天”），数值以轨迹和工具结果为准。
- Agent 路径的自动测试使用脚本化假模型，真实模型行为以 `agent-live-*.json` 为证。

## 7. 答辩问答参考

- **哪里用了 Agent？** Agent 模式下 DeepSeek 自主决定调用哪些工具、按什么顺序，并根据工具返回的结果决定下一步，例如发现超预算后主动试算缩短天数，把方案交给用户选择。
- **怎么防止模型编造？** 模型不算数：价格、天气、预算都来自工具；回复中出现工具结果之外的数字会被拦截并改用模板。
- **模型挂了怎么办？** 自动回退固定流程，页面功能不受影响，轨迹首行写明原因。
