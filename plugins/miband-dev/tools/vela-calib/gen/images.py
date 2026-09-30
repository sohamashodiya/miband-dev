#!/usr/bin/env python3
"""Test images for the calibration kit's Images and Animation pages (src/common/img/).

Every file is small and exactly specified, so measure.py can compare what the band draws with
what the file holds. Run through `npm run gen` (before gen.mjs).
"""
import os
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, '..', 'src', 'common', 'img')
os.makedirs(OUT, exist_ok=True)


def save(im, name, **kw):
    im.save(os.path.join(OUT, name), **kw)


def checker(n=32):
    """1 px white lines every 4 px on black, with a 1 px white border: shows resampling."""
    im = Image.new('RGBA', (n, n), (0, 0, 0, 255))
    px = im.load()
    for y in range(n):
        for x in range(n):
            if x % 4 == 0 or y % 4 == 0 or x == n - 1 or y == n - 1:
                px[x, y] = (255, 255, 255, 255)
    return im


def disc(n=64, aa=4):
    """White disc with an anti-aliased alpha edge on transparent (drawn 4x, downsampled)."""
    big = Image.new('L', (n * aa, n * aa), 0)
    ImageDraw.Draw(big).ellipse((2 * aa, 2 * aa, (n - 2) * aa - 1, (n - 2) * aa - 1), fill=255)
    a = big.resize((n, n), Image.LANCZOS)
    im = Image.new('RGBA', (n, n), (255, 255, 255, 0))
    im.putalpha(a)
    return im


def main():
    c = checker(32)
    save(c, 'checker32.png')                                   # 32-bit RGBA
    save(c.convert('RGB').convert('P', palette=Image.ADAPTIVE, colors=2), 'checker32_p8.png')  # PNG8
    save(c.convert('L'), 'checker32_l.png')                    # 8-bit greyscale

    d = disc(64)
    save(d, 'disc64.png')                                      # RGBA, soft alpha edge
    # PNG8 with a tRNS alpha table (palette alpha): 16 alpha levels
    q = Image.new('P', (64, 64))
    pal = []
    for i in range(16):
        pal += [255, 255, 255]
    q.putpalette(pal + [0, 0, 0] * (256 - 16))
    a = d.getchannel('A')
    q.putdata([min(15, round(v / 17)) for v in a.getdata()])
    save(q, 'disc64_p8.png', transparency=bytes(i * 17 for i in range(16)))
    # Hard-edged disc (alpha 0/255 only)
    save(Image.merge('RGBA', (d.getchannel('R'), d.getchannel('G'), d.getchannel('B'),
                              a.point(lambda v: 255 if v >= 128 else 0))), 'disc64_hard.png')

    # Alpha ramp 128 x 16: white, alpha 0 at the left to 255 at the right (linear per column)
    r = Image.new('RGBA', (128, 16))
    r.putdata([(255, 255, 255, round(x * 255 / 127)) for y in range(16) for x in range(128)])
    save(r, 'alpha_ramp.png')
    # Grey ramp as RGB (no alpha) 128 x 16: 0..255 per column, the photo reference for alpha_ramp
    g = Image.new('RGB', (128, 16))
    g.putdata([(round(x * 255 / 127),) * 3 for y in range(16) for x in range(128)])
    save(g, 'grey_ramp.png')

    # Wide stripe 64 x 32 for object-fit: white, 2 px pink border so the drawn extent is obvious
    w = Image.new('RGB', (64, 32), (255, 255, 255))
    dr = ImageDraw.Draw(w)
    dr.rectangle((0, 0, 63, 31), outline=(255, 45, 149), width=2)
    save(w, 'wide64x32.png')
    # Patterned 64 x 32 for object-fit cover (kit 2.0.0): black with a white block over source
    # columns 16-31, full height. fill -> white at +16, 16 x 64; cover (2x, centre 32 columns kept)
    # -> +0, 32 x 64; contain -> +16, 16 x 32 at +16. A plain image draws the same bbox for all.
    q = Image.new('RGB', (64, 32), (0, 0, 0))
    ImageDraw.Draw(q).rectangle((16, 0, 31, 31), fill=(255, 255, 255))
    save(q, 'wide64x32_q.png')

    # Animation lane squares: two byte-identical copies, so a src swap changes nothing visible
    sq = Image.new('RGBA', (24, 24), (255, 255, 255, 255))
    save(sq, 'sq_a.png')
    save(sq, 'sq_b.png')

    # App icon: black tile with a yellow ruler and a white 8
    ic = Image.new('RGB', (128, 128), (0, 0, 0))
    dr = ImageDraw.Draw(ic)
    for i in range(0, 128, 8):
        dr.rectangle((8, i, 8 + (24 if i % 32 == 0 else 12), i + 1), fill=(255, 214, 10) if i % 32 == 0 else (255, 255, 255))
    dr.ellipse((56, 22, 104, 62), outline=(255, 255, 255), width=10)
    dr.ellipse((52, 58, 108, 108), outline=(255, 255, 255), width=10)
    ic.save(os.path.join(HERE, '..', 'src', 'common', 'logo.png'))


if __name__ == '__main__':
    main()
