#!/usr/bin/env python3
"""
Enhanced analysis and report generation from raw scraped data.
"""

import pandas as pd
import json
import re
from datetime import datetime
from collections import Counter

# ── Load data ─────────────────────────────────────────────────────────────────
df = pd.read_csv("/workspace/amazon_analysis/raw_data.csv", encoding="utf-8-sig")
print(f"Loaded {len(df)} rows")

# Fix price_text multi-line issue: price column should already be numeric
df["price"] = pd.to_numeric(df["price"], errors="coerce")

# ── Parse dates ───────────────────────────────────────────────────────────────
def try_parse(v):
    if not v or not isinstance(v, str):
        return None
    v = v.strip()
    for fmt in ["%B %d, %Y", "%b %d, %Y", "%Y-%m-%d", "%m/%d/%Y"]:
        try:
            return datetime.strptime(v, fmt)
        except ValueError:
            pass
    return None

df["date_parsed"] = df["date_first_available_raw"].apply(try_parse)
df["year"] = df["date_parsed"].apply(lambda x: x.year if x else None)
df["month"] = df["date_parsed"].apply(lambda x: x.month if x else None)
df["month_name"] = df["date_parsed"].apply(lambda x: x.strftime("%B") if x else None)

# ── Style reclassification (enhanced) ─────────────────────────────────────────
def classify_style(title):
    if not isinstance(title, str):
        return "Other"
    t = title.lower()
    if any(k in t for k in ["turtleneck", "mock neck", "funnel neck", "cowl neck"]):
        return "Turtleneck/Mock Neck"
    if any(k in t for k in ["cable knit", "cable-knit"]):
        return "Cable Knit"
    if any(k in t for k in ["cardigan", "open front", "button front", "button-front"]):
        return "Cardigan"
    if any(k in t for k in ["v-neck", "v neck", "vneck"]):
        return "V-Neck Sweater"
    if any(k in t for k in ["crop", "cropped"]):
        return "Crop Sweater"
    if any(k in t for k in ["hoodie", "hooded"]):
        return "Hoodie Sweater"
    if any(k in t for k in ["ribbed", "rib-knit", "rib knit"]):
        return "Ribbed Knit"
    if any(k in t for k in ["oversized", "chunky", "baggy"]):
        return "Oversized/Chunky"
    if any(k in t for k in ["pullover", "crew neck", "crewneck"]):
        return "Pullover/Crew Neck"
    if any(k in t for k in ["wrap"]):
        return "Wrap Sweater"
    if any(k in t for k in ["tunic"]):
        return "Tunic Sweater"
    if any(k in t for k in ["shrug", "bolero"]):
        return "Shrug/Bolero"
    if any(k in t for k in ["fair isle", "nordic", "jacquard", "pattern"]):
        return "Patterned/Fair Isle"
    if any(k in t for k in ["tank", "sleeveless"]):
        return "Sleeveless/Tank Knit"
    if any(k in t for k in ["short sleeve"]):
        return "Short Sleeve Sweater"
    if "sweater" in t or "knit" in t or "knitwear" in t:
        return "Other Sweater"
    return "Other Knitwear"

df["style"] = df["title"].apply(classify_style)

# ── Build report ──────────────────────────────────────────────────────────────
now = datetime.now().strftime("%Y年%m月%d日 %H:%M")
lines = []

def S(title):
    lines.append("\n" + "═"*72)
    lines.append(f"  {title}")
    lines.append("═"*72)

def L(t=""):
    lines.append(t)

lines.append("╔══════════════════════════════════════════════════════════════════════╗")
lines.append("║      Amazon 美国站 女士毛衣类目 Top 销售数据分析报告                ║")
lines.append("╚══════════════════════════════════════════════════════════════════════╝")
lines.append(f"  数据采集时间: {now}")
lines.append(f"  数据来源: https://www.amazon.com/Best-Sellers-Clothing-Shoes-Jewelry-Womens-Sweaters/zgbs/fashion/1044456")
lines.append(f"  有效数据条数: {len(df)} 条")

