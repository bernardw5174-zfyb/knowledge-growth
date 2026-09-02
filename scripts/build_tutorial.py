#!/usr/bin/env python3
"""
build_tutorial.py — 从 README.md 生成离线教程 HTML 与 PDF。
- HTML 用作离线双击即读的中间产物（可复制、可缩放）
- PDF 由 Chromium 打印（基于同一份 HTML）

用法：在仓库根目录运行
  python3 scripts/build_tutorial.py
产出（直接落在仓库内、随 Download ZIP 一起打包）：
  第一次用-从这里开始.pdf        # 仓库根目录，双击即读
  docs/第一次用-从这里开始.html  # HTML，引用 docs/images/ 的图片
"""

import re
import shutil
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
README_PATH = REPO_ROOT / "README.md"
DOCS_DIR = REPO_ROOT / "docs"
OUTPUT_HTML = DOCS_DIR / "第一次用-从这里开始.html"
OUTPUT_PDF = REPO_ROOT / "第一次用-从这里开始.pdf"

# PDF 教程用的精简版 README：只截「第一次用，从这里开始」到第一次跑通说明。
# 即从 ## 第一次用，从这里开始  到  ## 它解决什么问题 之间的内容。
TUTORIAL_SECTION_RE = re.compile(
    r"(## 第一次用，从这里开始.*?)(?=^## 它解决什么问题)",
    re.DOTALL | re.MULTILINE,
)


def slice_tutorial(readme_text: str) -> str:
    """从 README 抽出「教程片段」，并补上文档级标题。"""
    match = TUTORIAL_SECTION_RE.search(readme_text)
    if not match:
        raise SystemExit("未在 README 中找到「第一次用，从这里开始」段落，请检查 README 结构是否变化。")
    body = match.group(1).rstrip()

    # 把所有 docs/images/xxx.png 改成相对 dist/ 目录的相对路径
    body = body.replace("](docs/images/", "](images/")

    header = (
        "# 知识生长 · 起步教程（离线版）\n\n"
        "> **第一次用，从这里开始。**一屏一个动作，每一步做完再走下一步。\n\n"
        "本教程与 GitHub 仓库 README 同源；改动以 GitHub 为准，PDF 为派生。\n\n"
        "---\n\n"
    )
    return header + body


CSS = """
@page {
  size: A4;
  margin: 18mm 16mm 18mm 16mm;
  @bottom-center {
    content: "知识生长 · 起步教程 v0.1.0 · 第 " counter(page) " / " counter(pages) " 页";
    font-size: 9pt;
    color: #888;
  }
}
body {
  font-family: "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", "Noto Sans CJK SC", sans-serif;
  font-size: 11pt;
  line-height: 1.65;
  color: #1f2328;
  max-width: 100%;
  margin: 0;
}
h1, h2, h3, h4 {
  font-weight: 600;
  line-height: 1.3;
  page-break-after: avoid;
}
h1 { font-size: 22pt; margin-top: 0; margin-bottom: 8mm; border-bottom: 2px solid #1f2328; padding-bottom: 3mm; }
h2 { font-size: 16pt; margin-top: 8mm; margin-bottom: 4mm; }
h3 { font-size: 13pt; margin-top: 5mm; margin-bottom: 3mm; }
h4 { font-size: 12pt; margin-top: 4mm; margin-bottom: 2mm; }
p { margin: 2mm 0; }
ul, ol { margin: 2mm 0 2mm 6mm; }
li { margin: 1mm 0; }
blockquote {
  margin: 3mm 0;
  padding: 2mm 3mm;
  border-left: 3px solid #d0d7de;
  background: #f6f8fa;
  color: #57606a;
  font-size: 10.5pt;
  page-break-inside: avoid;
}
blockquote blockquote { background: transparent; padding: 0; margin: 1mm 0; }
code {
  font-family: "Menlo", "Consolas", monospace;
  font-size: 10pt;
  background: #f6f8fa;
  padding: 1pt 3pt;
  border-radius: 2pt;
}
pre {
  background: #f6f8fa;
  border: 1px solid #d0d7de;
  border-radius: 4pt;
  padding: 3mm;
  overflow-x: auto;
  font-size: 9.5pt;
  line-height: 1.5;
  page-break-inside: avoid;
}
pre code { background: transparent; padding: 0; font-size: inherit; }
img {
  max-width: 100%;
  height: auto;
  display: block;
  margin: 4mm auto;
  border: 1px solid #d0d7de;
  border-radius: 4pt;
  page-break-inside: avoid;
}
hr {
  border: 0;
  border-top: 1px solid #d0d7de;
  margin: 6mm 0;
}
a { color: #0969da; text-decoration: none; }
"""


def build_html(tutorial_md: str) -> str:
    """用 markdown 包把教程 md 渲染成 HTML，外面套上 CSS。"""
    import markdown
    body_html = markdown.markdown(
        tutorial_md,
        extensions=["extra", "sane_lists", "tables"],
    )
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>知识生长 · 起步教程 v0.1.0</title>
<style>{CSS}</style>
</head>
<body>
{body_html}
</body>
</html>
"""


def write_pdf_via_playwright(html_path: Path, pdf_path: Path) -> None:
    """用 Chromium 把本地 HTML 转 PDF。"""
    from playwright.sync_api import sync_playwright

    file_url = html_path.resolve().as_uri()
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(file_url, wait_until="networkidle")
        page.emulate_media(media="print")
        page.pdf(
            path=str(pdf_path),
            format="A4",
            print_background=True,
            margin={"top": "0", "right": "0", "bottom": "0", "left": "0"},
        )
        browser.close()


def main() -> None:
    if not README_PATH.exists():
        raise SystemExit(f"未找到 README：{README_PATH}")
    if not (DOCS_DIR / "images").exists():
        raise SystemExit(f"未找到 docs/images/，请先 commit 实操截图后再构建 PDF。")

    readme_text = README_PATH.read_text(encoding="utf-8")
    tutorial_md = slice_tutorial(readme_text)
    html_text = build_html(tutorial_md)
    OUTPUT_HTML.write_text(html_text, encoding="utf-8")
    print(f"[OK] HTML 已生成：{OUTPUT_HTML}")

    write_pdf_via_playwright(OUTPUT_HTML, OUTPUT_PDF)
    size_kb = OUTPUT_PDF.stat().st_size / 1024
    print(f"[OK] PDF 已生成：{OUTPUT_PDF}（{size_kb:.1f} KB）")


if __name__ == "__main__":
    main()