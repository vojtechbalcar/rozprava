# Rozprava

Search and read Czech parliamentary transcripts. The current build is an interactive
design preview using real, cached psp.cz excerpts.

```sh
uv sync
uv run python scripts/render_preview.py
python3 -m http.server 8000 --bind 127.0.0.1 --directory preview/site
```

Open [the preview](http://127.0.0.1:8000/) or [component review](http://127.0.0.1:8000/_design/).
Design source: [DESIGN.md](DESIGN.md). Implementation status: [design-preview](docs/design-preview.md).

```sh
uv run pytest
uv run ruff check .
uv run pyright
uv run python scripts/build_tokens.py --check
```
