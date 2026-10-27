# -*- coding: utf-8 -*-
"""騰信工業官網產生器（只用 Python 標準函式庫）。

讀 src/ 之後，在 repo 根目錄產生 30 個 */index.html 與 sitemap.xml。
執行：python build.py
重複執行結果完全相同（冪等），產生的檔案一律是 UTF-8、LF 換行。

  src/layout/site.json   全站設定：選單、語言字串、GA、email
  src/layout/layout.html 共用版型（<head>、頁首、手機選單、頁尾）
  src/pages/**.html      每頁一檔：開頭 <!--page {...} --> 是該頁設定，其後是正文
"""
import glob
import hashlib
import html
import json
import os
import re

ROOT = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(ROOT, 'src')

ARROW_DESKTOP = ('<span class="ct-toggle-dropdown-desktop"><svg class="ct-icon" width="8" height="8" viewBox="0 0 15 15" aria-hidden="true">'
                 '<path d="M2.1,3.2l5.4,5.4l5.4-5.4L15,4.3l-7.5,7.5L0,4.3L2.1,3.2z"/></svg></span>')
ARROW_MOBILE = ('<svg class="ct-icon toggle-icon-1" width="15" height="15" viewBox="0 0 15 15" aria-hidden="true">'
                '<path d="M3.9,5.1l3.6,3.6l3.6-3.6l1.4,0.7l-5,5l-5-5L3.9,5.1z"/></svg>')
CURRENT = ['current-menu-item', 'page_item', 'page-item-{page_id}', 'current_page_item']
ANCESTOR = ['current-page-ancestor', 'current-menu-ancestor', 'current-menu-parent',
            'current-page-parent', 'current_page_parent', 'current_page_ancestor']

SPECULATION_RULES = '''<script type="speculationrules">
{"prefetch":[{"source":"document","where":{"and":[{"href_matches":"/*"},{"not":{"href_matches":["/wp-*.php","/wp-admin/*","/wp-content/uploads/*","/wp-content/*","/wp-content/plugins/*","/wp-content/themes/blocksy/*","/*\\\\?(.+)"]}},{"not":{"selector_matches":"a[rel~=\\"nofollow\\"]"}},{"not":{"selector_matches":".no-prefetch, .no-prefetch a"}}]},"eagerness":"conservative"}]}
</script>'''


def read(path):
    with open(path, encoding='utf-8') as f:
        return f.read()


def write_if_changed(path, text):
    """內容相同就不重寫，避免無謂的檔案異動。"""
    data = text.encode('utf-8')
    if os.path.exists(path):
        with open(path, 'rb') as f:
            if f.read() == data:
                return False
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'wb') as f:
        f.write(data)
    return True


def asset(url_path):
    """回傳帶版本參數的資源網址（內容改了版本就變，避免瀏覽器快取舊檔）。"""
    with open(os.path.join(ROOT, url_path.lstrip('/')), 'rb') as f:
        digest = hashlib.md5(f.read()).hexdigest()[:8]
    return '%s?v=%s' % (url_path, digest)


def obfuscate_email(address):
    """把 email 每個字元轉成 HTML 實體，降低被垃圾信程式抓走的機率（原 WordPress 也這樣做）。"""
    return ''.join('&#%d;' % ord(c) for c in address)


def load_page(path):
    text = read(path)
    m = re.match(r'<!--page\n(.*?)\n-->\n', text, re.S)
    if not m:
        raise SystemExit('%s 開頭缺少 <!--page {...} --> 設定' % path)
    meta = json.loads(m.group(1))
    body = text[m.end():]
    page_css = ''
    m = re.match(r'<style data-page-css>\n(.*?)\n</style>\n', body, re.S)
    if m:
        page_css = m.group(1)
        body = body[m.end():]
    meta['_file'] = os.path.relpath(path, ROOT)
    return meta, page_css, body


def page_id(meta):
    return re.search(r'\bpage-id-(\d+)\b', meta['body_class']).group(1)


# ---------- 選單 ----------

def item_classes(item, state, variant, pid):
    c = ['menu-item', 'menu-item-type-post_type', 'menu-item-object-page']
    if item.get('home'):
        c.append('menu-item-home')
    if state == 'current':
        c += [x.format(page_id=pid) for x in CURRENT]
    elif state == 'ancestor':
        c += ANCESTOR
    if item.get('children') and variant != 'footer':
        c.append('menu-item-has-children')
    c.append('menu-item-%s' % item['id'])
    if item.get('children') and variant == 'desktop':
        c.append('animated-submenu-block')
    return ' '.join(c)


