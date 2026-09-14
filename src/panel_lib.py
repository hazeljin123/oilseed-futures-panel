# -*- coding: utf-8 -*-
"""
htfc-tech-panel 数据层 + 指标引擎（国内 8 农产品 + WTI 原油，均为主力合约口径）
数据源:
  1) 天玑 smart-kline  (HTFC_BASE_URL + HTFC_API_KEY) -> 国内日线 OHLC + AI 解读 + 研报观点
  2) 天玑 trend-compass -> 风向分数/动量/偏度/期限结构（仅覆盖国内品种）
  3) 新浪 GlobalFuturesDailyKLine -> WTI 原油(CL) 主力连续日线 OHLC（外盘）
输出: 每品种 dict -> JSON (由 run_panel.py 汇总并生成 HTML)
"""
import json
import os
import sys
import math
import datetime as _dt

# ---------- HTFC env fallback (环境变量 -> 注册表 HKCU\Environment) ----------
def _env(name):
    v = os.getenv(name, "").strip()
    if v:
        return v
    try:
        import winreg
        k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment")
        v, _ = winreg.QueryValueEx(k, name)
        return str(v).strip()
    except Exception:
        return ""

def _ensure_env():
    for name in ("HTFC_BASE_URL", "HTFC_API_KEY"):
        v = _env(name)
        if v:
            os.environ[name] = v

_ensure_env()
HTFC_BASE_URL = os.getenv("HTFC_BASE_URL", "").strip()
HTFC_API_KEY = os.getenv("HTFC_API_KEY", "").strip()

# 品种表: symbol/名称/交易所/数据源(src: htfc=天玑智能K线, sina=新浪外盘日线)/kline代码/风向代码
VARIETIES = [
    {"symbol": "M",  "name": "豆粕",   "exch": "DCE",  "src": "htfc", "kline": "m_2",  "compass": "M"},
    {"symbol": "Y",  "name": "豆油",   "exch": "DCE",  "src": "htfc", "kline": "y_2",  "compass": "Y"},
    {"symbol": "B",  "name": "豆二",   "exch": "DCE",  "src": "htfc", "kline": "b_2",  "compass": "B"},
    {"symbol": "P",  "name": "棕榈油", "exch": "DCE",  "src": "htfc", "kline": "p_2",  "compass": "P"},
    {"symbol": "LH", "name": "生猪",   "exch": "DCE",  "src": "htfc", "kline": "lh_2", "compass": "LH"},
    {"symbol": "JD", "name": "鸡蛋",   "exch": "DCE",  "src": "htfc", "kline": "jd_2", "compass": "JD"},
    {"symbol": "RM", "name": "菜粕",   "exch": "CZCE", "src": "htfc", "kline": "rm_2", "compass": "RM"},
    {"symbol": "OI", "name": "菜油",   "exch": "CZCE", "src": "htfc", "kline": "oi_2", "compass": "OI"},
    {"symbol": "CL", "name": "WTI原油", "exch": "NYMEX", "src": "sina", "kline": "CL", "compass": None},
]

# 技能目录解析: ① 环境变量 HTFC_SKILL_DIR ② 本脚本同目录下 skills/ (GitHub Actions 仓库内)
# ③ 回退本机 WorkBuddy 用户技能目录 (本地日常运行)
def _resolve_skill_dir():
    env = os.getenv("HTFC_SKILL_DIR", "").strip()
    if env and os.path.isdir(env):
        return env
    local = os.path.join(os.path.dirname(os.path.abspath(__file__)), "skills")
    if os.path.isdir(os.path.join(local, "htfc-smart-kline-skill", "scripts")):
        return local
    return r"C:\Users\DELL\.workbuddy\skills"

SKILL_DIR = _resolve_skill_dir()

# ---------- load HTFC skill modules ----------
def _load(name, rel):
    import importlib.util
    p = os.path.join(SKILL_DIR, rel, "scripts", "get_data.py")
    if not os.path.exists(p):
        raise FileNotFoundError(p)
    sys.path.insert(0, os.path.dirname(p))
    spec = importlib.util.spec_from_file_location(name, p)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod

_skmod = _load("htfc_skmod", "htfc-smart-kline-skill")
_tcmod = _load("htfc_tcmod", "htfc-trend-compass-skill")

