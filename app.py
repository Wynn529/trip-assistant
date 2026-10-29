"""Run with: streamlit run app.py

来源：文斓前期 `前期工作/可视化界面入口.py`；C 按 A v1.2 合同修改。
页面只读取 AgentResponse 显示，不重算预算，不自行决定雨天替换。
"""

from __future__ import annotations

from datetime import date
from os import getenv

import streamlit as st

from travel_agent import TravelAgent
from travel_agent.contracts import AgentResponse, TripRequest, WeatherContext
from travel_agent.llm import load_local_env
from travel_agent.storage.exports import expense_csv, itinerary_csv
from travel_agent.storage.local import list_trips, load_trip, save_trip
from travel_agent.ui.theme import CSS


# 与 A 的 demo_agent.py 四轮输入保持一致，便于对照证据。
DEMO_PROMPTS = (
    "去成都三天，预算3000元，带一位老人",
    "第二天下雨，改成室内行程",
    "预算降到2500元",
    "尽量少走路",
)
NON_CHENGDU_PROMPT = "去杭州三天，预算3000元"

FIELD_LABELS = {
    "city": "目的地", "start_date": "出发日期", "days": "天数", "budget": "预算",
    "adults": "成人数", "elderly": "老人数", "children": "儿童数", "pace": "节奏",
    "rain_days": "雨天", "preferences": "偏好", "origin": "出发地",
}
BUDGET_STATUSES = {"estimated_within_budget", "estimated_over_budget", "unverified"}
# 状态值来自 A 的 service.py `_weather` 中的 known 集合。
WEATHER_STATUS_LABELS = {
    "ok": "已获取", "no_date": "未提供出发日期", "past": "出发日期已过",
    "out_of_range": "超出可查询范围", "city_not_found": "暂不支持该城市",
    "incomplete": "数据不完整", "error": "查询失败", "disabled": "未开启天气查询",
}
# Open-Meteo 使用 WMO 天气代码。
WEATHER_CODE_LABELS = {
    0: "晴", 1: "大致晴", 2: "多云", 3: "阴", 45: "雾", 48: "雾凇",
    51: "小毛毛雨", 53: "毛毛雨", 55: "大毛毛雨", 56: "冻毛毛雨", 57: "冻毛毛雨",
    61: "小雨", 63: "中雨", 65: "大雨", 66: "冻雨", 67: "冻雨",
    71: "小雪", 73: "中雪", 75: "大雪", 77: "雪粒",
    80: "小阵雨", 81: "阵雨", 82: "强阵雨", 85: "阵雪", 86: "强阵雪",
    95: "雷暴", 96: "雷暴伴冰雹", 99: "雷暴伴冰雹",
}
RAIN_SOURCE_LABELS = {
    "user_simulate": "用户模拟", "user_simulated": "用户模拟",
    "api_forecast": "接口预报", "forecast": "接口预报",
}


def restore_response(raw: dict) -> AgentResponse:
    """按 A 的 README 写法还原完整响应，保留 budget_status 等新增字段。"""
    fields = dict(raw)
    fields["request"] = TripRequest(**raw["request"])
    fields["weather"] = WeatherContext(**raw["weather"])
    return AgentResponse(**fields)


