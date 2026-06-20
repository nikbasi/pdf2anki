"""CLI entry point for pdf2anki."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import os

import typer
from rich.console import Console
from rich.table import Table

from pdf2anki.anki_export import export_apkg, export_json, load_json_cards
from pdf2anki.berlitz import extract_berlitz_cards
from pdf2anki.config import load_config, save_config
from pdf2anki.generator import generate_cards
from pdf2anki.models import BookConfig
from pdf2anki.pdf_reader import extract_chapters

DEFAULT_LMSTUDIO_URL = "http://127.0.0.1:1234/v1"
DEFAULT_LMSTUDIO_MODEL = "gemma-4-26b-a4b-it-heretic"

app = typer.Typer(
    name="pdf2anki",
    help="Create Anki flashcards from PDF language-learning books, chapter by chapter.",
    no_args_is_help=True,
)
console = Console()


@app.command("init-config")
def init_config(
    output: Path = typer.Option(
        Path("book.yaml"),
        "--output",
        "-o",
        help="Path to write example config",
    ),
    source_lang: str = typer.Option("fi", "--source", "-s", help="Source language code (e.g. fi)"),
    target_lang: str = typer.Option("en", "--target", "-t", help="Target language code (e.g. en)"),
    deck_name: str = typer.Option("Finnish Book", "--deck", help="Anki deck name"),
) -> None:
    """Write an example YAML config for your book."""
    config = BookConfig(
        title=deck_name,
        deck_name=deck_name,
        source_language=source_lang,
        target_language=target_lang,
        extra_prompt="Focus on practical vocabulary and example sentences from dialogues.",
    )
    save_config(config, output)
    console.print(f"[green]Wrote config to[/green] {output}")
    console.print("Edit chapter page ranges under `chapters:` if auto-detection misses headings.")


@app.command("preview")
def preview(
    pdf: Path = typer.Argument(..., help="Path to PDF book", exists=True),
    config_path: Optional[Path] = typer.Option(None, "--config", "-c", help="YAML config"),
) -> None:
    """Preview detected chapters without generating cards."""
    config = load_config(config_path)
    chapters = extract_chapters(pdf, config)

    table = Table(title=f"Chapters in {pdf.name}")
    table.add_column("#", style="dim")
    table.add_column("Title")
    table.add_column("Pages")
    table.add_column("Chars", justify="right")

    for i, ch in enumerate(chapters, 1):
        table.add_row(str(i), ch.title, f"{ch.page_start}–{ch.page_end}", str(len(ch.text)))

    console.print(table)
    console.print(f"\n[bold]{len(chapters)}[/bold] chapters detected.")


@app.command("extract")
def extract_cmd(
    pdf: Path = typer.Argument(..., help="Path to PDF book", exists=True),
    output: Path = typer.Option(Path("chapters.json"), "--output", "-o"),
    config_path: Optional[Path] = typer.Option(None, "--config", "-c"),
) -> None:
    """Extract chapter text to JSON (for inspection or manual editing)."""
    config = load_config(config_path)
    chapters = extract_chapters(pdf, config)
    payload = [c.model_dump() for c in chapters]
    output.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    console.print(f"[green]Wrote {len(chapters)} chapters to[/green] {output}")


@app.command("generate")
def generate_cmd(
    pdf: Path = typer.Argument(..., help="Path to PDF book", exists=True),
    output: Path = typer.Option(Path("deck.apkg"), "--output", "-o"),
    config_path: Optional[Path] = typer.Option(None, "--config", "-c"),
    chapter: Optional[str] = typer.Option(
        None,
        "--chapter",
        help="Only generate cards for chapters matching this substring",
    ),
    model: str = typer.Option("gpt-4o-mini", "--model", "-m"),
    api_key: Optional[str] = typer.Option(None, "--api-key", envvar="OPENAI_API_KEY"),
    base_url: Optional[str] = typer.Option(None, "--base-url", envvar="OPENAI_BASE_URL"),
    json_only: bool = typer.Option(False, "--json-only", help="Save cards as JSON instead of .apkg"),
    cards_json: Optional[Path] = typer.Option(
        None,
        "--cards-json",
        help="Also save intermediate cards JSON at this path",
    ),
    mode: str = typer.Option(
        "auto",
        "--mode",
        help="Card generation: auto (LLM if API key set, else berlitz), llm, berlitz",
    ),
) -> None:
    """Generate Anki deck from a PDF book."""
    config = load_config(config_path)
    chapters = extract_chapters(pdf, config)

    if chapter:
        chapters = [c for c in chapters if chapter.lower() in c.title.lower()]
        if not chapters:
            console.print(f"[red]No chapters matching '{chapter}'[/red]")
            raise typer.Exit(1)

    use_llm = mode == "llm" or (
        mode == "auto"
        and (api_key or os.environ.get("OPENAI_API_KEY") or base_url or os.environ.get("OPENAI_BASE_URL"))
    )
    use_berlitz = mode == "berlitz" or (mode == "auto" and not use_llm)

    if use_llm and not base_url and not os.environ.get("OPENAI_BASE_URL") and not api_key and not os.environ.get("OPENAI_API_KEY"):
        base_url = DEFAULT_LMSTUDIO_URL
    if use_llm and model == "gpt-4o-mini" and (base_url == DEFAULT_LMSTUDIO_URL or os.environ.get("OPENAI_BASE_URL") == DEFAULT_LMSTUDIO_URL):
        model = DEFAULT_LMSTUDIO_MODEL

    console.print(f"Generating cards for [bold]{len(chapters)}[/bold] chapter(s)...")
    if use_llm and not use_berlitz:
        effective_url = base_url or os.environ.get("OPENAI_BASE_URL") or DEFAULT_LMSTUDIO_URL
        console.print(f"Using LLM ([dim]{model}[/dim] @ {effective_url})")
        cards = []
        for idx, ch in enumerate(chapters, 1):
            console.print(f"  [{idx}/{len(chapters)}] {ch.title[:60]}...")
            try:
                chapter_cards = generate_cards(
                    [ch],
                    config,
                    model=model,
                    api_key=api_key or "lm-studio",
                    base_url=effective_url,
                )
            except Exception as exc:
                console.print(f"       [red]failed: {exc}[/red]")
                if cards_json and cards:
                    export_json(cards, cards_json)
                    console.print(f"       saved partial progress to {cards_json}")
                raise
            console.print(f"       → {len(chapter_cards)} cards")
            cards.extend(chapter_cards)
            if cards_json:
                export_json(cards, cards_json)
    else:
        console.print("Using Berlitz rule-based extraction ([dim]no API key required[/dim])")
        cards = []
        for ch in chapters:
            cards.extend(extract_berlitz_cards(ch))
    console.print(f"Created [bold]{len(cards)}[/bold] cards.")

    if cards_json:
        export_json(cards, cards_json)
        console.print(f"Saved cards JSON to {cards_json}")

    if json_only:
        json_out = output if output.suffix == ".json" else output.with_suffix(".json")
        export_json(cards, json_out)
        console.print(f"[green]Wrote[/green] {json_out}")
    else:
        export_apkg(cards, config, output)
        console.print(f"[green]Wrote Anki deck to[/green] {output}")
        console.print("Import it in Anki: File → Import → select the .apkg file")


@app.command("export")
def export_cmd(
    cards_json: Path = typer.Argument(..., help="Cards JSON from a previous run", exists=True),
    output: Path = typer.Option(Path("deck.apkg"), "--output", "-o"),
    config_path: Optional[Path] = typer.Option(None, "--config", "-c"),
    deck_name: Optional[str] = typer.Option(None, "--deck", help="Override deck name"),
) -> None:
    """Export previously generated cards JSON to an Anki .apkg file."""
    config = load_config(config_path)
    if deck_name:
        config.deck_name = deck_name
    cards = load_json_cards(cards_json)
    export_apkg(cards, config, output)
    console.print(f"[green]Wrote Anki deck to[/green] {output}")


if __name__ == "__main__":
    app()
