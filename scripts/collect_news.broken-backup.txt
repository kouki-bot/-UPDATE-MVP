import re
import json
import time
from html.parser import HTMLParser
# collect_news.py 修正用コード
# GitHubの scripts/collect_news.py で、以下の2か所を置き換えてください。
# 1) class PageParser(HTMLParser): から次の「# 共通処理」の直前まで
# 2) def extract_page_text(parser): の関数全体
#
# 重要:
# - press_main_body の中だけを優先して取得します。
# - SKIP_TAGS の中身は取得しません。
# - div の入れ子を数えて正しく終了を判定します。
# - 既存のリンク・日付・通常テキスト取得も維持します.

class PageParser(HTMLParser):
    def __init__(self):
        super().__init__()

        self.links = []
        self.current_href = None
        self.current_text = []

        self.title_parts = []
        self.meta_dates = []

        self.text_parts = []
        self.article_parts = []

        self.tag_stack = []
        self.skip_depth = 0
        self.article_depth = 0
        self.in_title = False

        # 山口県公式サイトの報道発表本文用
        self.press_body_parts = []
        self.press_body_depth = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)

        # 本文領域の開始を検出
        if tag == "div":
            if attrs.get("id") == "press_main_body":
                self.press_body_depth = 1
            elif self.press_body_depth > 0:
                self.press_body_depth += 1

        if tag in SKIP_TAGS:
            self.skip_depth += 1
            self.tag_stack.append(tag)
            return

        if self.skip_depth:
            self.tag_stack.append(tag)
            return

        if tag == "title":
            self.in_title = True

        if tag == "a":
            self.current_href = attrs.get("href")
            self.current_text = []

        if tag == "meta":
            name = (
                attrs.get("property")
                or attrs.get("name")
                or ""
            ).strip().lower()

            content = (
                attrs.get("content") or ""
            ).strip()

            if content and name in PUBLISHED_META_NAMES:
                self.meta_dates.append({
                    "name": name,
                    "value": content,
                })

        if tag in ("main", "article"):
            self.article_depth += 1

        self.tag_stack.append(tag)

    def handle_endtag(self, tag):
        # SKIP_TAGS の終了処理を先に行う
        if tag in SKIP_TAGS:
            for index in range(
                len(self.tag_stack) - 1,
                -1,
                -1,
            ):
                if self.tag_stack[index] == tag:
                    removed = self.tag_stack[index:]
                    self.tag_stack = self.tag_stack[:index]
                    self.skip_depth = max(
                        0,
                        self.skip_depth - removed.count(tag),
                    )
                    break
            return

        if self.skip_depth:
            if self.tag_stack:
                self.tag_stack.pop()
            return

        if tag == "title":
            self.in_title = False

        if tag in ("main", "article"):
            self.article_depth = max(
                0,
                self.article_depth - 1,
            )

        if tag == "a" and self.current_href:
            title = re.sub(
                r"\s+",
                " ",
                " ".join(self.current_text),
            ).strip()

            if title:
                self.links.append({
                    "title": title,
                    "url": self.current_href,
                })

            self.current_href = None
            self.current_text = []

        # press_main_body 内の div 深度を戻す
        if tag == "div" and self.press_body_depth > 0:
            self.press_body_depth -= 1

        if self.tag_stack:
            self.tag_stack.pop()

    def handle_data(self, data):
        if self.skip_depth:
            return

        text = re.sub(
            r"\s+",
            " ",
            data,
        ).strip()

        if not text:
            return

        self.text_parts.append(text)

        if self.article_depth > 0:
            self.article_parts.append(text)

        if self.press_body_depth > 0:
            self.press_body_parts.append(text)

        if self.in_title:
            self.title_parts.append(text)

        if self.current_href:
            self.current_text.append(text)


def extract_page_text(parser):
    """
    press_main_body が取得できた場合は優先する。
    見つからない場合は従来の main/article、通常テキストを使用する。
    """

    press_text = clean_text(
        " ".join(parser.press_body_parts)
    )

    if len(press_text) >= 100:
        return press_text[:MAX_BODY_CHARS]

    article_text = clean_text(
        " ".join(parser.article_parts)
    )

    full_text = clean_text(
        " ".join(parser.text_parts)
    )

    if len(article_text) >= 100:
        return article_text[:MAX_BODY_CHARS]

    return full_text[:MAX_BODY_CHARS]
