import json
import os

# 获取当前py文件所在文件夹
base_path = os.path.dirname(__file__)
json_path = os.path.join(base_path, "chengdu.json")

with open(json_path,"r",encoding="utf-8") as f:
    chengdu_data = json.load(f)


def calc_budget(total_days:int, nights:int, people:int, budget_input:int, is_elderly:bool, rain_days):
    hotel_price = chengdu_data["hotels"][0]["price_per_night"]
    meal_pp = chengdu_data["meal_price_per_person"]
    traffic_day = chengdu_data["traffic_per_day"]
    flex = chengdu_data["flex_cost"]

    accommodation = hotel_price * nights
    food = meal_pp * people * total_days
    traffic = traffic_day * total_days
    ticket_sum = 0
    flexible = flex

    total = accommodation + food + traffic + ticket_sum + flexible
    budget_diff = budget_input - total
    within_budget = total <= budget_input

    return {
        "accommodation": accommodation,
        "food": food,
        "traffic": traffic,
        "ticket_sum": ticket_sum,
        "flexible": flexible,
        "program_total": total,
        "budget_diff": budget_diff,
        "within_budget": within_budget,
        "is_elderly": is_elderly
    }


if __name__ == "__main__":
    print("=====场景1：预算3000，3天，2人=====")
    res1 = calc_budget(total_days=3, nights=2, people=2, budget_input=3000, is_elderly=False, rain_days=[])
    print(res1)

    print("\n=====场景2：预算2500，3天，2人=====")
    res2 = calc_budget(total_days=3, nights=2, people=2, budget_input=2500, is_elderly=False, rain_days=[])
    print(res2)

    print("\n=====场景3：超预算场景 预算1000=====")
    res3 = calc_budget(total_days=7, nights=6, people=2, budget_input=1000, is_elderly=False, rain_days=[])
    print(res3)

    print("\n=====边界：7天行程测试=====")
    res7 = calc_budget(total_days=7, nights=6, people=2, budget_input=5000, is_elderly=False, rain_days=[])
    print(res7)
