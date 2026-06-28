"""CLI entry point for pdf2anki."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional

import os
import time

import typer
from rich.console import Console
from rich.table import Table

from pdf2anki.anki_export import export_apkg, export_colpkg, export_json, export_multideck_apkg, load_json_cards
from pdf2anki.berlitz import extract_berlitz_cards
from pdf2anki.config import load_config, save_config
from pdf2anki.generator import generate_cards
from pdf2anki.local_profile import profile_for_model
from pdf2anki.lmstudio import ensure_model_loaded, ensure_server
from pdf2anki.models import BookConfig, GenerationStyle
from pdf2anki.pdf_reader import extract_chapters
from pdf2anki.tags import chapter_deck_name, chapter_filename_slug, chapter_label

DEFAULT_LMSTUDIO_URL = "http://127.0.0.1:1234/v1"
# Gemma fits 24 GB RAM reliably; Qwen works but uses tighter batch limits automatically.
DEFAULT_LMSTUDIO_MODEL = "gemma-4-26b-a4b-it-heretic"

app = typer.Typer(
    name="pdf2anki",
    help="Create Anki flashcards from PDF language-learning books, chapter by chapter.",
    no_args_is_help=True,
)
console = Console()


def _book_slug(name: str) -> str:
    slug = re.sub(r"[^\w\s-]", "", name.lower())
    slug = re.sub(r"[\s_]+", "-", slug.strip())
    return re.sub(r"-+", "-", slug).strip("-") or "deck"


def _deck_output_dir(output: Path) -> Path:
    """When writing one deck per chapter, -o is a directory (or deck.apkg → deck/)."""
    if output.suffix == ".apkg":
        return output.parent / output.stem
    return output


def _chapter_apkg_path(output_dir: Path, config: BookConfig, chapter_title: str) -> Path:
    slug = chapter_filename_slug(chapter_title)
    return output_dir / f"{_book_slug(config.deck_name)}-{slug}.apkg"


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
    resume: bool = typer.Option(
        False,
        "--resume",
        help="Skip chapters already present in --cards-json",
    ),
    comprehensive: bool = typer.Option(
        False,
        "--comprehensive",
        help="Cover all teachable content in each chapter (no card limit)",
    ),
    deck_per_chapter: bool = typer.Option(
        False,
        "--deck-per-chapter",
        help="Write one .apkg file per chapter (-o is a directory)",
    ),
) -> None:
    """Generate Anki deck from a PDF book."""
    config = load_config(config_path)
    if comprehensive:
        config.generation_style = GenerationStyle.COMPREHENSIVE
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
    if comprehensive:
        console.print(
            "[cyan]Comprehensive mode:[/cyan] covering all teachable content per chapter "
            "(may take longer and produce many cards)"
        )
    if deck_per_chapter:
        if json_only:
            console.print("[red]--deck-per-chapter requires .apkg output (omit --json-only)[/red]")
            raise typer.Exit(1)
        deck_dir = _deck_output_dir(output)
        deck_dir.mkdir(parents=True, exist_ok=True)
        console.print(f"[cyan]Deck per chapter:[/cyan] writing .apkg files to {deck_dir}/")
    if use_llm and not use_berlitz:
        effective_url = base_url or os.environ.get("OPENAI_BASE_URL") or DEFAULT_LMSTUDIO_URL
        console.print(f"Using LLM ([dim]{model}[/dim] @ {effective_url})")
        if effective_url.startswith(("http://127.0.0.1", "http://localhost")):
            ensure_server()
            prof = profile_for_model(model)
            ensure_model_loaded(model, context_length=prof.context_length)
            if "qwen" in model.lower():
                console.print(
                    "[yellow]Qwen safe mode:[/yellow] small batches "
                    f"({prof.cards_per_batch} cards × {prof.batches_per_chapter}, "
                    f"{prof.cooldown_seconds:.0f}s pause). Close other apps."
                )
        cards: list = []
        done_chapters: set[str] = set()
        if resume and cards_json and cards_json.exists():
            cards = load_json_cards(cards_json)
            done_chapters = {c.chapter for c in cards}
            console.print(f"Resuming — {len(done_chapters)} chapter(s) already in {cards_json}")
        for idx, ch in enumerate(chapters, 1):
            label = chapter_label(ch.title)
            if label in done_chapters:
                console.print(f"  [{idx}/{len(chapters)}] {ch.title[:60]}... [dim]skipped[/dim]")
                continue
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
                continue
            console.print(f"       → {len(chapter_cards)} cards")
            cards.extend(chapter_cards)
            if deck_per_chapter and chapter_cards:
                apkg_path = _chapter_apkg_path(deck_dir, config, ch.title)
                export_apkg(
                    chapter_cards,
                    config,
                    apkg_path,
                    deck_name=chapter_deck_name(config.deck_name, ch.title),
                )
                console.print(f"       [green]→[/green] {apkg_path.name}")
            if cards_json:
                export_json(cards, cards_json)
            prof = profile_for_model(model)
            if prof.cooldown_seconds > 0 and effective_url.startswith(
                ("http://127.0.0.1", "http://localhost")
            ):
                time.sleep(prof.cooldown_seconds)
    else:
        console.print("Using Berlitz rule-based extraction ([dim]no API key required[/dim])")
        cards = []
        for ch in chapters:
            chapter_cards = extract_berlitz_cards(ch)
            cards.extend(chapter_cards)
            if deck_per_chapter and chapter_cards:
                apkg_path = _chapter_apkg_path(deck_dir, config, ch.title)
                export_apkg(
                    chapter_cards,
                    config,
                    apkg_path,
                    deck_name=chapter_deck_name(config.deck_name, ch.title),
                )
                console.print(f"  [green]→[/green] {apkg_path.name} ({len(chapter_cards)} cards)")
    console.print(f"Created [bold]{len(cards)}[/bold] cards.")

    if cards_json:
        export_json(cards, cards_json)
        console.print(f"Saved cards JSON to {cards_json}")

    if json_only:
        json_out = output if output.suffix == ".json" else output.with_suffix(".json")
        export_json(cards, json_out)
        console.print(f"[green]Wrote[/green] {json_out}")
    elif not deck_per_chapter:
        export_apkg(cards, config, output)
        console.print(f"[green]Wrote Anki deck to[/green] {output}")
        console.print("Import it in Anki: File → Import → select the .apkg file")
    else:
        console.print(f"[green]Wrote {len(chapters)} chapter deck(s) to[/green] {deck_dir}/")
        console.print("Import each .apkg in AnkiDroid — one deck per chapter, no tag filtering needed")


@app.command("export")
def export_cmd(
    cards_json: Path = typer.Argument(..., help="Cards JSON from a previous run", exists=True),
    output: Path = typer.Option(Path("deck.apkg"), "--output", "-o"),
    config_path: Optional[Path] = typer.Option(None, "--config", "-c"),
    deck_name: Optional[str] = typer.Option(None, "--deck", help="Override deck name"),
    deck_per_chapter: bool = typer.Option(
        False,
        "--deck-per-chapter",
        help="Write one .apkg file per chapter (-o is a directory)",
    ),
    colpkg: bool = typer.Option(
        False,
        "--colpkg",
        help="Same as --multideck but writes a .colpkg file (replaces collection on import)",
    ),
    multideck: bool = typer.Option(
        False,
        "--multideck",
        help="One .apkg with a separate deck per chapter (merges into existing collection)",
    ),
) -> None:
    """Export previously generated cards JSON to an Anki .apkg file."""
    config = load_config(config_path)
    if deck_name:
        config.deck_name = deck_name
    cards = load_json_cards(cards_json)

    if (colpkg or multideck) and deck_per_chapter:
        console.print("[red]Use either --multideck/--colpkg or --deck-per-chapter, not both[/red]")
        raise typer.Exit(1)

    if colpkg or multideck:
        if colpkg:
            out = export_colpkg(cards, config, output)
        else:
            out = export_multideck_apkg(cards, config, output)
        chapters = len({c.chapter for c in cards})
        console.print(
            f"[green]Wrote[/green] {out} ({len(cards)} cards, {chapters} chapter decks)"
        )
        if multideck:
            console.print("Import in AnkiDroid — adds decks without replacing your collection")
        else:
            console.print("Import in AnkiDroid: replaces your entire collection")
        return

    if deck_per_chapter:
        deck_dir = _deck_output_dir(output)
        deck_dir.mkdir(parents=True, exist_ok=True)
        by_chapter: dict[str, list] = {}
        for card in cards:
            by_chapter.setdefault(card.chapter, []).append(card)
        for chapter_name, chapter_cards in sorted(by_chapter.items()):
            title = chapter_name  # cards store the label, not raw PDF title
            apkg_path = deck_dir / f"{_book_slug(config.deck_name)}-{chapter_filename_slug(title)}.apkg"
            export_apkg(
                chapter_cards,
                config,
                apkg_path,
                deck_name=chapter_deck_name(config.deck_name, title),
            )
            console.print(f"[green]Wrote[/green] {apkg_path.name} ({len(chapter_cards)} cards)")
        console.print(f"[green]Wrote {len(by_chapter)} chapter deck(s) to[/green] {deck_dir}/")
        return

    export_apkg(cards, config, output)
    console.print(f"[green]Wrote Anki deck to[/green] {output}")


if __name__ == "__main__":
    app()
