# -*- coding: utf-8 -*-
"""檢查工具（只用標準函式庫）。

  python _tools/verify.py                 檢查目前網站：站內連結與資源檔是否存在、canonical/hreflang、sitemap
  python _tools/verify.py <舊網站根目錄>    另外逐頁比對新舊版：可見文字、圖片清單、連結清單
"""
import glob
import html
import os
import re
import sys
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit, unquote

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = 'https://www.tosin.com.tw'


class Collector(HTMLParser):
    def __init__(self, page_url):
        super().__init__(convert_charrefs=True)
        self.base = SITE + page_url
        self.text, self.images, self.links, self.resources = [], [], [], []
        self.head = {'canonical': [], 'alternate': {}}
        self.skip = 0

    def url(self, u):
        u = (u or '').strip()
        if not u or u.startswith(('data:', 'mailto:', 'tel:', 'javascript:')):
            return u
        return urljoin(self.base, u)

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in ('script', 'style', 'noscript'):
            self.skip += 1
        if tag == 'img':
            self.images.append(self.url(a.get('src')))
            for part in (a.get('srcset') or '').split(','):
                if part.strip():
                    self.images.append(self.url(part.split()[0]))
            if a.get('alt'):
                self.text.append(a['alt'])
        if tag == 'a' and 'href' in a:
            self.links.append(self.url(a['href']))
        if tag == 'link':
            rel = a.get('rel', '')
            if rel == 'canonical':
                self.head['canonical'].append(a.get('href'))
            elif rel == 'alternate' and a.get('hreflang'):
                self.head['alternate'][a['hreflang']] = a.get('href')
            if rel in ('stylesheet', 'icon', 'apple-touch-icon'):
                self.resources.append(self.url(a.get('href')))
        if tag in ('script', 'iframe', 'source', 'video', 'audio') and a.get('src'):
            self.resources.append(self.url(a['src']))
        if tag == 'input' and a.get('placeholder'):
            self.text.append(a['placeholder'])
        style = a.get('style') or ''
        for u in re.findall(r'url\(\s*["\']?([^"\')]+)', style):
            self.images.append(self.url(html.unescape(u)))

    def handle_endtag(self, tag):
        if tag in ('script', 'style', 'noscript'):
            self.skip = max(0, self.skip - 1)

    def handle_data(self, data):
        if not self.skip:
            self.text.append(data)


def collect(path, page_url):
    with open(path, encoding='utf-8') as f:
        h = f.read()
    c = Collector(page_url)
    c.feed(h)
    # <style> 內的 url()（例如頁面專屬背景圖）也算圖片
    for block in re.findall(r'<style\b[^>]*>(.*?)</style>', h, re.S):
        for u in re.findall(r'url\(\s*["\']?([^"\')]+)', block):
            if not u.startswith('data:') and not u.endswith(('.woff2', '.woff', '.ttf')):
                c.images.append(c.url(u))
    c.raw = h
    return c


def pages():
    out = []
    for path in [os.path.join(ROOT, 'index.html')] + sorted(glob.glob(os.path.join(ROOT, '*', '**', 'index.html'), recursive=True)):
        rel = os.path.relpath(path, ROOT).replace(os.sep, '/')
        if rel.startswith(('_src/', '_tools/', 'wp-', 'assets/')):
            continue
        url = '/' + rel[:-len('index.html')]
        out.append((url, path))
    return out


def norm_text(parts):
    return re.sub(r'\s+', '', ''.join(parts))


def local_path(u):
    parts = urlsplit(u)
    if parts.netloc and parts.netloc != 'www.tosin.com.tw':
        return None
    p = unquote(parts.path)
    if p.endswith('/'):
        p += 'index.html'
    return os.path.join(ROOT, p.lstrip('/'))


