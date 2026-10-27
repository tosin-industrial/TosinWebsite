# -*- coding: utf-8 -*-
"""一次性工具：把 WordPress（Blocksy 主題＋Elementor）的 CSS 合併成 assets/css/ 下的檔案，
並刪掉 30 頁都用不到的規則。

用法：python tools/build_css.py <舊網站根目錄（main 分支 checkout）>
需先執行過 build.py（要掃描產生出來的 30 頁 HTML 有哪些 class/id）。

刪除規則的判斷很保守：
- 一個 selector 只要「必要」的 class 或 id 有任何一個沒在頁面（或 JS 會動態加上的清單）出現過，才算用不到；
- :not() / :is() / :where() / :has() 括號裡的東西、屬性選擇器、標籤名一律不當作刪除依據（寧可多留）；
- @font-face 只在字型家族有被引用、且 unicode-range 涵蓋到網站實際用到的字元時保留；
- @keyframes 只在名稱有被引用時保留。
"""
import glob
import os
import re
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

BLOCKSY = 'wp-content/themes/blocksy/static/bundle/'
EL = 'wp-content/plugins/elementor/assets/'
GF = 'wp-content/uploads/elementor/google-fonts/css/'

# 順序照原本 <head> 的載入順序；頁面專屬樣式（原本夾在 Elementor 核心與 widget 樣式之間）由 build.py 放在兩檔中間
SITE_PARTS = [
    ('inline', 'wp-img-auto-sizes-contain-inline-css'),
    ('file', 'wp-content/uploads/blocksy/css/global.css'),
    ('inline', 'global-styles-inline-css'),
    ('file', BLOCKSY + 'main.min.css'),
    ('file', BLOCKSY + 'page-title.min.css'),
    ('file', BLOCKSY + 'elementor-frontend.min.css'),
    ('file', EL + 'css/frontend.min.css'),
    ('kit', 'tools/kit.css'),
]
WIDGET_PARTS = [
    ('file', EL + 'css/widget-heading.min.css'),
    ('file', EL + 'lib/animations/styles/fadeIn.min.css'),
    ('file', EL + 'lib/animations/styles/fadeInUp.min.css'),
    ('file', EL + 'css/widget-image.min.css'),
    ('file', EL + 'lib/swiper/v8/css/swiper.min.css'),
    ('file', EL + 'css/conditionals/e-swiper.min.css'),
    ('file', EL + 'css/widget-image-carousel.min.css'),
    ('file', EL + 'lib/animations/styles/fadeInLeft.min.css'),
    ('file', EL + 'lib/animations/styles/fadeInRight.min.css'),
    ('file', EL + 'lib/animations/styles/fadeInDown.min.css'),
    ('file', EL + 'css/widget-google_maps.min.css'),
    ('file', EL + 'css/widget-icon-box.min.css'),
    ('file', EL + 'css/widget-icon-list.min.css'),
    ('file', EL + 'css/widget-spacer.min.css'),
    ('file', GF + 'notosans.css'),
    ('file', GF + 'notoserif.css'),
    ('file', GF + 'roboto.css'),
    ('file', GF + 'rubik.css'),
    ('file', GF + 'oswald.css'),
    ('inline', 'wp-custom-css'),
    # 以下三個原本是 Blocksy main.js 事後動態載入的
    ('file', BLOCKSY + 'non-critical-styles.min.css'),
    ('file', BLOCKSY + 'back-to-top.min.css'),
    ('file', BLOCKSY + 'non-critical-search-styles.min.css'),
]
NOSCRIPT_PARTS = [('file', BLOCKSY + 'no-scripts.min.css')]

# JS 執行時才會加上的 class（site.js、Swiper、Elementor 動畫）
DYNAMIC_CLASSES = {
    'active', 'ct-active', 'e-swiper-container', 'e-widget-swiper', 'dropdown-active', 'ct-show', 'animated', 'elementor-invisible',
    'fadeIn', 'fadeInUp', 'fadeInDown', 'fadeInLeft', 'fadeInRight',
}
DYNAMIC_PREFIXES = ('swiper-',)


# ---------- 簡易 CSS 解析 ----------