def item_state(item, url):
    if item['url'] == url:
        return 'current'
    if any(ch['url'] == url for ch in item.get('children', [])):
        return 'ancestor'
    return ''


def link(item, state):
    current = ' aria-current="page"' if state == 'current' else ''
    return '<a href="%s"%s class="ct-menu-link">%s</a>' % (item['url'], current, item['label'])


def render_menu(lang, variant, url, pid, alt_url):
    """variant：desktop（頁首）、mobile（手機側選單）、footer（頁尾，不含子選單）。"""
    t = lang['t']
    ul_id = {'desktop': lang['menu_ul_id'], 'mobile': lang['menu_ul_id'] + '-1', 'footer': lang['menu_ul_id'] + '-2'}[variant]
    ul_class = '' if variant == 'mobile' else 'menu'
    lis = []
    for item in lang['menu']:
        state = item_state(item, url)
        cls = item_classes(item, state, variant, pid)
        li_id = ' id="menu-item-%s"' % item['id'] if variant == 'desktop' else ''
        children = item.get('children') if variant != 'footer' else None
        if not children:
            lis.append('<li%s class="%s">%s</li>' % (li_id, cls, link(item, state)))
            continue
        if variant == 'desktop':
            a = link(item, state).replace('</a>', ARROW_DESKTOP + '</a>')
            head = a + '<button class="ct-toggle-dropdown-desktop-ghost" aria-label="%s" aria-haspopup="true" aria-expanded="false"></button>' % t['expand']
        else:
            head = ('<span class="ct-sub-menu-parent">%s<button class="ct-toggle-dropdown-mobile" aria-label="%s" aria-haspopup="true" aria-expanded="false">%s</button></span>'
                    % (link(item, state), t['expand'], ARROW_MOBILE))
        subs = []
        for ch in children:
            ch_state = 'current' if ch['url'] == url else ''
            ch_id = ' id="menu-item-%s"' % ch['id'] if variant == 'desktop' else ''
            subs.append('\t<li%s class="%s">%s</li>' % (ch_id, item_classes(ch, ch_state, variant, pid), link(ch, ch_state)))
        lis.append('<li%s class="%s">%s\n<ul class="sub-menu">\n%s\n</ul>\n</li>' % (li_id, cls, head, '\n'.join(subs)))
    sw = lang['lang_switch']
    sw_id = ' id="menu-item-%s"' % sw['id'] if variant == 'desktop' else ''
    lis.append('<li%s class="%s menu-item menu-item-type-custom menu-item-object-custom menu-item-%s">'
               '<a href="%s" class="ct-menu-link" hreflang="%s" lang="%s"><img src="%s" alt="%s" width="16" height="11" style="width: 16px; height: 11px;"  loading="lazy"/></a></li>'
               % (sw_id, sw['class'], sw['id'], alt_url, sw['hreflang'], sw['hreflang'], sw['flag'], sw['alt']))
    return '<ul id="%s" class="%s">%s\n</ul>' % (ul_id, ul_class, '\n'.join(lis))


# ---------- 組頁 ----------

def render_head(site, meta, page_css):
    url = site['site_url'] + meta['url']
    out = ["<meta name='robots' content='max-image-preview:large' />"]
    for code in ('en', 'zh', 'x-default'):
        out.append('<link rel="alternate" href="%s" hreflang="%s" />' % (meta['hreflang'][code], code))
    out.append("<link rel='stylesheet' href='https://fonts.googleapis.com/css2?family=Noto%20Sans:wght@700&amp;display=swap' media='all' />")
    out.append('<link rel="stylesheet" href="%s" media="all" />' % asset('/assets/css/site.css'))
    if page_css:
        out.append('<style id="page-css">\n%s\n</style>' % page_css)
    out.append('<link rel="stylesheet" href="%s" media="all" />' % asset('/assets/css/widgets.css'))
    out.append('<link rel="canonical" href="%s" />' % url)
    out.append('<noscript><link rel="stylesheet" href="%s" /></noscript>' % asset('/assets/css/no-scripts.css'))
    out.append('<link rel="icon" href="/wp-content/uploads/2024/01/cropped-TOSIN-LOGO-e1706707555633-32x32.png" />')
    out.append('<link rel="icon" href="/wp-content/uploads/2024/01/cropped-TOSIN-LOGO-e1706707555633-192x192.png" />')
    out.append('<link rel="apple-touch-icon" href="/wp-content/uploads/2024/01/cropped-TOSIN-LOGO-e1706707555633-180x180.png" />')
    out.append('<meta name="msapplication-TileImage" content="%s/wp-content/uploads/2024/01/cropped-TOSIN-LOGO-e1706707555633-270x270.png" />' % site['site_url'])
    out.append('<script async src="https://www.googletagmanager.com/gtag/js?id=%s"></script>' % site['ga4'])
    out.append("<script>\n  window.dataLayer = window.dataLayer || [];\n  function gtag(){dataLayer.push(arguments);}\n"
               "  gtag('js', new Date());\n  gtag('config', '%s');\n</script>" % site['ga4'])
    return '\n'.join(out)


