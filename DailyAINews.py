"""
每日AI资讯 - 自动抓取 & 微信推送脚本
适配 GitHub Actions 定时运行，使用 PushPlus 推送 HTML 格式消息
"""

import requests
import feedparser
from bs4 import BeautifulSoup
import re
import os
from datetime import datetime, timezone, timedelta

# 尝试导入农历库
try:
    from lunarcalendar import Converter, Solar
    HAS_LUNAR = True
except ImportError:
    HAS_LUNAR = False

# ================= 配置区域 =================
# Token 优先从环境变量读取（GitHub Actions 安全方式），本地调试可直接填写
PUSHPLUS_TOKEN = os.environ.get("PUSHPLUS_TOKEN", "你的PushPlus_Token")

# RSS 数据源
RSS_FEEDS = [
    "https://aihot.virxact.com/feed/daily.xml",
    "https://aihot.virxact.com/feed.xml",
    "https://aihot.virxact.com/feed/all.xml",
]

# 目标新闻条数
TARGET_NEWS_COUNT = 50

# 金山词霸每日一句 API（替代微语）
ICIBA_API = "http://open.iciba.com/dsapi/"
# ============================================


def get_beijing_now():
    """获取北京时间"""
    return datetime.now(timezone(timedelta(hours=8)))


def get_lunar_date_str(dt):
    """计算农历日期字符串"""
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
        month_str = lunar_months[lunar.month - 1] + "月"
        day_str = lunar_days[lunar.day - 1]
        return f" 农历{month_str}{day_str}"
    except Exception:
        return ""


def get_daily_quote():
    """从金山词霸 API 获取每日一句"""
    try:
        resp = requests.get(ICIBA_API, timeout=10)
        data = resp.json()
        english = data.get("content", "").strip()
        chinese = data.get("note", "").strip()
        if english and chinese:
            return english, chinese
    except Exception as e:
        print(f"[警告] 获取每日一句失败: {e}")
    return "Stay hungry, stay foolish.", "求知若饥，虚心若愚。"


def extract_news_from_html(html_content):
    """
    从 RSS entry 的 HTML 内容中提取新闻列表。
    每条新闻返回 (标题文本, 链接URL)。
    """
    soup = BeautifulSoup(html_content, "html.parser")
    news_items = []

    # 策略1: 提取所有 <a> 标签（最常见的 RSS 新闻格式）
    for a_tag in soup.find_all("a", href=True):
        text = a_tag.get_text(strip=True)
        href = a_tag["href"]
        # 过滤掉太短的文本、纯链接文本、导航类链接
        if len(text) > 5 and not text.startswith("http") and href.startswith("http"):
            # 去掉开头的序号 (如 "1. " "1、" "1) ")
            clean_text = re.sub(r"^\d+[\.\、\)\s]+", "", text).strip()
            if clean_text:
                news_items.append((clean_text, href))

    # 策略2: 如果没提取到带链接的条目，退化为纯文本提取
    if not news_items:
        for br in soup.find_all(["br", "p", "div", "li"]):
            br.insert_before("\n")
        raw_text = soup.get_text()
        lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
        for line in lines:
            match = re.match(r"^\d+[\.\、\)\s]+(.*)", line)
            if match:
                news_items.append((match.group(1).strip(), ""))
            elif len(line) > 10 and not line.startswith("http"):
                news_items.append((line, ""))

    return news_items


def fetch_all_rss_news():
    """依次从 RSS 源获取新闻，返回去重后的列表"""
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/125.0.0.0"}
    all_news = []  # [(title, link), ...]
    seen_titles = set()

    for url in RSS_FEEDS:
        try:
            print(f"[抓取] {url}")
            response = requests.get(url, headers=headers, timeout=20)
            response.raise_for_status()
            feed = feedparser.parse(response.content)
            print(f"  -> 获取到 {len(feed.entries)} 个条目")

            for entry in feed.entries:
                # 1) 尝试从 content/description 中提取带链接的新闻列表
                content_html = ""
                if hasattr(entry, "content") and entry.content:
                    content_html = entry.content[0].get("value", "")
                if not content_html:
                    content_html = entry.get("description", "") or entry.get("summary", "")

                items = extract_news_from_html(content_html)

                # 2) 如果 entry 本身就是一条新闻（无嵌套列表）
                if not items and hasattr(entry, "title") and hasattr(entry, "link"):
                    title = entry.title.strip()
                    if len(title) > 5:
                        items = [(title, entry.link)]

                # 去重并添加
                for title, link in items:
                    key = title[:30]  # 用前30字符做去重键
                    if key not in seen_titles:
                        seen_titles.add(key)
                        all_news.append((title, link))

        except Exception as e:
            print(f"[警告] 获取 {url} 失败: {e}")

    print(f"[汇总] 共获取 {len(all_news)} 条不重复新闻")
    return all_news[:TARGET_NEWS_COUNT]


