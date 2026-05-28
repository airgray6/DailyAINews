"""
每日AI资讯 - 自动抓取 & 微信推送脚本 (v3)
方案：生成 HTML 页面部署到 GitHub Pages，PushPlus 推送摘要 + 页面链接
解决 PushPlus 不支持链接点击的问题
"""

import requests
import os
import json
import subprocess
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

# GitHub Pages 配置（自动从环境变量获取）
GITHUB_REPO = os.environ.get("GITHUB_REPOSITORY", "airgray6/DailyAINews")
PAGES_URL = f"https://{GITHUB_REPO.split('/')[0]}.github.io/{GITHUB_REPO.split('/')[1]}"

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

    # 优先拉日报
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

    # 退回精选条目
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


def generate_html_page(sections, source_type, quote_en, quote_cn):
    """生成完整的 HTML 页面文件（带可点击链接），部署到 GitHub Pages"""
    today = get_beijing_now()
    week_days = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
    week_day = week_days[today.weekday()]
    lunar_str = get_lunar_date_str(today)
    date_str = f"{today.year}年{today.month:02d}月{today.day:02d}日 {week_day}{lunar_str}"
    total = sum(len(s["items"]) for s in sections)
    subtitle = "AI HOT 日报" if source_type == "daily" else "AI HOT 精选"

    # 构建新闻条目 HTML
    news_html = ""
    idx = 0
    for sec in sections:
        cat = sec["category"]
        items = sec["items"]
        news_html += f'''
        <div class="section-title">{cat}（{len(items)} 篇）</div>'''

        for item in items:
            idx += 1
            title = item["title"]
            url = item["url"]
            source = item["source"]
            summary = item["summary"]

            source_tag = f'<span class="source">{source}</span>' if source else ""
            summary_short = (summary[:120] + "...") if len(summary) > 120 else summary
            summary_html = f'<div class="summary">{summary_short}</div>' if summary_short else ""

            if url:
                title_html = f'<a href="{url}" target="_blank" rel="noopener">{title}</a>'
            else:
                title_html = f'<span>{title}</span>'

            news_html += f'''
        <div class="news-item">
            <div class="news-title"><span class="idx">{idx}.</span> {title_html} {source_tag}</div>
            {summary_html}
        </div>'''

    html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>每日AI资讯 {today.strftime("%m月%d日")}</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #f5f5f5; color: #1a1a1a; line-height: 1.6; }}