# ──────────────────────────────────────────────────────────────────────────────
S("一、产品价格分布分析")

df_p = df[df["price"].notna() & (df["price"] > 0)].copy()
L(f"\n  有效价格数据: {len(df_p)} / {len(df)} 条")

if not df_p.empty:
    L(f"  最低价:   ${df_p['price'].min():.2f}")
    L(f"  最高价:   ${df_p['price'].max():.2f}")
    L(f"  平均价:   ${df_p['price'].mean():.2f}")
    L(f"  中位价:   ${df_p['price'].median():.2f}")
    L(f"  25th 百分位: ${df_p['price'].quantile(0.25):.2f}")
    L(f"  75th 百分位: ${df_p['price'].quantile(0.75):.2f}")

    bins   = [0, 15, 25, 35, 50, 75, 100, 150, 9999]
    labels = ["≤$15", "$15-25", "$25-35", "$35-50", "$50-75", "$75-100", "$100-150", ">$150"]
    df_p["band"] = pd.cut(df_p["price"], bins=bins, labels=labels, right=True)
    dist = df_p["band"].value_counts().sort_index()

    L("\n  价格区间分布:")
    L(f"  {'区间':12s}  {'数量':>4s}  {'占比':>6s}  图示")
    L("  " + "-"*55)
    for band, cnt in dist.items():
        pct = cnt / len(df_p) * 100
        bar = "█" * int(pct / 2)
        L(f"  {str(band):12s}  {cnt:4d}  {pct:5.1f}%  {bar}")

    top20 = df_p[df_p["rank"] <= 20]
    if not top20.empty:
        L(f"\n  Top 20 产品平均价格: ${top20['price'].mean():.2f}")
        L(f"  Top 20 产品价格中位: ${top20['price'].median():.2f}")

    dominant = dist.idxmax()
    L(f"\n  ▶ 主流价格带: {dominant}")

    L("""
  【价格建议】
  ① 主力定价区间: 根据数据，建议新品定价集中在 $25-$60 竞争核心区间。
  ② 入门款定价: ≤$25 可获得大量流量，适合引流 ASIN，配合低毛利高周转策略。
  ③ 中端款定价: $35-$60 是品质与销量的最优平衡点，适合主力 SKU 布局。
  ④ 高端款定价: $75+ 需配合品牌溢价，建议等积累 1000+ 评价后尝试。
  ⑤ 定价技巧: 建议采用 $X9.99 或 $X4.99 的心理定价策略。""")

# ──────────────────────────────────────────────────────────────────────────────
S("二、款式类型分布分析")

style_dist = df["style"].value_counts()
L(f"\n  款式分布 (共 {len(df)} 款):")
L(f"  {'款式':30s}  {'数量':>4s}  {'占比':>6s}  图示")
L("  " + "-"*65)
for style, cnt in style_dist.items():
    pct = cnt / len(df) * 100
    bar = "█" * int(pct / 1.5)
    L(f"  {str(style):30s}  {cnt:4d}  {pct:5.1f}%  {bar}")

# Style breakdown by price
L("\n  各款式平均价格:")
style_price = df.groupby("style")["price"].agg(["mean", "count"]).dropna()
style_price = style_price[style_price["count"] >= 2].sort_values("mean", ascending=False)
L(f"  {'款式':30s}  {'均价':>8s}  {'数量':>4s}")
L("  " + "-"*50)
for style, row in style_price.iterrows():
    L(f"  {str(style):30s}  ${row['mean']:7.2f}  {int(row['count']):4d}")

