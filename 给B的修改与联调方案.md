# 给 B 的修改与联调方案

提出方：A；方案由 Codex 根据双方现有代码辅助整理  
日期：2026-10-28（北京时间）  
状态：待执行。本文件是待办和验收约定，不代表修改或测试已经完成。

版本更新：A-1.1已完成第五区段的A侧提示与测试调整，并通过44项离线测试。B领取新版A包后，无需重复修改A的service.py或tests/test_agent.py；本方案其余B功能、统一接口和联合验收仍待执行。

## 一、目标与执行原则

请 B 在一个独立分支中完成数据规则模块及与 A 的兼容调整，提交一个可审查的 PR。A侧提示与测试已在A-1.1完成，B直接以新版为基底接入自己的正式模块，不必重复更改A代码。

公共接口以当前 A 交付包中的 travel_agent/contracts.py 为统一合同，不另建一套 TripRequest/WeatherContext/AgentResponse，也不要求 C 改成消费 B 的独立费用字典。

请同时领取“当前 A 交付包”和本方案。A 的运行包已包含可工作的前期天气/规划代码，可以在这份工作目录上完善 B 模块，保留 B 已完成的估算依据、预算计算和来源表。合并团队仓库时保留其他成员的新改动，先看差异，不以整个文件夹覆盖团队最新版。

B 现有 calc_budget(...)、get_weather(...) 可以保留为内部函数，但对外必须提供本文第三区段的接口。只加参数包装不足以补齐缺失的行程、天气日期和规则逻辑。

## 二、允许修改的范围

| 文件 | 操作 |
|---|---|
| travel_agent/data/chengdu.json | B维护数据和教学估算标签，按现有工作包schema扩展 |
| travel_agent/rules/planner.py | B完成完整规划与费用函数，保留load_chengdu_data供现有测试调用 |
| travel_agent/tools/weather.py | B实现统一天气接口、日期判断、失败处理和可替换网络访问 |
| tests/test_rules.py、tests/test_weather.py | 新增B的离线规则/天气测试 |
| docs/modules/数据规则.md | 按实际实现更新，不写未实现的规则为已完成 |
| docs/qa/数据来源表.md、预算复算.md | 更新来源、适用条件、当前程序输出和复算 |
| travel_agent/service.py | A-1.1已完成第五区段，B沿用新版，不必重复修改；其余A编排、校验、预算状态保留 |
| tests/test_agent.py | A-1.1已调整旧断言并新增回归，B运行验证，不删减实质验收 |
| docs/qa/AB-联调记录.md | 新增联调结果、修改文件、证据、限制和签收栏 |

本次不改 travel_agent/contracts.py、travel_agent/llm.py 的公共合同和提取逻辑，不覆盖 C 的 app.py、README.md、storage/、ui/。如实施中确实需要额外合同变化，先列出具体原因和影响，不静默改名或新增必填字段。

根目录原有 planner.py/weather.py/chengdu.json 不作为正式应用调用入口；需要保留时标记为旧版/内部演示，避免两套数据分别生效。

## 三、必须对齐的对外接口

### 3.1 共用请求对象

```python
from travel_agent.contracts import TripRequest, WeatherContext
```

直接使用 request.city、start_date、days、budget、adults、elderly、children、travelers、pace、rain_days、preferences、origin。保留 assumed_fields，不把默认成都/老人当作用户已确认。

注意：normalized() 返回新副本，调用时应写 request = request.normalized()；不要依赖原地修改，不修改传入对象及其列表。合法范围以现有合同为准：days为1—7，budget为0—100000整数，各类人数为0—10，合计至少1人。

### 3.2 规划接口

在 travel_agent/rules/planner.py 提供：

```python
def build_chengdu_plan(
    request: TripRequest,
    weather: WeatherContext,
) -> tuple[list[dict], list[dict], int, list[str], list[str]]:
    # 实际实现后返回以下五项，顺序不能改变。
    return itinerary, budget_items, total_cost, changes, warnings
```

返回要求：

