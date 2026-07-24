"""Regenerate the favicon / app-icon set from the master artwork.

Run it inside the api image (which has Pillow) with the static dir mounted:

    docker run --rm -v "$PWD/api/app/static:/static" \
        retro-hardware-db-2-api python /static/../../../tools/make_icons.py

or, more simply, from the repo root:

    docker run --rm -v "$PWD/api/app/static:/static" \
        -v "$PWD/tools:/tools" retro-hardware-db-2-api python /tools/make_icons.py

It crops the master to its solid content (ignoring any soft drop-shadow in the
transparent padding), squares it, and writes every size the pages reference.
Rebuild the api image afterwards so the files are copied in.
"""
from PIL import Image

STATIC = "/static"
MASTER = f"{STATIC}/app-icon.png"
# Alpha below this is treated as empty padding (excludes soft shadows), so the
# icon is cropped to its solid artwork rather than the shadow's faint halo.
ALPHA_THRESHOLD = 32


def load_tight_square():
    base = Image.open(MASTER).convert("RGBA")
    mask = base.getchannel("A").point(lambda v: 255 if v > ALPHA_THRESHOLD else 0)
    bbox = mask.getbbox()
    icon = base.crop(bbox) if bbox else base
    w, h = icon.size
    s = max(w, h)
    sq = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    sq.paste(icon, ((s - w) // 2, (s - h) // 2), icon)
    return sq


def main():
    sq = load_tight_square()
    print(f"cropped+squared master to {sq.size}")

    def out(size, name, white=False):
        im = sq.resize((size, size), Image.LANCZOS)
        if white:  # iOS composites transparency on black, so flatten on white
            bg = Image.new("RGBA", (size, size), (255, 255, 255, 255))
            im = Image.alpha_composite(bg, im).convert("RGB")
        im.save(f"{STATIC}/{name}", optimize=True)

    out(16, "favicon-16x16.png")
    out(32, "favicon-32x32.png")
    out(180, "apple-touch-icon.png", white=True)
    out(192, "icon-192.png")
    out(512, "icon-512.png")
    sq.save(f"{STATIC}/favicon.ico", format="ICO", sizes=[(16, 16), (32, 32), (48, 48)])
    print("regenerated favicon.ico + png icons")


if __name__ == "__main__":
    main()
