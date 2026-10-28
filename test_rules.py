"""
预算planner模块自动化测试
B角色 10.31任务，提前交付
"""
from planner import calc_budget

def test_planner():
    print("====场景1：3天2人 预算3000====")
    r1 = calc_budget(3, 2, 2, 3000, False, [])
    assert r1["program_total"] == 1390
    assert r1["within_budget"] == True
    print("✅ 场景1通过")

    print("\n====场景2：3天2人 预算2500====")
    r2 = calc_budget(3, 2, 2, 2500, False, [])
    assert r2["program_total"] == 1390
    assert r2["within_budget"] == True
    print("✅ 场景2通过")

    print("\n====场景3：7天2人 预算1000（超支）====")
    r3 = calc_budget(7, 6, 2, 1000, False, [])
    assert r3["program_total"] == 3470
    assert r3["within_budget"] == False
    print("✅ 场景3通过")

    print("\n====场景4：7天2人 预算5000====")
    r4 = calc_budget(7, 6, 2, 5000, False, [])
    assert r4["program_total"] == 3470
    assert r4["within_budget"] == True
    print("✅ 场景4通过")

    print("\n🎉 planner预算全部测试通过！")

if __name__ == "__main__":
    test_planner()
