# -*- coding: utf-8 -*-
"""一次性抽取腳本：把 HTTrack 抓下來的 WordPress 靜態頁拆成 src/pages/ 的內容檔。

用法：python tools/extract.py <舊網站根目錄> <輸出的 repo 根目錄>
（舊網站根目錄通常是 main 分支的 checkout。重建完成後此腳本已無用途，留存備查。）
"""
import json
import os
import re
import sys
from urllib.parse import urljoin, urlsplit

SITE = 'https://www.tosin.com.tw'

PAGES = [
    '', 'about-us/', 'products/', 'products/o-ring/', 'products/hydraulic-seal/',
    'products/washer-gasket/', 'products/grommet/', 'products/sucker/',
    'products/metal-filter/', 'products/metal-bonded-rubber-seal/',
    'products/customized-product/', 'quality/', 'equipment/', 'material/', 'contact-us/',
    'zh/', 'zh/about-us-zh/', 'zh/products-zh/', 'zh/products-zh/o-ring-zh/',
    'zh/products-zh/hydraulic-seal-zh/', 'zh/products-zh/washer-gasket-zh/',
    'zh/products-zh/grommet-zh/', 'zh/products-zh/sucker-zh/', 'zh/products-zh/metal-filter-zh/',
    'zh/products-zh/metal-bonded-rubber-seal-zh/', 'zh/products-zh/customized-product-zh/',
    'zh/quality-zh/', 'zh/equipment-zh/', 'zh/material-zh/', 'zh/contact-us-zh/',
]

URL_ATTR = re.compile(r'''(\s(?:href|src|data-src|poster)=)(["'])(.*?)\2''', re.S)
SRCSET_ATTR = re.compile(r'''(\s(?:srcset|data-srcset)=)(["'])(.*?)\2''', re.S)
CSS_URL = re.compile(r'''url\(\s*(["']?)([^"')]+)\1\s*\)''')


def absolutize(url, page_url):
    """相對網址 → 站根絕對路徑（/xxx）。外部網址、錨點、mailto 等原樣保留。"""
    u = url.strip()
    if not u or u.startswith(('#', 'mailto:', 'tel:', 'data:', 'javascript:', '//')):
        return url
    if re.match(r'^[a-zA-Z][a-zA-Z0-9+.-]*:', u):
        return url
    full = urljoin(SITE + '/' + page_url, u)
    parts = urlsplit(full)
    out = parts.path
    if parts.query:
        out += '?' + parts.query
    if parts.fragment:
        out += '#' + parts.fragment
    return out


def rewrite_urls(html, page_url):
    """改寫 HTML 屬性與 inline style 裡的相對網址；<script> 內容不動。"""
    pieces = re.split(r'(<script\b.*?</script>)', html, flags=re.S | re.I)
    out = []
    for i, piece in enumerate(pieces):
        if i % 2 == 1:
            # script 標籤本身的 src 仍要改，內容不動
            head_end = piece.index('>') + 1
            tag = URL_ATTR.sub(lambda m: m.group(1) + m.group(2) + absolutize(m.group(3), page_url) + m.group(2), piece[:head_end])
            out.append(tag + piece[head_end:])
            continue
        piece = URL_ATTR.sub(lambda m: m.group(1) + m.group(2) + absolutize(m.group(3), page_url) + m.group(2), piece)

        def fix_srcset(m):
            items = []
            for item in m.group(3).split(','):
                item = item.strip()
                if not item:
                    continue
                bits = item.split(None, 1)
                bits[0] = absolutize(bits[0], page_url)
                items.append(' '.join(bits))
            return m.group(1) + m.group(2) + ', '.join(items) + m.group(2)
        piece = SRCSET_ATTR.sub(fix_srcset, piece)
        piece = CSS_URL.sub(lambda m: 'url(' + m.group(1) + absolutize(m.group(2), page_url) + m.group(1) + ')', piece)
        out.append(piece)
    return ''.join(out)


def strip_junk(html):
    # Elementor 燈箱的動作雜湊（內含本機 WordPress 主機名，靜態站用不到）
    html = re.sub(r'\s+data-e-action-hash="[^"]*"', '', html)
    return html


def extract(old_root, page_url):
    path = os.path.join(old_root, page_url, 'index.html')
    with open(path, encoding='utf-8') as f:
        h = f.read()
    lang = 'zh' if page_url.startswith('zh/') else 'en'
    title = re.search(r'<title>(.*?)</title>', h, re.S).group(1).strip()
    alts = dict((m.group(2), m.group(1)) for m in re.finditer(r'<link rel="alternate" href="([^"]+)" hreflang="([^"]+)" />', h))
    body_tag = re.search(r'<body\b[^>]*>', h).group(0)
    body_class = re.search(r'class="([^"]*)"', body_tag).group(1)
    inline = re.search(r"<style id=['\"]elementor-frontend-inline-css['\"]>(.*?)</style>", h, re.S).group(1)
    # 第一行是 Elementor 全站 kit 樣式（已併入 assets/css/site.css），其餘是本頁專屬樣式
    lines = inline.strip('\n').split('\n')
    kit, page_css = lines[0], '\n'.join(l for l in lines[1:] if l.strip() and not l.startswith('/*# sourceURL'))
    start = h.index('>', h.index('<main id="main"')) + 1
    end = h.rindex('</main>')
    main = h[start:end]
    main = strip_junk(rewrite_urls(main, page_url))
    page_css = rewrite_urls(page_css, page_url)

    scripts = []
    for m in re.finditer(r'<script src="(https://cdn\.jsdelivr\.net/npm/fslightbox[^"]*)"([^>]*)></script>', h):
        scripts.append({'src': m.group(1), 'attrs': m.group(2).strip()})
    meta = {
        'url': '/' + page_url,
        'lang': lang,
        'title': title,
        'hreflang': {k: alts[k] for k in ('en', 'zh', 'x-default') if k in alts},
        'body_class': body_class,
        'carousel': 'image-carousel.default' in main,
        'scripts': scripts,
    }
    return meta, kit, page_css, main


def page_file(page_url):
    name = page_url.rstrip('/') or 'index'
    if name == 'zh':
        name = 'zh/index'
    return name + '.html'


def main():
    old_root, out_root = sys.argv[1], sys.argv[2]
    kits = set()
    for page_url in PAGES:
        meta, kit, page_css, body = extract(old_root, page_url)
        kits.add(kit)
        dest = os.path.join(out_root, 'src', 'pages', page_file(page_url))
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, 'w', encoding='utf-8', newline='\n') as f:
            f.write('<!--page\n' + json.dumps(meta, ensure_ascii=False, indent=2) + '\n-->\n')
            if page_css.strip():
                f.write('<style data-page-css>\n' + page_css.strip() + '\n</style>\n')
            f.write(body.strip('\n') + '\n')
        print('ok', page_url or '/')
    print('kit 樣式種類：', len(kits))
    with open(os.path.join(out_root, 'tools', 'kit.css'), 'w', encoding='utf-8', newline='\n') as f:
        f.write(sorted(kits)[0] + '\n')


if __name__ == '__main__':
    main()
