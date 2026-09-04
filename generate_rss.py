#!/usr/bin/env python3
"""
NO&T Asia Legal Update のRSSフィード生成スクリプト
"""

import os
import re
import ssl
import warnings
from datetime import datetime, timezone, timedelta
from feedgen.feed import FeedGenerator
from bs4 import BeautifulSoup
import requests
from urllib.parse import urljoin
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import urllib3

# SSL警告を無視する（自己署名証明書の場合）
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 設定
BASE_URL = "https://www.nagashima.com"
TARGET_URL = f"{BASE_URL}/newsletters/nl_asia_legal_update/"
OUTPUT_FILE = "rss.xml"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

# JSTタイムゾーン（UTC+9）
JST = timezone(timedelta(hours=9))


def get_session_with_retry():
    """リトライ機能付きのセッションを作成"""
    session = requests.Session()
    
    # SSL証明書の検証をスキップ（自己署名証明書対応）
    session.verify = False
    
    # リトライ設定
    retry_strategy = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    
    return session


def fetch_html(url):
    """HTMLを取得する（SSLエラー対応）"""
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
    }
    
    try:
        session = get_session_with_retry()
        response = session.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        response.encoding = "utf-8"
        return response.text
    except requests.exceptions.SSLError as e:
        # SSLエラーが発生した場合、さらに強制的に取得を試みる
        print(f"SSLエラーが発生しました。代替方法で再試行します: {e}")
        try:
            # verify=Falseを明示的に指定
            response = requests.get(
                url,
                headers=headers,
                timeout=30,
                verify=False  # SSL検証をスキップ
            )
            response.raise_for_status()
            response.encoding = "utf-8"
            return response.text
        except Exception as e2:
            print(f"代替方法でも失敗しました: {e2}")
            raise


def parse_articles(html):
    """記事一覧をパースする"""
    soup = BeautifulSoup(html, "html.parser")
    articles = []

    # 記事カードのセレクタ
    # contents-list-item クラスのli要素を探す
    items = soup.select("li.contents-list-item")
    
    if not items:
        # 別のセレクタで試す
        items = soup.select(".contents-list-item")
    
    if not items:
        # articleタグで探す
        items = soup.select("article.contents-card")
        if items:
            # articleタグの親要素を取得
            items = [item.parent for item in items if item.parent]
    
    print(f"見つかった記事数: {len(items)}")
    
    for item in items:
        article = {}
        
        # リンク
        link_tag = item.find("a")
        if link_tag and link_tag.get("href"):
            article["link"] = urljoin(BASE_URL, link_tag["href"])
        else:
            continue
        
        # タイトル (h2.heading)
        title_tag = item.select_one("h2.heading")
        if title_tag:
            article["title"] = title_tag.get_text(strip=True)
        else:
            # 代替: h2タグ全般
            title_tag = item.find("h2")
            if title_tag:
                article["title"] = title_tag.get_text(strip=True)
            else:
                continue
        
        # 日付 (Newsletter番号から抽出)
        # 例: "NO&T Asia Legal Update ～アジア最新法律情報～ No.289（2026年8月）"
        date_tag = item.select_one(".newsletter")
        article["date_str"] = ""
        article["pub_date"] = datetime.now(JST)  # デフォルト
        
        if date_tag:
            text = date_tag.get_text(strip=True)
            article["date_str"] = text
            
            # 日付を抽出（例: 2026年8月 または 2026年8月20日）
            # パターン: （YYYY年MM月） または （YYYY年MM月DD日）
            match = re.search(r'（(\d{4})年(\d{1,2})月(?:(\d{1,2})日)?）', text)
            if match:
                year = int(match.group(1))
                month = int(match.group(2))
                day = int(match.group(3)) if match.group(3) else 1
                try:
                    article["pub_date"] = datetime(year, month, day, tzinfo=JST)
                except ValueError:
                    # 日付が無効な場合（例: 2月30日）は月初めに設定
                    try:
                        article["pub_date"] = datetime(year, month, 1, tzinfo=JST)
                    except ValueError:
                        pass
        
        # 著者
        author_tag = item.select_one(".lawyers")
        if author_tag:
            article["author"] = author_tag.get_text(strip=True)
        else:
            article["author"] = "長島・大野・常松法律事務所"
        
        # 説明（タグから生成）
        tags = item.select(".contents-practice .item span")
        categories = [tag.get_text(strip=True) for tag in tags if tag.get_text(strip=True)]
        article["categories"] = categories
        article["description"] = f"カテゴリー: {', '.join(categories[:5])}" if categories else ""
        
        articles.append(article)
        print(f"  - {article['title'][:50]}...")
    
    return articles


