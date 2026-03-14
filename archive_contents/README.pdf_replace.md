
# PDF Replace Text (Chinese overlay)

After labels are downloaded, the script overlays translated product lines onto the PDF using ReportLab.
- Default mapping: `replacements.json` (edit to update)
- Font: `simsun.ttf` (put a valid Chinese TTF in the project root); falls back to Helvetica if missing.

CLI (defaults enabled):
- `--pdf-replace` (on by default)
- `--pdf-replace-json replacements.json`
- `--pdf-font simsun.ttf`

Example run:
```
python main.py --product "G-BOX-FD-JELLO-PEACH-L" --download-pdf-dir labels
```