- itinerary：长度为 request.days，每天包含 day、date、rainy、rain_source、activities、note。day从1开始；date为用户指定出发日期推算的ISO日期，未指定为""。排期日期可由用户出发日期计算，不等于已有真实天气预报。
- activities：活动列表；每项至少包含 id、name、indoor、elderly_friendly、price_per_person、area、duration_hours。费用为整数估算，不能缺字段或用字符串冒充金额。
- rain_source：用户给定的模拟雨天为“演示模拟”，真实天气触发为“实时预报”，无雨天来源为""；测试替身的来源必须另在WeatherContext.source/summary和测试记录中说明，不写成真实联网成功。
- budget_items：列表，每项至少为 {"category": "住宿", "amount": 640, "detail": "教学估算及计算说明"}。金额示例不代表验收固定值。
- total_cost：非负Python整数，严格等于各项amount之和。不能返回字符串、None或小数。
- changes/warnings：字符串列表。changes记录实际发生的方案变化；warnings记录约束未满足、候选不足、价格未核实等。

A服务负责比较预算并生成budget_status。B不必另建AgentResponse，也不向页面另外输出一套program_total取代统一字段。

非成都城市由A当前服务走未核实方向性建议，不套成都价格；B内部独立函数如被直接调用到非成都，应明确拒绝/提示，不能静默套价。

### 3.3 天气接口

在 travel_agent/tools/weather.py 提供：

```python
from datetime import date

def fetch_weather(
    request: TripRequest,
    today: date | None = None,
) -> WeatherContext:
    ...
```

today参数供离线测试固定日期。实际返回必须为同一份合同定义的WeatherContext实例，不能直接返回独立dict。

统一状态约定：

| status | 条件 | daily |
|---|---|---|
| no_date | 用户没给出发日期，不联网 | [] |
| past | 出发日期已过去，不联网 | [] |
| out_of_range | 行程日期超过工具所支持的实际预报范围 | [] |
| city_not_found | 城市查找无结果/当前工具不支持 | [] |
| error | 网络、超时、解析等失败 | [] |
| incomplete | 返回的逐日日期不完整 | [] |
| ok | 查询成功、请求日期完整 | 恰好days条 |
| disabled | 由A关闭天气时产生 | [] |

B原任务单的error/city_not_found存在两种解释；此次为兼容现有A，明确拆为error与city_not_found两个状态。B内部如保留旧组合字符串，应在对外返回前归一化。

ok的daily必须含连续且匹配请求日期的date，以及0—100有限数字或None类型的rain_probability。可以附weather_code/max_c/min_c。不能继续使用只有day/rain的固定两条数据。

source：真实查询为实际来源名称，例如Open-Meteo；测试替身为test-double，summary明确“测试替身，非真实预报”。不能把用户说“第二天下雨”塞进天气服务的ok结果，用户模拟条件放request.rain_days，规则直接读取即可。

真实请求失败就返回明确失败状态，不硬编码“晴朗”。如果真实查询暂时未实现，也应返回error及说明，留为未测/未实现，不能让mock=False伪装api_forecast。建议优先沿用A运行包已有天气代码，修补测试与边界，减少重写。

## 四、B 必须补齐的功能

### 4.1 活动与成都数据

沿用工作包已有activities/hotels/notes等数据结构。酒店使用room_per_night，活动使用price_per_person、indoor、elderly_friendly等字段。

如果希望保留自己的spots、ticket、price_per_night，必须在内部显式转换，最终提供统一字段；同步规划器、数据加载与测试，不能只把旧JSON覆盖进去导致KeyError。保留来源类型、核对日期或未核实标签，不虚构官方价格。

### 4.2 老人和雨天规则

- elderly>0时限制活动强度，规则应产生可观察的活动选择/数量/时长或休息安排变化；不是只回传is_elderly。
- 第2天由用户指定下雨时，去除/替换该天不适合雨天的户外活动，记录原因和“演示模拟”来源。
- 只有weather.status=ok且逐日概率有效时，才用接口结果触发雨天规则。
- 同一天不重复安排同一活动。跨天优先避免重复；候选不足时明确说明、安排休息或允许有标记的合理重复，不能无提示地填充。
- 七天仍返回七个day对象。若无法排满，明确指出未满足的天数/活动，不虚构景点或保证“完整满足”。七天费用算出来不等于七天行程已验收。

### 4.3 少走路

