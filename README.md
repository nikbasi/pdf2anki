# pdf2anki

Create Anki flashcards from PDF language-learning books, one deck per book with tags for each chapter.

Designed for language learners: extract vocabulary, phrases, example sentences, and grammar notes from textbook chapters using an LLM, then export a ready-to-import `.apkg` deck.

## Install

```bash
cd pdf2anki
pip install -e .
```

Set your OpenAI API key (or any OpenAI-compatible endpoint):

```bash
export OPENAI_API_KEY="sk-..."
# Optional: use Ollama, LiteLLM, etc.
# export OPENAI_BASE_URL="http://localhost:11434/v1"
```

## Quick start (Finnish example)

```bash
# 1. Create a config for your book
pdf2anki init-config -s fi -t en --deck "Suomen kieli" -o finnish.yaml

# 2. Preview how chapters are detected
pdf2anki preview my-finnish-book.pdf -c finnish.yaml

# 3. Generate cards for the whole book
pdf2anki generate my-finnish-book.pdf -c finnish.yaml -o suomi.apkg

# Or just one chapter
pdf2anki generate my-finnish-book.pdf -c finnish.yaml --chapter "Luku 3" -o luku3.apkg
```

Import `suomi.apkg` in Anki via **File → Import**.

## Commands

| Command | Description |
|---------|-------------|
| `init-config` | Write an example YAML config |
| `preview` | List detected chapters and text length |
| `extract` | Save chapter text to JSON |
| `generate` | Create flashcards + `.apkg` deck |
| `export` | Convert saved cards JSON to `.apkg` |

## Config file

Example `finnish.yaml`:

```yaml
title: "Suomen kieli"
deck_name: "Suomen kieli"
source_language: fi
target_language: en
cards_per_chapter: 30
extra_prompt: "Include case forms for nouns. Prefer dialogue vocabulary."

# Auto-detection looks for headings like "Luku 1", "Chapter 1", "Kappale 2".
# If your book uses different layout, define chapters manually:
chapters:
  - title: "Luku 1 - Tervetuloa"
    page_start: 7
    page_end: 24
  - title: "Luku 2 - Perhe"
    page_start: 25
    page_end: 42
```

## Card types

Each card includes chapter and type tags for filtered study:

- **vocabulary** — word → translation + usage note
- **phrase** — expression → translation
- **sentence** — example sentence → translation
- **grammar** — pattern → explanation + examples

## Workflow tips

1. Run `preview` first. If chapters look wrong, add manual `chapters:` page ranges.
2. Use `--chapter "Luku 1"` to test one chapter before processing the full book.
3. Save intermediate output with `--cards-json cards.json` so you can re-export without calling the API again.
4. Review/edit `cards.json` manually, then `pdf2anki export cards.json -o deck.apkg`.

## Requirements

- Python 3.10+
- OpenAI API key (or compatible API via `OPENAI_BASE_URL`)
- A PDF with selectable text (scanned images need OCR first)
