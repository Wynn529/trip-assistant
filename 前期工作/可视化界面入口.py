"""Run with: streamlit run app.py"""

from __future__ import annotations

from datetime import date

import streamlit as st

from travel_agent import TravelAgent
from travel_agent.contracts import TripRequest
from travel_agent.llm import load_local_env
from travel_agent.storage.exports import expense_csv, itinerary_csv
from travel_agent.storage.local import list_trips, load_trip, save_trip
from travel_agent.ui.theme import CSS


st.set_page_config(page_title="行知 · 旅行规划助理", page_icon="🧭", layout="wide")
st.markdown(CSS, unsafe_allow_html=True)
load_local_env()

if "messages" not in st.session_state:
    st.session_state.messages = []
if "request" not in st.session_state:
    st.session_state.request = None
if "result" not in st.session_state:
    st.session_state.result = None
if "expenses" not in st.session_state:
    st.session_state.expenses = []
if "done_tasks" not in st.session_state:
    st.session_state.done_tasks = set()


def run_prompt(prompt: str, live_model: bool, live_weather: bool) -> None:
    agent = TravelAgent(live_model=live_model, live_weather=live_weather)
    previous = st.session_state.request
    with st.spinner("正在提取需求、查询工具并检查约束…"):
        result = agent.turn(prompt, previous)
    st.session_state.request = result.request
    st.session_state.result = result.to_dict()
    st.session_state.messages.append({"role": "user", "content": prompt})
    st.session_state.messages.append({"role": "assistant", "content": result.answer})
    st.session_state.done_tasks = set()


with st.sidebar:
    st.header("演示控制台")
    from os import getenv

    has_key = bool(getenv("DEEPSEEK_API_KEY"))
    live_model = st.toggle("使用 DeepSeek API", value=has_key, disabled=not has_key)
    live_weather = st.toggle("查询实时天气", value=True)
    st.caption("关闭模型后可零成本演示；真实天气仍依赖网络。")
    st.divider()
    st.subheader("一键演示")
    demo_prompts = [
        "去成都三天，预算3000元，带一位老人",
        "第二天下雨，帮我改成室内行程",
        "预算降到2500元，尽量少走路",
        "去杭州三天，预算3000元",
    ]
    for index, prompt in enumerate(demo_prompts):
        if st.button(f"{index + 1}. {prompt}", width="stretch"):
            run_prompt(prompt, live_model, live_weather)
            st.rerun()
    if st.button("清空当前对话", width="stretch"):
        st.session_state.messages = []
        st.session_state.request = None
        st.session_state.result = None
        st.session_state.expenses = []
        st.session_state.done_tasks = set()
        st.rerun()
    st.divider()
    st.subheader("本地保存")
    if st.session_state.result and st.button("保存当前行程", width="stretch"):
        from travel_agent.contracts import AgentResponse, WeatherContext

        raw = st.session_state.result
        saved = save_trip(AgentResponse(
            request=TripRequest(**raw["request"]),
            weather=WeatherContext(**raw["weather"]),
            itinerary=raw["itinerary"], budget_items=raw["budget_items"],
            total_cost=raw["total_cost"], within_budget=raw["within_budget"],
            changes=raw["changes"], warnings=raw["warnings"],
            booking_tasks=raw["booking_tasks"], trace=raw["trace"],
            coverage=raw["coverage"], answer=raw["answer"],
        ))
        st.success(f"已保存：{saved.name}")
    saved_files = list_trips()
    if saved_files:
        selected = st.selectbox("已保存行程", saved_files, format_func=lambda path: path.name)
        if st.button("载入选中行程", width="stretch"):
            raw = load_trip(selected)
            st.session_state.result = raw
            st.session_state.request = TripRequest(**raw["request"])
            st.session_state.messages.append({"role": "assistant", "content": "已载入本地保存的行程。"})
            st.rerun()

st.markdown('<div class="hero"><h1>行知 · 旅行规划助理</h1><p>从一句想法到可调整的行程、预算、提醒和费用记录</p></div>', unsafe_allow_html=True)
st.markdown('<span class="tag">成都完整演示</span><span class="tag">天气实时查询</span><span class="tag">费用为样例估算</span>', unsafe_allow_html=True)

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
        st.caption(result["coverage"])
        if result["budget_items"]:
            a, b, c = st.columns(3)
            a.metric("估算总费用", f"¥{result['total_cost']:,}")
            b.metric("预算", f"¥{req['budget']:,}")
            c.metric("预算余额", f"¥{req['budget'] - result['total_cost']:,}")
        else:
            st.warning("此城市缺少可核实报价，暂不显示预算合计。")
        if result["changes"]:
            st.success("调整说明：" + "；".join(result["changes"]))
        tabs = st.tabs(["每日行程", "预算", "预订与提醒", "执行轨迹", "模拟报销"])
        with tabs[0]:
            st.info(result["weather"]["summary"])
            for day in result["itinerary"]:
                with st.container(border=True):
                    title = f"第 {day['day']} 天" + (f" · {day['date']}" if day["date"] else "")
                    st.markdown(f"#### {title}")
                    if day["rainy"]:
                        st.caption(f"雨天调整 · {day['rain_source']}")
                    for activity in day["activities"]:
                        st.write(f"• {activity['name']}")
                    st.caption(day["note"])
            for warning in result["warnings"]:
                st.warning(warning)
            st.download_button("导出行程 CSV", itinerary_csv(result), file_name="行程表.csv", mime="text/csv")
        with tabs[1]:
            if result["budget_items"]:
                st.dataframe(result["budget_items"], hide_index=True, width="stretch")
                if not result["within_budget"]:
                    st.error("估算超预算，请调整条件。")
            else:
                st.write("无法核算非成都城市的真实预算。")
        with tabs[2]:
            for index, task in enumerate(result["booking_tasks"]):
                checked = st.checkbox(f"{task['task']} · {task['due']}", key=f"task_{index}")
                if checked:
                    st.session_state.done_tasks.add(index)
                else:
                    st.session_state.done_tasks.discard(index)
                if task["due"] and task["due"] <= date.today().isoformat() and index not in st.session_state.done_tasks:
                    st.warning(f"到期提醒：{task['task']}")
            st.caption("提醒仅在本机应用打开时显示；不会发送系统推送或代为下单。")
        with tabs[3]:
            for index, entry in enumerate(result["trace"], 1):
                st.write(f"{index}. **{entry['step']}**：{entry['detail']}")
        with tabs[4]:
            with st.form("expense_form", clear_on_submit=True):
                expense_date = st.date_input("消费日期", value=date.today())
                category = st.selectbox("类别", ["住宿", "餐饮", "市内交通", "景点门票", "其他"])
                amount = st.number_input("金额（元）", min_value=0, step=10)
                note = st.text_input("备注")
                submitted = st.form_submit_button("添加模拟费用")
            if submitted and amount > 0:
                st.session_state.expenses.append({"date": expense_date.isoformat(), "category": category, "amount": int(amount), "note": note})
            st.dataframe(st.session_state.expenses, hide_index=True, width="stretch")
            total_spent = sum(item["amount"] for item in st.session_state.expenses)
            st.metric("已录入费用", f"¥{total_spent:,}")
            st.download_button("导出费用汇总 CSV", expense_csv(st.session_state.expenses), file_name="模拟报销汇总.csv", mime="text/csv")
            st.caption("教学演示账本，不处理发票识别或真实报销审批。")
