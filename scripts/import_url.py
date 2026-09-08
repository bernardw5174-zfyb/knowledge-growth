#!/usr/bin/env python3
"""Fetch a URL's public body text and save it as a non-byte-identical Raw copy.

Web pages cannot satisfy the Starter's byte-level Raw requirement, so this
script saves an explicitly-marked text extraction instead of pretending to be
the original. It only fetches the single URL given by the user and never
crawls other pages.

Usage: python3 scripts/import_url.py <url> <domain>

Set STARTER_ROOT only for automated tests. Normal use derives the root
from this script's parent directory.
"""
from datetime import date, datetime
import gzip
import html
import os
from pathlib import Path
import re
import sys
import urllib.error
import urllib.request

DEFAULT_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)

_IMG_PLACEHOLDER = "[图片]"


def workspace_root() -> Path:
    override = os.environ.get("STARTER_ROOT")
    return Path(override).resolve() if override else Path(__file__).resolve().parents[1]


def fetch_html(url: str, timeout: int = 20) -> str:
    """Fetch a URL and return its decoded HTML text. Raises on failure."""
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": DEFAULT_UA,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Encoding": "gzip",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
        charset = resp.headers.get_content_charset()
        if resp.headers.get("Content-Encoding", "").lower() == "gzip":
            raw = gzip.decompress(raw)
        return _decode(raw, charset)