def render_scripts(meta):
    out = [SPECULATION_RULES]
    if meta.get('carousel'):
        out.append('<script src="%s"></script>' % asset('/assets/vendor/swiper/swiper.min.js'))
    out.append('<script src="%s"></script>' % asset('/assets/js/site.js'))
    for s in meta.get('scripts', []):
        attrs = (' ' + s['attrs']) if s.get('attrs') else ''
        out.append('<script src="%s"%s></script>' % (s['src'], attrs))
    return '\n'.join(out)


def render_page(site, layout, meta, page_css, body):
    lang = site['languages'][meta['lang']]
    other = 'zh' if meta['lang'] == 'en' else 'en'
    alt_url = meta['hreflang'][other].replace(site['site_url'], '', 1)
    pid = page_id(meta)
    values = {
        'html_lang': lang['html_lang'],
        'title': meta['title'],
        'head': render_head(site, meta, page_css),
        'body_class': meta['body_class'],
        'home': lang['home'],
        'search_action': lang['search_action'],
        'email': obfuscate_email(site['email']),
        'menu_desktop': render_menu(lang, 'desktop', meta['url'], pid, alt_url),
        'menu_mobile': render_menu(lang, 'mobile', meta['url'], pid, alt_url),
        'menu_footer': render_menu(lang, 'footer', meta['url'], pid, alt_url),
        'content': body.rstrip('\n'),
        'scripts': render_scripts(meta),
    }
    for k, v in lang['t'].items():
        values['t.' + k] = v

    def fill(m):
        key = m.group(1)
        if key not in values:
            raise SystemExit('版型裡的 {{%s}} 沒有對應的值' % key)
        return values[key]
    # 只替換一次：正文裡就算出現 {{ }} 也不會被再處理
    return re.sub(r'\{\{([\w.]+)\}\}', fill, layout)


def output_path(url):
    return os.path.join(ROOT, url.strip('/'), 'index.html') if url != '/' else os.path.join(ROOT, 'index.html')


def render_sitemap(site, pages):
    """格式沿用原本的 sitemap.xml：每頁一行 <loc>，依輸出檔案路徑排序。"""
    rows = ['<?xml version="1.0" encoding="UTF-8"?>',
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for meta in sorted(pages, key=lambda m: os.path.relpath(output_path(m['url']), ROOT).replace(os.sep, '/')):
        rows.append('  <url><loc>%s%s</loc></url>' % (site['site_url'], html.escape(meta['url'])))
    rows.append('</urlset>')
    return '\n'.join(rows) + '\n'


def main():
    site = json.loads(read(os.path.join(SRC, 'layout', 'site.json')))
    layout = read(os.path.join(SRC, 'layout', 'layout.html'))
    files = sorted(glob.glob(os.path.join(SRC, 'pages', '**', '*.html'), recursive=True))
    metas, seen = [], set()
    changed = 0
    for path in files:
        meta, page_css, body = load_page(path)
        if meta['url'] in seen:
            raise SystemExit('網址重複：%s' % meta['url'])
        seen.add(meta['url'])
        metas.append(meta)
        changed += write_if_changed(output_path(meta['url']), render_page(site, layout, meta, page_css, body))
    changed += write_if_changed(os.path.join(ROOT, 'sitemap.xml'), render_sitemap(site, metas))
    print('完成：%d 頁，%d 個檔案有變動' % (len(metas), changed))


if __name__ == '__main__':
    main()