def strip_comments(css):
    out, i, n = [], 0, len(css)
    while i < n:
        c = css[i]
        if c in '"\'':
            j = i + 1
            while j < n and css[j] != c:
                j += 2 if css[j] == '\\' else 1
            out.append(css[i:j + 1])
            i = j + 1
        elif css.startswith('/*', i):
            j = css.find('*/', i + 2)
            i = n if j < 0 else j + 2
        else:
            out.append(c)
            i += 1
    return ''.join(out)


def find_block_end(css, i):
    """css[i] == '{'，回傳對應 '}' 的位置。"""
    depth, n = 0, len(css)
    while i < n:
        c = css[i]
        if c in '"\'':
            j = i + 1
            while j < n and css[j] != c:
                j += 2 if css[j] == '\\' else 1
            i = j
        elif c == '{':
            depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0:
                return i
        i += 1
    raise ValueError('大括號不成對')


def parse(css):
    """回傳節點清單：('stmt', text) / ('rule', selector, body) / ('at', prelude, children|None, body)"""
    nodes, i, n = [], 0, len(css)
    while i < n:
        while i < n and css[i] in ' \t\r\n;':
            i += 1
        if i >= n:
            break
        j = i
        while j < n and css[j] not in '{;':
            if css[j] in '"\'':
                q = css[j]
                j += 1
                while j < n and css[j] != q:
                    j += 2 if css[j] == '\\' else 1
            j += 1
        if j >= n:
            break
        prelude = css[i:j].strip()
        if css[j] == ';':
            nodes.append(('stmt', prelude + ';'))
            i = j + 1
            continue
        end = find_block_end(css, j)
        inner = css[j + 1:end]
        if prelude.startswith('@'):
            name = prelude[1:].split(None, 1)[0].split('(')[0].lower()
            if name in ('media', 'supports', 'container', 'layer', 'document', '-moz-document'):
                nodes.append(('at', prelude, parse(inner), None))
            else:
                nodes.append(('at', prelude, None, inner))
        else:
            nodes.append(('rule', prelude, inner))
        i = end + 1
    return nodes


def split_selectors(sel):
    parts, depth, cur, q = [], 0, [], None
    for c in sel:
        if q:
            cur.append(c)
            if c == q:
                q = None
            continue
        if c in '"\'':
            q = c
        elif c in '([':
            depth += 1
        elif c in ')]':
            depth -= 1
        elif c == ',' and depth == 0:
            parts.append(''.join(cur).strip())
            cur = []
            continue
        cur.append(c)
    parts.append(''.join(cur).strip())
    return [p for p in parts if p]


def required_tokens(selector):
    s = re.sub(r'\[[^\]]*\]', ' ', selector)
    # 去掉 :not(...) 等函式型偽類（可能巢狀），只看「一定要存在」的部分
    while True:
        m = re.search(r':{1,2}[\w-]+\(', s)
        if not m:
            break
        depth, k = 1, m.end()
        while k < len(s) and depth:
            depth += {'(': 1, ')': -1}.get(s[k], 0)
            k += 1
        s = s[:m.start()] + ' ' + s[k:]
    classes = set(re.findall(r'\.((?:\\.|[\w-])+)', s))
    ids = set(re.findall(r'#((?:\\.|[\w-])+)', s))
    unescape = lambda t: re.sub(r'\\(.)', r'\1', t)
    return {unescape(c) for c in classes}, {unescape(i) for i in ids}


class Pruner:
    def __init__(self, classes, ids):
        self.classes, self.ids = classes, ids
        self.removed = 0
        self.kept = 0

    def class_ok(self, c):
        return c in self.classes or c.startswith(DYNAMIC_PREFIXES)

    def selector_ok(self, sel):
        cls, ids = required_tokens(sel)
        return all(self.class_ok(c) for c in cls) and all(i in self.ids for i in ids)

    def prune(self, nodes):
        out = []
        for node in nodes:
            if node[0] == 'rule':
                sels = split_selectors(node[1])
                keep = [s for s in sels if self.selector_ok(s)]
                self.removed += len(sels) - len(keep)
                if keep and node[2].strip():
                    self.kept += len(keep)
                    out.append(('rule', ','.join(keep), node[2]))
            elif node[0] == 'at' and node[2] is not None:
                children = self.prune(node[2])
                if children:
                    out.append(('at', node[1], children, None))
            else:
                out.append(node)
        return out


