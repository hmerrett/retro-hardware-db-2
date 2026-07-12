# Label font

Drop a TrueType font (`.ttf`) here and point `label.font_path` in `config.yml`
at it to style the **asset number + title** on printed labels.

Expected by default: **`Audiowide-Regular.ttf`**

- Get it from Google Fonts (search "Audiowide") — it's licensed under the SIL
  Open Font License (OFL).
- If you commit the font to a public repo, drop its `OFL.txt` alongside it.
- If this file is missing, labels fall back to Helvetica automatically (no error).

The body/spec lines stay in a plain sans for legibility; change
`render_label()` in `scripts/make_labels.py` if you want the whole label in the
display font.