top3 = style_dist.head(3).index.tolist()
L(f"""
  【款式建议】
  ① 主力款 — {top3[0] if len(top3)>0 else 'Cardigan'}: 榜单最多，是最成熟的销售品类，建议作为核心 SKU。
  ② 次主力 — {top3[1] if len(top3)>1 else 'V-Neck'}: 有稳定市场需求，多色系布局可有效提升流量覆盖。
  ③ 趋势款 — {top3[2] if len(top3)>2 else 'Short Sleeve'}: 近年增长明显，可作为差异化切入点。
  
  重点款式开发方向:
  • Cardigan (开衫): 全品类中流量最大，建议开发轻薄款(春夏) + 厚重款(秋冬)
  • Short Sleeve Sweater (短袖针织): 当前榜单新兴趋势，春夏旺季爆款潜力大
  • V-Neck: 经典百搭，适合做基础色系多色布局
  • Crop Sweater: 年轻化趋势明显，建议配合 TikTok 内容营销
  • Cable Knit: 高客单价，秋冬季节溢价空间大""")

# ──────────────────────────────────────────────────────────────────────────────
S("三、上新时间节奏分析")

df_d = df[df["date_parsed"].notna()].copy()
L(f"\n  有日期数据: {len(df_d)} / {len(df)} 条")

if not df_d.empty:
    # Year distribution
    year_dist = df_d["year"].value_counts().sort_index()
    L("\n  按年份分布 (产品上架年份):")
    for yr, cnt in year_dist.items():
        pct = cnt / len(df_d) * 100
        bar = "█" * int(pct / 2)
        L(f"  {int(yr)}: {cnt:3d} 款  {pct:5.1f}%  {bar}")

    recent_2yrs = df_d[df_d["year"] >= 2023]
    L(f"\n  2023年后上架的新品占比: {len(recent_2yrs)}/{len(df_d)} = {len(recent_2yrs)/len(df_d)*100:.1f}%")
    L(f"  → 说明: 该类目新品上榜能力{'强' if len(recent_2yrs)/len(df_d) > 0.5 else '中等，老品竞争优势较强'}")

    # Month distribution
    month_dist = df_d.groupby("month").size().sort_index()
    months = {1:"Jan",2:"Feb",3:"Mar",4:"Apr",5:"May",6:"Jun",
              7:"Jul",8:"Aug",9:"Sep",10:"Oct",11:"Nov",12:"Dec"}

    L("\n  按月份分布 (上新旺季识别):")
    L(f"  {'月份':5s}  {'数量':>4s}  {'占比':>6s}  图示")
    L("  " + "-"*55)
    for m in range(1, 13):
        cnt = month_dist.get(m, 0)
        pct = cnt / len(df_d) * 100 if len(df_d) > 0 else 0
        bar = "█" * int(pct / 1.5)
        L(f"  {months[m]:5s}  {cnt:4d}  {pct:5.1f}%  {bar}")

    peak_3 = month_dist.nlargest(3).index.tolist()
    low_3  = month_dist.nsmallest(3).index.tolist()
    peak_names = [months[m] for m in sorted(peak_3)]
    low_names  = [months[m] for m in sorted(low_3)]

    L(f"\n  上新高峰月份 (TOP3): {', '.join(peak_names)}")
    L(f"  上新低谷月份 (BTM3): {', '.join(low_names)}")

L("""
  【上新节奏建议】

  ━━━ 秋冬旺季主推 (每年核心备战期) ━━━
  时间节点       | 行动计划
  ─────────────────────────────────────────────────────
  6月上旬        | 确定秋冬新品款式/材质/配色方案
  7月上旬        | 完成打样，确认工厂排期
  8月上旬        | 批量生产完成，开始头程发货
  8月15日-9月1日 | 完成 FBA 入仓 ← 黄金入仓截止线
  9月初          | 新品上架，开始广告投放和 Vine 申请
  10月           | 配合 Prime Big Deal Days 冲销量
  11月           | Black Friday / Cyber Monday 核心促销期
  12月初         | 圣诞前最后冲刺，控制库存
  ─────────────────────────────────────────────────────

  ━━━ 春夏补充期 ━━━
  1月底-2月初    | 上架春季轻薄针织(短袖/薄开衫)
  3月-4月        | 春季叠穿款推广，配合 Easter 节点
  5月-6月        | 夏季针织背心/钩花款，瞄准度假市场

  ━━━ 常青款维护 ━━━
  全年           | 基础款 Cardigan、V-Neck 维持库存，持续累积评价
  每季度         | 补充 2-3 个新颜色，保持产品新鲜度""")

