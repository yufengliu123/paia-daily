"""
公共管理信息助手 - AI 驱动的政策信息聚合工具

功能：
  1. 从多个 RSS 源抓取公共管理相关资讯
  2. 使用 DeepSeek AI 对每条信息进行专业摘要
  3. 生成综合日报和分类卡片
  4. 输出精美的 HTML 报告

用法：
  python main.py              # 立即运行一次，生成今日报告
  python main.py --daemon     # 守护进程模式：持续运行，每日 7:00 自动执行
  python main.py --test       # 测试模式：使用缓存数据，限5条
  python main.py --setup-task # 注册 Windows 定时任务（推荐，无需保持窗口）
"""

import argparse
import json
import os
import sys
import logging
import traceback
from datetime import datetime

from fetcher import fetch_and_cache
from summarizer import DeepSeekSummarizer
from reporter import HTMLReporter

# ---------- 日志设置 ----------
os.makedirs("logs", exist_ok=True)
LOG_FILE = os.path.join("logs", f"assistant_{datetime.now().strftime('%Y%m')}.log")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("PublicAdmin")


def report_already_generated_today() -> bool:
    """检查今天的报告是否已经生成过"""
    from config import REPORT_DIR
    today = datetime.now().strftime("%Y-%m-%d")
    filename = f"PAIA_Daily_{today}.html"
    filepath = os.path.join(REPORT_DIR, filename)
    return os.path.exists(filepath)


def run_pipeline(force: bool = False):
    """执行完整流水线：抓取 -> 摘要 -> 日报 -> 输出"""
    if not force and report_already_generated_today():
        log.info("今日报告已存在，跳过（使用 --force 强制重新生成）")
        return None

    log.info("=" * 50)
    log.info("  公共管理信息助手 - 开始运行")
    log.info("=" * 50)

    filepath = None
    try:
        # Step 1: 抓取 RSS
        log.info("[第1步] 抓取信息源...")
        entries = fetch_and_cache()
        if not entries:
            log.warning("未获取到任何信息，请检查网络连接或 RSS 源配置")
            return None

        # Step 2: AI 摘要
        log.info("[第2步] DeepSeek AI 智能摘要...")
        summarizer = DeepSeekSummarizer()
        entries = summarizer.batch_summarize(entries)

        # 更新缓存，保存带 AI 摘要的完整数据（原子写入防损坏）
        import json, shutil
        cache_path = os.path.join(".cache", "latest_entries.json")
        tmp_path = cache_path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(entries, f, ensure_ascii=False, indent=2)
        shutil.move(tmp_path, cache_path)

        # Step 3: 生成综合日报
        log.info("[第3步] 生成综合日报...")
        digest = summarizer.generate_daily_digest(entries)

        # Step 4: 生成 HTML 报告
        log.info("[第4步] 生成 HTML 报告...")
        reporter = HTMLReporter()
        filepath = reporter.generate(digest, entries)

        log.info(f"完成! 报告已保存至: {filepath}")

    except Exception as e:
        log.error(f"运行失败: {e}")
        log.debug(traceback.format_exc())

    log.info("=" * 50)
    return filepath


def run_test():
    """测试模式：使用缓存数据，少量 API 调用"""
    cache_path = ".cache/latest_entries.json"
    if not os.path.exists(cache_path):
        log.warning("无缓存数据，请先运行 `python main.py` 抓取数据")
        return

    with open(cache_path, "r", encoding="utf-8") as f:
        entries = json.load(f)

    log.info(f"[测试] 加载缓存条目: {len(entries)} 条")

    summarizer = DeepSeekSummarizer()
    entries = summarizer.batch_summarize(entries[:5])
    digest = summarizer.generate_daily_digest(entries)

    reporter = HTMLReporter()
    filepath = reporter.generate(digest, entries)
    log.info(f"[测试] 报告: {filepath}")


