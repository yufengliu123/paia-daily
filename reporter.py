import os
import re as _re
from datetime import datetime

from config import REPORT_DIR, CATEGORIES, CATEGORY_COLORS


def _get_all_fields(ai_summary):
    """Extract fields from concise AI summary."""
    lines = ai_summary.split("\n")
    fields = {}
    current_field = None

    for line in lines:
        line = line.strip()
        for tag in ["标题", "分类", "重要度", "要点", "分析", "关键词"]:
            prefix = f"【{tag}】"
            if line.startswith(prefix):
                current_field = tag
                fields[tag] = line[len(prefix):].strip()
                break
        else:
            if current_field and line:
                fields[current_field] = fields.get(current_field, "") + "\n" + line

    # 要点转成 bullets
    key_points = fields.get("要点", "")
    if key_points:
        bullets = []
        for pt in key_points.split("\n"):
            pt = pt.strip("- ").strip()
            if pt:
                bullets.append(f"<li>{pt}</li>")
        key_points = f"<ul class='card-bullets'>{''.join(bullets)}</ul>" if bullets else ""

    return {
        "title": fields.get("标题", ""),
        "category": fields.get("分类", "综合"),
        "importance": fields.get("重要度", "★★★☆☆"),
        "core": key_points,
        "insight": fields.get("分析", ""),
        "keywords": fields.get("关键词", ""),
    }


def _star_count(s):
    return s.count("★")


def _render_digest(text):
    """Render markdown to HTML with table support."""
    if not text:
        return ""
    lines = text.strip().split("\n")
    out = []
    in_list = False
    in_table = False
    table_rows = []

    for line in lines:
        line = line.rstrip()

        # Empty line
        if not line:
            if in_list:
                out.append("</ul>")
                in_list = False
            if in_table:
                out.append(_build_table(table_rows))
                table_rows = []
                in_table = False
            continue

        # Table detection
        if line.startswith("|") and line.endswith("|"):
            if in_list:
                out.append("</ul>"); in_list = False
            if "---" in line:
                table_rows.append(("sep", line))
            else:
                cells = [c.strip() for c in line[1:-1].split("|")]
                table_rows.append(("row", cells))
            in_table = True
            continue

        # Exit table mode on non-table line
        if in_table:
            out.append(_build_table(table_rows))
            table_rows = []
            in_table = False

        # Headings / lists / paragraphs
        if line.startswith("### "):
            if in_list:
                out.append("</ul>"); in_list = False
            out.append(f"<h4 class='dg-h4'>{line[4:]}</h4>")
        elif line.startswith("## "):
            if in_list:
                out.append("</ul>"); in_list = False
            out.append(f"<h3 class='dg-h3'>{line[3:]}</h3>")
        elif line.startswith("- ") or line.startswith("* "):
            if not in_list:
                out.append("<ul class='dg-ul'>"); in_list = True
            content = _re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", line[2:])
            out.append(f"<li>{content}</li>")
        else:
            if in_list:
                out.append("</ul>"); in_list = False
            line = _re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", line)
            if line.startswith("# "):
                out.append(f"<h2 class='dg-h2'>{line[2:]}</h2>")
            else:
                out.append(f"<p class='dg-p'>{line}</p>")

    if in_list:
        out.append("</ul>")
    if in_table:
        out.append(_build_table(table_rows))

    return "\n".join(out)


def _build_table(rows):
    """Build HTML table from parsed markdown rows."""
    if not rows:
        return ""
    has_header = len(rows) >= 2 and rows[1][0] == "sep"
    html = "<table class='dg-table'><thead><tr>"
    for cell in rows[0][1]:
        html += f"<th>{cell}</th>"
    html += "</tr></thead><tbody>"
    for i in range(2 if has_header else 0, len(rows)):
        if rows[i][0] == "sep":
            continue
        html += "<tr>"
        for cell in rows[i][1]:
            html += f"<td>{cell}</td>"
        html += "</tr>"
    html += "</tbody></table>"
    return html


