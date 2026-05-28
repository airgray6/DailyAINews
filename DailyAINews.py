"""
每日AI资讯 - 推送 AIHOT 日报链接到微信
"""

import requests
import os
from datetime import datetime, timezone, timedelta

try:
    from lunarcalendar import Converter, Solar
    HAS_LUNAR = True
except ImportError:
    HAS_LUNAR = False

PUSHPLUS_TOKEN = os.environ.get("PUSHPLUS_TOKEN", "你的PushPlus_Token")
ICIBA_API = "http://open.iciba.com/dsapi/"


def get_beijing_now():
    return datetime.now(timezone(timedelta(hours=8)))


def get_lunar_date_str(dt):
    if not HAS_LUNAR:
        return ""
    try:
        solar = Solar(dt.year, dt.month, dt.day)
        lunar = Converter.Solar2Lunar(solar)
        lunar_months = ["正", "二", "三", "四", "五", "六", "七", "八", "九", "十", "冬", "腊"]
        lunar_days = [
            "初一", "初二", "初三", "初四", "初五", "初六", "初七", "初八", "初九", "初十",
            "十一", "十二", "十三", "十四", "十五", "十六", "十七", "十八", "十九", "二十",
            "廿一", "廿二", "廿三", "廿四", "廿五", "廿六", "廿七", "廿八", "廿九", "三十",
        ]
        return f" 农历{lunar_months[lunar.month - 1]}月{lunar_days[lunar.day - 1]}"
    except Exception:
        return ""


def get_daily_quote():
    try:
        resp = requests.get(ICIBA_API, timeout=10)
        data = resp.json()
        en = data.get("content", "").strip()
        cn = data.get("note", "").strip()
        if en and cn:
            return en, cn
    except Exception as e:
        print(f"[警告] 获取每日一句失败: {e}")
    return "Stay hungry, stay foolish.", "求知若饥，虚心若愚。"


def send_to_wechat(title, content):
    if not PUSHPLUS_TOKEN or PUSHPLUS_TOKEN == "你的PushPlus_Token":
        print("[错误] 未配置 PUSHPLUS_TOKEN！")
        return False

    url = "http://www.pushplus.plus/send"
    data = {
        "token": PUSHPLUS_TOKEN,
        "title": title,
        "content": content,
        "template": "txt",
    }
    try:
        response = requests.post(url, json=data, timeout=15)
        result = response.json()
        if result.get("code") == 200:
            print("[成功] 微信推送成功！")
            return True
        else:
            print(f"[失败] 推送失败: {result}")
            return False
    except Exception as e:
        print(f"[错误] 推送请求异常: {e}")
        return False


def main():
    today = get_beijing_now()
    date_str = today.strftime("%Y-%m-%d")
    week_days = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
    lunar_str = get_lunar_date_str(today)

    # AIHOT 当天日报链接
    daily_url = f"https://aihot.virxact.com/daily/{date_str}"

    # 每日一句
    quote_en, quote_cn = get_daily_quote()

    content = f"""📡 每日AI资讯
{today.year}年{today.month:02d}月{today.day:02d}日 {week_days[today.weekday()]}{lunar_str}

👉 今日AI日报：
{daily_url}

✨ {quote_en}
{quote_cn}"""

    title = f"每日AI资讯 ({today.strftime('%m月%d日')})"
    send_to_wechat(title, content)
    print(f"[完成] 已推送: {daily_url}")


if __name__ == "__main__":
    main()
