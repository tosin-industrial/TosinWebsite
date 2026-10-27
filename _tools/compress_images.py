# -*- coding: utf-8 -*-
"""一次性工具：壓縮超過 300KB 的 JPG／PNG（需要 Pillow）。

用法：python _tools/compress_images.py
- 檔名、路徑不變（保留 Google 圖片收錄）
- 寬度不超過網頁上最大顯示寬度的約 2 倍、上限 2000px，絕不放大
- JPEG 品質 82、progressive，保留 ICC 色彩描述檔，去掉其他 EXIF
- 壓完沒有變小就保留原檔
最大顯示寬度是用無頭瀏覽器在 390～2560px 六種視窗寬度量測的結果；
燈箱（點圖放大）會用到原圖的，最大顯示寬度視為整個螢幕，只重新壓縮不縮小。
"""
import io
import os

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIMIT = 300 * 1024
MAX_WIDTH = 2000
QUALITY = 82

# 檔案：(最大顯示寬度 CSS px, 說明)；None 表示用於燈箱或全幅背景，只壓縮不縮小（仍受 2000px 上限）
DISPLAY = {
    'wp-content/uploads/2024/01/Building-2-scaled.jpg': (None, '全幅背景（最寬 2560px 視窗）'),
    'wp-content/uploads/2024/01/Building-1-scaled.jpg': (None, '全幅背景（最寬 2560px 視窗）'),
    'wp-content/uploads/2026/03/Reach_RoHS_Declartion-2026-scaled.jpg': (None, '證書，燈箱大圖'),
    'wp-content/uploads/2026/03/ISO9001_2026-scaled.jpg': (None, '證書，燈箱大圖'),
    'wp-content/uploads/2026/03/IATF16949_2026-scaled.jpg': (None, '證書，燈箱大圖'),
    'wp-content/uploads/2024/02/AOI_3.jpg': (657, '背景 cover，框 370×413'),
    'wp-content/uploads/2024/01/CNC4.jpg': (572, '背景 cover，框 370×349'),
    'wp-content/uploads/2025/09/slice_1.jpg': (370, '背景 cover，框 370×200'),
    'wp-content/uploads/2025/09/curing_1.jpg': (642, '內文圖片'),
    'wp-content/uploads/2025/09/air_1.jpg': (633, '內文圖片'),
    'wp-content/uploads/2025/09/cutting-Machine_1.jpg': (None, '輪播燈箱大圖'),
    'wp-content/uploads/2025/09/aoi_2.jpg': (None, '輪播燈箱大圖'),
    'wp-content/uploads/2025/09/curing_2.jpg': (None, '輪播燈箱大圖'),
    'wp-content/uploads/2025/09/cutting-Machine_2.jpg': (None, '燈箱大圖＋背景'),
}


def target_width(width, shown):
    limit = MAX_WIDTH if shown is None else min(MAX_WIDTH, int(round(shown * 2 / 10.0)) * 10)
    return min(width, limit)


def compress(path, shown):
    with open(path, 'rb') as f:
        original = f.read()
    im = Image.open(io.BytesIO(original))
    icc = im.info.get('icc_profile')
    fmt = im.format
    w, h = im.size
    tw = target_width(w, shown)
    if tw < w:
        im = im.resize((tw, int(round(h * tw / float(w)))), Image.LANCZOS)
    out = io.BytesIO()
    if fmt == 'JPEG':
        if im.mode not in ('RGB', 'L'):
            im = im.convert('RGB')
        im.save(out, 'JPEG', quality=QUALITY, optimize=True, progressive=True, icc_profile=icc)
    elif fmt == 'PNG':
        im.save(out, 'PNG', optimize=True, icc_profile=icc)
    else:
        return len(original), len(original), (w, h), (w, h)
    data = out.getvalue()
    if len(data) >= len(original):
        return len(original), len(original), (w, h), (w, h)
    with open(path, 'wb') as f:
        f.write(data)
    return len(original), len(data), (w, h), im.size


def main():
    rows = []
    for rel, (shown, note) in sorted(DISPLAY.items()):
        path = os.path.join(ROOT, rel)
        if os.path.getsize(path) <= LIMIT:
            continue
        before, after, size0, size1 = compress(path, shown)
        rows.append((rel, before, after, size0, size1, note))
    total0 = total1 = 0
    for rel, b, a, s0, s1, note in rows:
        total0 += b
        total1 += a
        print('%-62s %4dKB → %4dKB  %4dx%-4d → %4dx%-4d  %s' % ('/' + rel, b // 1024, a // 1024, s0[0], s0[1], s1[0], s1[1], note))
    print('合計 %d 張：%.1fMB → %.1fMB' % (len(rows), total0 / 1048576.0, total1 / 1048576.0))


if __name__ == '__main__':
    main()