# ---------- fetch ----------
def fetch_kline(var_num, period="-1year"):
    """Return dict: dates, open, high, low, close, ai, report(有则非None)"""
    if not HTFC_BASE_URL or not HTFC_API_KEY:
        raise RuntimeError("HTFC_BASE_URL / HTFC_API_KEY 未配置（环境变量或注册表）")
    import time
    raw = None
    last_err = None
    for attempt in range(3):
        try:
            raw = _skmod.get_report_k_line(var_num, period)
            break
        except Exception as e:
            last_err = e
            time.sleep(1.5)
    if raw is None:
        raise last_err
    data = (raw or {}).get("data") or {}
    md = data.get("marketData") or {}
    dates = md.get("date") or []
    out = {
        "dates": list(dates),
        "open": [float(x) for x in (md.get("openPrice") or [])],
        "high": [float(x) for x in (md.get("highPrice") or [])],
        "low": [float(x) for x in (md.get("lowPrice") or [])],
        "close": [float(x) for x in (md.get("closePrice") or [])],
        "ai": data.get("kLineAiContent") or data.get("kLineAiContentJson") or None,
        "report": data.get("reportData") or None,
    }
    n = len(dates)
    for k in ("open", "high", "low", "close"):
        out[k] = out[k][:n]
    return out

def fetch_sina_daily(symbol="CL"):
    """新浪 GlobalFuturesDailyKLine -> 外盘主力连续日线。返回与 fetch_kline 相同结构的 dict。
    注意: 当日 K 线为盘中实时滚动 bar, 收盘价在对应交易所结算后才定型。"""
    import re, time, urllib.request
    url = ("https://stock2.finance.sina.com.cn/futures/api/jsonp.php/var%20_x=/GlobalFuturesService"
           ".getGlobalFuturesDailyKLine?symbol=" + symbol)
    last_err = None
    body = None
    for _ in range(3):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0",
                "Referer": "https://finance.sina.com.cn/"})
            body = urllib.request.urlopen(req, timeout=20).read().decode("utf-8", "ignore")
            break
        except Exception as e:
            last_err = e
            time.sleep(1.5)
    if body is None:
        raise last_err
    m = re.search(r"var\s+_x=\((.*)\)\s*;?\s*$", body, re.S)
    if not m:
        raise RuntimeError("新浪日线返回格式异常: " + body[:120])
    rows = json.loads(m.group(1))
    if not rows:
        raise RuntimeError(f"新浪日线为空(symbol={symbol})")
    dates = [r["date"] for r in rows]
    if dates and dates[0] > dates[-1]:  # 保证升序
        rows = list(reversed(rows))
        dates = [r["date"] for r in rows]
    return {
        "dates": dates,
        "open": [float(r["open"]) for r in rows],
        "high": [float(r["high"]) for r in rows],
        "low": [float(r["low"]) for r in rows],
        "close": [float(r["close"]) for r in rows],
        "ai": None, "report": None,
    }

def fetch_compass_map():
    """code -> {score, change, momlong, momshort, skew, termstructure, date}"""
    raw = _tcmod.get_overview()
    data = raw.get("data") if isinstance(raw, dict) else raw
    m = {}
    if isinstance(data, list):
        for it in data:
            c = it.get("code")
            if c:
                m[c] = {k: it.get(k) for k in ("code", "codeName", "score", "change",
                                               "momlong", "momshort", "skew", "termstructure", "date")}
    return m

# ---------- indicators (pure list math) ----------
def sma(x, n):
    out = [None] * len(x)
    s = 0.0
    for i, v in enumerate(x):
        s += v
        if i >= n:
            s -= x[i - n]
        if i >= n - 1:
            out[i] = s / n
    return out

def ema(x, n):
    out = [None] * len(x)
    if not x:
        return out
    k = 2.0 / (n + 1)
    e = x[0]
    out[0] = e
    for i in range(1, len(x)):
        e = x[i] * k + e * (1 - k)
        out[i] = e
    return out

def macd(close, fast=12, slow=26, sig=9):
    ef, es = ema(close, fast), ema(close, slow)
    dif = [(f - s) if f is not None and s is not None else None for f, s in zip(ef, es)]
    # dea = ema of dif (skip None head)
    start = slow - 1
    difv = [d for d in dif[start:] if d is not None]
    if not difv:
        return [], [], []
    k = 2.0 / (sig + 1)
    dea_head = [None] * start
    e = difv[0]
    dea_tail = [e]
    for d in difv[1:]:
        e = d * k + e * (1 - k)
        dea_tail.append(e)
    dea = dea_head + dea_tail
    hist = [(d - g) * 2 if d is not None and g is not None else None for d, g in zip(dif, dea)]
    return dif, dea, hist

