# A 智能体交付与运行说明

仓库提交上下文：本分支保留根目录B模块不变，新增的travel_agent/rules与tools是A包自带前期基线；A/B当前是独立运行状态，未完成统一接口联调。版本、检查和后续边界见docs/qa/A-v1.1-仓库提交说明.md。

交付版本：A-1.1（2026-10-28）；公共合同 schema_version 仍为 1.0，字段与调用方式不变。新版去除了固定的“B尚未实现少走路”提示，保留规则返回的真实调整/警告；预算下调不再强制要求原已可负担方案降价。44项A离线测试通过，尚非外部B交付的联合验收。

运行演示：`python -B demo_agent.py`；交互输入：`python -B demo_agent.py --interactive`。详细更新、合并范围与未完成项见 `A交付说明-v1.1.md`。

负责人：李可心  
基线： `前期工作.zip`，暂无 Git 提交号  
更新时间：2026-10-28（北京时间）  




## 一键测试并保存证据

```powershell
python -B run_agent_checks.py
```

内部执行 `python -B -m unittest discover -s tests -p test_agent.py -v`，随后运行四轮与失败演示。输出存到 `docs/evidence/agent-checks-日期时间.log`、`agent-checks-latest.json`、`agent-demo.json`。每次检查日志单独保存，失败记录不会被下一次检查覆盖。

测试使用标准库 unittest；`tests/test_agent.py` 也能被 pytest 收集。当前机器未安装 pytest，本次使用 unittest 实测，不能写成 pytest 已通过。

本机已测 Python 3.14.6；源码使用 Python 3.10+ 语法，其他版本尚未实测。

## C 接入方式

```python
from travel_agent import TravelAgent

agent = TravelAgent(live_model=False, live_weather=False)
result = agent.turn("去成都三天，预算3000元，带一位老人")
result = agent.turn("第二天下雨，改成室内行程", result.request)
raw = result.to_dict()
```

界面每轮保存 `result.request`，下一轮作为 `previous` 传回。状态属于当前会话，不能用一个全局 `previous` 共享给多个用户。

新增合同字段：`request.assumed_fields`、`budget_status`、`extraction_status`、`schema_version`。旧字段保留；新增字段都有默认值，旧的构造代码仍可调用。

预算显示必须先判断 `budget_status`：

| 值 | 页面含义 |
|---|---|
| `estimated_within_budget` | 教学估算在预算内，不代表真实报价 |
| `estimated_over_budget` | 教学估算超预算 |
| `unverified` | 报价未核实，不显示零成本、预算余额或“符合预算” |

为兼容旧入口，未核实预算仍保留 `total_cost=0`、`within_budget=False`，该 0 仅是占位。不要只用 `total_cost` 或 `within_budget` 识别未知报价。

保存完整 `result.to_dict()`；若按字段重建 `AgentResponse`，务必带上新增字段，否则会回到安全默认值 `unverified`。载入已有 JSON 可用：

```python
from travel_agent.contracts import AgentResponse, TripRequest, WeatherContext

def restore_response(raw):
    fields = dict(raw)
    fields["request"] = TripRequest(**raw["request"])
    fields["weather"] = WeatherContext(**raw["weather"])
    return AgentResponse(**fields)
```

正常与异常响应完整样例见 `docs/evidence/agent-demo.json`。

## 可选真实模型手测

本次未进行真实 DeepSeek 或真实天气请求。`.env.agent.example` 是空密钥配置示例；仅在你准备真实手测时，将其中内容放入本机 `.env` 并自行填写。密钥不发聊天、不提交仓库。若团队已有 `.env`，合并所需字段即可。

```powershell
python -B demo_agent.py --live
```

此命令只启用模型，天气仍关闭。只有 `extraction_status` 显示实际模型成功，才能记录为真实调用；无 Key 或调用失败会明确显示回退。联网有请求费用，是否执行由你决定；本次未执行。

默认配置 `deepseek-flash`、JSON 输出和关闭 thinking 的参数依据 2026-10-28 查阅的官方文档：[调用入口](https://api-docs.deepseek.com/)、[JSON 输出](https://api-docs.deepseek.com/guides/json_mode/)、[thinking 参数](https://api-docs.deepseek.com/guides/thinking_mode/)。文档核对不等于本机调用成功。单次 HTTP 超时20秒，最多尝试2次；桌面应用真实网络耗时仍需实测。

## 交付范围与限制

A 修改 `contracts.py`、`llm.py`、`service.py`，新增测试、演示、检查脚本及 A 文档。`travel_agent/data/`、`rules/`、`tools/`、`storage/`、`ui/` 来自前期工作，未计为 A 新增实现。

“少走路”已被提取、跨轮保留并交给规则函数。A-1.1使用中性执行轨迹，直接保留B返回的changes/warnings，不固定宣称规则未实现或已成功。本包自带的前期B规则仍未据此减少路线，真实路线变化待B交付；文档中的这项限制仍然有效。七天能够返回结果；长行程重复活动、多位旅客房间数等规则仍需B核对。

没有真实预订、付款、系统推送或报销审批。完整页面、保存导出操作和团队签收尚未验收。详细说明与交接项见 `docs/modules/智能体.md`、`docs/qa/A-交接事项.md`。
