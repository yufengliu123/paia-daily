"""
PAIA Server - 一键启动 http://localhost:8899
"""

import glob
import http.server
import json
import os
import threading
from datetime import datetime
from collections import Counter
from urllib.parse import urlparse

from openai import OpenAI
from dotenv import load_dotenv

from fetcher import fetch_and_cache
from summarizer import DeepSeekSummarizer
from reporter import HTMLReporter

PORT = 8899
OUTPUT_DIR = "output"
CACHE_DIR = ".cache"


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=os.getcwd(), **kwargs)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/refresh":
            self._json(self._refresh())
        elif path == "/api/status":
            self._json(self._status())
        elif path == "/api/history":
            self._json(self._history())
        elif path == "/api/trends":
            self._json(self._trends())
        elif path == "/api/deepask":
            self._handle_deepask()
        elif path == "/api/chat":
            self._handle_chat()
        elif path == "/" or path == "/index.html":
            self._serve()
        else:
            super().do_GET()

    def _json(self, data):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)
        self.wfile.flush()

    def _refresh(self):
        def _run():
            try:
                e = fetch_and_cache()
                s = DeepSeekSummarizer()
                e = s.batch_summarize(e)
                d = s.generate_daily_digest(e)
                HTMLReporter().generate(d, e)
                print("[server] refresh done")
            except Exception as ex:
                print(f"[server] refresh error: {ex}")
        threading.Thread(target=_run, daemon=True).start()
        return {"ok": True, "msg": "刷新已启动，约5分钟后生效"}

    def _status(self):
        today = datetime.now().strftime("%Y-%m-%d")
        cache_path = os.path.join(CACHE_DIR, "latest_entries.json")
        info = {"date": today, "count": 0, "sources": {}, "categories": {}, "keywords": [], "source_list": []}
        if os.path.exists(cache_path):
            try:
                with open(cache_path, "r", encoding="utf-8") as f:
                    entries = json.load(f)
                info["count"] = len(entries)
                src = Counter(e.get("source","") for e in entries)
                cat = Counter(e.get("category","") for e in entries)
                info["sources"] = dict(src.most_common(10))
                info["categories"] = dict(cat.most_common(8))
                info["source_list"] = [{"name":k,"count":v} for k,v in src.most_common(8)]
                kw = Counter()
                for e in entries:
                    ai = e.get("ai_summary","")
                    for line in ai.split("\n"):
                        if line.strip().startswith("【关键词】"):
                            for w in line[5:].replace("，",",").replace("、",",").split(","):
                                w = w.strip()
                                if len(w) >= 2: kw[w] += 1
                info["keywords"] = [k for k,_ in kw.most_common(15)]
            except: pass
        return info

    def _handle_chat(self):
        """RAG 政策问答"""
        from urllib.parse import parse_qs
        qs = parse_qs(urlparse(self.path).query)
        question = qs.get("q", [""])[0]
        if not question:
            return self._json({"ok": False, "answer": "请输入问题"})

        cache_path = os.path.join(CACHE_DIR, "latest_entries.json")
        context = ""
        if os.path.exists(cache_path):
            try:
                with open(cache_path, "r", encoding="utf-8") as f:
                    entries = json.load(f)
                qwords = set(question)
                scored = []
                for e in entries:
                    if not e.get("ai_summary"): continue
                    title = e.get("title", "")
                    score = sum(1 for c in qwords if c in title + e.get("ai_summary", ""))
                    if score > 0:
                        scored.append((score, e))
                scored.sort(key=lambda x: x[0], reverse=True)
                parts = []
                for _, e in scored[:5]:
                    parts.append(f"[{e.get('source','')}] {e.get('title','')}: {e.get('ai_summary','')[:300]}")
                context = "\n\n".join(parts)
            except: pass

        try:
            load_dotenv()
            client = OpenAI(api_key=os.getenv("DEEPSEEK_API_KEY",""),
                           base_url=os.getenv("DEEPSEEK_BASE_URL","https://api.deepseek.com"))
            system = "你是公共管理政策助手。基于提供的政策资料回答问题。资料不足时诚实说明。150-300字。"
            user = f"参考资料：\n{context}\n\n问题：{question}" if context else question
            resp = client.chat.completions.create(
                model=os.getenv("DEEPSEEK_MODEL","deepseek-chat"),
                messages=[{"role":"system","content":system},{"role":"user","content":user}],
                temperature=0.4, max_tokens=500
            )
            return self._json({"ok": True, "answer": resp.choices[0].message.content.strip()})
        except Exception as e:
            return self._json({"ok": False, "answer": f"Error: {e}"})

    def _handle_deepask(self):
        """一键深问 / 多方听证"""
        from urllib.parse import parse_qs
        qs = parse_qs(urlparse(self.path).query)
        title = qs.get("title", [""])[0]
        q = qs.get("q", [""])[0]
        mode = qs.get("mode", [""])[0]
        if not title:
            return self._json({"ok": False, "answer": "Missing params"})

        if mode == "hearing":
            system = "你是公共管理政策模拟专家。模拟以下利益相关方对该政策的观点：市民代表、企业协会、基层执行者、学者专家。每方用50-80字表述立场和核心关切。"
            user = f"政策：「{title}」。请模拟四方观点。"
        else:
            system = "你是资深公共管理分析师。用100-200字精炼回答。"
            user = f"关于政策「{title}」，{q}"

        try:
            load_dotenv()
            client = OpenAI(api_key=os.getenv("DEEPSEEK_API_KEY",""),
                           base_url=os.getenv("DEEPSEEK_BASE_URL","https://api.deepseek.com"))
            resp = client.chat.completions.create(
                model=os.getenv("DEEPSEEK_MODEL","deepseek-chat"),
                messages=[{"role":"system","content":system},{"role":"user","content":user}],
                temperature=0.5, max_tokens=600
            )
            return self._json({"ok": True, "answer": resp.choices[0].message.content.strip()})
        except Exception as e:
            return self._json({"ok": False, "answer": f"Error: {e}"})

    def _trends(self):
        return _trends_raw()