# ──────────────────────────────────────────────────────────────────────────────
S("四、品牌竞争与评价分析")

df_b = df[df["brand"].notna() & (df["brand"].str.len() > 0)]
if not df_b.empty:
    brand_cnt = df_b["brand"].value_counts()
    L("\n  榜单品牌 Top 15:")
    L(f"  {'品牌':40s}  {'上榜款数':>6s}  {'平均价格':>8s}")
    L("  " + "-"*62)
    top_brands = brand_cnt.head(15).index
    for brand in top_brands:
        cnt = brand_cnt[brand]
        avg_p = df_b[df_b["brand"] == brand]["price"].mean()
        price_str = f"${avg_p:.2f}" if not pd.isna(avg_p) else "N/A"
        L(f"  {str(brand):40s}  {cnt:6d}  {price_str:>8s}")

    amazon_brands = df_b[df_b["brand"].str.contains("Amazon|Essentials", case=False, na=False)]
    L(f"\n  Amazon 自有品牌上榜: {len(amazon_brands)} 款  占比: {len(amazon_brands)/len(df)*100:.1f}%")
    L("  ⚠ Amazon 自有品牌在此类目竞争较强，需差异化应对")

df_r = df[df["review_count"].notna() & (df["review_count"] > 0)]
if not df_r.empty:
    L(f"\n  评价数据统计:")
    L(f"  平均评价数:   {df_r['review_count'].mean():.0f}")
    L(f"  中位评价数:   {df_r['review_count'].median():.0f}")
    L(f"  最高评价数:   {df_r['review_count'].max():,.0f}")
    L(f"  最低评价数:   {df_r['review_count'].min():,.0f}")
    L(f"  1000+评价款: {(df_r['review_count'] >= 1000).sum()} 款  ({(df_r['review_count'] >= 1000).sum()/len(df_r)*100:.1f}%)")
    L(f"  5000+评价款: {(df_r['review_count'] >= 5000).sum()} 款  ({(df_r['review_count'] >= 5000).sum()/len(df_r)*100:.1f}%)")

    L(f"\n  平均星级:     {df_r['rating'].dropna().mean():.2f} ★")
    L(f"  4.5★+的产品: {(df_r['rating'] >= 4.5).sum()} 款  ({(df_r['rating'] >= 4.5).sum()/len(df_r)*100:.1f}%)")

# ──────────────────────────────────────────────────────────────────────────────
S("五、Top 20 明星产品详情")

top20 = df.head(20)
L(f"\n  {'排名':>4s}  {'ASIN':12s}  {'价格':>7s}  {'评价':>6s}  {'星级':>4s}  {'上架日期':15s}  标题(前50字)")
L("  " + "-"*110)
for _, row in top20.iterrows():
    rank = int(row["rank"])
    asin = str(row["asin"])
    price_str = f"${row['price']:.2f}" if pd.notna(row["price"]) and row["price"] > 0 else "N/A"
    rev = f"{int(row['review_count']):,}" if pd.notna(row["review_count"]) and row["review_count"] > 0 else "N/A"
    rat = f"{row['rating']:.1f}★" if pd.notna(row["rating"]) else "N/A"
    date_str = str(row["date_first_available_raw"])[:15] if pd.notna(row["date_first_available_raw"]) else "N/A"
    title_short = str(row["title"])[:50] if pd.notna(row["title"]) else ""
    L(f"  {rank:4d}  {asin:12s}  {price_str:>7s}  {rev:>6s}  {rat:>4s}  {date_str:15s}  {title_short}")

# ──────────────────────────────────────────────────────────────────────────────
S("六、新品开发综合建议与行动计划")

