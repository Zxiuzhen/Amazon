#!/usr/bin/env python3
"""
Amazon Women's T-Shirts Best Sellers Analysis
Scrapes top products and generates new product development recommendations.
URL: https://www.amazon.com/Best-Sellers-Clothing-Shoes-Jewelry-Womens-T-Shirts/zgbs/fashion/1044544/
"""

import time
import random
import json
import re
import os
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
import pandas as pd

CATEGORY_URL = "https://www.amazon.com/Best-Sellers-Clothing-Shoes-Jewelry-Womens-T-Shirts/zgbs/fashion/1044544/"
OUTPUT_DIR   = "/workspace/tshirt_analysis"

# ─── Browser ──────────────────────────────────────────────────────────────────

def build_driver():
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    options.add_argument(
        "user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    )
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    driver.execute_script(
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    )
    return driver


def human_delay(lo=1.5, hi=3.5):
    time.sleep(random.uniform(lo, hi))


# ─── BSR List Scrape ──────────────────────────────────────────────────────────

def scrape_bsr_list(driver):
    products = []
    seen = set()

    for pg in range(1, 3):
        url = CATEGORY_URL if pg == 1 else f"{CATEGORY_URL}?pg={pg}"
        print(f"  [BSR page {pg}] {url}")
        driver.get(url)
        human_delay(3, 6)

        try:
            WebDriverWait(driver, 20).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, ".zg-item-immersion, .p13n-sc-uncoverable-faceout")
                )
            )
        except Exception:
            print("  ⚠ Grid wait timeout, proceeding anyway …")

        # Collect all product links
        anchors = driver.find_elements(
            By.CSS_SELECTOR,
            ".zg-item-immersion a, .p13n-gridRow a, [data-asin] a"
        )
        for a in anchors:
            href = a.get_attribute("href") or ""
            if "/dp/" not in href:
                continue
            m = re.search(r"/dp/([A-Z0-9]{10})", href)
            if not m:
                continue
            asin = m.group(1)
            if asin in seen:
                continue
            seen.add(asin)
            products.append({
                "rank": len(products) + 1,
                "asin": asin,
                "url": f"https://www.amazon.com/dp/{asin}",
            })
            if len(products) >= 100:
                break

        print(f"  → {len(products)} products collected so far")
        if len(products) >= 100:
            break
        human_delay(2, 4)

    # JSON fallback if list is short
    if len(products) < 40:
        print("  Trying JSON source fallback …")
        src = driver.page_source
        for asin in re.findall(r'"asin"\s*:\s*"([A-Z0-9]{10})"', src):
            if asin not in seen:
                seen.add(asin)
                products.append({
                    "rank": len(products) + 1,
                    "asin": asin,
                    "url": f"https://www.amazon.com/dp/{asin}",
                })
            if len(products) >= 100:
                break

    print(f"\n  ✅ Total BSR links collected: {len(products)}\n")
    return products[:100]


# ─── Product Detail Scrape ────────────────────────────────────────────────────

def _safe_text(driver, css=None, xpath=None, element_id=None):
    """Try multiple selectors, return first non-empty text."""
    targets = []
    if element_id:
        targets.append(("id", element_id))
    if css:
        targets.append(("css", css))
    if xpath:
        targets.append(("xpath", xpath))
    for kind, sel in targets:
        try:
            if kind == "id":
                el = driver.find_element(By.ID, sel)
            elif kind == "css":
                el = driver.find_element(By.CSS_SELECTOR, sel)
            else:
                el = driver.find_element(By.XPATH, sel)
            txt = (el.text or el.get_attribute("innerHTML") or "").strip()
            txt = re.sub(r"<[^>]+>", "", txt).strip()
            if txt:
                return txt
        except Exception:
            pass
    return ""


def parse_price(text):
    text = re.sub(r"<[^>]+>", "", text)
    prices = re.findall(r"\$?([\d,]+\.?\d*)", text.replace(",", ""))
    vals = [float(p) for p in prices if p and float(p) > 0]
    if not vals:
        return None
    return round(sum(vals) / len(vals), 2)


