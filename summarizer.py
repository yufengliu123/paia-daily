from openai import OpenAI

from config import (
    DEEPSEEK_API_KEY,
    DEEPSEEK_BASE_URL,
    DEEPSEEK_MODEL,
    SUMMARY_SYSTEM_PROMPT,
    DIGEST_SYSTEM_PROMPT,
)


class DeepSeekSummarizer:
    def __init__(self):
        if not DEEPSEEK_API_KEY or DEEPSEEK_API_KEY == "your_deepseek_api_key_here":
            raise ValueError("Please set DEEPSEEK_API_KEY in .env")
        self.client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL)
        self.model = DEEPSEEK_MODEL

    def summarize_entry(self, entry: dict) -> dict:
        pub = entry.get("published", "")
        source = entry.get("source", "")
        title = entry.get("title", "")
        link = entry.get("link", "")
        body = entry.get("summary", "")

        # 有正文用详细 Prompt，没有则用标题 Prompt
        if body and len(body) > 50:
            prompt = (
                f"来源：{source}\n"
                f"标题：{title}\n"
                f"发布日期：{pub if pub else '未知'}\n"
                f"链接：{link}\n"
                f"正文内容：\n{body[:600]}\n\n"
                f"请基于以上正文，进行全面的公共管理政策分析。"
            )
        else:
            prompt = (
                f"来源：{source}\n"
                f"标题：{title}\n"
                f"发布日期：{pub if pub else '未知'}\n"
                f"链接：{link}\n"
                f"请基于标题和来源信息，进行专业公共管理政策分析。"
            )

        try:
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": SUMMARY_SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
                max_tokens=600,
            )
            result = resp.choices[0].message.content.strip()
            entry["ai_summary"] = result
            # 从 AI 输出中提取分类并覆盖原始分类
            for line in result.split("\n"):
                line = line.strip()
                if line.startswith("【分类】"):
                    cat = line[4:].strip()
                    valid = ["宏观政策","数字中国","乡村振兴","产业发展","生态文明","民生保障","国家安全"]
                    if any(c in cat for c in valid):
                        entry["category"] = cat
                    break
            return entry
        except Exception as e:
            print(f"  [!] Summary failed ({title[:30]}...): {e}")
            entry["ai_summary"] = (
                f"【标题】{title}\n"
                f"【分类】综合\n"
                f"【重要度】★★★☆☆\n"
                f"【核心摘要】{title}\n"
                f"【关键洞察】请查看原文获取详细信息\n"
                f"【关键词】政策 资讯"
            )
            return entry

    def batch_summarize(self, entries: list[dict], max_items: int = 250) -> list[dict]:
        """批量摘要，并行调用 DeepSeek API 提速。
        将摘要写回原 entries，返回完整列表不截断。"""
        from concurrent.futures import ThreadPoolExecutor, as_completed
        count = min(max_items, len(entries))
        print(f"\n[AI Summary] Processing {count}/{len(entries)} items (parallel x5)...")

        with ThreadPoolExecutor(max_workers=5) as pool:
            futures = {}
            for i in range(count):
                f = pool.submit(self._summarize_one, entries[i], i + 1, count)
                futures[f] = i

            for f in as_completed(futures):
                idx = futures[f]
                try:
                    entries[idx] = f.result()
                except Exception as e:
                    print(f"  [!] [{idx+1}/{count}] failed: {e}")

        print(f"[AI Summary] Done: {count} items")
        return entries  # 返回完整列表，不只是摘要过的那些

    def _summarize_one(self, entry: dict, idx: int, total: int):
        print(f"  [{idx}/{total}] {entry.get('title', '')[:45]}...")
        return self.summarize_entry(entry)

    def generate_daily_digest(self, entries: list[dict]) -> str:
        """生成综合日报"""
        from datetime import datetime
        today = datetime.now()
        weekdays = ["周一","周二","周三","周四","周五","周六","周日"]
        date_cn = f"{today.year}年{today.month}月{today.day}日 {weekdays[today.weekday()]}"

        prompt = DIGEST_SYSTEM_PROMPT.replace("{date_cn}", date_cn)

        summaries = []
        for e in entries:
            ai = e.get("ai_summary", "")
            source = e.get("source", "")
            date = e.get("published", "")
            tag = f"[{source}]" + (f" [{date}]" if date else "")
            summaries.append(f"{tag}\n{ai}")

        combined = "\n\n---\n\n".join(summaries)

        if not combined.strip():
            return "今日暂无重要政策信息。"

        try:
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": f"当日政策信息汇总：\n\n{combined}"},
                ],
                temperature=0.4,
                max_tokens=6000,
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:
            print(f"  [!] Digest generation failed: {e}")
            return combined