def _trends_raw():
    """独立趋势分析函数，可被 deploy.py 调用"""
    from collections import defaultdict
    cache_path = os.path.join(CACHE_DIR, "latest_entries.json")
    if not os.path.exists(cache_path):
        return {"trends": [], "alerts": [], "causal": []}
    try:
        with open(cache_path, "r", encoding="utf-8") as f:
            entries = json.load(f)
    except:
        return {"trends": [], "alerts": [], "causal": []}

    daily_kw = defaultdict(Counter)
    for e in entries:
        pub = (e.get("published","") or e.get("fetched_at",""))[:10]
        for line in e.get("ai_summary","").split("\n"):
            if line.strip().startswith("【关键词】"):
                for w in line[5:].replace("，",",").replace("、",",").split(","):
                    w = w.strip()
                    if len(w) >= 2:
                        daily_kw[pub][w] += 1

    dates = sorted(daily_kw.keys())
    all_kw = Counter()
    for c in daily_kw.values():
        all_kw.update(c)

    today_kw = daily_kw.get(dates[-1], Counter()) if dates else Counter()
    yesterday_kw = daily_kw.get(dates[-2], Counter()) if len(dates) >= 2 else Counter()

    max_c = max(all_kw.values()) if all_kw else 1
    trends = []
    alerts = []

    for w, c in all_kw.most_common(15):
        delta = today_kw.get(w, 0) - yesterday_kw.get(w, 0)
        trend = "up" if delta > 2 else ("down" if delta < -1 else "stable")
        if delta > 2:
            alerts.append(f"{w} 关注度骤升 +{delta}")
        trends.append({"word": w, "count": c, "trend": trend, "delta": delta,
                        "bar_pct": round(c / max_c * 100, 1)})

    causal = []
    rules = [(["高温", "用电"], "能源保供压力"), (["出口", "关税", "贸易"], "产业链转移风险"),
             (["就业", "失业", "稳岗"], "社会稳定压力"), (["暴雨", "防汛", "降雨"], "农业受灾风险"),
             (["债务", "地方", "财政"], "财政可持续风险"), (["AI", "人工智能", "数字"], "技术治理挑战")]
    for kws, risk in rules:
        score = sum(all_kw.get(kw, 0) for kw in kws)
        if score >= 3:
            causal.append({"trigger": "+".join(kws[:2]), "risk": risk})

    return {"trends": trends, "alerts": alerts[:3], "causal": causal[:3]}

    def _serve(self):
        today = datetime.now().strftime("%Y-%m-%d")
        report_path = os.path.join(OUTPUT_DIR, f"PAIA_Daily_{today}.html")

        trends_data = self._trends()
        if os.path.exists(report_path):
            with open(report_path, "r", encoding="utf-8") as f:
                html = f.read()
            bar = _build_bar(trends_data)
            html = html.replace("<body>", f"<body>{bar}")
        else:
            trends_data = self._trends()
            html = _no_report(today)
            html = html.replace("<body>", f"<body>{_build_bar(trends_data)}")

        data = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)
        self.wfile.flush()

    def log_message(self, format, *args):
        pass


