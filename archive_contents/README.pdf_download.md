
# PDF Auto-download + Product Suffix

After `click_arrange_print`, the script now waits for the PDF tab, downloads the PDF using session cookies, and names it:
`<original>--<product>.pdf` (product value comes from `--product`).

Flags:
- `--download-pdf-dir DIR`  (default: downloads)
- `--no-pdf-download`
- `--no-append-product`

Example:
```
python main.py --product "G-BOX-FD-JELLO-PEACH-L" --download-pdf-dir labels
```