def init_state() -> None:
    defaults = {
        "messages": [], "request": None, "result": None,
        "expenses": [], "result_id": 0,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def set_result(response: AgentResponse) -> None:
    st.session_state.request = response.request
    st.session_state.result = response.to_dict()
    # 换一个编号，让待办勾选框使用新的 key，避免沿用上一份行程的勾选状态。
    st.session_state.result_id += 1


def run_prompt(prompt: str, live_model: bool, live_weather: bool) -> None:
    prompt = prompt.strip()
    if not prompt:
        return
    st.session_state.messages.append({"role": "user", "content": prompt})
    agent = TravelAgent(live_model=live_model, live_weather=live_weather)
    try:
        with st.spinner("正在提取需求、查询工具并检查约束…"):
            result = agent.turn(prompt, st.session_state.request)
    except Exception as exc:  # 保留上一轮结果，只提示失败
        st.session_state.messages.append(
            {"role": "assistant", "content": f"这次处理失败，已保留上一轮结果。错误类型：{type(exc).__name__}"}
        )
        return
    set_result(result)
    st.session_state.messages.append({"role": "assistant", "content": result.answer})


def weather_source_label(source: str) -> str:
    return "测试替身，非真实预报" if source == "test-double" else (source or "未知来源")


def weather_tag(result: dict | None, live_weather: bool) -> str:
    if result:
        weather = result.get("weather", {})
        status = weather.get("status", "")
        if status == "ok":
            return f"天气：已获取（{weather_source_label(weather.get('source', ''))}）"
        if status == "disabled":
            return "天气：未开启查询"
        return f"天气：未获取（{WEATHER_STATUS_LABELS.get(status, status or '未知')}）"
    return "天气：联网查询已开启" if live_weather else "天气：未开启查询"


def daily_weather_for(day: dict, weather: dict) -> dict | None:
    """按日期匹配当天预报；行程没有日期时按第几天对应。只在天气状态为 ok 时使用。"""
    daily = weather.get("daily") or []
    if weather.get("status") != "ok" or not daily:
        return None
    if day.get("date"):
        return next((entry for entry in daily if entry.get("date") == day["date"]), None)
    index = day.get("day", 0) - 1
    return daily[index] if 0 <= index < len(daily) else None


def format_daily_weather(entry: dict) -> str:
    parts = []
    code = entry.get("weather_code")
    if code is not None:
        parts.append(WEATHER_CODE_LABELS.get(code, f"天气代码 {code}"))
    low, high = entry.get("min_c"), entry.get("max_c")
    if low is not None and high is not None:
        parts.append(f"{low:.0f}–{high:.0f}℃")
    probability = entry.get("rain_probability")
    if probability is not None:
        parts.append(f"降水概率 {probability:.0f}%")
    date_text = entry.get("date", "")
    return f"天气预报（{date_text}）：" + " · ".join(parts) if parts else ""


def is_due(value: str, today: date) -> bool:
    """只对 YYYY-MM-DD 形式的截止日期判断到期；“待确定出发日期”等文字不提醒。"""
    try:
        return date.fromisoformat(value) <= today
    except (TypeError, ValueError):
        return False


st.set_page_config(page_title="行知 · 旅行规划助理", page_icon="🧭", layout="wide")
st.markdown(CSS, unsafe_allow_html=True)
load_local_env()
init_state()

with st.sidebar:
    st.header("演示控制台")
    has_key = bool(getenv("DEEPSEEK_API_KEY"))
    live_model = st.toggle("使用 DeepSeek API", value=has_key, disabled=not has_key)
    if not has_key:
        st.caption("未检测到 DEEPSEEK_API_KEY，开关不可用。在项目根目录的 .env 文件中写入密钥并重启页面后才能开启。")
    live_weather = st.toggle("查询实时天气", value=False)
    st.caption("无 Key 时使用规则提取。关闭天气查询时不联网；雨天只来自你在对话中的说明。")
    st.divider()
    st.subheader("一键演示")
    st.caption("按 1→4 顺序点击为主线四轮；第 5 项演示非成都城市。")
    for index, prompt in enumerate(DEMO_PROMPTS, start=1):
        if st.button(f"{index}. {prompt}", width="stretch"):
            run_prompt(prompt, live_model, live_weather)
            st.rerun()
    if st.button(f"5. {NON_CHENGDU_PROMPT}", width="stretch"):
        run_prompt(NON_CHENGDU_PROMPT, live_model, live_weather)
        st.rerun()
    if st.button("清空当前对话", width="stretch"):
        st.session_state.messages = []
        st.session_state.request = None
        st.session_state.result = None
        st.session_state.expenses = []
        st.session_state.result_id += 1
        st.rerun()

    st.divider()
    st.subheader("本地保存")
    if st.session_state.result and st.button("保存当前行程", width="stretch"):
        try:
            saved = save_trip(restore_response(st.session_state.result))
        except Exception as exc:
            st.error(f"保存失败：{type(exc).__name__}")
        else:
            st.success(f"已保存：{saved.name}")
    st.caption("只保存当前行程结果（需求、天气、行程、预算、待办、执行轨迹）；不保存对话记录、模拟费用和待办勾选状态。文件位于项目根目录 local_data/。")
    saved_files = list_trips()
    if saved_files:
        selected = st.selectbox("已保存行程", saved_files, format_func=lambda path: path.name)
        if st.button("载入选中行程", width="stretch"):
            try:
                response = restore_response(load_trip(selected))
            except Exception as exc:
                st.error(f"载入失败：{type(exc).__name__}")
            else:
                set_result(response)
                st.session_state.messages.append({"role": "assistant", "content": f"已载入本地保存的行程：{selected.name}"})
                st.rerun()

st.markdown('<div class="hero"><h1>行知 · 旅行规划助理</h1><p>从一句想法到可调整的行程、预算、提醒和费用记录</p></div>', unsafe_allow_html=True)
st.markdown(
    f'<span class="tag">成都完整演示</span><span class="tag">{weather_tag(st.session_state.result, live_weather)}</span>'
    '<span class="tag">费用为教学估算</span>',
    unsafe_allow_html=True,
)

left, right = st.columns([1.08, 1.92], gap="large")
with left:
    st.subheader("对话")
    with st.container(height=400):
        if not st.session_state.messages:
            st.info("输入“去成都三天，预算3000元，带老人”，或使用左侧一键演示。")
        for message in st.session_state.messages:
            with st.chat_message(message["role"]):
                st.write(message["content"])
    prompt = st.chat_input("告诉我目的地、天数、预算和同行人…")
    if prompt:
        run_prompt(prompt, live_model, live_weather)
        st.rerun()
    if st.session_state.request:
        with st.expander("调整出发日期"):
            chosen = st.date_input("出发日期", value=date.today())
            if st.button("按所选日期重新规划"):
                run_prompt(f"出发日期改为{chosen.isoformat()}", live_model, live_weather)
                st.rerun()

with right:
    result = st.session_state.result
    if not result:
        st.subheader("行程预览")
        st.info("生成行程后，这里会展示每日安排、费用、提醒和智能体执行轨迹。")
    else:
        req = result["request"]
        st.subheader(f"{req['city']} · {req['days']} 天")
        st.caption(result.get("coverage", ""))
        assumed = [FIELD_LABELS.get(name, name) for name in req.get("assumed_fields", [])]
        if assumed:
            st.caption("以下条件为演示默认值，你尚未明确说明：" + "、".join(assumed))

        budget_status = result.get("budget_status", "unverified")
        if budget_status not in BUDGET_STATUSES:
            budget_status = "unverified"
        verified = budget_status != "unverified" and bool(result["budget_items"])
        if verified:
            a, b, c = st.columns(3)
            a.metric("教学估算总费用", f"¥{result['total_cost']:,}")
            b.metric("预算", f"¥{req['budget']:,}")
            diff = req["budget"] - result["total_cost"]
            c.metric("预算差额", f"¥{diff:,}" if diff >= 0 else f"-¥{-diff:,}")
            if budget_status == "estimated_over_budget":
                st.error("教学估算超出预算，请调整天数、人数或预算。")
            else:
                st.success("教学估算在预算内（不代表真实报价）。")
        else:
            st.warning("此请求缺少可核实报价：不显示总费用和预算差额，也不判断是否符合预算。")

        if result["changes"]:
            st.success("调整说明：" + "；".join(result["changes"]))
        tabs = st.tabs(["每日行程", "预算", "预订与提醒", "执行轨迹", "模拟报销"])
        with tabs[0]:
            weather = result["weather"]
            w_status = weather.get("status", "")
            w_label = WEATHER_STATUS_LABELS.get(w_status, w_status or "未知")
            if w_status == "ok":
                st.info(f"天气（{weather_source_label(weather.get('source', ''))}）：{weather.get('summary', '')}")
            elif w_status == "disabled":
                st.info("未开启实时天气查询；行程中的雨天只来自你在对话中的说明。")
            else:
                st.warning(f"未获取天气（{w_label}）：{weather.get('summary', '')}")
            for day in result["itinerary"]:
                with st.container(border=True):
                    title = f"第 {day['day']} 天" + (f" · {day['date']}" if day.get("date") else "")
                    st.markdown(f"#### {title}")
                    forecast = daily_weather_for(day, weather)
                    if forecast and format_daily_weather(forecast):
                        st.markdown(f"**{format_daily_weather(forecast)}**")
                    if day.get("rainy"):
                        source = day.get("rain_source", "")
                        st.caption(f"雨天调整 · {RAIN_SOURCE_LABELS.get(source, source or '来源未标注')}")
                    for activity in day.get("activities", []):
                        st.write(f"• {activity['name']}")
                    if day.get("note"):
                        st.caption(day["note"])
            # 天气提示上面已显示过，警告列表里不再重复。
            for warning in result["warnings"]:
                if warning != weather.get("summary"):
                    st.warning(warning)
            st.download_button("导出行程 CSV", itinerary_csv(result), file_name="行程表.csv", mime="text/csv")
        with tabs[1]:
            if verified:
                st.dataframe(result["budget_items"], hide_index=True, width="stretch")
                st.caption("费用为教学估算，不含往返成都的大交通。")
            else:
                st.write("本次请求没有可核实报价，不显示预算明细。")
        with tabs[2]:
            today = date.today()
            for index, task in enumerate(result["booking_tasks"]):
                due = task.get("due", "")
                checked = st.checkbox(
                    f"{task['task']}" + (f" · {due}" if due else ""),
                    key=f"task_{st.session_state.result_id}_{index}",
                )
                if is_due(due, today) and not checked:
                    st.warning(f"到期提醒：{task['task']}")
            st.caption("提醒仅在本机应用打开时显示；不会发送系统推送或代为下单。勾选状态不会被保存。")
        with tabs[3]:
            st.caption(f"需求提取：{result.get('extraction_status') or '未记录'} · 合同版本：{result.get('schema_version', '未记录')}")
            for index, entry in enumerate(result["trace"], 1):
                st.write(f"{index}. **{entry['step']}**：{entry['detail']}")
        with tabs[4]:
            with st.form("expense_form", clear_on_submit=True):
                expense_date = st.date_input("消费日期", value=date.today())
                category = st.selectbox("类别", ["住宿", "餐饮", "市内交通", "景点门票", "其他"])
                amount = st.number_input("金额（元）", min_value=0, step=10)
                note = st.text_input("备注")
                submitted = st.form_submit_button("添加模拟费用")
            if submitted:
                if amount > 0:
                    st.session_state.expenses.append(
                        {"date": expense_date.isoformat(), "category": category, "amount": int(amount), "note": note}
                    )
                else:
                    st.warning("金额需大于 0。")
            st.dataframe(st.session_state.expenses, hide_index=True, width="stretch")
            total_spent = sum(item["amount"] for item in st.session_state.expenses)
            st.metric("已录入费用", f"¥{total_spent:,}")
            st.download_button("导出费用汇总 CSV", expense_csv(st.session_state.expenses), file_name="模拟报销汇总.csv", mime="text/csv")
            st.caption("教学演示账本，不处理发票识别或真实报销审批；清空对话时一并清空。")