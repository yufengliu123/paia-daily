"""
部署脚本 - 生成报告并发布到 GitHub Pages
运行: python deploy.py
"""
import json
import os
import subprocess
import sys
from datetime import datetime
from summarizer import DeepSeekSummarizer
from reporter import HTMLReporter


def deploy():
    print("=" * 50)
    print("  PAIA 部署 - 生成并发布")
    print("=" * 50)

    # 1. 从缓存生成报告
    cache_path = os.path.join(".cache", "latest_entries.json")
    if not os.path.exists(cache_path):
        print("[!] 无缓存数据，请先运行 python main.py")
        return

    with open(cache_path, "r", encoding="utf-8") as f:
        entries = json.load(f)

    entries_with_ai = [e for e in entries if e.get("ai_summary")]
    if not entries_with_ai:
        print("[!] 缓存中无 AI 摘要，请先运行 python main.py")
        return

    print(f"[1] 加载 {len(entries_with_ai)} 条 AI 摘要")

    # 2. 生成日报
    print("[2] 生成日报...")
    s = DeepSeekSummarizer()
    digest = s.generate_daily_digest(entries_with_ai)
    r = HTMLReporter()
    report_path = r.generate(digest, entries_with_ai)

    # 3. 复制报告为 index.html（GitHub Pages 默认页）
    index_path = os.path.join("output", "index.html")
    import shutil
    shutil.copy(report_path, index_path)
    print(f"[3] 已复制为 output/index.html")

    # 4. Git 提交推送
    print("[4] Git 提交...")
    try:
        subprocess.run(["git", "add", "output/"], check=True, capture_output=True)
        today = datetime.now().strftime("%Y-%m-%d")
        subprocess.run(["git", "commit", "-m", f"Daily update {today}"], 
                       check=True, capture_output=True)
        subprocess.run(["git", "push"], check=True, capture_output=True)
        print("[5] 推送成功！")
        print(f"    访问: https://YOUR_USERNAME.github.io/YOUR_REPO/")
    except subprocess.CalledProcessError as e:
        print(f"[!] Git 推送失败: {e}")
        print("    请先配置 GitHub 仓库: git remote add origin <你的仓库地址>")


if __name__ == "__main__":
    deploy()