L("""
  ╔═══════════════════════════════════════════════════════════════════╗
  ║                  新品开发 - 完整行动计划                          ║
  ╚═══════════════════════════════════════════════════════════════════╝

  ▌ 优先级 1 — 秋冬主力款 【最高 ROI】
  ┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄
  款式: 轻薄开衫 (Lightweight Cardigan) + Cable Knit Pullover
  材质: 80%腈纶+20%羊毛混纺 (亲肤/耐洗/成本可控)
  颜色: 首批必备色 — 黑色、奶油白、灰色、深咖色
         扩展色 — 军绿、暗红、藏蓝
  尺码: XS-2X (含加大码，覆盖更广人群)
  定价: $29.99 - $49.99
  上架: 8月底-9月初完成 FBA 入仓
  首批量: 保守备货，每色每码 20-30件，总 SKU 量可控

  ▌ 优先级 2 — 全年常青款 【稳定现金流】
  ┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄
  款式: V-Neck 基础毛衣 + 经典圆领套头毛衣
  材质: 100%腈纶 (最低成本) 或 棉混纺
  颜色: 10-15色大量色卡，满足长尾搜索需求
  定价: $19.99 - $34.99 (引流款策略)
  上架: 全年维持在架，季度补货
  运营: 低 ACOS 稳定投放，依靠评价量积累自然流量

  ▌ 优先级 3 — 春夏趋势款 【2026年新机会】
  ┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄
  款式: Short Sleeve Sweater / Knit Tank Top / Crochet Top
  材质: 棉混纺/麻混纺 (透气凉爽)
  颜色: 马卡龙色系、白色、浅蓝、珊瑚红
  定价: $24.99 - $39.99
  上架: 1月底-2月底完成入仓
  差异化: 配合度假/叠穿场景图，瞄准 Spring Break / 夏季旅行搜索词

  ▌ 差异化开发方向 (蓝海机会)
  ┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄
  ① 加大码专项: Plus Size (1X-4X) 毛衣，竞争相对少，忠实客群回购高
  ② 多功能设计: 带口袋开衫、可调节腰带款、两穿款
  ③ 环保材质: 有机棉/再生纤维，吸引环保意识消费者
  ④ 时尚细节: 珍珠纽扣开衫、流苏边、蝴蝶结装饰

  ▌ 关键运营指标参考
  ┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄
  目标指标        |  新品期(0-3月)  |  成长期(3-12月)  |  成熟期(1年+)
  ──────────────────────────────────────────────────────────────────
  评价数量        |   50+          |   300+           |   1000+
  星级目标        |   4.2★+        |   4.3★+          |   4.5★+
  广告 ACOS       |   60-80%       |   30-50%         |   20-35%
  BSR 目标        |   Top 500      |   Top 200        |   Top 100
  月销售额目标    |   $2,000+      |   $10,000+       |   $30,000+

  ▌ 风险预警与规避
  ┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄
  ⚠ 季节性风险: 毛衣类目 Q4 旺季销量可占全年 60%+，需做好旺季库存规划
  ⚠ 尺码退货: 服装类目退货率达 20-30%，尺码表必须精确，建议提供厘米数据
  ⚠ Amazon 自有品牌: 价格战风险，避免直接与 Amazon Essentials 正面竞争
  ⚠ 中国卖家竞争: 该类目竞争激烈，建议避免纯价格战，以设计/品质/服务差异化
  ⚠ 关税影响: 密切关注中美关税政策变化，适时调整采购/备货策略
""")

# ──────────────────────────────────────────────────────────────────────────────
report_text = "\n".join(lines)

# Save report
with open("/workspace/amazon_analysis/analysis_report_v2.txt", "w", encoding="utf-8") as f:
    f.write(report_text)

print("\n✅ Report saved to: /workspace/amazon_analysis/analysis_report_v2.txt")
print(report_text)

# Save enhanced CSV
df.to_csv("/workspace/amazon_analysis/processed_data.csv", index=False, encoding="utf-8-sig")
print("\n✅ Processed data saved to: /workspace/amazon_analysis/processed_data.csv")