def build_html_message(news_list, quote_en, quote_cn):
    """构建 HTML 格式的推送消息"""
    today = get_beijing_now()
    week_days = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
    week_day = week_days[today.weekday()]
    lunar_str = get_lunar_date_str(today)
    date_str = f"{today.year}年{today.month:02d}月{today.day:02d}日 {week_day}{lunar_str}"

    # 构建新闻列表 HTML
    news_html_parts = []
    for i, (title, link) in enumerate(news_list, 1):
        if link:
            news_html_parts.append(
                f'<p style="margin:6px 0;line-height:1.7;">'
                f'<span style="color:#0969da;font-weight:bold;">{i}.</span> '
                f'<a href="{link}" style="color:#1a1a1a;text-decoration:none;" target="_blank">{title}</a>'
                f'</p>'
            )
        else:
            news_html_parts.append(
                f'<p style="margin:6px 0;line-height:1.7;">'
                f'<span style="color:#0969da;font-weight:bold;">{i}.</span> {title}'
                f'</p>'
            )
    news_html = "\n".join(news_html_parts)

    html = f"""
<div style="max-width:640px;margin:0 auto;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;font-size:15px;color:#1a1a1a;">

  <!-- 日期头部 -->
  <div style="background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);color:#fff;padding:16px 20px;border-radius:10px 10px 0 0;text-align:center;">
    <div style="font-size:18px;font-weight:bold;">📡 每日AI资讯</div>
    <div style="font-size:13px;margin-top:6px;opacity:0.9;">{date_str}</div>
  </div>

  <!-- 新闻列表 -->
  <div style="background:#fff;padding:16px 20px;border-left:1px solid #e5e7eb;border-right:1px solid #e5e7eb;">
    {news_html}
  </div>

  <!-- 每日一句 -->
  <div style="background:#f8f9fa;padding:16px 20px;border-radius:0 0 10px 10px;border:1px solid #e5e7eb;border-top:none;">
    <div style="font-size:13px;color:#6b7280;margin-bottom:6px;">✨ 每日一句</div>
    <div style="font-size:14px;color:#374151;font-style:italic;line-height:1.6;">{quote_en}</div>
    <div style="font-size:14px;color:#6b7280;margin-top:4px;">{quote_cn}</div>
  </div>

  <!-- 底部来源 -->
  <div style="text-align:center;font-size:12px;color:#9ca3af;margin-top:10px;">
    数据来源：<a href="https://aihot.virxact.com" style="color:#9ca3af;">AIHOT</a> ｜ 每日一句：<a href="http://open.iciba.com" style="color:#9ca3af;">金山词霸</a>
  </div>

</div>
"""
    return html.strip()


def send_to_wechat(title, html_content):
    """通过 PushPlus 推送 HTML 消息到微信"""
    if not PUSHPLUS_TOKEN or PUSHPLUS_TOKEN == "你的PushPlus_Token":
        print("[错误] 未配置 PUSHPLUS_TOKEN，请设置环境变量或修改代码！")
        return False

    url = "http://www.pushplus.plus/send"
    data = {
        "token": PUSHPLUS_TOKEN,
        "title": title,
        "content": html_content,
        "template": "html",  # 使用 HTML 模板，支持链接和样式
    }

    try:
        response = requests.post(url, json=data, timeout=15)
        result = response.json()
        if result.get("code") == 200:
            print(f"[成功] 微信推送成功！")
            return True
        else:
            print(f"[失败] 推送失败: {result}")
            return False
    except Exception as e:
        print(f"[错误] 推送请求异常: {e}")
        return False


def main():
    """主函数 - 单次执行，适配 GitHub Actions"""
    print(f"========== 每日AI资讯推送 ==========")
    print(f"运行时间: {get_beijing_now().strftime('%Y-%m-%d %H:%M:%S')} (北京时间)")
    print()

    # 1. 获取新闻
    news_list = fetch_all_rss_news()
    if not news_list:
        send_to_wechat("每日AI资讯获取失败", "<p>未能从RSS源获取到任何新闻，请检查数据源状态。</p>")
        print("[结束] 未获取到新闻")
        return

    # 2. 获取每日一句
    quote_en, quote_cn = get_daily_quote()
    print(f"[每日一句] {quote_en} / {quote_cn}")

    # 3. 构建并推送消息
    html_content = build_html_message(news_list, quote_en, quote_cn)
    today_str = get_beijing_now().strftime("%m月%d日")
    title = f"每日AI资讯 ({today_str})"

    send_to_wechat(title, html_content)
    print(f"\n========== 执行完毕 ==========")


if __name__ == "__main__":
    main()