def serialize(nodes):
    out = []
    for node in nodes:
        if node[0] == 'stmt':
            out.append(node[1])
        elif node[0] == 'rule':
            out.append('%s{%s}' % (node[1], node[2].strip()))
        elif node[2] is not None:
            out.append('%s{%s}' % (node[1], serialize(node[2])))
        else:
            out.append('%s{%s}' % (node[1], node[3].strip()))
    return '\n'.join(out)


def walk(nodes):
    for node in nodes:
        yield node
        if node[0] == 'at' and node[2] is not None:
            for x in walk(node[2]):
                yield x


def filter_at(nodes, keep):
    out = []
    for node in nodes:
        if node[0] == 'at' and node[2] is not None:
            ch = filter_at(node[2], keep)
            if ch:
                out.append(('at', node[1], ch, None))
        elif node[0] == 'at' and not keep(node):
            continue
        else:
            out.append(node)
    return out


# ---------- 讀取來源 ----------

def inline_style(old_root, style_id):
    # 材料頁是較新的版本（多一條規則），以它為準
    h = open(os.path.join(old_root, 'material', 'index.html'), encoding='utf-8').read()
    m = re.search(r"<style id=['\"]%s['\"][^>]*>(.*?)</style>" % re.escape(style_id), h, re.S)
    return m.group(1)


def rewrite_css_urls(css, src_rel, fonts):
    base = os.path.dirname(src_rel)

    def fix(m):
        q, u = m.group(1), m.group(2).strip()
        if u.startswith('https://www.tosin.com.tw/'):
            u = '/' + u[len('https://www.tosin.com.tw/'):]
        if u.startswith('/'):
            u = os.path.relpath(u.lstrip('/'), base)
        if u.startswith(('data:', 'http:', 'https:', '//', '#')):
            return m.group(0)
        path = os.path.normpath(os.path.join(base, u.split('?')[0].split('#')[0])).replace(os.sep, '/')
        if re.search(r'\.(woff2?|ttf|otf|eot)$', path):
            fonts[os.path.basename(path)] = path
            return 'url(%s/assets/fonts/%s%s)' % (q, os.path.basename(path), q)
        return 'url(%s/%s%s)' % (q, path, q)
    return re.sub(r'''url\(\s*(["']?)([^"')]+)\1\s*\)''', fix, css)


def load_parts(old_root, parts, fonts):
    chunks = []
    for kind, ref in parts:
        if kind == 'file':
            css = open(os.path.join(old_root, ref), encoding='utf-8').read()
            css = rewrite_css_urls(css, ref, fonts)
        elif kind == 'kit':
            css = open(os.path.join(ROOT, ref), encoding='utf-8').read()
        else:
            css = inline_style(old_root, ref)
        chunks.append(strip_comments(css))
    return '\n'.join(chunks)


# ---------- 掃描頁面 ----------

def scan_pages():
    classes, ids, text_chars, blob = set(), set(), set(), []
    files = [os.path.join(ROOT, 'index.html')] + glob.glob(os.path.join(ROOT, '*', '**', 'index.html'), recursive=True)
    files = [f for f in files if '/wp-' not in f.replace(os.sep, '/') and not f.replace(os.sep, '/').startswith(ROOT.replace(os.sep, '/') + '/src/')]
    js = [os.path.join(ROOT, 'assets', 'js', 'site.js')]
    for f in files + js:
        h = open(f, encoding='utf-8').read()
        blob.append(h)
        for v in re.findall(r'\sclass=["\']([^"\']*)["\']', h):
            classes.update(v.split())
        ids.update(re.findall(r'\sid=["\']([^"\']+)["\']', h))
        # <script> 裡出現的字（材料頁表格、site.js）都當作可能的 class/id
        for s in re.findall(r'<script\b[^>]*>(.*?)</script>', h, re.S) if f.endswith('.html') else [h]:
            words = set(re.findall(r'[A-Za-z_][\w-]*', s))
            classes.update(words)
            ids.update(words)
        text = re.sub(r'<(script|style)\b.*?</\1>', ' ', h, flags=re.S)
        text = re.sub(r'<[^>]+>', ' ', text)
        text = re.sub(r'&#(\d+);', lambda m: chr(int(m.group(1))), text)
        text_chars.update(text)
    classes |= DYNAMIC_CLASSES
    return classes, ids, text_chars, '\n'.join(blob), len(files)


