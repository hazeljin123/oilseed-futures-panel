# -*- coding: utf-8 -*-
"""端到端运行：抓数 -> 指标/信号 -> JSON -> HTML 面板。用法: python run_panel.py [日期标签]"""
import json
import os
import sys
import datetime as _dt

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import panel_lib
import generate_html

def main():
    tag = sys.argv[1] if len(sys.argv) > 1 else _dt.date.today().strftime("%Y-%m-%d")
    print("== 拉取数据并计算指标 ==", flush=True)
    data = panel_lib.build_all()
    json_path = os.path.join(HERE, f"panel-{tag}.json")
    json_latest = os.path.join(HERE, "panel-latest.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    with open(json_latest, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    print("JSON ->", json_path)

    html = generate_html.build(data)
    html_path = os.path.join(HERE, f"panel-{tag}.html")
    html_latest = os.path.join(HERE, "panel-latest.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)
    with open(html_latest, "w", encoding="utf-8") as f:
        f.write(html)
    print("HTML ->", html_path)

    # 控制台摘要（供会话内播报）
    print("\n===== 摘要 =====")
    ok = [v for v in data["varieties"] if not v.get("error")]
    err = [v for v in data["varieties"] if v.get("error")]
    print("(总览已按综合多空强度降序排列: 最偏多→最偏空)")
    for v in ok:
        nl = v.get("near_levels") or {}
        cv = v.get("compass_view") or "-"
        print(f'{v["name"]:<6}{v["symbol"]:>3} 收 {v.get("close")}  {v.get("chg_pct")}%  '
              f'{v.get("trend")} | {v.get("signal")} | 支撑{nl.get("near_support")} '
              f'阻力{nl.get("near_resistance")} | 风向{cv} | {v.get("date_last")}')
    if err:
        print("失败:", [(v["symbol"], v["error"]) for v in err])
    sp = data.get("spreads") or {}
    if isinstance(sp, dict) and not sp.get("error"):
        print("\n----- 价差组合摘要 -----")
        for row in sp.get("cross", []):
            if row.get("error"):
                print(f'[跨] {row["combo"]}: {row["error"]}')
                continue
            nl = row.get("near_levels") or {}
            print(f'[跨] {row["combo"]:<10}{row.get("code",""):<14} = {row.get("close")} (Δ{row.get("chg")}) '
                  f'{row.get("trend")}|{row.get("signal")} 支{nl.get("near_support")} 阻{nl.get("near_resistance")} 至{row.get("date_last")}')
        for row in sp.get("month", []):
            if row.get("error"):
                print(f'[月] {row["combo"]}: {row["error"]}')
                continue
            nl = row.get("near_levels") or {}
            print(f'[月] {row["combo"]:<10}{row.get("code",""):<14} = {row.get("close")} (Δ{row.get("chg")}) '
                  f'{row.get("trend")}|{row.get("signal")} 支{nl.get("near_support")} 阻{nl.get("near_resistance")} 至{row.get("date_last")}')
    print(f"生成时间: {data.get('generated_at')}  风向数据日: {data.get('compass_date')}")
    print("HTML路径:", html_latest)

if __name__ == "__main__":
    main()