def check_site():
    problems = []
    urls = [u for u, _ in pages()]
    for url, path in pages():
        c = collect(path, url)
        want = SITE + url
        if c.head['canonical'] != [want]:
            problems.append('%s canonical 錯誤：%s' % (url, c.head['canonical']))
        alt = c.head['alternate']
        if set(alt) != {'en', 'zh', 'x-default'}:
            problems.append('%s hreflang 不完整：%s' % (url, sorted(alt)))
        else:
            if alt['x-default'] != alt['en']:
                problems.append('%s x-default 不等於英文版' % url)
            if want not in (alt['en'], alt['zh']):
                problems.append('%s hreflang 沒有指向自己' % url)
            for v in alt.values():
                if not v.startswith(SITE + '/'):
                    problems.append('%s hreflang 不是絕對網址：%s' % (url, v))
                elif v[len(SITE):] not in urls:
                    problems.append('%s hreflang 指向不存在的頁：%s' % (url, v))
        for u in set(c.links + c.images + c.resources):
            if not u or u.startswith(('mailto:', 'tel:', 'data:', 'javascript:')):
                continue
            lp = local_path(u)
            if lp and not os.path.isfile(lp):
                problems.append('%s 站內連結/資源不存在：%s' % (url, u))
    # CSS 裡引用的字型與圖片
    for css in glob.glob(os.path.join(ROOT, 'assets', 'css', '*.css')):
        for u in re.findall(r'url\(\s*["\']?([^"\')]+)', open(css, encoding='utf-8').read()):
            if u.startswith('/') and not os.path.isfile(os.path.join(ROOT, u.lstrip('/'))):
                problems.append('%s 引用不存在的檔案：%s' % (os.path.basename(css), u))
    sm = open(os.path.join(ROOT, 'sitemap.xml'), encoding='utf-8').read()
    locs = re.findall(r'<loc>([^<]+)</loc>', sm)
    if sorted(locs) != sorted(SITE + u for u in urls) or len(locs) != 30:
        problems.append('sitemap 與頁面不一致：sitemap %d 筆、頁面 %d 頁' % (len(locs), len(urls)))
    print('頁數：%d，sitemap：%d 筆' % (len(urls), len(locs)))
    return problems


def multiset_diff(a, b):
    from collections import Counter
    ca, cb = Counter(a), Counter(b)
    return sorted((ca - cb).elements()), sorted((cb - ca).elements())


def compare(old_root):
    report = []
    for url, path in pages():
        old_path = os.path.join(old_root, url.lstrip('/'), 'index.html')
        o, n = collect(old_path, url), collect(path, url)
        lines = []
        title = lambda c: re.search(r'<title>(.*?)</title>', c.raw, re.S).group(1).strip()
        if title(o) != title(n):
            lines.append('  標題不同：舊「%s」 新「%s」' % (title(o), title(n)))
        ot, nt = norm_text(o.text), norm_text(n.text)
        if ot != nt:
            i = next((k for k in range(min(len(ot), len(nt))) if ot[k] != nt[k]), min(len(ot), len(nt)))
            lines.append('  文字不同（第 %d 字起）：舊「%s」 新「%s」' % (i, ot[i:i + 60], nt[i:i + 60]))
        removed, added = multiset_diff(o.images, n.images)
        if removed or added:
            lines.append('  圖片：少了 %s；多了 %s' % (removed, added))
        removed, added = multiset_diff(o.links, n.links)
        if removed or added:
            lines.append('  連結：少了 %s；多了 %s' % (removed, added))
        report.append((url, lines))
    return report


def main():
    if len(sys.argv) > 1:
        print('=== 新舊版逐頁比對 ===')
        for url, lines in compare(sys.argv[1]):
            print(url, '一致' if not lines else '')
            for l in lines:
                print(l)
    print('=== 網站自我檢查 ===')
    problems = check_site()
    for p in problems:
        print('問題：', p)
    print('沒有發現問題' if not problems else '共 %d 個問題' % len(problems))
    return 1 if problems else 0


if __name__ == '__main__':
    sys.exit(main())