def parse_reviews(text):
    m = re.search(r"([\d,]+)", text.replace(",", ""))
    return int(m.group(1)) if m else 0


def parse_rating(text):
    m = re.search(r"([\d.]+)\s*out\s*of\s*5", text)
    if m:
        return float(m.group(1))
    m = re.search(r"^([\d.]+)", text.strip())
    return float(m.group(1)) if m else None


def extract_date(driver):
    # XPath approach
    for xpath in [
        "//th[contains(text(),'Date First Available')]/following-sibling::td",
        "//span[contains(text(),'Date First Available')]/following-sibling::span",
    ]:
        try:
            els = driver.find_elements(By.XPATH, xpath)
            for el in els:
                t = el.text.strip()
                if t:
                    return t
        except Exception:
            pass

    # Page source regex
    src = driver.page_source
    for pat in [
        r"Date First Available[^<]*<[^>]+>\s*([^<]+)<",
        r"Date First Available\s*[:\-]\s*([A-Za-z]+ \d+,\s*\d{4})",
        r"Date First Available.*?([A-Za-z]+ \d+, \d{4})",
    ]:
        m = re.search(pat, src, re.DOTALL)
        if m:
            return m.group(1).strip()
    return None


def classify_tshirt_style(title):
    """Classify T-shirt style based on title keywords."""
    if not isinstance(title, str):
        return "Other T-Shirt"
    t = title.lower()

    # Graphic / Print first (strong signal)
    if any(k in t for k in ["graphic", "print", "printed", "logo", "letter", "text", "slogan", "vintage", "band"]):
        return "Graphic/Print Tee"

    # Neckline variants
    if any(k in t for k in ["v-neck", "v neck", "vneck"]):
        if any(k in t for k in ["short sleeve", "t-shirt", "tshirt", "tee"]):
            return "V-Neck T-Shirt"
    if any(k in t for k in ["scoop neck", "u neck"]):
        return "Scoop Neck Tee"
    if any(k in t for k in ["mock neck", "turtleneck"]):
        return "Mock Neck Tee"
    if any(k in t for k in ["henley"]):
        return "Henley T-Shirt"

    # Sleeve variants
    if any(k in t for k in ["long sleeve", "long-sleeve"]):
        return "Long Sleeve T-Shirt"
    if any(k in t for k in ["3/4 sleeve", "3/4sleeve", "three quarter"]):
        return "3/4 Sleeve T-Shirt"
    if any(k in t for k in ["tank", "sleeveless", "cami", "muscle"]):
        return "Tank Top / Sleeveless"
    if any(k in t for k in ["crop", "cropped"]):
        return "Crop Top"

    # Fit variants
    if any(k in t for k in ["oversized", "boyfriend", "boxy", "loose", "relaxed"]):
        return "Oversized / Relaxed Fit"
    if any(k in t for k in ["fitted", "slim", "tight", "form"]):
        return "Fitted / Slim Tee"

    # Fabric special
    if any(k in t for k in ["linen", "bamboo"]):
        return "Natural Fabric Tee"
    if any(k in t for k in ["thermal", "waffle"]):
        return "Thermal / Waffle Knit"
    if any(k in t for k in ["tie dye", "tie-dye"]):
        return "Tie-Dye Tee"
    if any(k in t for k in ["polo"]):
        return "Polo Shirt"

    # Basic / Classic
    if any(k in t for k in ["basic", "essential", "classic", "everyday", "plain"]):
        return "Basic / Essential Tee"

    if any(k in t for k in ["t-shirt", "tshirt", "tee shirt", " tee "]):
        return "Basic / Essential Tee"

    return "Other T-Shirt"


def classify_fit(title):
    if not isinstance(title, str):
        return "Unknown"
    t = title.lower()
    if any(k in t for k in ["oversized", "boyfriend", "boxy", "loose", "relaxed", "flowy"]):
        return "Loose/Oversized"
    if any(k in t for k in ["fitted", "slim", "tight", "form-fitting"]):
        return "Fitted/Slim"
    if any(k in t for k in ["plus size", "plus-size", "1x", "2x", "3x", "4x", "curvy"]):
        return "Plus Size"
    return "Regular"