def rsi(close, n=14):
    out = [None] * len(close)
    if len(close) <= n:
        return out
    gains, losses = [], []
    for i in range(1, len(close)):
        ch = close[i] - close[i - 1]
        gains.append(max(ch, 0.0))
        losses.append(max(-ch, 0.0))
    ag = sum(gains[:n]); al = sum(losses[:n])
    for i in range(n, len(close)):
        if i > n:
            ag = (ag * (n - 1) + gains[i - 1]) / n
            al = (al * (n - 1) + losses[i - 1]) / n
        out[i] = 100.0 if al == 0 else 100.0 - 100.0 / (1 + ag / al) if al > 0 else (100.0 if ag > 0 else 50.0)
    return out

def kdj(high, low, close, n=9):
    k, d, j = [None] * len(close), [None] * len(close), [None] * len(close)
    if len(close) < n:
        return k, d, j
    kk, dd = 50.0, 50.0
    for i in range(len(close)):
        lo = min(low[max(0, i - n + 1):i + 1])
        hi = max(high[max(0, i - n + 1):i + 1])
        rsv = 50.0 if hi == lo else (close[i] - lo) / (hi - lo) * 100
        kk = rsv * 2 / 3 + kk / 3
        dd = kk * 2 / 3 + dd / 3
        k[i] = kk; d[i] = dd; j[i] = 3 * kk - 2 * dd
    return k, d, j

def boll(close, n=20, w=2):
    mid = sma(close, n)
    up, lo = [None] * len(close), [None] * len(close)
    for i in range(n - 1, len(close)):
        seg = close[i - n + 1:i + 1]
        sd = (sum((v - mid[i]) ** 2 for v in seg) / n) ** 0.5
        up[i] = mid[i] + w * sd
        lo[i] = mid[i] - w * sd
    return up, mid, lo

def atr(high, low, close, n=14):
    out = [None] * len(close)
    trs = [high[0] - low[0]]
    for i in range(1, len(close)):
        trs.append(max(high[i] - low[i], abs(high[i] - close[i - 1]), abs(low[i] - close[i - 1])))
    if len(trs) >= n:
        a = sum(trs[:n]) / n
        out[n - 1] = a
        for i in range(n, len(trs)):
            a = (a * (n - 1) + trs[i]) / n
            out[i] = a
    return out

def last(x):
    for v in reversed(x):
        if v is not None:
            return v
    return None

def prev(x, back=1):
    c = 0
    for v in reversed(x):
        if v is not None:
            if c == back:
                return v
            c += 1
    return None