# ──────────────────────────────────────────────
CSS = """\
    :root {
        --c-bg: #ffffff;
        --c-card: #ffffff;
        --c-text: #1a1a2e;
        --c-text2: #5a5a7a;
        --c-border: #e8e4df;
        --radius: 14px;
        --shadow-sm: 0 1px 2px rgba(0,0,0,0.03);
        --shadow: 0 2px 8px rgba(0,0,0,0.04);
        --shadow-hover: 0 8px 30px rgba(0,0,0,0.08);
    }
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body {
        font-family: "PingFang SC", "Microsoft YaHei", -apple-system, BlinkMacSystemFont, "Noto Sans SC", sans-serif;
        background: var(--c-bg);
        color: var(--c-text);
        font-size: 15px;
        line-height: 1.75;
        -webkit-font-smoothing: antialiased;
    }

    /* layout */
    .app { max-width: 1400px; margin: 0 auto; padding: 20px 28px 48px; }

    /* header */
    .masthead {
        background: linear-gradient(135deg, #0f172a 0%, #1a1a3e 30%, #312e81 60%, #1e3a5f 100%);
        color: #fff;
        border-radius: 18px;
        padding: 44px 40px;
        margin-bottom: 22px;
        position: relative;
        overflow: hidden;
        box-shadow: 0 4px 40px rgba(79,70,229,0.15);
    }
    .masthead::before {
        content: "";
        position: absolute; inset: 0;
        background: radial-gradient(circle at 20% 30%, rgba(236,72,153,0.15) 0%, transparent 40%),
                    radial-gradient(circle at 80% 70%, rgba(59,130,246,0.15) 0%, transparent 40%),
                    radial-gradient(circle at 50% 50%, rgba(139,92,246,0.08) 0%, transparent 60%);
        animation: mastGradient 8s ease-in-out infinite;
    }
    @keyframes mastGradient {
        0%, 100% { opacity: 0.8; }
        50% { opacity: 1; }
    }
    .masthead::after {
        content: "";
        position: absolute; top: -40px; right: -40px;
        width: 200px; height: 200px;
        border: 1px solid rgba(255,255,255,0.04); border-radius: 50%;
        animation: glowPulse 4s ease-in-out infinite;
    }
    @keyframes glowPulse {
        0%, 100% { opacity: 0.4; transform: scale(1); }
        50% { opacity: 1; transform: scale(1.05); }
    }
    .masthead h1 { font-size: 32px; font-weight: 800; position: relative; z-index: 1; letter-spacing: -0.5px; }
    .masthead .sub {
        font-size: 14px; opacity: 0.75; margin-top: 12px;
        display: flex; flex-wrap: wrap; gap: 18px; align-items: center;
        position: relative; z-index: 1;
    }
    .stat-chip {
        font-size: 12px; border: 1px solid rgba(255,255,255,0.2); border-radius: 14px;
        padding: 3px 12px; font-weight: 500; background: rgba(255,255,255,0.06);
        backdrop-filter: blur(4px);
    }

    /* tabs */
    .tabs { display: flex; gap: 6px; margin-bottom: 22px; flex-wrap: wrap; }
    .tab-btn {
        border: 1px solid var(--c-border); background: var(--c-card); color: var(--c-text2);
        font-size: 13px; font-weight: 500; padding: 10px 22px;
        border-radius: 22px; cursor: pointer; transition: all 0.25s;
        box-shadow: var(--shadow-sm); font-family: inherit;
    }
    .tab-btn:hover { background: #f1f5f9; transform: translateY(-1px); box-shadow: var(--shadow); }
    .tab-btn.active { background: #0f172a; color: #fff; border-color: #0f172a; box-shadow: 0 4px 16px rgba(15,23,42,0.25); }

    /* panels */
    .panel { display: none; }
    .panel.active { display: block; }

    /* digest */
    .digest-panel {
        background: var(--c-card); border-radius: var(--radius);
        padding: 32px 38px; margin-bottom: 26px;
        box-shadow: var(--shadow); border: 1px solid var(--c-border);
    }
    .dg-h2 { font-size: 21px; color: #0f172a; margin: 30px 0 12px; font-weight: 700; letter-spacing: -0.3px; }
    .dg-h2:first-child { margin-top: 0; }
    .dg-h3 { font-size: 17px; color: #1a1a2e; margin: 24px 0 10px; font-weight: 600;
             padding-bottom: 8px; border-bottom: 2px solid #f1f5f9; }
    .dg-h4 { font-size: 15px; color: #334155; margin: 18px 0 6px; font-weight: 600; }
    .dg-p { font-size: 14px; color: #475569; margin: 8px 0; line-height: 1.85; }
    .dg-ul { padding-left: 22px; margin: 8px 0; font-size: 14px; color: #475569; }
    .dg-ul li { margin: 5px 0; }
    .digest-panel strong { color: #dc2626; }

    /* table */
    .dg-table {
        width: 100%; border-collapse: collapse; margin: 16px 0;
        font-size: 13px; border-radius: 10px; overflow: hidden;
        box-shadow: var(--shadow-sm); border: 1px solid var(--c-border);
    }
    .dg-table thead { background: #0f172a; color: #fff; }
    .dg-table th { padding: 11px 14px; text-align: left; font-weight: 500; }
    .dg-table td { padding: 10px 14px; border-bottom: 1px solid #f8fafc; color: var(--c-text2); }
    .dg-table tbody tr:hover { background: #faf9f7; }
    .dg-table td:last-child a { color: #3b82f6; text-decoration: none; font-size: 12px; }

    /* category section */
    .cat-section { margin-bottom: 30px; }
    .cat-header {
        display: flex; align-items: center; gap: 12px;
        margin-bottom: 18px; padding-bottom: 14px;
        border-bottom: 2px solid #f1f5f9;
    }
    .cat-dot { width: 12px; height: 12px; border-radius: 50%; flex-shrink: 0; box-shadow: 0 0 8px currentColor; }
    .cat-title { font-size: 20px; font-weight: 700; color: #0f172a; }
    .cat-count {
        font-size: 13px; color: #94a3b8; font-weight: 400;
        background: #f8fafc; padding: 2px 10px; border-radius: 10px;
    }

    /* cards with scroll animation */
    .card-list { display: grid; grid-template-columns: repeat(auto-fill, minmax(420px, 1fr)); gap: 18px; }
    .card {
        background: var(--c-card); border-radius: var(--radius);
        padding: 22px 26px; box-shadow: var(--shadow);
        border: 1px solid var(--c-border);
        border-left: 3px solid var(--color, #94a3b8);
        transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        position: relative; overflow: hidden;
        animation: cardIn 0.6s ease-out both;
        animation-timeline: view();
        animation-range: entry 0% entry 100%;
    }
    @keyframes cardIn {
        from { opacity: 0; transform: translateY(30px); filter: blur(2px); }
        to { opacity: 1; transform: translateY(0); filter: blur(0); }
    }
    .card::after {
        content: ""; position: absolute; inset: 0;
        background: radial-gradient(circle at 100% 0%, rgba(59,130,246,0.03), transparent 60%),
                    radial-gradient(circle at 0% 100%, rgba(139,92,246,0.02), transparent 50%);
        pointer-events: none;
    }
    /* liquid glass border glow on hover */
    .card::before {
        content: ""; position: absolute; inset: -1px; border-radius: calc(var(--radius) + 1px);
        background: linear-gradient(135deg, rgba(59,130,246,0.15), transparent, rgba(139,92,246,0.1));
        opacity: 0; transition: opacity 0.4s; z-index: 0; pointer-events: none;
    }
    .card:hover::before { opacity: 1; }
    .card:hover {
        box-shadow: 0 12px 40px rgba(0,0,0,0.1), 0 0 0 1px rgba(59,130,246,0.1);
        transform: translateY(-4px);
        border-left-width: 4px;
    }
    .card-meta {
        display: flex; flex-wrap: wrap; align-items: center; gap: 8px; margin-bottom: 8px; position: relative; z-index: 1;
    }
    .src-badge {
        font-size: 11px; padding: 2px 10px; border-radius: 10px; font-weight: 600;
    }
    .star { font-size: 12px; color: #cbd5e1; }
    .star.full { color: #f59e0b; }
    .pub-date { font-size: 11px; color: #94a3b8; }
    .card-title { font-size: 15px; font-weight: 600; margin-bottom: 8px; color:#0f172a; line-height:1.45; position: relative; z-index: 1; }
    .card-core { font-size: 14px; color: #475569; line-height: 1.75; position: relative; z-index: 1; }
    .card-bullets { padding-left: 18px; margin: 6px 0; }
    .card-bullets li { margin: 5px 0; font-size: 13px; color: #475569; }
    .card-insight {
        font-size: 13px; color: #92400e; background: linear-gradient(90deg, #fffbeb, #fef3c7);
        border-left: 3px solid #f59e0b; margin: 12px 0 4px;
        padding: 10px 14px; border-radius: 0 8px 8px 0; line-height: 1.65;
        position: relative; z-index: 1;
    }
    .card-bottom {
        display: flex; flex-wrap: wrap; align-items: center; gap: 8px; margin-top: 12px; position: relative; z-index: 1;
    }
    .kw-tag {
        font-size: 11px; background: #f1f5f9; color: #64748b;
        padding: 3px 10px; border-radius: 8px; font-weight: 500;
    }
    .card-link {
        font-size: 12px; color: #3b82f6; text-decoration: none; font-weight: 500; margin-left: auto;
    }
    .card-link:hover { text-decoration: underline; }

    /* footer */
    .footer {
        text-align: center; padding: 32px 16px 8px;
        font-size: 12px; color: #94a3b8; border-top: 1px solid #e8e4df; margin-top: 24px;
    }

    @media (max-width: 600px) {
        .app { padding: 12px 12px 32px; }
        .masthead { padding: 28px 22px; border-radius: 14px; }
        .masthead h1 { font-size: 24px; }
        .card { padding: 16px 18px; }
        .card-list { grid-template-columns: 1fr; }
        .digest-panel { padding: 20px 18px; }
    }

/* empty state */
.empty-state { text-align: center; padding: 40px; color: #94a3b8; }

/* footer */
.footer {
    text-align: center; padding: 24px; margin-top: 20px;
    font-size: 12px; color: #94a3b8; border-top: 1px solid var(--c-border);
}

@media (max-width: 600px) {
    .app { padding: 12px 8px 32px; }
    .masthead { padding: 24px 20px; }
    .masthead h1 { font-size: 22px; }
    .card { padding: 14px 16px; }
}
"""

