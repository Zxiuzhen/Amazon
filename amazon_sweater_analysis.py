#!/usr/bin/env python3
"""
Amazon Women's Sweaters Best Sellers Analysis
Scrapes top 100 products and generates new product development recommendations.
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

# ─── Browser Setup ────────────────────────────────────────────────────────────

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
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    return driver


def human_delay(lo=1.5, hi=3.5):
    time.sleep(random.uniform(lo, hi))


# ─── Page 1: Best-Sellers List ─────────────────────────────────────────────

def scrape_bestsellerlist(driver):
    base_url = "https://www.amazon.com/Best-Sellers-Clothing-Shoes-Jewelry-Womens-Sweaters/zgbs/fashion/1044456"
    products = []

    for pg in range(1, 3):          # page 1 and page 2 → 50 items each
        url = base_url if pg == 1 else f"{base_url}?pg={pg}"
        print(f"  Fetching BSR list page {pg}: {url}")
        driver.get(url)
        human_delay(3, 6)

        # wait for product grid
        try:
            WebDriverWait(driver, 20).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, ".zg-item-immersion, .a-section.zg-item"))
            )
        except Exception:
            print("  ⚠ Grid not found, trying anyway …")

        cards = driver.find_elements(By.CSS_SELECTOR,
            ".zg-item-immersion, .p13n-sc-uncoverable-faceout, [data-asin]")

        print(f"  Found {len(cards)} candidate cards")

        # collect from anchor tags that point to product pages
        seen = set()
        anchors = driver.find_elements(By.CSS_SELECTOR, ".zg-item-immersion a, .p13n-gridRow a")
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

            # rank — try nearby rank badge
            rank = len(products) + 1

            products.append({
                "rank": rank,
                "asin": asin,
                "url": f"https://www.amazon.com/dp/{asin}",
            })

            if len(products) >= 100:
                break

        if len(products) >= 100:
            break
        human_delay(2, 4)

    # fallback: grab from JSON embedded in page if list is short
    if len(products) < 40:
        print("  Trying JSON fallback …")
        page_src = driver.page_source
        asins = re.findall(r'"asin"\s*:\s*"([A-Z0-9]{10})"', page_src)
        seen_fallback = {p["asin"] for p in products}
        for asin in asins:
            if asin not in seen_fallback:
                seen_fallback.add(asin)
                products.append({
                    "rank": len(products) + 1,
                    "asin": asin,
                    "url": f"https://www.amazon.com/dp/{asin}",
                })
            if len(products) >= 100:
                break

    print(f"\n  ✅ Collected {len(products)} product links from BSR list\n")
    return products[:100]


# ─── Page 2: Product Detail ─────────────────────────────────────────────────

def parse_price(text):
    """Extract numeric price from a string like '$29.99' or '$12.99–$34.00'."""
    prices = re.findall(r"\$?([\d,]+\.?\d*)", text.replace(",", ""))
    vals = [float(p) for p in prices if p]
    if not vals:
        return None
    return round(sum(vals) / len(vals), 2)   # use midpoint for ranges


def parse_reviews(text):
    m = re.search(r"([\d,]+)", text.replace(",", ""))
    return int(m.group(1)) if m else 0


def parse_rating(text):
    m = re.search(r"([\d.]+)\s*out\s*of\s*5", text)
    if m:
        return float(m.group(1))
    m = re.search(r"([\d.]+)", text)
    return float(m.group(1)) if m else None


def extract_date_first_available(driver):
    """Extract 'Date First Available' from product details table."""
    selectors = [
        "//th[contains(text(),'Date First Available')]/following-sibling::td",
        "//span[contains(text(),'Date First Available')]/following-sibling::span",
        "//li[contains(.,'Date First Available')]",
    ]
    for sel in selectors:
        try:
            els = driver.find_elements(By.XPATH, sel)
            for el in els:
                txt = el.text.strip()
                if txt:
                    return txt
        except Exception:
            pass

    # Try looking in productDetails table text
    try:
        detail_section = driver.find_element(By.ID, "detailBulletsWrapper_feature_div")
        txt = detail_section.text
        m = re.search(r"Date First Available[^\w]*([A-Za-z]+ \d+, \d{4})", txt)
        if m:
            return m.group(1)
    except Exception:
        pass

    try:
        detail_section = driver.find_element(By.ID, "productDetails_techSpec_section_1")
        txt = detail_section.text
        m = re.search(r"Date First Available[^\w]*([A-Za-z]+ \d+, \d{4})", txt)
        if m:
            return m.group(1)
    except Exception:
        pass

    # Search anywhere in page source
    src = driver.page_source
    m = re.search(r"Date First Available[^<]*<[^>]+>([^<]+)<", src)
    if m:
        return m.group(1).strip()
    m = re.search(r"Date First Available\s*:\s*([A-Za-z]+ \d+, \d{4})", src)
    if m:
        return m.group(1).strip()

    return None


def extract_bsr_rank(driver):
    """Extract Best Sellers Rank from product page."""
    try:
        src = driver.page_source
        m = re.search(r"#([\d,]+)\s+in\s+(?:Clothing|Women|Sweater|Fashion)", src)
        if m:
            return m.group(0)
    except Exception:
        pass
    try:
        el = driver.find_element(By.ID, "SalesRank")
        return el.text[:200]
    except Exception:
        pass
    return None


def classify_style(title):
    """Classify sweater style based on title keywords."""
    title_lower = title.lower()
    
    style_map = {
        "Turtleneck / Mock Neck": ["turtleneck", "mock neck", "cowl neck", "funnel neck"],
        "Cardigan": ["cardigan", "open front", "button front", "button-front", "button down"],
        "Pullover / Crew Neck": ["pullover", "crew neck", "crewneck"],
        "V-Neck": ["v-neck", "v neck", "vneck"],
        "Oversized / Chunky": ["oversized", "chunky", "baggy", "loose"],
        "Cable Knit": ["cable knit", "cable-knit"],
        "Crop Sweater": ["crop", "cropped"],
        "Hoodie Sweater": ["hoodie", "hooded", "hood"],
        "Fair Isle / Nordic": ["fair isle", "nordic", "nordic", "pattern", "jacquard"],
        "Ribbed": ["ribbed", "rib-knit", "rib knit"],
        "Wrap Sweater": ["wrap"],
        "Tunic": ["tunic", "longline", "long line"],
    }
    
    for style, keywords in style_map.items():
        if any(kw in title_lower for kw in keywords):
            return style
    return "Other Sweater"


def scrape_product_detail(driver, product):
    """Fetch and parse a single product page."""
    url = product["url"]
    try:
        driver.get(url)
        human_delay(2, 4)

        title = ""
        try:
            title = driver.find_element(By.ID, "productTitle").text.strip()
        except Exception:
            pass

        price = None
        price_text = ""
        for sel in ["#priceblock_ourprice", "#priceblock_dealprice",
                    ".a-price .a-offscreen", "#apex_offerDisplay_desktop .a-price",
                    "#price_inside_buybox", ".priceToPay .a-offscreen",
                    "#corePrice_feature_div .a-price .a-offscreen"]:
            try:
                el = driver.find_element(By.CSS_SELECTOR, sel)
                price_text = el.text or el.get_attribute("innerHTML") or ""
                price_text = re.sub(r"<[^>]+>", "", price_text).strip()
                if price_text:
                    price = parse_price(price_text)
                    break
            except Exception:
                pass

        # review count
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

        # rating
        rating = None
        try:
            el = driver.find_element(By.CSS_SELECTOR, "#acrPopover, [data-hook='rating-out-of-text']")
            rating = parse_rating(el.get_attribute("title") or el.text)
        except Exception:
            pass

        # brand
        brand = ""
        try:
            el = driver.find_element(By.ID, "bylineInfo")
            brand = el.text.strip().replace("Brand: ", "").replace("Visit the ", "").split(" Store")[0]
        except Exception:
            pass

        date_first_available = extract_date_first_available(driver)
        bsr_rank_text = extract_bsr_rank(driver)

        # number of images (color variants proxy)
        color_count = 0
        try:
            imgs = driver.find_elements(By.CSS_SELECTOR, "#altImages li.imageThumbnail, #imageBlock img")
            color_count = len(imgs)
        except Exception:
            pass

        style = classify_style(title)

        product.update({
            "title": title,
            "brand": brand,
            "price": price,
            "price_text": price_text,
            "rating": rating,
            "review_count": review_count,
            "date_first_available_raw": date_first_available,
            "bsr_rank_text": bsr_rank_text,
            "style_category": style,
            "color_variant_count": color_count,
        })

    except Exception as e:
        print(f"    ⚠ Error scraping {url}: {e}")
        product.update({
            "title": "", "brand": "", "price": None, "price_text": "",
            "rating": None, "review_count": 0,
            "date_first_available_raw": None,
            "bsr_rank_text": None,
            "style_category": "Unknown",
            "color_variant_count": 0,
        })

    return product


# ─── Analysis ──────────────────────────────────────────────────────────────

def parse_date_column(series):
    """Attempt to parse various date formats."""
    formats = [
        "%B %d, %Y",   # January 15, 2023
        "%b %d, %Y",   # Jan 15, 2023
        "%Y-%m-%d",
        "%m/%d/%Y",
    ]
    def try_parse(v):
        if not v or not isinstance(v, str):
            return None
        for fmt in formats:
            try:
                return datetime.strptime(v.strip(), fmt)
            except ValueError:
                pass
        return None
    return series.apply(try_parse)


def analyze_and_report(df):
    """Generate analysis and recommendations."""
    report_lines = []

    def section(title):
        report_lines.append("\n" + "="*70)
        report_lines.append(f"  {title}")
        report_lines.append("="*70)

    def line(txt=""):
        report_lines.append(txt)

    report_lines.append("Amazon 美国站女士毛衣类目 Top 100 销售数据分析报告")
    report_lines.append(f"数据采集时间: {datetime.now().strftime('%Y年%m月%d日 %H:%M')}")
    report_lines.append(f"数据来源: https://www.amazon.com/Best-Sellers-Clothing-Shoes-Jewelry-Womens-Sweaters/zgbs/fashion/1044456")

    # ── 1. Price Analysis ──────────────────────────────────────────────────
    section("一、价格分布分析")
    df_price = df[df["price"].notna() & (df["price"] > 0)].copy()
    if not df_price.empty:
        line(f"有效价格数据: {len(df_price)} 条")
        line(f"  最低价: ${df_price['price'].min():.2f}")
        line(f"  最高价: ${df_price['price'].max():.2f}")
        line(f"  平均价: ${df_price['price'].mean():.2f}")
        line(f"  中位价: ${df_price['price'].median():.2f}")

        bins = [0, 15, 25, 35, 50, 75, 100, 200, 9999]
        labels = ["≤$15", "$15-25", "$25-35", "$35-50", "$50-75", "$75-100", "$100-200", ">$200"]
        df_price["price_band"] = pd.cut(df_price["price"], bins=bins, labels=labels, right=True)
        price_dist = df_price["price_band"].value_counts().sort_index()
        line("\n  价格区间分布:")
        for band, cnt in price_dist.items():
            pct = cnt / len(df_price) * 100
            bar = "█" * int(pct / 2)
            line(f"    {str(band):12s}: {cnt:3d} 款  {pct:5.1f}%  {bar}")

        # top 20 avg price
        top20_price = df_price[df_price["rank"] <= 20]["price"].mean() if not df_price[df_price["rank"] <= 20].empty else None
        if top20_price:
            line(f"\n  Top 20 产品平均价格: ${top20_price:.2f}")

        line("\n  【价格建议】")
        dominant_band = price_dist.idxmax()
        line(f"  主流价格带为 {dominant_band}，建议新品定价优先布局该区间。")
        med = df_price["price"].median()
        line(f"  中位价 ${med:.2f} 可作为竞争定价参考基准。")
        if med < 35:
            line("  该类目整体偏中低价，建议新品以性价比为核心卖点切入，")
            line("  同时可开发 $40-60 的中高价段产品形成差异化。")
        else:
            line("  中高价格带市场较活跃，建议重视材质和工艺差异化。")

    # ── 2. Style Distribution ──────────────────────────────────────────────
    section("二、款式类型分布")
    style_dist = df["style_category"].value_counts()
    line(f"\n  款式分布 (共 {len(df)} 款):")
    for style, cnt in style_dist.items():
        pct = cnt / len(df) * 100
        bar = "█" * int(pct / 2)
        line(f"    {str(style):30s}: {cnt:3d} 款  {pct:5.1f}%  {bar}")

    line("\n  【款式建议】")
    top3_styles = style_dist.head(3).index.tolist()
    line(f"  前三大主流款式: {', '.join(top3_styles)}")
    line("  建议优先开发前三大款式，同时关注细分机会:")
    line("  - Turtleneck/Mock Neck: 秋冬核心款，百搭度高，建议为主力SKU")
    line("  - Cardigan: 春秋过渡季必备，开衫叠穿趋势明显，建议多色系布局")
    line("  - Oversized/Cable Knit: 休闲慵懒风强势，适合年轻消费者")
    line("  - 可开发 Ribbed + Crop 组合款，瞄准 Gen Z 市场")

    # ── 3. Date First Available Analysis ──────────────────────────────────
    section("三、上新时间分析")
    df["date_parsed"] = parse_date_column(df["date_first_available_raw"])
    df_dated = df[df["date_parsed"].notna()].copy()

    if not df_dated.empty:
        line(f"  有上架日期数据: {len(df_dated)} 款")
        df_dated["year"] = df_dated["date_parsed"].dt.year
        df_dated["month"] = df_dated["date_parsed"].dt.month
        df_dated["month_name"] = df_dated["date_parsed"].dt.strftime("%B")

        line("\n  按年份分布:")
        year_dist = df_dated["year"].value_counts().sort_index()
        for yr, cnt in year_dist.items():
            pct = cnt / len(df_dated) * 100
            line(f"    {yr}: {cnt:3d} 款  {pct:.1f}%")

        line("\n  按月份分布 (上新旺季):")
        month_dist = df_dated.groupby("month").size().sort_index()
        month_names = {1:"Jan",2:"Feb",3:"Mar",4:"Apr",5:"May",6:"Jun",
                       7:"Jul",8:"Aug",9:"Sep",10:"Oct",11:"Nov",12:"Dec"}
        for m, cnt in month_dist.items():
            pct = cnt / len(df_dated) * 100
            bar = "█" * int(pct / 1.5)
            line(f"    {month_names[m]}: {cnt:3d} 款  {pct:5.1f}%  {bar}")

        peak_months = month_dist.nlargest(3).index.tolist()
        peak_names = [month_names[m] for m in sorted(peak_months)]
        line(f"\n  上新峰值月份: {', '.join(peak_names)}")

        line("\n  【上新节奏建议】")
        line("  ① 秋冬主推期: 8月底-11月上旬是毛衣类目上新黄金窗口，")
        line("     建议提前 90 天完成打样，提前 60 天完成批量备货，")
        line("     提前 45 天完成入仓，保障在旺季前完成排名积累。")
        line("  ② 春季补充期: 2-3月可上新轻薄针织/开衫，配合春日穿搭搜索热度。")
        line("  ③ 常青款: 全年上架，以基础款Turtleneck、Cardigan为主，")
        line("     稳定库存水位，持续累积评价。")
        line("  ④ 节庆节点: 10月底(Halloween)、11月(Black Friday/感恩节)、")
        line("     12月(圣诞)是销售爆发点，需提前 2-3 个月布局。")
    else:
        line("  (日期数据不足，以下为基于行业经验的建议)")
        line("  建议新品上架窗口: 8月15日 - 10月15日")
        line("  圣诞/节日备货: 提前至10月1日前完成入仓")

    # ── 4. Brand & Review Analysis ─────────────────────────────────────────
    section("四、品牌与评价数据分析")
    df_brand = df[df["brand"].str.len() > 0] if "brand" in df.columns else df
    if not df_brand.empty:
        brand_dist = df_brand["brand"].value_counts().head(10)
        line("  Top 10 品牌 (按上榜次数):")
        for brand, cnt in brand_dist.items():
            line(f"    {str(brand):40s}: {cnt} 款")

    df_rev = df[df["review_count"].notna() & (df["review_count"] > 0)]
    if not df_rev.empty:
        line(f"\n  评价数据统计:")
        line(f"  平均评价数: {df_rev['review_count'].mean():.0f}")
        line(f"  中位评价数: {df_rev['review_count'].median():.0f}")
        line(f"  最高评价数: {df_rev['review_count'].max():,}")
        line(f"  平均星级:   {df_rev['rating'].dropna().mean():.2f} ★")

        line("\n  【评价建议】")
        med_rev = df_rev["review_count"].median()
        line(f"  榜单内产品中位评价数为 {med_rev:.0f}，")
        line("  新品需快速积累至 200+ 评价方可建立基础竞争力，")
        line("  建议通过 Vine 计划 + 早期测评活动加速评价积累。")

    # ── 5. Overall New Product Recommendations ─────────────────────────────
    section("五、新品开发综合建议")
    line("""
  ┌─────────────────────────────────────────────────────────────────┐
  │                    新品开发行动计划                               │
  └─────────────────────────────────────────────────────────────────┘

  【优先级1 - 秋冬主力款 (8-11月上新)】
  ● 款式: Turtleneck/Mock Neck 毛衣 + Cable Knit 纹理款
  ● 材质: 80%+ 消费者偏好: 羊毛混纺、腈纶混纺(亲肤耐洗)
  ● 颜色: 首选黑色、米白/奶油色、深咖、灰色，再布局2-3个流行色
  ● 定价: $25-45 主力区间，可配合首发优惠券快速冲排名
  ● SKU数: 建议首批 4-6 色 × 5 码 = 20-30 个 SKU
  ● 备货节奏: 6月确认设计 → 7月打样 → 8月批量生产 → 9月初入仓

  【优先级2 - 全年常青款 (Q4 主推+全年补货)】
  ● 款式: 多色系 Cardigan 开衫 (5 扣/长款最受欢迎)
  ● 定价: $20-40 (中低价带，流量最大)
  ● 差异化: 加大码 (1X-3X) 版型、口袋设计、高品质纽扣
  ● 颜色: 至少 8+ 色，满足多样化选购需求
  ● 备货节奏: 常备库存，每季补充新色 2-3 个

  【优先级3 - 趋势款 (年轻化/差异化)】
  ● 款式: Ribbed Crop Sweater + Oversized Knit
  ● 定价: $18-35 (吸引 Gen Z 预算)
  ● 营销: 配合 TikTok/Instagram 内容营销，重视图片和视频质量
  ● 上新: 春季(2-3月)轻薄款 + 秋季(9-10月)厚重款

  【关键成功要素】
  ✦ 图片质量: 主图纯白底，需有生活场景图，模特多角度展示
  ✦ 关键词布局: 标题含核心词 (womens sweater + 款式词 + 材质词)
  ✦ A+ 内容: 展示面料细节、版型对比、尺码参考
  ✦ 广告策略: 新品期 ACOS 可接受 50-80%，冲排名优先
  ✦ 定价策略: 上市初期 Coupon 10-15%，30天后根据排名调整

  【竞争风险提示】
  ⚠ 毛衣类目季节性强，库存积压风险高，首批建议保守备货
  ⚠ 退货率高发 (尺码不合/色差)，尺码表需详尽，描述需准确
  ⚠ 主要竞争对手多有 1000+ 评价积累，新品需有明确差异化点