def swing_levels(high, low, n=20, look=60):
    """最近 look 根内的显著摆动高低点(排除最近 n//2 根)，返回[(price,index,kind)]按价排序"""
    hh, ll = [], []
    start = max(0, len(high) - look)
    end = len(high) - max(3, n // 2)
    for i in range(start, end):
        seg_h = high[max(0, i - n // 2):i + n // 2 + 1]
        seg_l = low[max(0, i - n // 2):i + n // 2 + 1]
        if high[i] >= max(seg_h):
            hh.append((high[i], i, "H"))
        if low[i] <= min(seg_l):
            ll.append((low[i], i, "L"))
    return hh, ll

def pivots(prev_high, prev_low, prev_close):
    p = (prev_high + prev_low + prev_close) / 3
    return {
        "pivot": p,
        "r1": 2 * p - prev_low, "s1": 2 * p - prev_high,
        "r2": p + (prev_high - prev_low), "s2": p - (prev_high - prev_low),
    }

def analyze(variety, kd, compass):
    """kd: fetch_kline dict; compass: 风向项 or None; returns result dict"""
    c = kd["close"]; h = kd["high"]; l = kd["low"]
    n = len(c)
    r = {"symbol": variety["symbol"], "name": variety["name"], "exch": variety["exch"],
         "bars": n, "error": None}
    if n < 30:
        r["error"] = f"数据不足({n}根)"
        return r
    ma5, ma10, ma20 = sma(c, 5), sma(c, 10), sma(c, 20)
    ma60 = sma(c, 60) if n >= 60 else [None] * n
    dif, dea, hist = macd(c)
    rsi14 = rsi(c, 14)
    k, d, j = kdj(h, l, c)
    bu, bmid, blo = boll(c, 20)
    at14 = atr(h, l, c)
    px = c[-1]
    r.update({
        "date_last": kd["dates"][-1],
        "date_first": kd["dates"][0],
        "close": round(px, 2),
        "chg_pct": round((c[-1] / c[-2] - 1) * 100, 2) if n > 1 else 0,
        "ma5": round(last(ma5), 2), "ma10": round(last(ma10), 2),
        "ma20": round(last(ma20), 2), "ma60": round(last(ma60), 2) if last(ma60) else None,
        "macd": {"dif": round(last(dif), 3), "dea": round(last(dea), 3), "hist": round(last(hist), 3)},
        "rsi": round(last(rsi14), 1),
        "kdj": {"k": round(last(k), 1), "d": round(last(d), 1), "j": round(last(j), 1)},
        "boll": {"up": round(last(bu), 2), "mid": round(last(bmid), 2), "low": round(last(blo), 2)},
        "atr": round(last(at14), 2),
    })
    # --- 支撑阻力 ---
    levels = {"support": [], "resistance": []}
    hh, ll = swing_levels(h, l)
    seen_s, seen_r = set(), set()
    for price, idx, _ in sorted(hh, reverse=True):
        if price > px and round(price, 1) not in seen_r:
            seen_r.add(round(price, 1)); levels["resistance"].append(round(price, 2))
        if len(seen_r) >= 3:
            break
    for price, idx, _ in sorted(ll):
        if price < px and round(price, 1) not in seen_s:
            seen_s.add(round(price, 1)); levels["support"].append(round(price, 2))
        if len(seen_s) >= 3:
            break
    # 经典枢轴（用最近一根的H/L/C）
    if n >= 2:
        pv = pivots(h[-2], l[-2], c[-2])
        if pv["s1"] < px: levels["support"].append(round(pv["s1"], 2))
        if pv["s2"] < px: levels["support"].append(round(pv["s2"], 2))
        if pv["r1"] > px: levels["resistance"].append(round(pv["r1"], 2))
        if pv["r2"] > px: levels["resistance"].append(round(pv["r2"], 2))
    def uniq(lst):
        out = []
        for v in lst:
            if v not in out:
                out.append(v)
        return out[:3]
    levels["support"] = uniq(sorted(levels["support"]))
    levels["resistance"] = uniq(sorted(levels["resistance"], reverse=True))
    r["levels"] = levels
    # 最近支撑/阻力（供参考位）
    near_sup = max([s for s in levels["support"] if s < px], default=None)
    near_res = min([s for s in levels["resistance"] if s > px], default=None)
    atr_last = last(at14)
    r["near_levels"] = {
        "near_support": round(near_sup, 2) if near_sup else None,
        "near_resistance": round(near_res, 2) if near_res else None,
        "atr": round(atr_last, 2) if atr_last else None,
    }
    # 参考位：以"最近支撑下方 0.5ATR"为止损参考、最近阻力为止盈参考
    stop_ref = round(near_sup - 0.5 * atr_last, 2) if near_sup and atr_last else None
    tgt_ref = round(near_res, 2) if near_res else None
    r["ref"] = {"stop_ref": stop_ref, "target_ref": tgt_ref}
    m20, m60 = last(ma20), last(ma60)
    trend = "震荡"
    if m20 and m60:
        if px > m20 > m60 and last(hist) is not None and last(hist) >= 0:
            trend = "多头"
        elif px < m20 < m60 and last(hist) is not None and last(hist) <= 0:
            trend = "空头"
        elif px > m20 and px > m60:
            trend = "偏多震荡"
        elif px < m20 and px < m60:
            trend = "偏空震荡"
    r["trend"] = trend
    # --- 信号 ---
    events = []
    bullish, bearish = 0, 0
    def ev(txt, side):
        events.append({"text": txt, "side": side})
        nonlocal bullish, bearish
        if side == "B": bullish += 1
        elif side == "S": bearish += 1
    d0, d1 = last(dif), prev(dif); e0, e1 = last(dea), prev(dea)
    h0, h1 = last(hist), prev(hist)
    if d0 is not None and d1 is not None and e0 is not None and e1 is not None:
        if d1 <= e1 and d0 > e0:
            ev("MACD 金叉", "B" if d0 >= 0 else "B")
        if d1 >= e1 and d0 < e0:
            ev("MACD 死叉", "S")
    if h0 is not None and h1 is not None:
        if h1 <= 0 < h0:
            ev("MACD 红柱转正（动能转多）", "B")
        if h1 >= 0 > h0:
            ev("MACD 绿柱转负（动能转空）", "S")
    r14 = last(rsi14)
    if r14 is not None:
        if r14 >= 70:
            ev(f"RSI 超买({r14:.1f})", "S")
        elif r14 <= 30:
            ev(f"RSI 超卖({r14:.1f})", "B")
        elif 30 < r14 < 45:
            ev(f"RSI 偏弱({r14:.1f})", None)
        elif 55 < r14 < 70:
            ev(f"RSI 偏强({r14:.1f})", None)
    if last(k) is not None and last(d) is not None:
        if prev(k) is not None and prev(d) is not None:
            if prev(k) <= prev(d) and last(k) > last(d) and last(k) < 50:
                ev("KDJ 低位金叉", "B")
            if prev(k) >= prev(d) and last(k) < last(d) and last(k) > 50:
                ev("KDJ 高位死叉", "S")
        if last(j) is not None:
            if last(j) < 0:
                ev("KDJ-J 超卖(<0)", "B")
            if last(j) > 100:
                ev("KDJ-J 超买(>100)", "S")
    # MA 关系
    m5v = last(ma5); m10v = last(ma10)
    if m5v is not None and m10v is not None:
        if prev(ma5) is not None and prev(ma10) is not None:
            if prev(ma5) <= prev(ma10) and m5v > m10v:
                ev("MA5 上穿 MA10（短期转强）", "B")
            if prev(ma5) >= prev(ma10) and m5v < m10v:
                ev("MA5 下穿 MA10（短期转弱）", "S")
    if m20 and m60:
        if prev(ma20) is not None and prev(ma60) is not None:
            if prev(ma20) <= prev(ma60) and m20 > m60:
                ev("MA20 上穿 MA60（中期趋势转多）", "B")
            if prev(ma20) >= prev(ma60) and m20 < m60:
                ev("MA20 下穿 MA60（中期趋势转空）", "S")
    # 突破均线/布林
    if m20 and prev(ma20) is not None:
        if c[-1] > m20 and c[-2] <= prev(ma20):
            ev("收盘上破 MA20", "B")
        if c[-1] < m20 and c[-2] >= prev(ma20):
            ev("收盘下破 MA20", "S")
    buv = last(bu); blv = last(blo)
    if buv and c[-1] > buv:
        ev("突破布林上轨（强势但防回抽）", "B")
    if blv and c[-1] < blv:
        ev("跌破布林下轨（弱势但防反抽）", "S")
    # 近20日高低突破
    win_high = max(h[-21:-1]); win_low = min(l[-21:-1])
    if c[-1] > win_high:
        ev("创近20日新高", "B")
    if c[-1] < win_low:
        ev("创近20日新低", "S")
    r["events"] = events
    # 综合信号: B 权重 1, S 权重 1
    score = bullish - bearish
    signal = "观望"
    if score >= 3:
        signal = "偏多（可逢低关注）"
    elif score >= 1:
        signal = "谨慎偏多"
    elif score <= -3:
        signal = "偏空（反弹承压）"
    elif score <= -1:
        signal = "谨慎偏空"
    r["bull_count"], r["bear_count"] = bullish, bearish
    r["signal"] = signal
    # 风向罗盘叠加
    if compass:
        r["compass"] = {k: compass.get(k) for k in ("score", "change", "momlong", "momshort", "skew", "termstructure", "date")}
        try:
            sc = float(compass.get("score"))
            if sc >= 80:
                r["compass_view"] = "强多头风向"
            elif sc >= 65:
                r["compass_view"] = "偏多风向"
            elif sc <= 20:
                r["compass_view"] = "强空头风向"
            elif sc <= 35:
                r["compass_view"] = "偏空风向"
            else:
                r["compass_view"] = "中性风向"
        except Exception:
            r["compass_view"] = None
    # AI 解读(截断保存完整, HTML 展示截断)
    if kd.get("ai"):
        ai = kd["ai"]
        if isinstance(ai, str):
            r["ai_text"] = ai
        elif isinstance(ai, dict):
            r["ai_text"] = json.dumps(ai, ensure_ascii=False)[:800]
    return r

def build_all():
    if not HTFC_BASE_URL or not HTFC_API_KEY:
        raise RuntimeError("缺少 HTFC 配置")
    compass_map = fetch_compass_map()
    out = {"generated_at": _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
           "base_url": HTFC_BASE_URL, "varieties": [], "compass_date": None}
    for v in VARIETIES:
        try:
            if v.get("src") == "sina":
                kd = fetch_sina_daily(v["kline"])
                compass = None
            else:
                kd = fetch_kline(v["kline"], "-1year")
                compass = compass_map.get(v["compass"])
            res = analyze(v, kd, compass)
            if compass and not out["compass_date"]:
                out["compass_date"] = compass.get("date")
        except Exception as e:
            res = {"symbol": v["symbol"], "name": v["name"], "exch": v["exch"],
                   "error": f"{type(e).__name__}: {e}"}
        out["varieties"].append(res)
    try:
        out["spreads"] = build_spreads()
    except Exception as e:
        out["spreads"] = {"error": f"{type(e).__name__}: {e}"}
    # 总览按综合多空强度降序: 最偏多在前、最偏空在后(每天随数据动态调整, error 沉底)
    out["varieties"].sort(key=bull_bias, reverse=True)
    return out


# ================= 综合多空强度评分（总览排序用） =================
_TREND_W = {"多头": 3.0, "偏多震荡": 1.5, "震荡": 0.0, "偏空震荡": -1.5, "空头": -3.0}
_WIND_W = {"强多头风向": 2.0, "偏多风向": 1.0, "中性风向": 0.0,
           "偏空风向": -1.0, "强空头风向": -2.0}

def bull_bias(v):
    """综合多空强度分(越大越偏多): 趋势*2 + 信号净多空计数 + 风向分。
    供全品种总览每日排序使用; 出错品种沉底。"""
    if v.get("error"):
        return -1e9
    s = 2.0 * _TREND_W.get(str(v.get("trend")), 0.0)
    b, c = v.get("bull_count"), v.get("bear_count")
    if isinstance(b, (int, float)) and isinstance(c, (int, float)):
        s += float(b - c)
    else:
        sig = str(v.get("signal") or "")
        if ("偏多" in sig) or ("看多" in sig):
            s += 1.5
        elif ("偏空" in sig) or ("看空" in sig):
            s -= 1.5
    s += _WIND_W.get(str(v.get("compass_view") or ""), 0.0)
    return s


# ================= 价差组合技术分析 =================
# 合约支柱: 当前挂牌的 01/05/09 分别为 2701/2705/2609(2609 为临近交割的 09);
# 待 2709 上市后将 SPREAD_MONTHS["09"] 改为 "2709" 即可全局切换(5-9 月间价差随之变为 2705-2709)。
SPREAD_MONTHS = {"01": "2701", "05": "2705", "09": "2609"}
CROSS_SPREADS = [
    ("豆粕-菜粕", "M", "RM"),
    ("豆油-棕榈油", "Y", "P"),
    ("棕榈油-菜油", "P", "OI"),
    ("豆油-菜油", "Y", "OI"),
]
MONTH_SPREADS = {
    "M": [("1-5", "2701", "2705"), ("5-9", "2705", "2609"), ("9-1", "2609", "2701")],
    "Y": [("1-5", "2701", "2705"), ("5-9", "2705", "2609"), ("9-1", "2609", "2701")],
    "RM": [("1-5", "2701", "2705"), ("5-9", "2705", "2609"), ("9-1", "2609", "2701")],
    "OI": [("1-5", "2701", "2705"), ("5-9", "2705", "2609"), ("9-1", "2609", "2701")],
}
_VNAME = {v["symbol"]: v["name"] for v in VARIETIES}
_CONTRACT_CACHE = {}

def fetch_sina_contract(symbol):
    """新浪国内具体合约日线 (InnerFuturesNewService.getDailyKLine), symbol 如 'M2701'。
    返回与 fetch_kline 相同结构的 dict(键: dates/open/high/low/close)。"""
    import re, time, urllib.request
    url = ("https://stock2.finance.sina.com.cn/futures/api/jsonp.php/var%20_a=/InnerFuturesNewService"
           ".getDailyKLine?symbol=" + symbol)
    body, last_err = None, None
    for _ in range(3):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0",
                "Referer": "https://finance.sina.com.cn/"})
            body = urllib.request.urlopen(req, timeout=20).read().decode("utf-8", "ignore")
            break
        except Exception as e:
            last_err = e
            time.sleep(1.5)
    if body is None:
        raise last_err
    m = re.search(r"\((\[.*\])\)\s*;?\s*$", body, re.S)
    if not m:
        raise RuntimeError("合约日线返回格式异常: " + body[:120])
    rows = json.loads(m.group(1))
    if not rows:
        raise RuntimeError(f"合约日线为空(symbol={symbol})")
    dates = [r["d"] for r in rows if r.get("d") and r.get("c")]
    return {
        "dates": dates,
        "open": [float(r["o"]) for r in rows if r.get("d") and r.get("c")],
        "high": [float(r["h"]) for r in rows if r.get("d") and r.get("c")],
        "low": [float(r["l"]) for r in rows if r.get("d") and r.get("c")],
        "close": [float(r["c"]) for r in rows if r.get("d") and r.get("c")],
        "ai": None, "report": None,
    }

def get_contract(symbol):
    if symbol not in _CONTRACT_CACHE:
        _CONTRACT_CACHE[symbol] = fetch_sina_contract(symbol)
    return _CONTRACT_CACHE[symbol]

def align_spread_series(sym_a, sym_b):
    """两腿合约逐日收盘价之差(日期取交集)。返回 (dates, closes)"""
    ka, kb = get_contract(sym_a), get_contract(sym_b)
    bmap = dict(zip(kb["dates"], kb["close"]))
    dates, closes = [], []
    for d, ca in zip(ka["dates"], ka["close"]):
        if d in bmap:
            dates.append(d)
            closes.append(ca - bmap[d])
    return dates, closes

def spread_metrics(dates, closes):
    """仅收盘价的价差技术分析(无盘中高低, 故不做KDJ/ATR/枢轴)。"""
    n = len(closes)
    r = {"bars": n}
    if n < 30:
        r["error"] = f"数据不足({n}根)"
        return r
    px = closes[-1]
    ma5, ma10, ma20 = sma(closes, 5), sma(closes, 10), sma(closes, 20)
    ma60 = sma(closes, 60) if n >= 60 else [None] * n
    dif, dea, hist = macd(closes)
    rsi14 = rsi(closes, 14)
    bu, bmid, blo = boll(closes, 20)
    r.update({
        "date_last": dates[-1], "date_first": dates[0],
        "close": round(px, 2),
        "chg": round(px - closes[-2], 2) if n > 1 else None,
        "ma5": round(last(ma5), 2), "ma10": round(last(ma10), 2),
        "ma20": round(last(ma20), 2), "ma60": round(last(ma60), 2) if last(ma60) else None,
        "macd": {"dif": round(last(dif), 3), "dea": round(last(dea), 3), "hist": round(last(hist), 3)},
        "rsi": round(last(rsi14), 1) if last(rsi14) is not None else None,
        "boll": {"up": round(last(bu), 2), "mid": round(last(bmid), 2), "low": round(last(blo), 2)},
        "mean": round(sum(closes) / n, 2),
        "range": [round(min(closes), 2), round(max(closes), 2)],
    })
    # 趋势(价差语义): 上行=走阔, 下行=收窄
    m20v, m60v, h0 = last(ma20), last(ma60), last(hist)
    if m20v and m60v and h0 is not None:
        if px > m20v > m60v and h0 >= 0:
            trend = "上行"
        elif px < m20v < m60v and h0 <= 0:
            trend = "下行"
        elif px > m20v and px > m60v:
            trend = "震荡偏上"
        elif px < m20v and px < m60v:
            trend = "震荡偏下"
        else:
            trend = "区间震荡"
    else:
        trend = "区间震荡"
    r["trend"] = trend
    # 事件信号(与品种引擎同逻辑)
    events, bull, bear = [], 0, 0
    def ev(txt, side):
        events.append({"text": txt, "side": side})
        nonlocal bull, bear
        if side == "B": bull += 1
        elif side == "S": bear += 1
    d0, d1, e0, e1 = last(dif), prev(dif), last(dea), prev(dea)
    if None not in (d0, d1, e0, e1):
        if d1 <= e1 and d0 > e0: ev("MACD 金叉(价差走阔动能)", "B")
        if d1 >= e1 and d0 < e0: ev("MACD 死叉(价差收窄动能)", "S")
    h1 = prev(hist)
    if h0 is not None and h1 is not None:
        if h1 <= 0 < h0: ev("MACD 红柱转正", "B")
        if h1 >= 0 > h0: ev("MACD 绿柱转负", "S")
    rv = last(rsi14)
    if rv is not None:
        if rv >= 70: ev(f"RSI 超买({rv:.1f})", "S")
        elif rv <= 30: ev(f"RSI 超卖({rv:.1f})", "B")
        elif rv < 45: ev(f"RSI 偏弱({rv:.1f})", None)
        elif rv > 55: ev(f"RSI 偏强({rv:.1f})", None)
    m5v, m10v = last(ma5), last(ma10)
    if None not in (m5v, m10v, prev(ma5), prev(ma10)):
        if prev(ma5) <= prev(ma10) and m5v > m10v: ev("MA5 上穿 MA10(短期价差转强)", "B")
        if prev(ma5) >= prev(ma10) and m5v < m10v: ev("MA5 下穿 MA10(短期价差转弱)", "S")
    if m20v and prev(ma20) is not None and prev(ma20) is not None and m60v and prev(ma60) is not None:
        if prev(ma20) <= prev(ma60) and m20v > m60v: ev("MA20 上穿 MA60(中期转阔)", "B")
        if prev(ma20) >= prev(ma60) and m20v < m60v: ev("MA20 下穿 MA60(中期转窄)", "S")
    if m20v and prev(ma20) is not None:
        if closes[-1] > m20v and closes[-2] <= prev(ma20): ev("上破 MA20", "B")
        if closes[-1] < m20v and closes[-2] >= prev(ma20): ev("下破 MA20", "S")
    buv, blv = last(bu), last(blo)
    if buv and px > buv: ev("突破布林上轨(价差冲高防回抽)", "B")
    if blv and px < blv: ev("跌破布林下轨(价差走弱防反抽)", "S")
    w20h, w20l = max(closes[-21:-1]), min(closes[-21:-1])
    if px > w20h: ev("创近20日新高(价差)", "B")
    if px < w20l: ev("创近20日新低(价差)", "S")
    r["events"] = events
    score = bull - bear
    if score >= 3: signal = "看多价差(强)"
    elif score >= 1: signal = "谨慎看多价差"
    elif score <= -3: signal = "看空价差(强)"
    elif score <= -1: signal = "谨慎看空价差"
    else: signal = "观望"
    r["bull_count"], r["bear_count"], r["signal"] = bull, bear, signal
    # 支撑阻力: 收盘价摆动高低点 + 布林带兜底
    levels = {"support": [], "resistance": []}
    hh, ll = swing_levels(closes, closes)
    seen_r, seen_s = set(), set()
    for price, _, _ in sorted(hh, reverse=True):
        if price > px and round(price, 1) not in seen_r:
            seen_r.add(round(price, 1)); levels["resistance"].append(round(price, 2))
        if len(seen_r) >= 2: break
    for price, _, _ in sorted(ll):
        if price < px and round(price, 1) not in seen_s:
            seen_s.add(round(price, 1)); levels["support"].append(round(price, 2))
        if len(seen_s) >= 2: break
    near_sup = max(levels["support"], default=None) if levels["support"] else None
    near_res = min(levels["resistance"], default=None) if levels["resistance"] else None
    if near_sup is None and blv is not None and blv < px:
        near_sup = round(blv, 2)
    if near_res is None and buv is not None and buv > px:
        near_res = round(buv, 2)
    r["levels"] = levels
    r["near_levels"] = {"near_support": near_sup, "near_resistance": near_res}
    return r

def build_spreads():
    cross, month = [], []
    # 跨品种价差: 同合约月 01/05/09
    for name, sym_a, sym_b in CROSS_SPREADS:
        for mkey in ("01", "05", "09"):
            cmonth = SPREAD_MONTHS[mkey]
            a, b = sym_a + cmonth, sym_b + cmonth
            row = {"cat": "cross", "combo": f"{name} {mkey}合约",
                   "code": f"{a}-{b}", "mkey": mkey,
                   "name_a": _VNAME.get(sym_a, sym_a), "name_b": _VNAME.get(sym_b, sym_b)}
            try:
                dates, closes = align_spread_series(a, b)
                row.update(spread_metrics(dates, closes))
            except Exception as e:
                row["error"] = f"{type(e).__name__}: {e}"
            cross.append(row)
    # 月间价差
    for var, pairs in MONTH_SPREADS.items():
        for pname, near, far in pairs:
            a, b = var + near, var + far
            row = {"cat": "month", "combo": f"{_VNAME.get(var, var)} {pname}价差",
                   "code": f"{a}-{b}", "mkey": pname}
            try:
                dates, closes = align_spread_series(a, b)
                row.update(spread_metrics(dates, closes))
            except Exception as e:
                row["error"] = f"{type(e).__name__}: {e}"
            month.append(row)
    return {"cross": cross, "month": month,
            "months_note": "当前挂牌 01/05/09 = 2701/2705/2609（09 为临近交割月；2709 上市后将切换至 2709）"} 

if __name__ == "__main__":
    data = build_all()
    print(json.dumps(data, ensure_ascii=False)[:4000])
