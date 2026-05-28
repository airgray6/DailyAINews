"""
每日AI资讯 - 自动抓取 & 微信推送脚本 (v4)
简洁版：序号 + 标题 + 链接 + 完整内容，纯文本推送
"""

import requests
import os
from datetime import datetime, timezone, timedelta

try:
    from lunarcalendar import Converter, Solar
    HAS_LUNAR = True
except ImportError:
    HAS_LUNAR = False

# ================= 配置区域 =================
PUSHPLUS_TOKEN = os.environ.get("PUSHPLUS_TOKEN", "你的PushPlus_Token")

AIHOT_BASE = "https://aihot.virxact.com"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"

TARGET_NEWS_COUNT = 50

ICIBA_API = "http://open.iciba.com/dsapi/"

CATEGORY_MAP = {
    "ai-models": "🤖 模型发布",
    "ai-products": "📦 产品发布",
    "industry": "📊 行业动态",
    "paper": "📄 论文研究",
    "tip": "💡 技巧与观点",
}
# ============================================


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


def fetch_daily_news():
    headers = {"User-Agent": UA}

    print("[抓取] 尝试获取今日日报...")
    try:
        resp = requests.get(f"{AIHOT_BASE}/api/public/daily", headers=headers, timeout=20)
        if resp.status_code == 200:
            data = resp.json()
            sections = data.get("sections", [])
            if sections:
                print(f"  -> 日报获取成功，共 {len(sections)} 个版块")
                result = []
                for sec in sections:
                    label = sec.get("label", "其他")
                    news_items = []
                    for item in sec.get("items", []):
                        news_items.append({
                            "title": item.get("titleZh") or item.get("title", ""),
                            "url": item.get("url", ""),
                            "source": item.get("source", ""),
                            "summary": item.get("summaryZh") or item.get("summary", ""),
                        })
                    if news_items:
                        result.append({"category": label, "items": news_items})
                return result, "daily"
    except Exception as e:
        print(f"  -> 日报获取失败: {e}")

    print("[抓取] 退回精选条目...")
    try:
        since = (get_beijing_now() - timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%SZ")
        resp = requests.get(
            f"{AIHOT_BASE}/api/public/items",
            params={"mode": "selected", "since": since, "take": TARGET_NEWS_COUNT},
            headers=headers, timeout=20,
        )
        if resp.status_code == 200:
            data = resp.json()
            items = data.get("items", [])
            print(f"  -> 精选条目获取成功，共 {len(items)} 条")
            grouped = {}
            for item in items:
                cat_key = item.get("category", "industry")
                cat_label = CATEGORY_MAP.get(cat_key, "📌 其他")
                if cat_label not in grouped:
                    grouped[cat_label] = []
                grouped[cat_label].append({
                    "title": item.get("titleZh") or item.get("title", ""),
                    "url": item.get("url", ""),
                    "source": item.get("source", ""),
                    "summary": item.get("summaryZh") or item.get("summary", ""),
                })
            return [{"category": c, "items": n} for c, n in grouped.items()], "selected"
    except Exception as e:
        print(f"  -> 精选条目获取失败: {e}")
    return [], "none"


def build_message(sections, quote_en, quote_cn):
    """构建纯文本消息：每条 = 序号+标题+链接+完整内容"""
    today = get_beijing_now()
    week_days = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
    date_str = f"{today.year}年{today.month:02d}月{today.day:02d}日 {week_days[today.weekday()]}{get_lunar_date_str(today)}"
    total = sum(len(s["items"]) for s in sections)

    lines = []
    lines.append(f"📡 每日AI资讯")
    lines.append(f"{date_str}  共{total}条")
    lines.append("")

    idx = 0
    for sec in sections:
        cat = sec["category"]
        lines.append(f"{'='*20}")
        lines.append(f"{cat}（{len(sec['items'])}篇）")
        lines.append(f"{'='*20}")
        lines.append("")

        for item in sec["items"]:
            idx += 1
            title = item["title"]
            url = item["url"]
            source = item["source"]
            summary = item["summary"]

            # 序号 + 标题 + 来源
            source_str = f"（{source}）" if source else ""
            lines.append(f"{idx}. {title}{source_str}")

            # 链接单独一行
            if url:
                lines.append(f"链接：{url}")

            # 完整内容
            if summary:
                lines.append(f"{summary}")

            lines.append("")  # 每条之间空一行

    # 每日一句
    lines.append(f"{'='*20}")
    lines.append(f"✨ 每日一句")
    lines.append(f"{quote_en}")
    lines.append(f"{quote_cn}")
    lines.append(f"{'='*20}")
    lines.append(f"来源：aihot.virxact.com")

    return "\n".join(lines)


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
    print(f"========== 每日AI资讯推送 v4 ==========")
    print(f"运行时间: {get_beijing_now().strftime('%Y-%m-%d %H:%M:%S')} (北京时间)")
    print()

    sections, source_type = fetch_daily_news()
    if not sections:
        send_to_wechat("每日AI资讯获取失败", "未能从 AIHOT API 获取到新闻，请检查数据源。")
        return

    total = sum(len(s["items"]) for s in sections)
    print(f"[汇总] 共 {len(sections)} 个分类，{total} 条新闻")

    quote_en, quote_cn = get_daily_quote()
    print(f"[每日一句] {quote_en} / {quote_cn}")

    content = build_message(sections, quote_en, quote_cn)
    title = f"每日AI资讯 ({get_beijing_now().strftime('%m月%d日')})"

    send_to_wechat(title, content)
    print(f"\n========== 执行完毕 ==========")


if __name__ == "__main__":
    main()