def parse_unicode_range(value):
    ranges = []
    for part in value.split(','):
        part = part.strip().upper().replace('U+', '')
        if '-' in part:
            a, b = part.split('-')
            ranges.append((int(a, 16), int(b, 16)))
        elif '?' in part:
            ranges.append((int(part.replace('?', '0'), 16), int(part.replace('?', 'F'), 16)))
        elif part:
            ranges.append((int(part, 16), int(part, 16)))
    return ranges


def build(old_root, parts, out_name, classes, ids, chars, page_blob, fonts):
    css = load_parts(old_root, parts, fonts)
    nodes = parse(css)
    pruner = Pruner(classes, ids)
    nodes = pruner.prune(nodes)
    return nodes, pruner


def finalize(nodes_by_file, page_blob, chars, used_fonts):
    all_text = page_blob + '\n'.join(serialize(n) for n in nodes_by_file.values())
    codepoints = {ord(c) for c in chars}

    def keep_at(node):
        prelude = node[1].lower()
        body = node[3] or ''
        if prelude.startswith('@font-face'):
            fam = re.search(r'font-family:\s*([\'"]?)([^;\'"]+)\1', body)
            family = fam.group(2).strip() if fam else ''
            others = re.sub(r'@font-face\s*\{[^}]*\}', '', all_text)
            if family and family not in others:
                return False
            rng = re.search(r'unicode-range:\s*([^;]+)', body)
            if rng:
                ranges = parse_unicode_range(rng.group(1))
                if not any(a <= cp <= b for cp in codepoints for a, b in ranges):
                    return False
            for u in re.findall(r'/assets/fonts/([^)\'"]+)', body):
                used_fonts.add(u)
            return True
        if '@keyframes' in prelude:
            name = node[1].split()[-1]
            others = all_text.replace(node[1], '')
            return re.search(r'(?<![\w-])%s(?![\w-])' % re.escape(name), others) is not None
        return True
    return {k: filter_at(v, keep_at) for k, v in nodes_by_file.items()}


def main():
    old_root = sys.argv[1]
    classes, ids, chars, blob, npages = scan_pages()
    print('掃描頁面：%d 頁，class %d 種，id %d 種' % (npages, len(classes), len(ids)))
    fonts = {}
    targets = {'site.css': SITE_PARTS, 'widgets.css': WIDGET_PARTS, 'no-scripts.css': NOSCRIPT_PARTS}
    nodes_by_file, stats = {}, {}
    for name, parts in targets.items():
        nodes, pr = build(old_root, parts, name, classes, ids, chars, blob, fonts)
        nodes_by_file[name] = nodes
        before = sum(os.path.getsize(os.path.join(old_root, r)) for k, r in parts if k == 'file')
        stats[name] = (before, pr.kept, pr.removed)
    used_fonts = set()
    nodes_by_file = finalize(nodes_by_file, blob, chars, used_fonts)
    os.makedirs(os.path.join(ROOT, 'assets', 'css'), exist_ok=True)
    header = '/* 由 tools/build_css.py 從原 WordPress（Blocksy 2.1 + Elementor 3.35）樣式合併精簡而成。 */\n'
    for name, nodes in nodes_by_file.items():
        out = header + serialize(nodes) + '\n'
        with open(os.path.join(ROOT, 'assets', 'css', name), 'w', encoding='utf-8', newline='\n') as f:
            f.write(out)
        b, k, r = stats[name]
        print('%-15s 原始檔案 %7d bytes → %7d bytes（保留 selector %d、刪除 %d）' % (name, b, len(out.encode()), k, r))
    font_dir = os.path.join(ROOT, 'assets', 'fonts')
    os.makedirs(font_dir, exist_ok=True)
    for name in sorted(used_fonts):
        shutil.copyfile(os.path.join(old_root, fonts[name]), os.path.join(font_dir, name))
    print('字型檔：引用 %d 個，保留 %d 個' % (len(fonts), len(used_fonts)))
    left = re.findall(r'url\(([^)]*)\)', ''.join(open(os.path.join(ROOT, 'assets', 'css', n), encoding='utf-8').read() for n in targets))
    print('其他 url() 引用：', sorted({u for u in left if '/assets/fonts/' not in u and not u.strip('\'"').startswith('data:')}))


if __name__ == '__main__':
    main()
