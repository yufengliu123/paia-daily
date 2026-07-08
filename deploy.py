"""Deploy to GitHub Pages"""
import json, os, shutil, subprocess, sys
from datetime import datetime
sys.path.insert(0, os.path.dirname(__file__))

def deploy():
    cache_path = ".cache/latest_entries.json"
    if not os.path.exists(cache_path):
        print("[!] No cache. Run python main.py --force first.")
        return
    with open(cache_path, "r", encoding="utf-8") as f:
        entries = json.load(f)
    ai_entries = [e for e in entries if e.get("ai_summary")]
    display_entries = entries  # 全部抓取结果，无 AI 摘要的也显示基础信息
    if not ai_entries:
        print("[!] No AI summaries.")
        return
    print(f"[1] {len(display_entries)} items ({len(ai_entries)} with AI)")

    from summarizer import DeepSeekSummarizer
    from reporter import HTMLReporter
    from server import _build_bar, _trends_raw

    s = DeepSeekSummarizer()
    digest = s.generate_daily_digest(display_entries)
    r = HTMLReporter()
    path = r.generate(digest, display_entries)
    print(f"[2] {path}")

    with open(path, "r", encoding="utf-8") as f:
        html = f.read()
    bar = _build_bar(_trends_raw())
    html = html.replace("<body>", f"<body>{bar}")

    # 静态填充（用全部抓取数）
    from collections import Counter
    total = len(display_entries)
    src = Counter(e.get("source","") for e in display_entries)
    cat = Counter(e.get("category","") for e in display_entries)
    src_count = len(src)
    top_cat = cat.most_common(1)[0] if cat else ("-", 0)
    today = datetime.now().strftime("%Y-%m-%d")

    html = html.replace('id="sTotal">-<', f'id="sTotal">{total}条<')
    html = html.replace('id="sSources">-<', f'id="sSources">{src_count}源<')
    html = html.replace('id="sTime" style="font-size:11px;opacity:0.5"><', f'id="sTime" style="font-size:11px;opacity:0.5">{today}<')
    html = html.replace('id="qsTime">-<', f'id="qsTime">{today}<')
    html = html.replace('id="qsTotal">-<', f'id="qsTotal">{total}条<')
    html = html.replace('id="qsSources">-<', f'id="qsSources">{src_count}个活跃源<')
    html = html.replace('id="qsTopCat">-<', f'id="qsTopCat">{top_cat[0]}({top_cat[1]}条)<')

    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"[3] Bar+Stats injected: {total} items, {src_count} sources")

    docs = "docs"
    os.makedirs(docs, exist_ok=True)
    shutil.copy(path, os.path.join(docs, "index.html"))
    shutil.copy(path, os.path.join(docs, os.path.basename(path)))
    print("[4] docs updated")

    subprocess.run(["git", "add", "docs/"], check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", f"Deploy {datetime.now().strftime('%Y-%m-%d')}"], check=True, capture_output=True)
    try:
        subprocess.run(["git", "push"], check=True, capture_output=True, timeout=30)
        print("[5] Pushed! https://yufengliu123.github.io/paia-daily/")
    except:
        print("[5] Push failed (run 'git push' manually)")

if __name__ == "__main__":
    deploy()