JS = """\
function switchTab(panelId, btn) {
    document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.getElementById(panelId).classList.add('active');
    btn.classList.add('active');
}
"""


class HTMLReporter:
    def __init__(self):
        os.makedirs(REPORT_DIR, exist_ok=True)

    def generate(self, digest: str, entries: list[dict]) -> str:
        today = datetime.now().strftime("%Y-%m-%d")
        weekdays = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
        date_cn = f"{datetime.now().strftime('%Y年%m月%d日')} {weekdays[datetime.now().weekday()]}"
        now = datetime.now().strftime("%Y-%m-%d %H:%M")

        # process entries
        processed = []
        for e in entries:
            fld = _get_all_fields(e.get("ai_summary", ""))
            fld["source"] = e.get("source", "")
            fld["link"] = e.get("link", "")
            fld["published"] = e.get("published", "")
            fld["raw_title"] = e.get("title", "")
            processed.append(fld)

        # categorize & sort by importance
        categorized = {}
        for p in processed:
            cat = p.get("category", "综合")
            categorized.setdefault(cat, []).append(p)
        for cat in categorized:
            categorized[cat].sort(key=lambda x: _star_count(x.get("importance", "")), reverse=True)

        # stats chips
        color_map = CATEGORY_COLORS
        cat_order = ["宏观政策", "数字中国", "乡村振兴", "产业发展", "生态文明", "民生保障", "国家安全", "综合"]
        stats_chips = ""
        for cat_name in cat_order:
            items = categorized.get(cat_name, [])
            if not items:
                continue
            c = color_map.get(cat_name, "#7f8c8d")
            stats_chips += (
                f'<span class="stat-chip" style="border-color:{c};color:{c}">'
                f'{cat_name} {len(items)}</span> '
            )

        # build tab buttons
        tab_btns = (
            '<button class="tab-btn active" onclick="switchTab(\'panel-digest\',this)">'
            '&#128203; 今日综述</button>'
        )
        for cat_name in cat_order:
            items = categorized.get(cat_name, [])
            if not items:
                continue
            tab_btns += (
                f'<button class="tab-btn" onclick="switchTab(\'panel-{cat_name}\',this)">'
                f'{cat_name} ({len(items)})</button>'
            )

        # build panels
        digest_html = _render_digest(digest)
        panels = (
            '<div class="panel active digest-panel" id="panel-digest">'
            f'{digest_html}</div>'
        )

        for cat_name in cat_order:
            items = categorized.get(cat_name, [])
            if not items:
                continue
            c = color_map.get(cat_name, "#7f8c8d")

            cards = ""
            for p in items:
                title = p.get("title") or p.get("raw_title", "")
                core = p.get("core", "")
                insight = p.get("insight", "")
                background = p.get("background", "")
                eco = p.get("eco_impact", "")
                soc = p.get("soc_impact", "")
                gov = p.get("gov_impact", "")
                advice = p.get("advice", "")
                keywords = p.get("keywords", "")
                importance = p.get("importance", "")
                source = p.get("source", "")
                link = p.get("link", "")
                pub = p.get("published", "")

                stars = ""
                sc = _star_count(importance)

                kw_tags = ""
                if keywords:
                    for kw in keywords.replace("，", ",").replace("、", ",").split(","):
                        kw = kw.strip()
                        if kw:
                            kw_tags += f"<span class='kw-tag'>{kw}</span>"

                # Impact rows
                impact_html = ""
                if eco or soc or gov:
                    impact_html = "<div class='card-impacts'>"
                    if eco:
                        impact_html += f"<div class='impact-row'><span class='impact-label'>经济</span>{eco}</div>"
                    if soc:
                        impact_html += f"<div class='impact-row'><span class='impact-label'>社会</span>{soc}</div>"
                    if gov:
                        impact_html += f"<div class='impact-row'><span class='impact-label'>治理</span>{gov}</div>"
                    impact_html += "</div>"

                cards += f"""\
                <article class="card" style="--color:{c}">
                    <div class="card-meta">
                        <span class="src-badge" style="background:{c}15;color:{c}">{source}</span>
                        {importance}
                        {f'<span class="pub-date">{pub}</span>' if pub else ''}
                    </div>
                    <h4 class="card-title">{title}</h4>
                    {f'<div class="card-bg">{background}</div>' if background else ''}
                    <div class="card-core">{core}</div>
                    {impact_html}
                    {f'<blockquote class="card-insight">{insight}</blockquote>' if insight else ''}
                    {f'<div class="card-advice">&#128161; {advice}</div>' if advice else ''}
                    <div class="card-bottom">
                        {kw_tags}
                        <a class="card-link" href="{link}" target="_blank">查看原文</a>
                    </div>
                </article>"""

            panels += f"""\
            <div class="panel" id="panel-{cat_name}">
                <div class="cat-header">
                    <span class="cat-dot" style="background:{c}"></span>
                    <h2 class="cat-title">{cat_name}</h2>
                    <span class="cat-count">{len(items)} 条</span>
                </div>
                <div class="card-list">{cards if cards else '<div class="empty-state">暂无信息</div>'}</div>
            </div>"""

        html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>PAIA Daily - {date_cn}</title>
<style>{CSS}</style>
</head>
<body>
<div class="app">

    <header class="masthead">
        <h1>公共管理 · 每日晨报</h1>
        <div class="sub">
            <span>{date_cn}</span><span>|</span>
            <span>共 {len(processed)} 条</span><span>|</span>
            {stats_chips}
        </div>
    </header>

    <nav class="tabs">{tab_btns}</nav>

    {panels}

    <footer class="footer">
        PAIA &middot; Public Admin Intelligence Assistant &middot; Generated at {now} &middot; Powered by DeepSeek
    </footer>

</div>
<script>{JS}</script>
</body>
</html>"""

        filename = f"PAIA_Daily_{today}.html"
        filepath = os.path.join(REPORT_DIR, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"[report] generated: {filepath}")
        return filepath
