import os
from dotenv import load_dotenv

load_dotenv()

# ---------- DeepSeek API ----------
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

# ---------- 报告输出 ----------
REPORT_DIR = os.getenv("REPORT_DIR", "output")

# ---------- 公管领域分类 ----------
CATEGORIES = {
    "宏观政策": ["国务院", "法规", "规划", "改革", "条例", "十四五", "十五五",
              "常务会议", "总理", "中央", "部署", "习近平", "外交", "部",
              "通知", "发布", "印发", "党建", "党"],
    "数字中国": ["数字", "人工智能", "AI", "大数据", "5G", "工业互联网",
              "算力", "信息化", "算法", "平台", "互联网", "区块链",
              "数据", "智能", "数字化"],
    "乡村振兴": ["农村", "农业", "粮食", "乡村", "脱贫", "农民", "种业",
              "耕地", "水利", "灌溉", "供销", "渔"],
    "产业发展": ["制造", "产业", "供应链", "新能源", "汽车", "芯片",
              "半导体", "新质生产力", "中小", "工业", "外贸", "消费",
              "PMI", "GDP", "经济", "财政", "税", "金融", "投资"],
    "生态文明": ["碳", "排放", "绿色", "生态环境", "污染", "减排", "清洁",
              "光伏", "风电", "保护", "自然", "资源", "能源", "环境"],
    "民生保障": ["就业", "教育", "医疗", "养老", "社保", "住房", "医保",
              "药品", "高考", "招生", "学校", "生", "健康"],
    "国家安全": ["安全", "国防", "军事", "应急", "救灾", "地震", "防疫",
              "网络", "主权", "领土", "海洋", "制裁"],
}

CATEGORY_COLORS = {
    "宏观政策": "#ef4444",
    "数字中国": "#3b82f6",
    "乡村振兴": "#22c55e",
    "产业发展": "#f59e0b",
    "生态文明": "#06b6d4",
    "民生保障": "#ec4899",
    "国家安全": "#8b5cf6",
    "综合": "#94a3b8",
}

# ---------- 网页抓取信息源 ----------
WEB_SOURCES = [
    # ---- 核心时政 ----
    {"name": "新华网-时政", "url": "http://www.news.cn/politics/",
     "selector": "ul li a, [class*=list] a, [class*=item] a, h3 a", "min_length": 14},
    {"name": "新华网-国际", "url": "http://www.news.cn/world/",
     "selector": "ul li a, [class*=list] a, [class*=item] a, h3 a", "min_length": 14},
    {"name": "中国政府网-政策", "url": "http://www.gov.cn/zhengce/",
     "selector": "ul li a", "min_length": 14},

    # ---- 经济与产业 ----
    {"name": "发改委-新闻", "url": "https://www.ndrc.gov.cn/xwdt/",
     "selector": "ul li a, [class*=list] a, [class*=news] a", "min_length": 12},
    {"name": "工信部-新闻", "url": "https://www.miit.gov.cn/xwdt/",
     "selector": "ul li a, [class*=list] a, [class*=news] a", "min_length": 12},
    {"name": "财政部-信息", "url": "http://www.mof.gov.cn/zhengwuxinxi/",
     "selector": "ul li a, [class*=list] a, [class*=xx] a", "min_length": 12},

    # ---- 科技创新 ----
    {"name": "科技部-新闻", "url": "https://www.most.gov.cn/kjbgz/",
     "selector": "ul li a, [class*=list] a, [class*=news] a", "min_length": 12},

    # ---- 民生与社会 ----
    {"name": "教育部-新闻", "url": "http://www.moe.gov.cn/jyb_xwfb/",
     "selector": "ul li a, [class*=list] a, [class*=news] a", "min_length": 12},

    # ---- 农业农村 ----
    {"name": "农业农村部-新闻", "url": "http://www.moa.gov.cn/xw/",
     "selector": "ul li a, [class*=list] a, [class*=news] a", "min_length": 12},

    # ---- 资源与生态 ----
    {"name": "自然资源部-动态", "url": "http://www.mnr.gov.cn/dt/",
     "selector": "ul li a, [class*=list] a, [class*=news] a", "min_length": 12},
    {"name": "生态环境部-动态", "url": "https://www.mee.gov.cn/ywdt/",
     "selector": "ul li a, [class*=list] a, [class*=news] a", "min_length": 12},

    # ---- 文化与旅游 ----
    {"name": "文旅部-新闻", "url": "https://www.mct.gov.cn/whzx/",
     "selector": "ul li a, [class*=list] a, [class*=news] a", "min_length": 12},
]

# ---------- AI 摘要 Prompt ----------
SUMMARY_SYSTEM_PROMPT = """你是一位资深公共管理政策分析师。请对以下政策/新闻条目进行简要精炼的分析。

输出格式（每条一行，严格按此结构）：
【标题】精简标题（保留发文机关）
【分类】从以下选一：宏观政策 / 数字中国 / 乡村振兴 / 产业发展 / 生态文明 / 民生保障 / 国家安全 / 综合
【重要度】★★★★★ ~ ★☆☆☆☆
【要点】用3-5个短横线分点列出核心要点（每条≤25字）
【分析】1-2句话简要分析政策影响或趋势（≤60字）
【关键词】3-5个关键词，顿号分隔

要求：精炼、要点化、不写长段落。数字和文件号要保留。"""

# 综合日报 Prompt - 更详细
DIGEST_SYSTEM_PROMPT = """你是资深公共管理研究员"政析"，为高层决策者编写每日政策情报。

注意：今天是{date_cn}。用专业、敏锐的口吻撰写。

## 主编寄语
以第一人称写一段80-100字的开场，点明今日政策环境的整体态势。语气类似："今天的政策信号表明……值得关注的是……"。要有判断力，不模棱两可。

## 今日头条
最重要的2-3条政策动态，每条200-250字深度解读（背景/核心内容/政策信号/影响）。

## 政策矩阵
用 Markdown 表格格式输出：

| # | 来源 | 标题 | 分类 | 重要度 | 核心要点 | 链接 |
|---|------|------|------|--------|----------|------|
| 1 | 新华网 | 国务院部署AI发展 | 宏观政策 | ★★★★★ | ... | http://... |

至少10行。

## 部委动态
各部门最新政策行动，按部委分组详细说明，每条说明具体举措和影响。

## 趋势研判（必须3条）
综合当日信息研判3条宏观趋势。每条必须：
1. 明确指出判断依据的具体政策文件名称、发文机关、日期
2. 引用当日信息中的量化数据支撑趋势
3. 说明该趋势对公共管理实操的具体影响
每条180字以上。

## 风险提示
可能影响政策执行的潜在风险或不确定性，每条充分说明风险来源和影响机制（2-3条）。

## 明日关注
预判近期可能出台的政策方向（5条，每条说明预判依据）。

风格：直接输出内容，不要任何问候语或开场白（如"好的""以下是"等），直接从 ## 主编寄语 开始。"""

# ---------- 定时任务 ----------
SCHEDULE_TIME = "07:00"