def _decode(raw: bytes, charset_hint: str | None) -> str:
    if charset_hint:
        try:
            return raw.decode(charset_hint)
        except (LookupError, UnicodeDecodeError):
            pass
    for enc in ("utf-8", "gb18030"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def extract_title(html_str: str) -> str:
    """Best-effort title from og:title, then <title>."""
    m = re.search(
        r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)',
        html_str,
        re.I,
    )
    if not m:
        m = re.search(
            r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:title["\']',
            html_str,
            re.I,
        )
    if m:
        return html.unescape(m.group(1)).strip()
    m = re.search(r"<title[^>]*>(.*?)</title>", html_str, re.S | re.I)
    if m:
        return html.unescape(re.sub(r"<[^>]+>", "", m.group(1))).strip()
    return ""


def extract_date(html_str: str) -> str | None:
    """Best-effort original publish date as YYYY-MM-DD, or None."""
    m = re.search(
        r'<meta[^>]+property=["\'](?:og:)?article:published_time["\'][^>]+content=["\']([^"\']+)',
        html_str,
        re.I,
    )
    if not m:
        m = re.search(
            r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\'](?:og:)?article:published_time["\']',
            html_str,
            re.I,
        )
    if m:
        normalized = _normalize_date(m.group(1))
        if normalized:
            return normalized
    m = re.search(r"(?:publish_time|createTime)\s*[:=]\s*[\"'](\d{4}-\d{2}-\d{2})", html_str, re.I)
    if m:
        return m.group(1)
    m = re.search(r"\bct\s*=\s*[\"'](\d{10})[\"']", html_str)
    if m:
        try:
            return datetime.fromtimestamp(int(m.group(1))).strftime("%Y-%m-%d")
        except (ValueError, OSError):
            pass
    return None


def _normalize_date(value: str) -> str | None:
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", value)
    if not m:
        return None
    year, month, day = (int(m.group(1)), int(m.group(2)), int(m.group(3)))
    try:
        return date(year, month, day).isoformat()
    except ValueError:
        return None


def extract_body(html_str: str) -> str:
    """Extract the main body as plain text, preferring known containers."""
    cleaned = _strip_noise(html_str)
    # 强信号容器：js_content（微信）、article、main —— 存在且有文本即采用
    for pattern, tag in (
        (r'<div[^>]+id=["\']js_content["\'][^>]*>', "div"),
        (r"<article\b[^>]*>", "article"),
        (r"<main\b[^>]*>", "main"),
    ):
        m = re.search(pattern, cleaned, re.I)
        if m:
            text = _html_to_text(_slice_element(cleaned, m.start(), tag=tag))
            if text.strip():
                return text
    # 兜底：body（或全文），卡一个最低长度避免抓进整页导航
    m = re.search(r"<body\b[^>]*>", cleaned, re.I)
    if m:
        text = _html_to_text(_slice_element(cleaned, m.start(), tag="body"))
        if len(text.strip()) >= 40:
            return text
    return _html_to_text(cleaned)


def _strip_noise(html_str: str) -> str:
    html_str = re.sub(r"<!--.*?-->", "", html_str, flags=re.S)
    for tag in ("script", "style", "noscript", "template"):
        html_str = re.sub(rf"<{tag}\b[^>]*>.*?</{tag}\s*>", "", html_str, flags=re.S | re.I)
    return html_str


def _slice_element(html_str: str, start_idx: int, tag: str = "div") -> str:
    """Return the element starting at start_idx, matched by tag depth."""
    depth = 0
    i = start_idx
    n = len(html_str)
    open_re = re.compile(rf"<{tag}\b", re.I)
    close_re = re.compile(rf"</{tag}\s*>", re.I)
    while i < n:
        om = open_re.match(html_str, i)
        cm = close_re.match(html_str, i)
        if om:
            depth += 1
            i = om.end()
            continue
        if cm:
            depth -= 1
            i = cm.end()
            if depth == 0:
                return html_str[start_idx:i]
            continue
        i += 1
    return html_str[start_idx:]


def _html_to_text(fragment: str) -> str:
    fragment = re.sub(r"<img[^>]*>", _IMG_PLACEHOLDER, fragment, flags=re.I)
    fragment = re.sub(r"<br\s*/?>", "\n", fragment, flags=re.I)
    fragment = re.sub(r"</(p|div|li|h[1-6]|section|blockquote|tr|pre)>", "\n", fragment, flags=re.I)
    fragment = re.sub(r"<(p|div|li|h[1-6]|section|blockquote|tr)[^>]*>", "", fragment, flags=re.I)
    fragment = re.sub(r"<[^>]+>", "", fragment)
    fragment = html.unescape(fragment)
    out: list[str] = []
    prev_blank = False
    for line in fragment.splitlines():
        line = line.strip()
        if not line:
            if not prev_blank:
                out.append("")
            prev_blank = True
        else:
            out.append(line)
            prev_blank = False
    return "\n".join(out).strip()


def sanitize_filename(name: str, max_len: int = 40) -> str:
    name = re.sub(r'[\\/:*?"<>|\r\n\t]', "", name).strip().strip(".")
    name = re.sub(r"\s+", " ", name)
    if len(name) > max_len:
        name = name[:max_len].rstrip()
    return name


def build_raw_markdown(
    title: str,
    source_url: str,
    original_date: str | None,
    fetched_at: str,
    body: str,
) -> str:
    lines = [
        "# 抓取元信息（非原文内容，由 Agent 添加）",
        "",
        f"- 标题：{title or '（未提取到）'}",
        f"- 原文 URL：{source_url}",
    ]
    if original_date:
        lines.append(f"- 原文发布/更新时间：{original_date}（页面提取，可能不准确）")
    lines += [
        f"- 抓取时间：{fetched_at}",
        "- 抓取方式：HTTP GET 获取原始 HTML，脚本提取正文主体并转为纯文本",
        "- 字节级完整性：**否**。本文件为文本化抓取副本，非字节级原件。",
        "  - 已丢失：图片内容（以 `[图片]` 占位）、排版样式、超链接、列表编号等",
        "- 归档口径：只进不改。若后续取得本地原件（PDF / 截图 / 存档页），另行新增 Raw，不修改本文件。",
        "",
        "---",
        "",
        "# 原文正文（抓取文本）",
        "",
        body,
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: python3 scripts/import_url.py <url> <domain>")
        return 2

    url = sys.argv[1].strip()
    domain = sys.argv[2].strip()
    if not (url.startswith("http://") or url.startswith("https://")):
        print("ERROR: url must start with http:// or https://")
        return 2
    if not domain or len(domain) > 40 or re.search(r"[\\/\x00|]", domain):
        print("ERROR: invalid domain")
        return 2

    root = workspace_root()
    raw_dir = root / "vault" / domain / "00-raw"
    if not raw_dir.is_dir():
        print(f"ERROR: domain not initialized: vault/{domain}; run create_domain.py first")
        return 2

    try:
        html_str = fetch_html(url)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as exc:
        print(f"ERROR: fetch failed: {exc}")
        return 3

    title = extract_title(html_str)
    original_date = extract_date(html_str)
    body = extract_body(html_str)
    if not body.strip():
        print("ERROR: no extractable body text")
        return 4

    fetched_at = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %Z")
    date_str = original_date or date.today().isoformat()
    safe_title = sanitize_filename(title) or "未命名文章"
    filename = f"{date_str}_{safe_title}_网页抓取文本.md"
    content = build_raw_markdown(title, url, original_date, fetched_at, body)

    dest = raw_dir / filename
    if dest.exists():
        if dest.read_text(encoding="utf-8") == content:
            print(f"raw-path: {dest.relative_to(root)}")
            print("byte-identical: NO")
            print("raw-status: existing-identical")
            return 0
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        dest = raw_dir / f"{date_str}_{safe_title}-{stamp}_网页抓取文本.md"

    dest.write_text(content, encoding="utf-8")
    print(f"raw-path: {dest.relative_to(root)}")
    print("byte-identical: NO")
    print("raw-status: saved")
    print(f"content-chars: {len(body)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
