"""
每日AI资讯 - 自动抓取 & 微信推送脚本 (v2)
使用 AIHOT JSON API 获取结构化数据，每条新闻自带原文链接和来源
适配 GitHub Actions 定时运行，使用 PushPlus 推送 HTML 格式消息
"""

import requests
import os
import json
from datetime import datetime, timezone, timedelta

# 尝试导入农历库
try:
    from lunarcalendar import Converter, Solar
    HAS_LUNAR = True
except ImportError:
    HAS_LUNAR = False

# ================= 配置区域 =================
PUSHPLUS_TOKEN = os.environ.get("PUSHPLUS_TOKEN", "你的PushPlus_Token")

# AIHOT API 配置
AIHOT_BASE = "https://aihot.virxact.com"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"

# 目标新闻条数
TARGET_NEWS_COUNT = 50

# 金山词霸每日一句 API
ICIBA_API = "http://open.iciba.com/dsapi/"

# 分类中文映射
CATEGORY_MAP = {
    "ai-models": "🤖 模型发布",
    "ai-products": "📦 产品发布",
    "industry": "📊 行业动态",
    "paper": "📄 论文研究",
    "tip": "💡 技巧与观点",
}
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


def fetch_daily_news():
    """
    从 AIHOT JSON API 获取今日日报（结构化数据）。
    返回按分类分组的新闻列表:
    [{"category": "模型发布", "items": [{"title": ..., "url": ..., "source": ..., "summary": ...}, ...]}, ...]
    """
    headers = {"User-Agent": UA}
    
    # 优先拉日报（编辑精选的成品）
    print("[抓取] 尝试获取今日日报...")
    try:
        resp = requests.get(f"{AIHOT_BASE}/api/public/daily", headers=headers, timeout=20)
        if resp.status_code == 200:
            data = resp.json()
            sections = data.get("sections", [])
            if sections:
                print(f"  -> 日报获取成功，日期: {data.get('date', '未知')}，共 {len(sections)} 个版块")
                result = []
                for sec in sections:
                    label = sec.get("label", "其他")
                    items = sec.get("items", [])
                    news_items = []
                    for item in items:
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

    # 日报不可用时，退回精选条目
    print("[抓取] 退回精选条目...")
    try:
        since = (get_beijing_now() - timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%SZ")
        resp = requests.get(
            f"{AIHOT_BASE}/api/public/items",
            params={"mode": "selected", "since": since, "take": TARGET_NEWS_COUNT},
            headers=headers,
            timeout=20,
        )
        if resp.status_code == 200:
            data = resp.json()
            items = data.get("items", [])
            print(f"  -> 精选条目获取成功，共 {len(items)} 条")

            # 按 category 分组
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

            result = [{"category": cat, "items": news} for cat, news in grouped.items()]
            return result, "selected"
    except Exception as e:
        print(f"  -> 精选条目获取失败: {e}")

    return [], "none"


def build_html_message(sections, source_type, quote_en, quote_cn):
    """构建 HTML 格式的推送消息（按分类展示，每条带来源和链接）"""
    today = get_beijing_now()
    week_days = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
    week_day = week_days[today.weekday()]
    lunar_str = get_lunar_date_str(today)
    date_str = f"{today.year}年{today.month:02d}月{today.day:02d}日 {week_day}{lunar_str}"

    # 统计总条数
    total = sum(len(sec["items"]) for sec in sections)
    subtitle = "AI HOT 日报" if source_type == "daily" else "AI HOT 精选"

    # 构建各分类 HTML
    sections_html = ""
    idx = 0
    for sec in sections:
        cat = sec["category"]
        items = sec["items"]
        
        # 分类标题
        sections_html += f'''
    <div style="margin:18px 0 8px 0;padding:8px 12px;background:#f0f4ff;border-left:3px solid #667eea;border-radius:0 6px 6px 0;font-size:15px;font-weight:bold;color:#4338ca;">
      {cat}（{len(items)} 篇）
    </div>'''

        for item in items:
            idx += 1
            title = item["title"]
            url = item["url"]
            source = item["source"]
            summary = item["summary"]

            # 来源标签（醒目的灰色背景标签）
            source_tag = ""
            if source:
                source_tag = f' <span style="background:#eef1f5;color:#555;font-size:12px;padding:2px 8px;border-radius:4px;">[{source}]</span>'

            # 摘要行
            summary_html = ""
            if summary:
                short = summary[:100] + "..." if len(summary) > 100 else summary
                summary_html = f'<div style="font-size:13px;color:#888;margin-top:4px;line-height:1.5;">{short}</div>'

            # 原文链接行（单独一行，蓝色醒目可点击）
            link_html = ""
            if url:
                link_html = f'<div style="margin-top:4px;"><a href="{url}" style="color:#1a73e8;font-size:13px;text-decoration:underline;" target="_blank">🔗 查看原文</a></div>'

            sections_html += f'''
    <div style="margin:8px 0;padding:10px 12px;border-bottom:1px solid #f0f0f0;">
      <div style="line-height:1.6;font-size:15px;">
        <span style="color:#667eea;font-weight:bold;">{idx}.</span>
        <b>{title}</b>{source_tag}
      </div>{summary_html}{link_html}
    </div>'''

    html = f'''
<div style="max-width:640px;margin:0 auto;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;font-size:15px;color:#1a1a1a;">

  <!-- 头部 -->
  <div style="background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);color:#fff;padding:18px 20px;border-radius:10px 10px 0 0;text-align:center;">
    <div style="font-size:18px;font-weight:bold;">📡 每日AI资讯</div>
    <div style="font-size:13px;margin-top:6px;opacity:0.9;">{date_str}</div>
    <div style="font-size:12px;margin-top:4px;opacity:0.7;">{subtitle} · 共 {total} 条</div>
  </div>

  <!-- 新闻列表 -->
  <div style="background:#fff;padding:4px 8px;border-left:1px solid #e5e7eb;border-right:1px solid #e5e7eb;">
    {sections_html}
  </div>

  <!-- 每日一句 -->
  <div style="background:#f8f9fa;padding:16px 20px;border:1px solid #e5e7eb;border-top:none;">
    <div style="font-size:13px;color:#6b7280;margin-bottom:6px;">✨ 每日一句</div>
    <div style="font-size:14px;color:#374151;font-style:italic;line-height:1.6;">{quote_en}</div>
    <div style="font-size:14px;color:#6b7280;margin-top:4px;">{quote_cn}</div>
  </div>

  <!-- 底部 -->
  <div style="background:#f8f9fa;padding:10px 20px;border-radius:0 0 10px 10px;border:1px solid #e5e7eb;border-top:none;text-align:center;font-size:12px;color:#9ca3af;">
    数据来源：<a href="https://aihot.virxact.com" style="color:#667eea;">AI HOT</a> ｜ 每日一句：<a href="http://open.iciba.com" style="color:#667eea;">金山词霸</a>
  </div>

</div>
'''
    return html.strip()


def send_to_wechat(title, html_content):
    """通过 PushPlus 推送 HTML 消息到微信"""
    if not PUSHPLUS_TOKEN or PUSHPLUS_TOKEN == "你的PushPlus_Token":
        print("[错误] 未配置 PUSHPLUS_TOKEN，请设置环境变量！")
        return False

    url = "http://www.pushplus.plus/send"
    data = {
        "token": PUSHPLUS_TOKEN,
        "title": title,
        "content": html_content,
        "template": "html",
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
    """主函数 - 单次执行"""
    print(f"========== 每日AI资讯推送 v2 ==========")
    print(f"运行时间: {get_beijing_now().strftime('%Y-%m-%d %H:%M:%S')} (北京时间)")
    print()

    # 1. 获取新闻（使用 JSON API）
    sections, source_type = fetch_daily_news()
    if not sections:
        send_to_wechat(
            "每日AI资讯获取失败",
            "<p>未能从 AIHOT API 获取到任何新闻，请检查数据源状态。</p>"
        )
        print("[结束] 未获取到新闻")
        return

    total = sum(len(sec["items"]) for sec in sections)
    print(f"[汇总] 共 {len(sections)} 个分类，{total} 条新闻")

    # 2. 获取每日一句
    quote_en, quote_cn = get_daily_quote()
    print(f"[每日一句] {quote_en} / {quote_cn}")

    # 3. 构建并推送
    html_content = build_html_message(sections, source_type, quote_en, quote_cn)
    today_str = get_beijing_now().strftime("%m月%d日")
    title = f"每日AI资讯 ({today_str})"

    send_to_wechat(title, html_content)
    print(f"\n========== 执行完毕 ==========")


if __name__ == "__main__":
    main()