""")

    report_text = "\n".join(report_lines)
    return report_text


# ─── Main ──────────────────────────────────────────────────────────────────

def main():
    output_dir = "/workspace/amazon_analysis"
    os.makedirs(output_dir, exist_ok=True)

    print("="*60)
    print("Amazon 女士毛衣 Best Sellers 数据采集 & 分析")
    print("="*60)

    driver = build_driver()

    try:
        # Step 1: Collect product links
        print("\n[Step 1] 采集 BSR 榜单链接 …")
        products = scrape_bestsellerlist(driver)
        print(f"  共获取 {len(products)} 条产品链接")

        # Step 2: Scrape product details
        print(f"\n[Step 2] 采集产品详情页 (共 {len(products)} 条，预计需要 5-10 分钟) …")
        for i, p in enumerate(products):
            print(f"  [{i+1:3d}/{len(products)}] ASIN: {p['asin']} …", end=" ", flush=True)
            scrape_product_detail(driver, p)
            title_short = p.get("title", "")[:50]
            price = p.get("price")
            print(f"${price:.2f}  " if price else "N/A   ", end="")
            print(f"⭐{p.get('rating', '')}  {p.get('review_count', 0):,}评  {title_short}")
            # randomize delay to avoid blocks
            human_delay(1.5, 3.5)

        # Step 3: Save raw data
        df = pd.DataFrame(products)
        raw_csv = os.path.join(output_dir, "raw_data.csv")
        df.to_csv(raw_csv, index=False, encoding="utf-8-sig")
        print(f"\n  ✅ 原始数据已保存: {raw_csv}")

        # Step 4: Analyze
        print("\n[Step 3] 生成分析报告 …")
        report = analyze_and_report(df)

        # Step 5: Save report
        report_path = os.path.join(output_dir, "analysis_report.txt")
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(report)
        print(f"  ✅ 分析报告已保存: {report_path}")

        # Also save a JSON for further processing
        json_path = os.path.join(output_dir, "products.json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(products, f, ensure_ascii=False, indent=2, default=str)
        print(f"  ✅ JSON 数据已保存: {json_path}")

        print("\n" + "="*60)
        print(report)

    finally:
        driver.quit()


if __name__ == "__main__":
    main()
