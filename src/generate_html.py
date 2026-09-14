# -*- coding: utf-8 -*-
"""根据 panel JSON 生成自包含 HTML 全品种总览表（纯表格，无图表，可双击打开）。"""
import json
import datetime as _dt

def _esc(s):
    if s is None:
        return ""
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")

def fmt(v, nd=2):
    if v is None:
        return "-"
    return ("%." + str(nd) + "f") % v if isinstance(v, float) else str(v)

TREND_CLS = {"多头": "t-up", "偏多震荡": "t-up", "上行": "t-up", "震荡偏上": "t-up",
             "空头": "t-down", "偏空震荡": "t-down", "下行": "t-down", "震荡偏下": "t-down",
             "震荡": "t-flat", "区间震荡": "t-flat"}
def trend_cls(t):
    return TREND_CLS.get(t or "", "t-flat")

def sig_cls(s):
    s = str(s or "")
    if "偏空" in s or "看空" in s:
        return "t-down"
    if "偏多" in s or "看多" in s:
        return "t-up"
    return "t-flat"

def compass_text(v):
    """风向分 -> 文字叙述（用户在总览表只展示文字）。无分返回 None"""
    cv = v.get("compass_view")
    return cv if cv else None

def _spread_rows_html(rows):
    parts = []
    for v in rows:
        if v.get("error"):
            parts.append(f'<tr><td>{_esc(v["combo"])} <span class="code">{_esc(v.get("code") or "")}</span></td>'
                         f'<td colspan="7" style="color:#b91c1c">数据获取失败：{_esc(v["error"])}</td></tr>')
            continue
        chg = v.get("chg")
        chg_cls = "up" if (chg or 0) > 0 else ("down" if (chg or 0) < 0 else "flat")
        chg_txt = ("+" if (chg or 0) > 0 else "") + fmt(chg)
        nl = v.get("near_levels") or {}
        parts.append(
            f'<tr><td><b>{_esc(v["combo"])}</b><br><span class="code">{_esc(v.get("code") or "")}</span></td>'
            f'<td class="num">{fmt(v.get("close"))}</td>'
            f'<td class="num {chg_cls}">{chg_txt}</td>'
            f'<td><span class="tag {trend_cls(v.get("trend"))}">{_esc(v.get("trend") or "-")}</span></td>'
            f'<td><span class="tag {sig_cls(v.get("signal"))}">{_esc(v.get("signal") or "-")}</span></td>'
            f'<td class="num">{fmt(nl.get("near_support"))}</td><td class="num">{fmt(nl.get("near_resistance"))}</td>'
            f'<td class="num">{fmt(v.get("date_last"), 0)}</td></tr>'
        )
    return "".join(parts)

def spread_card(title, rows, note=""):
    if not rows:
        return ""
    note_html = f'<p class="note">{_esc(note)}</p>' if note else ""
    return f"""
  <div class="card">
    <h3>{title}</h3>
    {note_html}
    <table>
      <tr><th>价差组合</th><th class="num">最新价差</th><th class="num">较昨</th><th>趋势</th><th>信号</th>
          <th class="num">最近支撑</th><th class="num">最近阻力</th><th class="num">数据至</th></tr>
      {_spread_rows_html(rows)}
    </table>
    <p class="hint">趋势“上行/下行”表示价差走阔/收窄；信号以价差方向表述（看多价差=价差扩大、看空价差=价差收窄）。指标基于两腿合约逐日收盘价之差，MA/MACD/RSI/BOLL/支撑阻力为纯收盘价口径，不含盘中高低。</p>
  </div>
"""

def build(data):
    gen = data.get("generated_at", "")
    compass_date = data.get("compass_date") or "-"
    rows = data.get("varieties", [])

    ov = []
    # 品种顺序: 已按综合多空强度降序(最偏多在前/最偏空在后), 不再做外盘分组
    for v in rows:
        if v.get("error"):
            ov.append(f'<tr><td>{_esc(v["name"])} <span class="code">{_esc(v["symbol"])}</span></td>'
                      f'<td colspan="8" style="color:#b91c1c">数据获取失败：{_esc(v["error"])}</td></tr>')
            continue
        chg = v.get("chg_pct")
        chg_cls = "up" if (chg or 0) > 0 else ("down" if (chg or 0) < 0 else "flat")
        chg_txt = ("+" if (chg or 0) > 0 else "") + fmt(chg) + "%"
        trend = v.get("trend", "-")
        sig = v.get("signal", "-")
        nl = v.get("near_levels") or {}
        sup, res = nl.get("near_support"), nl.get("near_resistance")
        wind = compass_text(v) or "-"
        ov.append(
            f'<tr><td><b>{_esc(v["name"])}</b> <span class="code">{_esc(v["symbol"])}·{_esc(v["exch"])}</span></td>'
            f'<td class="num">{fmt(v.get("close"))}</td>'
            f'<td class="num {chg_cls}">{chg_txt}</td>'
            f'<td><span class="tag {trend_cls(trend)}">{_esc(trend)}</span></td>'
            f'<td><span class="tag {sig_cls(sig)}">{_esc(sig)}</span></td>'
            f'<td class="num">{fmt(sup)}</td><td class="num">{fmt(res)}</td>'
            f'<td class="wind">{_esc(wind)}</td>'
            f'<td class="num">{fmt(v.get("date_last"), 0)}</td></tr>'
        )
    ov_html = "".join(ov)

    sp = data.get("spreads") or {}
    sp_cross = sp_month = ""
    if isinstance(sp, dict):
        if sp.get("error"):
            sp_cross = f'<div class="card"><h3>价差组合</h3><p class="err">价差数据生成失败：{_esc(sp["error"])}</p></div>'
        else:
            note = sp.get("months_note") or ""
            sp_cross = spread_card("🔗 跨品种价差技术分析（同合约月 01/05/09）", sp.get("cross") or [], note)
            sp_month = spread_card("📅 月间价差技术分析（1-5 / 5-9 / 9-1）", sp.get("month") or [], note)

    today = _dt.date.today().isoformat()
    # 品种清单(顺序同表) 用于页眉
    names = "、".join(f'{_esc(v["name"])}' for v in rows if not v.get("error"))
    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>期货技术分析总览（主力合约） {today}</title>