def generate_rss(articles, output_file):
    """RSSフィードを生成する"""
    fg = FeedGenerator()
    fg.title("NO&T Asia Legal Update アジア最新法律情報")
    fg.description("アジア地域の最新法律情報や時事問題についてタイムリーにお伝えしています。")
    fg.link(href=TARGET_URL, rel="alternate")
    fg.link(href=f"{BASE_URL}/rss.xml", rel="self")
    fg.language("ja")
    fg.copyright("Copyright©2000-2026 Nagashima Ohno & Tsunematsu. All Rights Reserved.")
    fg.generator("Python RSS Feed Generator")
    fg.lastBuildDate(datetime.now(JST))
    
    # 最新の記事から順に追加（最大50件）
    for article in articles[:50]:
        fe = fg.add_entry()
        fe.title(article["title"])
        fe.link(href=article["link"])
        fe.guid(article["link"], permalink=True)
        fe.pubDate(article["pub_date"])
        
        # 説明
        description = article.get("description", "")
        if article.get("categories"):
            desc = f"カテゴリー: {', '.join(article['categories'])}"
            if article.get("date_str"):
                desc = f"{article['date_str']} | {desc}"
            fe.description(desc)
        else:
            fe.description(f"{article.get('date_str', '')}")
        
        # 著者
        if article.get("author"):
            fe.author({"name": article["author"]})
        
        # カテゴリ
        for cat in article.get("categories", []):
            fe.category(term=cat)
    
    # RSSファイルに出力
    rss_str = fg.rss_str(pretty=True)
    with open(output_file, "wb") as f:
        f.write(rss_str)
    
    print(f"RSSフィードを生成しました: {output_file}")
    print(f"記事数: {len(articles[:50])}")


def main():
    """メイン関数"""
    print(f"Fetching: {TARGET_URL}")
    print("SSL証明書の検証をスキップします（自己署名証明書対応）")
    
    try:
        html = fetch_html(TARGET_URL)
        
        # HTMLの一部をデバッグ表示（最初の500文字）
        print("\n--- HTMLの最初の500文字 ---")
        print(html[:500])
        print("---\n")
        
        articles = parse_articles(html)
        
        if not articles:
            print("警告: 記事が見つかりませんでした。HTML構造が変わった可能性があります。")
            # デバッグ用にHTMLの構造を表示
            soup = BeautifulSoup(html, "html.parser")
            print("\n--- デバッグ情報 ---")
            
            # 様々なセレクタで検索
            selectors = [
                "li.contents-list-item",
                ".contents-list-item",
                "article.contents-card",
                ".contents-card",
                ".contents-list .item",
                ".post-item",
            ]
            
            for selector in selectors:
                found = soup.select(selector)
                print(f"'{selector}': {len(found)}件")
            
            # クラス名の一覧を表示（デバッグ用）
            print("\n--- クラス名のサンプル ---")
            classes = set()
            for tag in soup.find_all(class_=True):
                classes.update(tag.get("class", []))
            print(list(classes)[:20])
        
        generate_rss(articles, OUTPUT_FILE)
        
    except Exception as e:
        print(f"エラーが発生しました: {e}")
        import traceback
        traceback.print_exc()
        raise


if __name__ == "__main__":
    main()