检测 "少走路" in request.preferences 或适当的pace约束。为固定四轮演示安排可观察的调整，例如减少主要景点数量、降低活动时长或选择同片区活动，并把真实变化写入changes。

最低可解释方案：基础老人行程每天最多2个主要地点；少走路后将存在2个主要地点的天数压到1个、增加休息。需要依活动数据和当日候选验证，不能只是改note文字。

如本已无可进一步减少的安排，应明确说明已达当前最简安排；如确实无法满足则写warnings。没有路线距离数据时，不宣称减少了精确步行米数，也不把活动时长直接说成步行距离。

### 4.4 费用与预算

保留B的教学估算原则。住宿核对晚数和房间数，餐饮核对人数/天数，交通核对适用人数，门票按实际选择的活动和参与人数求和，机动费有说明。不承诺无依据的老人优惠，不把付费景点门票固定算0。

用户budget可以为0；尊重输入，超预算时明确警告，不篡改预算，不无依据压低单价。

3000与2500两次都为1390并不自动构成错误。如果当前合理方案已满足2500，可以重新核算后保留并说明。如果改变酒店、活动或其它方案，则必须重新计算，不能只换标签。

费用不必匹配旧2790/2070，也不必保留现1390。以最终选定数据与方案为准，同时更新来源表、复算表和测试预期。预算不含往返大交通，必须明确提示。

## 五、A-1.1 已完成的联动调整（B无需重复修改）

以下保留为变更说明，已由A-1.1实施。公共合同、提取、多轮记忆、异常隔离和未知预算状态保持不变。B只需领取新版并运行测试，不按下面说明再修改一次。

### 5.1 service.py 的少走路提示

旧版在发现少走路时，无条件追加“B基线尚未优化”的warning，并在trace写“待B接入”。A-1.1已移除这两句固定判断。

新版对成都采用下述中性轨迹，是否已调整/是否未满足由B返回的changes/warnings说明；非成都另行说明未运行成都规则：

```python
if "少走路" in request.preferences:
    trace.append({
        "step": "偏好交接",
        "detail": "少走路偏好已传入规划规则；实际调整与未满足约束见调整说明和警告。",
    })
```

不新增一条固定“优化已成功”的提示。A已有changes/warnings合并逻辑继续保留。对非成都，只说明方向建议，不能声称执行了成都规则。

### 5.2 tests/test_agent.py 的两条过时断言

test_four_rounds_retain_state_and_budget中：

1. 移除/替换“第四轮warnings必须含尚未”的断言。成功案例应断言有实际路线/活动变化和对应changes；无法满足案例在B规则测试中明确断言warnings，不靠固定文字过测。
2. 当前最后一条assertLess(history[2].total_cost, history[1].total_cost)把“预算降低”一律等同于“费用必须下降”。当最终方案在两个预算下都已满足时这不是通用合同，应改为检验新预算确实为2500、分项重新求和一致、预算状态与比较结果一致；B实际换方案的场景再单独断言费用变化。

保留城市、天数、老人、雨天、预算跨轮保留、历史对象不变、费用与预算状态一致等已有断言。不删除无Key、坏JSON、天气失败、非成都、旧构造兼容等实质测试。禁止为了凑40项通过而清空或跳过测试。

A-1.1已落实上述提示与测试调整，新增4项回归验证。公共合同仍为1.0；B无需重写或重复修改A文件，但仍要实现自己的实际规则并提交联合运行证据。

## 六、验收用例与运行命令

至少完成以下验证，全部留实际输入/输出，不依赖现场网络：

