"""
weather模块自动化测试
B角色 10.31任务，提前交付
"""
from weather import get_weather, weather_out_of_range_sample

def test_weather():
    print("====测试1：成都模拟下雨 ok====")
    res1 = get_weather("成都", None, mock=True)
    assert res1["status"] == "ok"
    assert res1["rain_source"] == "user_simulate"
    assert len(res1["daily"]) == 2
    print("✅ 测试1通过")

    print("\n====测试2：其他城市，city_not_found====")
    res2 = get_weather("北京", None, mock=True)
    assert res2["status"] == "error/city_not_found"
    assert len(res2["daily"]) == 0
    print("✅ 测试2通过")

    print("\n====测试3：日期超出范围 out_of_range====")
    res3 = weather_out_of_range_sample()
    assert res3["status"] == "out_of_range"
    assert len(res3["daily"]) == 0
    print("✅ 测试3通过")

    print("\n🎉 weather全部测试通过！")

if __name__ == "__main__":
    test_weather()
