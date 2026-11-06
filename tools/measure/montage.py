"""Joins screenshots into one contact sheet: montage.py out.png in1.png in2.png ... [--cols 4] [--width 560]  (for the review folders)."""
import argparse

from PIL import Image

ap = argparse.ArgumentParser()
ap.add_argument('out')
ap.add_argument('inputs', nargs='+')
ap.add_argument('--cols', type=int, default=4)
ap.add_argument('--width', type=int, default=560)
a = ap.parse_args()
ims = []
for path in a.inputs:
    im = Image.open(path).convert('RGB')
    ims.append(im.resize((a.width, round(im.height * a.width / im.width))))
h = max(i.height for i in ims)
rows = (len(ims) + a.cols - 1) // a.cols
sheet = Image.new('RGB', (a.cols * a.width, rows * h), (20, 20, 20))
for n, im in enumerate(ims):
    sheet.paste(im, ((n % a.cols) * a.width, (n // a.cols) * h))
sheet.save(a.out)
print('đã ghi', a.out, sheet.size)