def classify_sleeve(title):
    if not isinstance(title, str):
        return "Short Sleeve"
    t = title.lower()
    if any(k in t for k in ["long sleeve", "long-sleeve"]):
        return "Long Sleeve"
    if any(k in t for k in ["3/4", "three quarter"]):
        return "3/4 Sleeve"
    if any(k in t for k in ["sleeveless", "tank", "muscle", "cami"]):
        return "Sleeveless"
    if any(k in t for k in ["crop"]):
        return "Crop"
    return "Short Sleeve"


def scrape_product_detail(driver, product):
    url = product["url"]
    try:
        driver.get(url)
        human_delay(2, 4)

        # Title
        title = _safe_text(driver, element_id="productTitle")

        # Price — try many selectors
        price = None
        price_text = ""
        for css in [
            ".priceToPay .a-offscreen",
            "#priceblock_ourprice",
            "#priceblock_dealprice",
            ".a-price .a-offscreen",
            "#apex_offerDisplay_desktop .a-price .a-offscreen",
            "#price_inside_buybox",
            "#corePrice_feature_div .a-offscreen",
            ".a-color-price",
        ]:
            try:
                el = driver.find_element(By.CSS_SELECTOR, css)
                txt = (el.get_attribute("innerHTML") or el.text or "").strip()
                txt = re.sub(r"<[^>]+>", "", txt).strip()
                if txt and "$" in txt:
                    price_text = txt
                    price = parse_price(txt)
                    break
            except Exception:
                pass

        # Also try from page source if price still None
        if price is None:
            src = driver.page_source
            m = re.search(r'"priceAmount"\s*:\s*([\d.]+)', src)
            if m:
                price = float(m.group(1))

        # Reviews
        review_count = 0
        try:
            el = driver.find_element(By.ID, "acrCustomerReviewText")
            review_count = parse_reviews(el.text)
        except Exception:
            try:
                el = driver.find_element(By.CSS_SELECTOR, "[data-hook='total-review-count']")
                review_count = parse_reviews(el.text)
            except Exception:
                pass

        # Rating
        rating = None
        try:
            el = driver.find_element(By.CSS_SELECTOR, "#acrPopover")
            rating = parse_rating(el.get_attribute("title") or el.text or "")
        except Exception:
            try:
                el = driver.find_element(By.CSS_SELECTOR, "[data-hook='rating-out-of-text']")
                rating = parse_rating(el.text)
            except Exception:
                pass

        # Brand
        brand = ""
        try:
            el = driver.find_element(By.ID, "bylineInfo")
            brand = el.text.strip()
            brand = re.sub(r"^(Brand:|Visit the)\s*", "", brand, flags=re.IGNORECASE)
            brand = brand.split(" Store")[0].strip()
        except Exception:
            pass

        date_available = extract_date(driver)

        # Color variant count (thumbnail images)
        color_count = 0
        try:
            imgs = driver.find_elements(
                By.CSS_SELECTOR,
                "#altImages li.imageThumbnail, #variation_color_name li, "
                "#imageBlock_feature_div .a-button-thumbnail"
            )
            color_count = len(imgs)
        except Exception:
            pass

        style   = classify_tshirt_style(title)
        fit     = classify_fit(title)
        sleeve  = classify_sleeve(title)

        product.update({
            "title": title,
            "brand": brand,
            "price": price,
            "price_text": price_text,
            "rating": rating,
            "review_count": review_count,
            "date_first_available_raw": date_available,
            "style_category": style,
            "fit_type": fit,
            "sleeve_type": sleeve,
            "color_variant_count": color_count,
        })

    except Exception as e:
        print(f"    ⚠ Error scraping {url}: {e}")
        product.update({
            "title": "", "brand": "", "price": None, "price_text": "",
            "rating": None, "review_count": 0,
            "date_first_available_raw": None,
            "style_category": "Unknown", "fit_type": "Unknown",
            "sleeve_type": "Unknown", "color_variant_count": 0,
        })
    return product


# ─── Analysis & Report ────────────────────────────────────────────────────────