def _build_bar(trends_data=None):
    if trends_data is None:
        trends_data = {"trends": [], "alerts": [], "causal": []}
    trends_js = json.dumps(trends_data, ensure_ascii=False)
    
    # 预渲染趋势 HTML
    t_html = ""
    for t in trends_data.get("trends", [])[:10]:
        arrow = "↑" if t.get("trend") == "up" else ""
        cls = "paia-trend-hot" if t.get("trend") == "up" else "paia-trend-normal"
        t_html += '<span class="paia-trend-item"><span class="paia-trend-bar '+cls+'" style="width:'+str(max(t.get("bar_pct",4),4))+'px"></span>'+t["word"]+' <b>'+str(t["count"])+'</b>'+arrow+'</span>'
    a_html = ""
    for a in trends_data.get("alerts", [])[:3]:
        a_html += '<span style="margin-left:auto;color:#dc2626;font-size:11px;font-weight:600">⚠ '+a+'</span>'
    c_html = ""
    for c in trends_data.get("causal", [])[:3]:
        c_html += '<span style="margin-left:8px;color:#b45309;font-size:11px">🔗 '+c["trigger"]+'→'+c["risk"]+'</span>'
    
    html = """<style>
.paia-top {position:fixed;top:0;left:0;right:0;z-index:9999;
    background:rgba(15,23,42,0.85);color:#fff;padding:8px 20px;
    display:flex;align-items:center;gap:10px;font-size:12px;
    font-family:"PingFang SC","Microsoft YaHei",sans-serif;
    backdrop-filter:blur(20px) saturate(180%);
    -webkit-backdrop-filter:blur(20px) saturate(180%);
    border-bottom:1px solid rgba(255,255,255,0.08);
    box-shadow:0 2px 24px rgba(0,0,0,0.15);}
body {background:#fff !important;}
.paia-trends,.paia-quickstats {background:#fff !important;border-bottom-color:#e8e4df !important;color:#64748b !important;}
.paia-quickstats b {color:#0f172a !important;}
.paia-top .logo {font-weight:700;font-size:15px;display:flex;align-items:center;gap:6px;margin-right:4px;}
.paia-top input {background:rgba(255,255,255,0.12);border:1px solid rgba(255,255,255,0.2);
    border-radius:16px;padding:4px 12px;color:#fff;font-size:12px;width:130px;outline:none;
    font-family:inherit;transition:.2s;}
.paia-top input:focus {background:rgba(255,255,255,0.2);width:170px;}
.paia-top input::placeholder {color:rgba(255,255,255,0.4);}
.paia-top .btn {border:none;padding:5px 12px;border-radius:14px;cursor:pointer;
    font-size:11px;font-weight:500;font-family:inherit;transition:all .2s cubic-bezier(.4,0,.2,1);white-space:nowrap;
    position:relative;overflow:hidden;}
.paia-top .btn::after {content:"";position:absolute;inset:0;background:linear-gradient(180deg,rgba(255,255,255,0.15),transparent);pointer-events:none;}
.paia-top .btn:active {transform:scale(0.95);}
.paia-top .btn-r {background:linear-gradient(135deg,#3b82f6,#6366f1);color:#fff;box-shadow:0 2px 12px rgba(59,130,246,0.3);}
.paia-top .btn-r:hover {background:linear-gradient(135deg,#2563eb,#4f46e5);box-shadow:0 4px 20px rgba(59,130,246,0.4);transform:translateY(-1px);}
.paia-top .btn-o {background:transparent;color:rgba(255,255,255,0.7);border:1px solid rgba(255,255,255,0.2);}
.paia-top .btn-o:hover {color:#fff;border-color:rgba(255,255,255,0.5);background:rgba(255,255,255,0.06);}
.paia-top .stat {font-size:11px;opacity:0.85;background:rgba(255,255,255,0.08);padding:2px 8px;border-radius:8px;}
.paia-top .spacer {flex:1;}
.paia-top .sep {width:1px;height:20px;background:rgba(255,255,255,0.15);}
/* history dropdown */
.paia-drop {position:relative;}
.paia-drop .menu {display:none;position:absolute;top:100%;right:0;margin-top:6px;
    background:#1e293b;border:1px solid rgba(255,255,255,0.1);border-radius:10px;
    padding:6px 0;min-width:200px;max-height:320px;overflow-y:auto;z-index:10000;}
.paia-drop .menu a {display:block;padding:6px 16px;color:#cbd5e1;text-decoration:none;font-size:12px;}
.paia-drop .menu a:hover {background:rgba(255,255,255,0.08);color:#fff;}
.paia-drop.active .menu {display:block;}
.paia-drop .menu .src-foot {padding:6px 16px 2px;font-size:10px;color:#64748b;border-top:1px solid rgba(255,255,255,0.08);margin-top:4px;}
/* scroll top */
.paia-gotop {position:fixed;bottom:24px;right:24px;z-index:9998;
    width:36px;height:36px;border-radius:50%;background:rgba(15,23,42,0.85);color:#fff;
    border:none;cursor:pointer;font-size:16px;display:none;align-items:center;justify-content:center;
    box-shadow:0 2px 8px rgba(0,0,0,0.2);transition:.2s;}
.paia-gotop.show {display:flex;}
.paia-gotop:hover {background:rgba(15,23,42,1);transform:translateY(-2px);}
/* category chips in bar */
.cat-chips {display:flex;gap:4px;overflow-x:scroll;white-space:nowrap;
    -webkit-overflow-scrolling:touch;scrollbar-width:thin;scrollbar-color:rgba(255,255,255,0.3) transparent;}
.cat-chips::-webkit-scrollbar {display:none;}
.cat-chip {font-size:10px;padding:3px 8px;border-radius:10px;cursor:pointer;white-space:nowrap;flex:0 0 auto;
    background:rgba(255,255,255,0.08);color:rgba(255,255,255,0.7);border:none;font-family:inherit;}
.cat-chip:hover {background:rgba(255,255,255,0.15);color:#fff;}
/* progress bar */
.paia-prog {position:fixed;top:0;left:0;height:2px;background:linear-gradient(90deg,#3b82f6,#8b5cf6);z-index:10000;transition:width .1s;}
/* source tooltip */
.src-pop {display:none;position:absolute;background:#1e293b;color:#cbd5e1;border-radius:8px;padding:8px 12px;font-size:11px;z-index:10000;white-space:nowrap;box-shadow:0 4px 12px rgba(0,0,0,0.3);}
.app {padding-top:0 !important;}
.app {padding-top:0 !important;}
@media (max-width:900px) {.cat-chips{display:none}.paia-top .sep{display:none}}
@media (max-width:600px) {.paia-top{flex-wrap:wrap}}
/* trend bars */
.paia-trend-item {display:flex;align-items:center;gap:4px;white-space:nowrap;}
.paia-trend-bar {height:12px;border-radius:6px;min-width:4px;transition:width .5s;}
.paia-trend-hot {background:linear-gradient(90deg,#dc2626,#ef4444);}
.paia-trend-normal {background:linear-gradient(90deg,#3b82f6,#60a5fa);}
</style>
<div class="paia-top">
    <span class="logo">&#128202; 公共管理信息助手</span>
    <span class="stat" id="sTotal">-</span>
    <span class="stat" id="sSources">-</span>
    <span class="sep"></span>
    <div style="overflow:hidden;min-width:0;flex:0 1 auto">
        <div class="cat-chips" id="catChips"></div>
    </div>
    <span class="sep"></span>
    <input placeholder="搜索..." oninput="doSearch(this.value)" id="si">
    <span style="font-size:11px;opacity:0.6;min-width:30px" id="sc"></span>
    <span class="spacer"></span>
    <span id="sTime" style="font-size:11px;opacity:0.5"></span>
    <span class="sep"></span>
    <div class="paia-drop" id="paiaDrop">
        <button class="btn btn-o" onclick="toggleHist(event)">&#128196; 历史</button>
        <div class="menu">
            <div id="histList" style="color:#94a3b8;padding:6px 16px;">加载中...</div>
            <div class="src-foot" id="srcFoot"></div>
        </div>
    </div>
    <button class="btn btn-o" onclick="window.print()">&#128424; 打印</button>
    <button class="btn btn-r" onclick="doRefresh(event)">&#8635; 刷新</button>
</div>
<!-- 趋势条 -->
<div class="paia-trends" style="padding:6px 20px;margin-top:44px;display:flex;align-items:center;gap:8px;flex-wrap:wrap;font-size:12px;font-family:'PingFang SC','Microsoft YaHei',sans-serif;background:#fff;border-bottom:1px solid #e2e8f0;min-height:32px;overflow:hidden">
    <span style="font-weight:600;color:#0f172a;white-space:nowrap">📊 趋势：</span>
    __TRENDS__
    __ALERTS__
    __CAUSAL__
</div>
<div class="paia-quickstats" id="quickStats" style="padding:8px 20px;display:flex;gap:16px;flex-wrap:wrap;font-size:11px;font-family:'PingFang SC','Microsoft YaHei',sans-serif;background:#fff;border-bottom:1px solid #e8e4df;color:#64748b">
    <span>🕐 <b id="qsTime">-</b></span>
    <span>📰 <b id="qsTotal">-</b></span>
    <span>📡 <b id="qsSources">-</b></span>
    <span>🏷 <b id="qsTopCat">-</b></span>
</div>
<button class="paia-gotop" id="goTop" onclick="window.scrollTo({top:0,behavior:'smooth'})">&#9650;</button>
<div class="paia-prog" id="progBar"></div>
<div class="src-pop" id="srcPop"></div>
<script>
// embedded trends data
var __TRENDS = __TRENDS_JS__;
// populate trends bar + quick stats
(function(){var d=__TRENDS;
// trends
var trends=d.trends||[], html=[];
trends.slice(0,10).forEach(function(t){
    var arrow=t.trend==="up"?"↑":"",color=t.trend==="up"?"paia-trend-hot":"paia-trend-normal";
    html.push('<span class="paia-trend-item"><span class="paia-trend-bar '+color+
        '" style="width:'+Math.max(t.bar_pct,4)+'px"></span>'+t.word+' <b>'+t.count+'</b>'+arrow+'</span>');
});
// quick stats
fetch("/api/status").then(function(r){return r.json()}).then(function(d){
    document.getElementById("sTotal").textContent=(d.count||0)+"\u6761";
    document.getElementById("sSources").textContent=Object.keys(d.sources||{}).length+"\u6e90";
    document.getElementById("sTime").textContent=d.date;
    document.getElementById("qsTotal").textContent=(d.count||0)+"\u6761";
    document.getElementById("qsSources").textContent=Object.keys(d.sources||{}).length+"\u4e2a\u6d3b\u8dc3\u6e90";
    document.getElementById("qsTime").textContent=d.date;
    var cats=d.categories||{},top=Object.entries(cats).sort(function(a,b){return b[1]-a[1]})[0];
    document.getElementById("qsTopCat").textContent=top?top[0]+"("+top[1]+"\u6761)":"-";
    var srcDiv=document.getElementById("sSources");srcDiv.style.cursor="pointer";
    srcDiv.onmouseenter=function(){
        var sl=d.source_list||[],h=sl.map(function(s){return '<div>'+s.name+' <b>'+s.count+'</b></div>';}).join("");
        if(h)document.getElementById("srcPop").innerHTML=h;
        var r=srcDiv.getBoundingClientRect();
        document.getElementById("srcPop").style.cssText="display:block;top:"+(r.bottom+4)+"px;left:"+r.left+"px";
    };
    srcDiv.onmouseleave=function(){document.getElementById("srcPop").style.display="none";};
    // category chips
    var cats2=d.categories||{},html2=[];
    for(var k in cats2)html2.push('<button class="cat-chip" data-cat="'+k+'">'+k+' '+cats2[k]+'</button>');
    document.getElementById("catChips").innerHTML=html2.join("");
    document.querySelectorAll(".cat-chip").forEach(function(b){b.onclick=function(){jumpCat(this.getAttribute("data-cat"));}});
});
function jumpCat(cat){
    document.getElementById("si").value="";document.getElementById("sc").textContent="";
    document.querySelectorAll(".card").forEach(function(c){c.style.display="";});
    document.querySelectorAll(".cat-section,.panel").forEach(function(c){c.style.display="";});
    var tabs=document.querySelectorAll(".tab-btn");
    tabs.forEach(function(t){if(t.textContent.indexOf(cat)>=0)t.click();});
}
function doSearch(q){
    q=q.toLowerCase().trim();
    var cards=document.querySelectorAll(".card"), cats=document.querySelectorAll(".cat-section,.panel"), cnt=0;
    cards.forEach(function(c){c.querySelectorAll("mark").forEach(function(m){m.replaceWith(m.textContent);});});
    if(!q){cards.forEach(function(c){c.style.display="";});cats.forEach(function(c){c.style.display="";});document.getElementById("sc").textContent="";return}
    cats.forEach(function(c){
        var hm=false;
        c.querySelectorAll(".card").forEach(function(card){
            if(card.textContent.toLowerCase().indexOf(q)>=0){card.style.display="";hm=true;cnt++;}
            else card.style.display="none";
        });
        c.style.display=hm?"":"none";
    });
    document.getElementById("sc").textContent=cnt+"\u6761";
}
function toggleHist(e){e.stopPropagation();document.getElementById("paiaDrop").classList.toggle("active");}
document.addEventListener("click",function(){document.getElementById("paiaDrop").classList.remove("active");});
})();
function doRefresh(e){
    var btn=e.target;btn.disabled=true;btn.textContent="\u5237\u65b0\u4e2d...";
    fetch("/api/refresh").then(function(r){return r.json()}).then(function(d){alert(d.msg);setTimeout(function(){location.reload()},15000);});
}
window.onscroll=function(){
    document.getElementById("goTop").classList.toggle("show",window.scrollY>400);
    var h=document.documentElement,p=Math.round(h.scrollTop/(h.scrollHeight-h.clientHeight)*100);
    document.getElementById("progBar").style.width=p+"%";
};
</script>
<!-- chat widget -->
<div id="chatBtn" style="position:fixed;bottom:24px;left:24px;width:44px;height:44px;border-radius:50%;background:#3b82f6;color:#fff;border:none;cursor:pointer;font-size:20px;z-index:9998;box-shadow:0 4px 16px rgba(59,130,246,0.4);display:flex;align-items:center;justify-content:center;transition:.2s" onclick="toggleChat()" title="AI政策问答">💬</div>
<div id="chatBox" style="display:none;position:fixed;bottom:76px;left:24px;width:360px;height:420px;background:#fff;border-radius:14px;box-shadow:0 8px 32px rgba(0,0,0,0.15);z-index:9997;font-family:'PingFang SC','Microsoft YaHei',sans-serif;overflow:hidden;flex-direction:column">
<div style="background:#0f172a;color:#fff;padding:12px 16px;font-size:14px;font-weight:600;display:flex;justify-content:space-between;align-items:center">
    AI政策问答
    <button onclick="toggleChat()" style="background:none;border:none;color:#fff;cursor:pointer;font-size:18px">&times;</button>
</div>
<div id="chatMsgs" style="flex:1;overflow-y:auto;padding:12px;font-size:13px;color:#475569;line-height:1.6"></div>
<div style="display:flex;padding:8px;border-top:1px solid #e2e8f0">
    <input id="chatInput" placeholder="输入政策相关问题..." style="flex:1;border:1px solid #e2e8f0;border-radius:16px;padding:6px 14px;font-size:13px;font-family:inherit;outline:none" onkeydown="if(event.key==='Enter')sendChat()">
    <button onclick="sendChat()" style="margin-left:6px;background:#3b82f6;color:#fff;border:none;border-radius:16px;padding:6px 14px;cursor:pointer;font-size:13px">发送</button>
</div>
</div>
<script>
function toggleChat(){
    var b=document.getElementById("chatBox"), btn=document.getElementById("chatBtn");
    if(b.style.display==="flex"){b.style.display="none";btn.style.display="flex"}
    else{b.style.display="flex";b.style.display="flex"}
}
function sendChat(){
    var input=document.getElementById("chatInput"), q=input.value.trim();
    if(!q)return;
    var msgs=document.getElementById("chatMsgs");
    msgs.innerHTML+='<div style="text-align:right;margin:6px 0"><span style="background:#3b82f6;color:#fff;padding:6px 12px;border-radius:14px;display:inline-block;max-width:80%">'+q+'</span></div>';
    input.value="";input.disabled=true;
    msgs.innerHTML+='<div style="margin:6px 0;color:#94a3b8">分析中...</div>';
    msgs.scrollTop=msgs.scrollHeight;
    fetch("/api/chat?q="+encodeURIComponent(q)).then(function(r){return r.json()}).then(function(d){
        msgs.lastChild.remove();
        msgs.innerHTML+='<div style="margin:6px 0"><span style="background:#f1f5f9;padding:8px 14px;border-radius:14px;display:inline-block;max-width:85%">'+d.answer+'</span></div>';
        msgs.scrollTop=msgs.scrollHeight;input.disabled=false;
    }).catch(function(){input.disabled=false;});
}
// history today
(function(){
    var d=new Date(),m=d.getMonth()+1,day=d.getDate();
    var events={"7-1":"1921\u5e747\u67081\u65e5\uff0c\u4e2d\u56fd\u5171\u4ea7\u515a\u6210\u7acb\u30021997\u5e747\u67081\u65e5\uff0c\u9999\u6e2f\u56de\u5f52\u7956\u56fd\u3002","7-2":"1959\u5e747\u67082\u65e5\uff0c\u5e90\u5c71\u4f1a\u8bae\u53ec\u5f00\uff0c\u5f6d\u5fb7\u6000\u4e0a\u4e66\u6bdb\u6cfd\u4e1c\u3002","7-3":"1998\u5e747\u67083\u65e5\uff0c\u56fd\u5bb6\u542f\u52a8\u201c\u897f\u90e8\u5927\u5f00\u53d1\u201d\u6218\u7565\u3002","7-4":"1776\u5e747\u67084\u65e5\uff0c\u300a\u72ec\u7acb\u5ba3\u8a00\u300b\u901a\u8fc7\uff0c\u7f8e\u5229\u575a\u5408\u4f17\u56fd\u5efa\u56fd\u3002"};
    var key=m+"-"+day, evt=events[key];
    if(evt){
        var bar=document.getElementById("trendsBar");
        if(bar)bar.innerHTML+='<span style="margin-left:auto;font-size:11px;color:#64748b;white-space:nowrap">\U0001F4D6 '+evt+'</span>';
    }
})();
</script>
<div id="deepModal" style="display:none;position:fixed;inset:0;background:rgba(0,0,0,0.5);z-index:10002;justify-content:center;align-items:center">
<div style="background:#fff;border-radius:14px;padding:24px;max-width:500px;width:90%;max-height:70vh;overflow-y:auto;box-shadow:0 8px 32px rgba(0,0,0,0.2);font-family:'PingFang SC','Microsoft YaHei',sans-serif">
<h3 id="dTitle" style="margin:0 0 6px;font-size:15px;color:#1e293b"></h3>
<p id="dQ" style="color:#64748b;font-size:13px;margin-bottom:12px"></p>
<div id="dA" style="color:#475569;font-size:14px;line-height:1.7;min-height:40px"></div>
<button onclick="document.getElementById('deepModal').style.display='none'" style="margin-top:12px;border:none;background:#e2e8f0;padding:6px 18px;border-radius:14px;cursor:pointer;font-size:13px">\u5173\u95ed</button>
</div></div>
<script>
setTimeout(function(){
    document.querySelectorAll(".card").forEach(function(card){
        var t=card.querySelector(".card-title");if(!t)return;
        var title=t.textContent.trim().substring(0,50);
        var btns='<span style="font-size:10px;color:#94a3b8;margin-right:2px">\u6df1\u95ee:</span>';
        ["\u80cc\u666f","\u5f71\u54cd","\u5173\u8054","\u542c\u8bc1"].forEach(function(q){
            btns+='<button class="kw-tag" style="cursor:pointer" onclick="deepAsk(this)" data-t="'+title.replace(/"/g,'')+'" data-q="'+q+'">'+q+'</button>';
        });
        var b=card.querySelector(".card-bottom");if(b)b.insertAdjacentHTML("afterbegin",btns);
    });
},700);
function deepAsk(btn){
    var t=btn.getAttribute("data-t"),q=btn.getAttribute("data-q");
    var m={"\u80cc\u666f":"\u8bf7\u5206\u6790\u8be5\u653f\u7b56\u7684\u6df1\u5c42\u80cc\u666f\u4e0e\u51fa\u53f0\u539f\u56e0","\u5f71\u54cd":"\u8bf7\u5206\u6790\u5bf9\u57fa\u5c42\u6cbb\u7406\u7684\u5177\u4f53\u5f71\u54cd","\u5173\u8054":"\u8bf7\u5206\u6790\u4e0e\u5176\u4ed6\u653f\u7b56\u7684\u5173\u8054\u6027","\u542c\u8bc1":"\u6a21\u62df\u591a\u65b9\u5229\u76ca\u76f8\u5173\u65b9\u89c2\u70b9"};
    var isHearing=q==="\u542c\u8bc1";
    document.getElementById("deepModal").style.display="flex";
    document.getElementById("dTitle").textContent=isHearing?"\u25c6 "+t+"\uff08\u591a\u65b9\u89c6\u89d2\u6a21\u62df\uff09":t;
    document.getElementById("dQ").textContent="\u25b6 "+(isHearing?"\u5e02\u6c11\u00b7\u4f01\u4e1a\u00b7\u57fa\u5c42\u00b7\u5b66\u8005\u56db\u65b9\u89c2\u70b9":m[q]);
    document.getElementById("dA").textContent="\u5206\u6790\u4e2d...";
    var url="/api/deepask?title="+encodeURIComponent(t)+"&q="+encodeURIComponent(m[q]||"");
    if(isHearing)url+="&mode=hearing";
    fetch(url).then(function(r){return r.json()}).then(function(d){
        document.getElementById("dA").textContent=d.answer||"\u5206\u6790\u5931\u8d25";
    });
}
</script>"""
    return html.replace("__TRENDS_JS__", trends_js).replace("__TRENDS__", t_html).replace("__ALERTS__", a_html).replace("__CAUSAL__", c_html)


def _no_report(date_str):
    return f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>PAIA</title>
<style>
body{{font-family:"PingFang SC","Microsoft YaHei",sans-serif;display:flex;justify-content:center;align-items:center;min-height:100vh;background:#f4f6f9;margin:0}}
.card{{background:#fff;border-radius:16px;padding:48px;text-align:center;box-shadow:0 4px 24px rgba(0,0,0,0.06)}}
.card h1{{color:#1e293b}} .card p{{color:#64748b;margin:16px 0}}
.card button{{border:none;background:#3b82f6;color:#fff;padding:12px 32px;border-radius:24px;font-size:15px;cursor:pointer;font-family:inherit}}
</style></head><body><div class="card"><h1>暂无今日报告</h1><p>点击下方按钮生成</p>
<button onclick="fetch('/api/refresh').then(r=>r.json()).then(d=>{{alert(d.msg);setTimeout(()=>location.reload(),12000)}})">生成报告</button></div></body></html>"""


def start():
    server = http.server.ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"\n  PAIA ready: http://localhost:{PORT}\n  Ctrl+C to stop\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[server] stopped")


if __name__ == "__main__":
    start()