.container {{ max-width: 680px; margin: 0 auto; padding: 0; }}
.header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: #fff; padding: 24px 20px; text-align: center; }}
.header h1 {{ font-size: 22px; margin-bottom: 6px; }}
.header .date {{ font-size: 14px; opacity: 0.9; }}
.header .sub {{ font-size: 13px; opacity: 0.7; margin-top: 4px; }}
.content {{ background: #fff; padding: 12px 16px; }}
.section-title {{ margin: 16px 0 8px 0; padding: 8px 12px; background: #f0f4ff; border-left: 3px solid #667eea; border-radius: 0 6px 6px 0; font-size: 16px; font-weight: bold; color: #4338ca; }}
.news-item {{ padding: 12px 0; border-bottom: 1px solid #f0f0f0; }}
.news-item:last-child {{ border-bottom: none; }}
.news-title {{ font-size: 15px; line-height: 1.6; }}
.news-title a {{ color: #1a73e8; text-decoration: none; font-weight: 500; }}
.news-title a:hover {{ text-decoration: underline; }}
.idx {{ color: #667eea; font-weight: bold; }}
.source {{ display: inline-block; background: #eef1f5; color: #555; font-size: 12px; padding: 1px 8px; border-radius: 4px; margin-left: 6px; vertical-align: middle; }}
.summary {{ font-size: 13px; color: #666; margin-top: 6px; line-height: 1.6; }}
.quote {{ background: #f9fafb; padding: 16px 20px; border-top: 1px solid #eee; }}
.quote .label {{ font-size: 13px; color: #999; margin-bottom: 6px; }}
.quote .en {{ font-size: 14px; color: #374151; font-style: italic; }}
.quote .cn {{ font-size: 14px; color: #888; margin-top: 4px; }}
.footer {{ text-align: center; padding: 12px; font-size: 12px; color: #aaa; }}
.footer a {{ color: #667eea; text-decoration: none; }}
</style>
</head>
<body>
<div class="container">
    <div class="header">
        <h1>📡 每日AI资讯</h1>
        <div class="date">{date_str}</div>
        <div class="sub">{subtitle} · 共 {total} 条</div>
    </div>
    <div class="content">
        {news_html}
    </div>
    <div class="quote">
        <div class="label">✨ 每日一句</div>
        <div class="en">{quote_en}</div>
        <div class="cn">{quote_cn}</div>
    </div>
    <div class="footer">
        数据来源：<a href="https://aihot.virxact.com">AI HOT</a> ｜ 每日一句：<a href="http://open.iciba.com">金山词霸</a>
    </div>
</div>
</body>
</html>'''

    # 写入文件
    os.makedirs("docs", exist_ok=True)
    date_file = today.strftime("%Y-%m-%d")
    filepath = f"docs/{date_file}.html"
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(html)

    # 同时更新 index.html 指向最新
    with open("docs/index.html", "w", encoding="utf-8") as f:
        f.write(f'<meta http-equiv="refresh" content="0;url={date_file}.html">')

    print(f"[生成] HTML 页面已保存: {filepath}")
    return filepath, date_file


def git_push_pages():
    """将 docs 目录推送到仓库，触发 GitHub Pages 部署"""
    try:
        subprocess.run(["git", "config", "user.name", "AI News Bot"], check=True)
        subprocess.run(["git", "config", "user.email", "bot@example.com"], check=True)
        subprocess.run(["git", "add", "docs/"], check=True)
        result = subprocess.run(["git", "commit", "-m", f"更新每日资讯 {get_beijing_now().strftime('%Y-%m-%d')}"],
                                capture_output=True, text=True)
        if result.returncode == 0:
            subprocess.run(["git", "push"], check=True)
            print("[推送] GitHub Pages 已更新")
            return True
        else:
            print(f"[跳过] 无变更需要提交: {result.stderr}")
            return True
    except Exception as e:
        print(f"[错误] Git 推送失败: {e}")
        return False


def build_wechat_summary(sections, date_file, quote_en, quote_cn):
    """构建推送到微信的精简摘要（附页面链接）"""
    today = get_beijing_now()
    week_days = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
    date_str = f"{today.month:02d}月{today.day:02d}日 {week_days[today.weekday()]}"

    total = sum(len(s["items"]) for s in sections)
    page_url = f"{PAGES_URL}/{date_file}.html"

    lines = []
    lines.append(f"📡 每日AI资讯 · {date_str}")
    lines.append(f"共 {total} 条，分 {len(sections)} 个版块")
    lines.append("")

    # 每个分类只列标题，不列摘要
    idx = 0
    for sec in sections:
        cat = sec["category"]
        lines.append(f"━━ {cat} ━━")
        for item in sec["items"]:
            idx += 1
            source = f" [{item['source']}]" if item["source"] else ""
            lines.append(f"{idx}. {item['title']}{source}")
        lines.append("")

    lines.append(f"✨ {quote_en}")
    lines.append(f"   {quote_cn}")
    lines.append("")
    lines.append(f"👉 点击查看完整内容（含原文链接）：")
    lines.append(page_url)

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
    print(f"========== 每日AI资讯推送 v3 ==========")
    print(f"运行时间: {get_beijing_now().strftime('%Y-%m-%d %H:%M:%S')} (北京时间)")
    print()

    # 1. 获取新闻
    sections, source_type = fetch_daily_news()
    if not sections:
        send_to_wechat("每日AI资讯获取失败", "未能从 AIHOT API 获取到新闻，请检查数据源。")
        return

    total = sum(len(s["items"]) for s in sections)
    print(f"[汇总] 共 {len(sections)} 个分类，{total} 条新闻")

    # 2. 获取每日一句
    quote_en, quote_cn = get_daily_quote()
    print(f"[每日一句] {quote_en} / {quote_cn}")

    # 3. 生成 HTML 页面
    filepath, date_file = generate_html_page(sections, source_type, quote_en, quote_cn)

    # 4. 推送到 GitHub Pages
    git_push_pages()

    # 5. 推送摘要到微信
    summary = build_wechat_summary(sections, date_file, quote_en, quote_cn)
    title = f"每日AI资讯 ({get_beijing_now().strftime('%m月%d日')})"
    send_to_wechat(title, summary)

    print(f"\n========== 执行完毕 ==========")


if __name__ == "__main__":
    main()