def try_parse_date(v):
    if not v or not isinstance(v, str):
        return None
    v = v.strip()
    for fmt in ["%B %d, %Y", "%b %d, %Y", "%Y-%m-%d", "%m/%d/%Y"]:
        try:
            return datetime.strptime(v, fmt)
        except ValueError:
            pass
    return None


def bar_chart(pct, scale=2):
    return "█" * max(1, int(pct / scale)) if pct > 0 else ""


def build_report(df):
    lines = []

    def S(title):
        lines.append("\n" + "═" * 72)
        lines.append(f"  {title}")
        lines.append("═" * 72)

    def L(t=""):
        lines.append(t)

    now = datetime.now().strftime("%Y年%m月%d日 %H:%M")
    lines.append("╔══════════════════════════════════════════════════════════════════════╗")
    lines.append("║     Amazon 美国站 女士T恤类目 Top BSR 销售数据分析报告              ║")
    lines.append("╚══════════════════════════════════════════════════════════════════════╝")
    L(f"  数据采集时间: {now}")
    L(f"  数据来源: {CATEGORY_URL}")
    L(f"  有效数据条数: {len(df)} 条")

    # ── 1. Price ──────────────────────────────────────────────────────────────
    S("一、产品价格分布分析")
    df_p = df[df["price"].notna() & (df["price"] > 0)].copy()
    L(f"\n  有效价格数据: {len(df_p)} / {len(df)} 条")
    if not df_p.empty:
        L(f"  最低价:          ${df_p['price'].min():.2f}")
        L(f"  最高价:          ${df_p['price'].max():.2f}")
        L(f"  平均价:          ${df_p['price'].mean():.2f}")
        L(f"  中位价:          ${df_p['price'].median():.2f}")
        L(f"  25th 百分位:     ${df_p['price'].quantile(0.25):.2f}")
        L(f"  75th 百分位:     ${df_p['price'].quantile(0.75):.2f}")

        bins   = [0, 10, 15, 20, 25, 30, 40, 50, 75, 9999]
        labels = ["≤$10", "$10-15", "$15-20", "$20-25", "$25-30",
                  "$30-40", "$40-50", "$50-75", ">$75"]
        df_p["band"] = pd.cut(df_p["price"], bins=bins, labels=labels, right=True)
        dist = df_p["band"].value_counts().sort_index()

        L("\n  价格区间分布:")
        L(f"  {'区间':12s}  {'数量':>4s}  {'占比':>6s}  图示")
        L("  " + "-" * 60)
        for band, cnt in dist.items():
            pct = cnt / len(df_p) * 100
            L(f"  {str(band):12s}  {cnt:4d}  {pct:5.1f}%  {bar_chart(pct, 1.5)}")

        top20_p = df_p[df_p["rank"] <= 20]
        if not top20_p.empty:
            L(f"\n  Top 20 均价: ${top20_p['price'].mean():.2f}  中位价: ${top20_p['price'].median():.2f}")

        dominant = dist.idxmax()
        L(f"\n  ▶ 主流价格带: {dominant}")

        L("""
  【价格建议】
  ① 主力定价: T恤属于高频/低单价类目，大部分消费者预算在 $15-30。
              建议新品首选 $16.99–$24.99 区间，兼顾流量与毛利。
  ② 引流款:   ≤$15 可用于抢占 Best Seller Badge，适合基础素色款。
  ③ 溢价款:   图案/设计款可定价 $25-35，依靠设计差异化支撑。
  ④ 定价技巧: 采用 $X9.99 心理定价；上市初期配合 10-15% Coupon 冲排名。""")

    # ── 2. Style ──────────────────────────────────────────────────────────────
    S("二、款式类型分布分析")
    style_dist = df["style_category"].value_counts()
    L(f"\n  款式分布 (共 {len(df)} 款):")
    L(f"  {'款式':35s}  {'数量':>4s}  {'占比':>6s}  图示")
    L("  " + "-" * 72)
    for style, cnt in style_dist.items():
        pct = cnt / len(df) * 100
        L(f"  {str(style):35s}  {cnt:4d}  {pct:5.1f}%  {bar_chart(pct, 1.5)}")

    # Style × Price
    L("\n  各款式平均价格 (≥2款):")
    sp = df.groupby("style_category")["price"].agg(["mean", "count"]).dropna()
    sp = sp[sp["count"] >= 2].sort_values("mean", ascending=False)
    L(f"  {'款式':35s}  {'均价':>8s}  {'数量':>4s}")
    L("  " + "-" * 55)
    for style, row in sp.iterrows():
        L(f"  {str(style):35s}  ${row['mean']:7.2f}  {int(row['count']):4d}")

    # Sleeve distribution
    L("\n  袖型分布:")
    sleeve_dist = df["sleeve_type"].value_counts()
    for sl, cnt in sleeve_dist.items():
        pct = cnt / len(df) * 100
        L(f"  {str(sl):20s}: {cnt:3d} 款  {pct:5.1f}%  {bar_chart(pct, 2)}")

    # Fit distribution
    L("\n  版型分布:")
    fit_dist = df["fit_type"].value_counts()
    for fit, cnt in fit_dist.items():
        pct = cnt / len(df) * 100
        L(f"  {str(fit):20s}: {cnt:3d} 款  {pct:5.1f}%  {bar_chart(pct, 2)}")

    top3 = style_dist.head(3).index.tolist()
    L(f"""
  【款式建议】
  ① 主力款 — {top3[0] if len(top3) > 0 else 'Basic Tee'}: 榜单占比最高，需重点布局，多色系覆盖。
  ② 次主力 — {top3[1] if len(top3) > 1 else 'Graphic Tee'}: 有稳定需求，可与主力款共用工厂资源。
  ③ 趋势款 — {top3[2] if len(top3) > 2 else 'V-Neck'}: 建议差异化切入，主打某一细分场景。
  
  重点款式开发方向:
  • Graphic/Print Tee:  图案款是T恤类目最大流量池，建议每季上新5-10个图案
  • Basic/Essential Tee: 基础素色款，建议12+色系，以量取胜，稳定复购
  • V-Neck T-Shirt:     百搭基础款，用于补充SKU矩阵
  • Oversized/Relaxed:  当下最强趋势，适合年轻客群，可配合社媒内容营销
  • Crop Top:           年轻化/夏季款，结合 TikTok 热点快速上新""")

    # ── 3. Date / Timing ──────────────────────────────────────────────────────
    S("三、上新时间节奏分析")
    df["date_parsed"] = df["date_first_available_raw"].apply(try_parse_date)
    df_d = df[df["date_parsed"].notna()].copy()
    L(f"\n  有日期数据: {len(df_d)} / {len(df)} 条")

    if not df_d.empty:
        df_d["year"]  = df_d["date_parsed"].dt.year
        df_d["month"] = df_d["date_parsed"].dt.month

        L("\n  按年份分布:")
        year_dist = df_d["year"].value_counts().sort_index()
        for yr, cnt in year_dist.items():
            pct = cnt / len(df_d) * 100
            L(f"  {int(yr)}: {cnt:3d} 款  {pct:5.1f}%  {bar_chart(pct, 2)}")

        recent = df_d[df_d["year"] >= 2023]
        L(f"\n  2023年后上架新品: {len(recent)}/{len(df_d)} = {len(recent)/len(df_d)*100:.1f}%")
        trend = "该类目新品上榜能力强，产品迭代速度快" if len(recent)/len(df_d) > 0.5 \
                else "老品积累优势较大，新品需要较长时间突破"
        L(f"  → {trend}")

        months = {1:"Jan",2:"Feb",3:"Mar",4:"Apr",5:"May",6:"Jun",
                  7:"Jul",8:"Aug",9:"Sep",10:"Oct",11:"Nov",12:"Dec"}
        month_dist = df_d.groupby("month").size().sort_index()
        L("\n  按月份分布 (上新旺季识别):")
        L(f"  {'月份':5s}  {'数量':>4s}  {'占比':>6s}  图示")
        L("  " + "-" * 55)
        for m in range(1, 13):
            cnt = month_dist.get(m, 0)
            pct = cnt / len(df_d) * 100 if len(df_d) > 0 else 0
            L(f"  {months[m]:5s}  {cnt:4d}  {pct:5.1f}%  {bar_chart(pct, 1.5)}")

        peak_3 = month_dist.nlargest(3).index.tolist()
        low_3  = month_dist.nsmallest(3).index.tolist()
        L(f"\n  上新高峰月份 (TOP3): {', '.join(months[m] for m in sorted(peak_3))}")
        L(f"  上新低谷月份 (BTM3): {', '.join(months[m] for m in sorted(low_3))}")

    L("""
  【上新节奏建议】

  ━━━ 春夏旺季主推 (T恤核心销售季) ━━━
  时间节点       | 行动计划
  ─────────────────────────────────────────────────────
  12月-1月       | 确定春夏图案/款式/配色方案，下单打样
  2月            | 确认批量订单，安排生产
  3月初          | 生产完成，开始头程发货
  3月底-4月初    | 完成 FBA 入仓 ← 春夏旺季入仓截止线
  4月            | 新品上架，开始广告+Vine申请
  5月-6月        | Memorial Day/夏季促销，冲 BSR 排名
  7月            | Prime Day 核心爆发期，提前备足库存
  8月            | Back to School 促销节点
  ─────────────────────────────────────────────────────

  ━━━ 秋冬补充期 ━━━
  8月底-9月初    | 上架 Long Sleeve / 厚款T恤，布局秋季
  10月           | 万圣节主题图案款上架
  11月           | 感恩节/圣诞主题款，Black Friday 促销

  ━━━ 常青款全年维护 ━━━
  全年           | 基础素色T恤多色系维持库存，持续广告投放
  每季度         | 补充 3-5 个新图案/新颜色，保持产品新鲜度
  节日前8周      | 上架节日主题图案款（情人节/圣诞/万圣节等）""")

    # ── 4. Brand & Reviews ────────────────────────────────────────────────────
    S("四、品牌竞争与评价分析")
    df_b = df[df["brand"].notna() & (df["brand"].str.len() > 0)]
    if not df_b.empty:
        brand_cnt = df_b["brand"].value_counts()
        L("\n  榜单品牌 Top 15:")
        L(f"  {'品牌':40s}  {'上榜款数':>6s}  {'均价':>8s}")
        L("  " + "-" * 62)
        for brand in brand_cnt.head(15).index:
            cnt = brand_cnt[brand]
            avg_p = df_b[df_b["brand"] == brand]["price"].mean()
            ps = f"${avg_p:.2f}" if not pd.isna(avg_p) else "N/A"
            L(f"  {str(brand):40s}  {cnt:6d}  {ps:>8s}")

        amz = df_b[df_b["brand"].str.contains("Amazon|Essentials", case=False, na=False)]
        L(f"\n  Amazon 自有品牌上榜: {len(amz)} 款  占比: {len(amz)/len(df)*100:.1f}%")

    df_r = df[df["review_count"].notna() & (df["review_count"] > 0)]
    if not df_r.empty:
        L(f"\n  评价数据统计:")
        L(f"  平均评价数:   {df_r['review_count'].mean():.0f}")
        L(f"  中位评价数:   {df_r['review_count'].median():.0f}")
        L(f"  最高评价数:   {df_r['review_count'].max():,.0f}")
        L(f"  1000+评价款: {(df_r['review_count'] >= 1000).sum()} 款  ({(df_r['review_count'] >= 1000).sum()/len(df_r)*100:.1f}%)")
        L(f"  5000+评价款: {(df_r['review_count'] >= 5000).sum()} 款  ({(df_r['review_count'] >= 5000).sum()/len(df_r)*100:.1f}%)")
        L(f"  平均星级:     {df_r['rating'].dropna().mean():.2f} ★")
        L(f"  4.5★+产品:   {(df_r['rating'] >= 4.5).sum()} 款  ({(df_r['rating'] >= 4.5).sum()/len(df_r)*100:.1f}%)")

        L("""
  【评价建议】
  • T恤类目竞争极激烈，中位评价数高，新品冷启动难度大
  • 建议一开始就申请 Amazon Vine（最多30个评价）快速起步
  • 同时配合小红书/TikTok 达人合作，引入站外流量辅助爆单
  • 评价维护: 严控退货率(<8%)，主动跟进差评，防止星级下滑""")

    # ── 5. Top 20 Detail ──────────────────────────────────────────────────────
    S("五、Top 20 明星产品详情")
    top20 = df.head(20)
    L(f"\n  {'排名':>4s}  {'ASIN':12s}  {'价格':>7s}  {'评价':>7s}  {'星级':>4s}  {'上架日期':18s}  标题(前48字)")
    L("  " + "-" * 115)
    for _, row in top20.iterrows():
        rank = int(row["rank"])
        asin = str(row["asin"])
        ps   = f"${row['price']:.2f}" if pd.notna(row["price"]) and row["price"] > 0 else "N/A"
        rev  = f"{int(row['review_count']):,}" if pd.notna(row["review_count"]) and row["review_count"] > 0 else "N/A"
        rat  = f"{row['rating']:.1f}★"         if pd.notna(row["rating"]) else "N/A"
        dt   = str(row["date_first_available_raw"])[:18] if pd.notna(row["date_first_available_raw"]) else "N/A"
        ti   = str(row["title"])[:48]           if pd.notna(row["title"]) else ""
        L(f"  {rank:4d}  {asin:12s}  {ps:>7s}  {rev:>7s}  {rat:>4s}  {dt:18s}  {ti}")

    # ── 6. Recommendations ───────────────────────────────────────────────────
    S("六、新品开发综合建议与行动计划")
    L("""
  ╔═══════════════════════════════════════════════════════════════════╗
  ║               女士T恤新品开发 - 完整行动计划                      ║
  ╚═══════════════════════════════════════════════════════════════════╝

  ▌ 优先级 1 — 图案款 Graphic Tee 【最高流量池】
  ┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄
  款式: 圆领短袖图案T恤（正面印花 / 全幅印花）
  面料: 100%棉 或 棉/聚酯混纺（柔软悬垂感好）
  颜色底色: 黑色、白色、灰色、藏蓝（最万能底色）
  图案方向:
    → Vintage/复古风（摇滚/80s/90s 风格复古图案）
    → Inspirational/励志语录（英文 Slogan）
    → Floral/花卉（春夏热卖）
    → Funny/幽默（节日礼品场景需求大）
    → Nature/动物（猫狗/大自然题材常青）
  尺码: XS-3XL（覆盖加大码）
  定价: $16.99–$24.99
  上架: 提前8周上架（节日主题款）；常规图案全年滚动上新
  SKU策略: 1个图案 × 5个颜色 × 6个码 = 30 SKU/款

  ▌ 优先级 2 — 基础素色款 Basic Essential Tee 【稳定现金流】
  ┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄
  款式: 圆领短袖 + V领短袖 各一款，12-15色色系
  面料: 棉/Modal混纺（提升质感，降低皱褶）
  颜色: 黑、白、灰、米白、藏蓝、军绿、粉、红、橙、薰衣草紫…
  定价: $13.99–$19.99（引流策略）
  运营: 多变体合并，积累单 ASIN 评价量，冲 Best Seller Badge
  差异化: 主打"超柔软"/"不透明"/"完美贴合"等具体面料卖点

  ▌ 优先级 3 — 当季趋势款 Oversized / Crop 【年轻化增量】
  ┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄
  款式 A: Oversized Boxy Tee（宽松男友风）
    颜色: 大地色系为主（卡其/沙漠棕/鼠尾草绿）
    定价: $18.99–$26.99
    差异化: 加重磅面料(200g+)，洗水做旧感
  款式 B: Crop Top / Short Tee
    颜色: 白、黑、粉、薰衣草
    定价: $15.99–$22.99
    营销: TikTok "outfit of the day" 内容联动

  ▌ 优先级 4 — 节日限定款 Holiday / Seasonal Tee 【爆款机会】
  ┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄
  Valentine's Day (2月14日)  → 提前 8 周上架 (12月中旬)
  St. Patrick's Day (3月17日) → 提前 6 周上架
  Mother's Day (5月第2周)    → 提前 8 周上架 (3月底)
  4th of July (7月4日)      → 提前 8 周上架 (5月初)
  Halloween (10月31日)      → 提前 8 周上架 (9月初)
  Christmas/Xmas (12月25日) → 提前 10 周上架 (10月中旬)
  注: 节日款不可用长尾词打广告，需卡准节日词+提前排名

  ▌ 蓝海差异化方向
  ┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄
  ① 加大码专项: 2X-5X，图案款竞争少，客单价可高 20%
  ② 妈妈款/家庭套装: Mom/Mama tee，家庭匹配 T 恤礼品场景
  ③ 定制/个性化: 配合 Amazon Custom，用户可定制名字/图案
  ④ 环保/可持续: Organic Cotton 认证款，吸引环保消费者
  ⑤ 运动/功能款: Moisture-wicking 速干 T 恤，运动场景

  ▌ 关键运营指标参考
  ┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄
  目标指标        |  新品期(0-3月)  |  成长期(3-12月)  |  成熟期(1年+)
  ──────────────────────────────────────────────────────────────────
  评价数量        |   30+          |   200+           |   500+
  星级目标        |   4.2★+        |   4.3★+          |   4.5★+
  广告 ACOS       |   60-80%       |   30-50%         |   20-35%
  退货率控制      |   <10%         |   <8%            |   <6%
  月销售额目标    |   $1,500+      |   $8,000+        |   $25,000+

  ▌ 竞争风险与关键注意事项
  ┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄
  ⚠ T恤是Amazon竞争最激烈的服装类目之一，价格敏感度极高
  ⚠ 图案版权: 图案设计需原创或购买版权，避免侵权下架风险
  ⚠ Amazon 自有品牌压制: Essentials 在基础款占主导，避免正面竞争
  ⚠ 尺码/色差退货: 严格控制色差，尺码表提供英寸+厘米双标准
  ⚠ 印花质量: 低质量印花会导致洗后褪色差评，需严格质检
  ⚠ 库存管理: T恤 SKU 数量多，库存管理复杂，建议用 FBA 精细化运营
""")

    return "\n".join(lines)


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    print("=" * 60)
    print("Amazon 女士T恤 Best Sellers 数据采集 & 分析")
    print("=" * 60)

    driver = build_driver()
    try:
        print("\n[Step 1] 采集 BSR 榜单链接 …")
        products = scrape_bsr_list(driver)

        print(f"\n[Step 2] 采集产品详情 (共 {len(products)} 条) …")
        for i, p in enumerate(products):
            print(f"  [{i+1:3d}/{len(products)}] ASIN: {p['asin']} …", end=" ", flush=True)
            scrape_product_detail(driver, p)
            ps    = f"${p['price']:.2f}" if p.get("price") else "N/A"
            rev   = f"{int(p.get('review_count', 0)):,}"
            rat   = f"⭐{p.get('rating', '')}"
            style = p.get("style_category", "")[:25]
            title = str(p.get("title", ""))[:45]
            print(f"{ps}  {rat}  {rev}评  [{style}]  {title}")
            human_delay(1.5, 3.5)

        # Save raw CSV
        df = pd.DataFrame(products)
        raw_csv = os.path.join(OUTPUT_DIR, "raw_data.csv")
        df.to_csv(raw_csv, index=False, encoding="utf-8-sig")
        print(f"\n  ✅ 原始数据: {raw_csv}")

        # Save JSON
        json_path = os.path.join(OUTPUT_DIR, "products.json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(products, f, ensure_ascii=False, indent=2, default=str)
        print(f"  ✅ JSON 数据: {json_path}")

        print("\n[Step 3] 生成分析报告 …")
        report = build_report(df)

        report_path = os.path.join(OUTPUT_DIR, "analysis_report.txt")
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(report)
        print(f"  ✅ 分析报告: {report_path}")

        # Save processed CSV
        df.to_csv(os.path.join(OUTPUT_DIR, "processed_data.csv"), index=False, encoding="utf-8-sig")

        print("\n" + "=" * 60)
        print(report)

    finally:
        driver.quit()


if __name__ == "__main__":
    main()