| 编号 | 用例 | 必须可观察到 |
|---|---|---|
| 1 | 成都3天、3000元、1位老人 | 每日安排、老人规则、教学估算、分项等于总额 |
| 2 | 追加第2天下雨 | 保留其它约束，第2天室内替换、模拟来源及实际changes |
| 3 | 追加预算2500 | 状态改为2500，重新核算，未满足时明确超支 |
| 4 | 追加少走路 | 原约束仍在，实际活动/强度调整及原因；无固定“尚未实现”误报 |
| 5 | 成都7天 | 返回7个day对象，无索引中断，重复/候选不足有明确策略 |
| 6 | 成都极低预算和0预算 | 不提高用户预算，within_budget=False |
| 7 | 费用边界 | 总额等于预算时判预算内，分项求和正确 |
| 8 | 请求中无日期 | no_date，daily=[]，不联网 |
| 9 | 有效日期+假网络响应 | ok、days条正确日期与概率，明确测试替身 |
| 10 | 过去/超范围日期 | 对输入日期真正判断，失败daily=[] |
| 11 | 网络超时/坏JSON/缺逐日日期 | error或incomplete，不伪造晴天 |
| 12 | 天气城市未找到 | city_not_found，保留解释，不套成都天气 |
| 13 | 清空后非成都请求 | A返回unverified，items=[]，不显示零成本或套成都报价 |
| 14 | B函数输入保护 | 不修改request/preferences/rain_days历史数据 |
| 15 | 付费活动/人数变化 | 门票及适用费用实际变化，房间数/容量有明确规则 |
| 16 | 多日雨天候选耗尽 | 没有不适合雨天的强行填充，警告指出未满足项 |

固定时间的天气测试请注入today或mock日期，替换网络函数，不把独立打印的样例当作日期逻辑测试。真实联网如有实测，另外记录来源、实际日期、耗时与状态，不记录密钥。

在合并后的项目根目录执行：

```powershell
python -B -m unittest discover -s tests -p "test_*.py" -v
python -B demo_agent.py --write-evidence
python -B run_agent_checks.py
```

建议B测试使用unittest以便与当前无额外依赖的检查统一。如使用普通pytest函数，必须额外执行并记录python -m pytest的实际输出；unittest不会自动运行普通test_*函数，不能拿“发现0项”当成功。注意run_agent_checks.py当前只运行A测试，不能代替B的测试记录。

导入验收：

```powershell
python -B -c "from travel_agent.rules.planner import build_chengdu_plan, load_chengdu_data; from travel_agent.tools.weather import fetch_weather; print('AB_IMPORT_OK')"
```

四轮通过必须调用真实TravelAgent.turn并使用正式B模块，不能只分别跑calc_budget和get_weather的自测。天气服务成功可使用明确标注的替身，不能伪装真实查询。

## 七、交付内容与签收

B交付PR应包含：

1. 修改后的正式B模块、数据、测试、三份文档。
2. 在PR正文注明使用A-1.1，并确认第五区段已由A提供；列出B自己的实际修改，不把A现成修正重复计为B新增工作。
3. docs/qa/AB-联调记录.md：基于哪个A/B提交或文件版本、实际修改文件、命令、输入、实际输出、日志/JSON路径、通过/失败/未测、已知限制。
4. 四轮完整AgentResponse JSON、B自动测试原始输出、当前数据的预算复算。更新demo证据与源文件检查清单；保留旧版日志，不把旧版金额当最新版实测。
5. 对原A文档里“B基线未实现”的过时描述，在联调记录中逐条注明已解决/仍未解决；由A签收后同步模块说明和答辩材料，不能让不同版本的文档相互矛盾。

签收门槛：接口可导入、完整返回格式正确、规则有实际行为、失败不造假、A+B测试通过、四轮及边界有证据。A只需拉取分支/接收修改后复现和审阅，不需要重新实现B模块。

C后续接入只消费统一AgentResponse；页面、保存载入和CSV仍由C负责。A+B联调通过不等于整应用或C已验收。

## 八、可直接转发给 B 的说明

请以A-1.1交付包的共享合同为准，在你的分支中将规划和天气接入travel_agent/rules/planner.py、travel_agent/tools/weather.py。规划接口为build_chengdu_plan(request, weather)，返回行程、费用分项、总额、调整说明、警告五项；天气接口为fetch_weather(request, today=None)，返回共享WeatherContext，补齐真实日期和明确失败状态。保留你已有估算依据，但补齐老人/雨天/少走路、门票、七天与候选不足规则。第五区段的A提示和测试已由新版A完成，你无需重复修改A服务、合同或提取逻辑。最终给一个可审查PR、完整四轮JSON、A+B测试输出和当前预算复算；不把模拟天气说成实时。金额以你最终数据和方案为准，不强行对齐旧金额。