def run_daemon():
    """守护进程模式：持续运行，每日定时执行"""
    import time
    try:
        import schedule
    except ImportError:
        log.error("请先安装 schedule: pip install schedule")
        return

    from config import SCHEDULE_TIME

    log.info(f"守护进程已启动 | 每日 {SCHEDULE_TIME} 自动执行 | 日志: {LOG_FILE}")
    log.info("按 Ctrl+C 停止")

    schedule.every().day.at(SCHEDULE_TIME).do(run_pipeline)

    # 启动时不立即执行（如果今天已生成过就跳过）
    if not report_already_generated_today():
        log.info("今日报告尚未生成，立即执行一次...")
        run_pipeline()
    else:
        log.info("今日报告已存在，等待下次定时触发")

    while True:
        try:
            schedule.run_pending()
            time.sleep(60)
        except KeyboardInterrupt:
            raise
        except Exception as e:
            log.error(f"调度器异常: {e}")
            time.sleep(60)


def setup_windows_task():
    """注册 Windows 定时任务"""
    import subprocess

    python_path = sys.executable
    script_path = os.path.abspath(__file__)
    task_name = "PublicAdminDailyReport"
    task_time = "07:00"

    xml = f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <Triggers>
    <CalendarTrigger>
      <StartBoundary>{datetime.now().strftime('%Y-%m-%d')}T{task_time}:00</StartBoundary>
      <ScheduleByDay>
        <DaysInterval>1</DaysInterval>
      </ScheduleByDay>
    </CalendarTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>true</AllowHardTerminate>
    <StartWhenAvailable>true</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>
    <IdleSettings>
      <Duration>PT5M</Duration>
      <WaitTimeout>PT1H</WaitTimeout>
      <StopOnIdleEnd>false</StopOnIdleEnd>
      <RestartOnIdle>false</RestartOnIdle>
    </IdleSettings>
    <Enabled>true</Enabled>
    <Hidden>false</Hidden>
    <ExecutionTimeLimit>PT30M</ExecutionTimeLimit>
    <Priority>7</Priority>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>"{python_path}"</Command>
      <Arguments>"{script_path}"</Arguments>
      <WorkingDirectory>"{os.path.dirname(script_path)}"</WorkingDirectory>
    </Exec>
  </Actions>
</Task>"""

    task_xml_path = os.path.join(os.path.dirname(script_path), ".cache", "task.xml")
    os.makedirs(os.path.dirname(task_xml_path), exist_ok=True)
    with open(task_xml_path, "w", encoding="utf-16") as f:
        f.write(xml)

    try:
        # 先删除旧任务（如果存在）
        subprocess.run(
            ["schtasks", "/Delete", "/TN", task_name, "/F"],
            capture_output=True, shell=True
        )
        # 创建新任务
        result = subprocess.run(
            ["schtasks", "/Create", "/TN", task_name, "/XML", task_xml_path, "/F"],
            capture_output=True, text=True, shell=True
        )
        if result.returncode == 0:
            log.info(f"Windows 定时任务创建成功!")
            log.info(f"  任务名称: {task_name}")
            log.info(f"  执行时间: 每日 {task_time}")
            log.info(f"  执行命令: {python_path} {script_path}")
            log.info(f"  管理入口: taskschd.msc (搜索 '{task_name}')")
        else:
            log.error(f"创建失败: {result.stderr}")
    except Exception as e:
        log.error(f"注册定时任务失败: {e}")
        log.info("手动替代方案: 运行 python main.py --daemon 保持窗口")


def main():
    parser = argparse.ArgumentParser(description="公共管理信息助手 - AI 政策聚合")
    parser.add_argument("--daemon", action="store_true", help="守护进程：每日定时执行")
    parser.add_argument("--test", action="store_true", help="测试模式（缓存+5条）")
    parser.add_argument("--force", action="store_true", help="强制重新生成今日报告")
    parser.add_argument("--setup-task", action="store_true", help="注册 Windows 定时任务")
    args = parser.parse_args()

    try:
        if args.test:
            run_test()
        elif args.setup_task:
            setup_windows_task()
        elif args.daemon:
            run_daemon()
        else:
            run_pipeline(force=args.force)
    except ValueError as e:
        log.error(f"配置错误: {e}")
        log.error("请在 .env 文件中配置你的 DeepSeek API Key")
        sys.exit(1)
    except KeyboardInterrupt:
        log.info("用户中断，已停止")


if __name__ == "__main__":
    main()