<style>
  * {{ box-sizing: border-box; }}
  body {{ font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif; margin: 0; padding: 22px;
        background: #f4f6f9; color: #1f2937; }}
  .wrap {{ max-width: 1280px; margin: 0 auto; }}
  header {{ background: linear-gradient(135deg,#123a5e,#1d6fa5); color: #fff; border-radius: 14px; padding: 20px 26px;
           margin-bottom: 14px; }}
  header h1 {{ margin: 0 0 6px; font-size: 22px; }}
  header .meta {{ font-size: 12.5px; opacity: .9; line-height: 1.8; }}
  .card {{ background: #fff; border-radius: 12px; padding: 16px 18px; box-shadow: 0 1px 4px rgba(15,23,42,.06); }}
  .card h3 {{ margin: 0 0 8px; font-size: 16px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 13.5px; }}
  th {{ background: #eef2f7; text-align: left; padding: 9px 10px; font-weight: 600; white-space: nowrap; }}
  td {{ padding: 8px 10px; border-bottom: 1px solid #eef2f7; }}
  tr:last-child td {{ border-bottom: none; }}
  .num {{ text-align: right; font-variant-numeric: tabular-nums; }}
  .code {{ color: #6b7280; font-size: 11.5px; font-weight: 400; }}
  .up {{ color: #d23c3c; }} .down {{ color: #0a9d6e; }} .flat {{ color: #6b7280; }}
  .tag {{ display: inline-block; padding: 1px 8px; border-radius: 999px; font-size: 12px; }}
  .t-up {{ background: #fde8e8; color: #b91c1c; }} .t-down {{ background: #d7f3e8; color: #0a7a55; }}
  .t-flat {{ background: #eef0f3; color: #4b5563; }}
  .wind {{ white-space: nowrap; }}
  .foot {{ color: #6b7280; font-size: 12px; line-height: 1.9; padding: 10px 4px 30px; }}
  .err {{ color: #b91c1c; }}
  .note {{ margin: 0 0 8px; color: #6b7280; font-size: 12px; }}
  .hint {{ margin: 10px 0 0; color: #8a94a6; font-size: 12px; line-height: 1.8; }}
  @media (max-width: 900px) {{ body {{ padding: 10px; overflow-x: auto; }} }}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1>📊 期货技术分析总览 · 主力合约与价差组合</h1>
    <div class="meta">生成时间：{gen} ｜ 品种：{names} ＋ 价差组合（跨品种/月间，覆盖 豆粕/菜粕/豆油/棕榈油/菜油 的 2701/2705/2609 合约）
    <br>数据来源：天玑智能K线日线(国内8品种) ＋ 新浪财经外盘日线(WTI原油 NYMEX CL 主力连续) ＋ 新浪合约日线(价差两腿，逐日收盘价差) ＋ 天玑风向罗盘(国内，数据日 {_esc(compass_date)})</div>
  </header>

  <div class="card">
    <h3>📋 全品种总览 <span style="font-size:12px;font-weight:400;color:#6b7280">（按综合多空强度降序：最偏多→最偏空）</span></h3>
    <table>
      <tr><th>品种</th><th class="num">收盘</th><th class="num">涨跌</th><th>趋势</th><th>信号</th>
          <th class="num">最近支撑</th><th class="num">最近阻力</th><th>风向</th><th class="num">数据至</th></tr>
      {ov_html}
    </table>
  </div>

  {sp_cross}
  {sp_month}

  <div class="foot">
    ⚠️ <b>免责声明</b>：本面板由程序基于授权/公开接口数据与量化技术指标自动生成，支撑/阻力与买卖信号仅为技术面统计提示，
    不构成任何投资建议或交易依据。行情具有时效性，请以交易所与期货公司实时行情为准。市场有风险，投资需谨慎。过往表现不预示未来收益。
    <br>口径说明：① 全品种总览按“趋势/信号/风向”三维综合的多空强度评分降序排列（趋势权重最高），最偏多在前、最偏空在后，
    随每日数据自动调整；出错品种沉底。② 风向为天玑风向罗盘文字表述
    （风向分 ≥80 强多头、65~79 偏多、36~64 中性、21~35 偏空、≤20 强空头），外盘品种无罗盘数据故显示"-"；
    ③ 国内K线为天玑智能K线(无复权)，WTI 当日 bar 为盘中实时滚动价、结算后才定型，如遇节假日/数据未更新则展示最近交易日数据；
    ④ 价差口径：跨品种价差 = A品种同月合约 − B品种同月合约（如 M2701−RM2701）；月间价差 = 近月 − 远月
    （如 豆粕1-5 = M2701−M2705、9-1 = M2609−M2701）。09 合约当前为 2609（临近交割月），2709 上市后将切换；
    05/09 腿部分合约数据可能止于前一日（合约当日无成交），以各行"数据至"为准。
  </div>
</div>
</body>
</html>
"""
    return html

if __name__ == "__main__":
    import sys
    d = json.load(open(sys.argv[1], encoding="utf-8"))
    out = sys.argv[2] if len(sys.argv) > 2 else "panel.html"
    open(out, "w", encoding="utf-8").write(build(d))
    print("written:", out)
