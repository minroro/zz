"""Command-line interface for the YouTube channel contact finder."""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from typing import Any

from dotenv import load_dotenv

from .criteria import ChannelCriteria
from .pipeline import ChannelMatch, find_channels


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="yt-finder",
        description="Find YouTube channels matching criteria and extract their contacts.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    _build_search_parser(sub.add_parser(
        "search",
        help="Keyword search with hard filters.",
        description="Search YouTube channels by keyword and apply hard filters.",
    ))
    _build_discover_parser(sub.add_parser(
        "discover",
        help='Natural-language discovery: "find channels like X that are Y".',
        description="Discover channels similar to a seed and matching a natural-language brief.",
    ))
    return parser


def _build_search_parser(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("queries", nargs="+", help="One or more search keywords.")
    parser.add_argument("--max-per-query", type=int, default=25)
    parser.add_argument("--region")
    parser.add_argument("--language")
    parser.add_argument("--min-subs", type=int, default=0)
    parser.add_argument("--max-subs", type=int, default=None)
    parser.add_argument("--min-views", type=int, default=0)
    parser.add_argument("--min-videos", type=int, default=0)
    parser.add_argument("--country", action="append", default=[])
    parser.add_argument("--require-keyword", action="append", default=[])
    parser.add_argument("--exclude-keyword", action="append", default=[])
    parser.add_argument("--max-age-days", type=int, default=None)
    parser.add_argument("--fetch-recent-videos", action="store_true")
    parser.add_argument("--require-contact", action="store_true")
    _add_output_args(parser)
    parser.add_argument("--api-key", default=None, help="YouTube API key (defaults to YOUTUBE_API_KEY).")


def _build_discover_parser(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("description", help="Natural-language description of the channels you want.")
    parser.add_argument(
        "--like",
        dest="seed_url",
        help="A YouTube channel URL/handle to use as a similarity seed.",
    )
    parser.add_argument("--max-per-query", type=int, default=15)
    parser.add_argument("--max-candidates", type=int, default=60)
    parser.add_argument("--min-score", type=int, default=7,
                        help="Reject candidates Claude scores below this (0-10).")
    parser.add_argument("--no-recent-videos", action="store_true",
                        help="Skip fetching recent video descriptions for contact fallback.")
    _add_output_args(parser)
    parser.add_argument("--api-key", default=None, help="YouTube API key (defaults to YOUTUBE_API_KEY).")
    parser.add_argument("--anthropic-key", default=None,
                        help="Anthropic API key (defaults to ANTHROPIC_API_KEY).")


def _add_output_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--output", choices=["table", "json", "csv"], default="table")
    parser.add_argument("--output-file", help="Write output to file instead of stdout.")


def _match_to_dict(match: ChannelMatch, score: int | None = None, reason: str | None = None) -> dict:
    c = match.channel
    row: dict[str, Any] = {
        "channel_id": c.channel_id,
        "title": c.title,
        "url": c.url,
        "country": c.country or "",
        "subscribers": c.subscriber_count,
        "views": c.view_count,
        "videos": c.video_count,
        "published_at": c.published_at,
        "emails": match.contact.emails,
        "websites": match.contact.websites,
        "socials": match.contact.socials,
    }
    if score is not None:
        row["score"] = score
    if reason is not None:
        row["reason"] = reason
    return row


def _print_table(rows: list[dict], stream) -> None:
    if not rows:
        stream.write("No matching channels found.\n")
        return
    for row in rows:
        stream.write(f"\n=== {row['title']} ===\n")
        if "score" in row:
            stream.write(f"  Score:       {row['score']}/10  ({row.get('reason', '')})\n")
        stream.write(f"  URL:         {row['url']}\n")
        stream.write(f"  Country:     {row['country'] or '-'}\n")
        stream.write(
            f"  Subscribers: {row['subscribers']:,}   Views: {row['views']:,}   Videos: {row['videos']:,}\n"
        )
        stream.write(f"  Emails:      {', '.join(row['emails']) if row['emails'] else '-'}\n")
        if row["socials"]:
            for platform, urls in row["socials"].items():
                stream.write(f"  {platform.capitalize():<12} {', '.join(urls)}\n")
        if row["websites"]:
            stream.write(f"  Websites:    {', '.join(row['websites'])}\n")
    stream.write(f"\n{len(rows)} channel(s) matched.\n")


def _print_csv(rows: list[dict], stream) -> None:
    if not rows:
        return
    fieldnames = list(rows[0].keys())
    writer = csv.DictWriter(stream, fieldnames=fieldnames)
    writer.writeheader()
    for row in rows:
        flat = dict(row)
        flat["emails"] = "; ".join(row["emails"])
        flat["websites"] = "; ".join(row["websites"])
        flat["socials"] = "; ".join(
            f"{k}:{u}" for k, urls in row["socials"].items() for u in urls
        )
        writer.writerow(flat)


def _open_output(path: str | None):
    if path:
        return open(path, "w", encoding="utf-8", newline="")
    return sys.stdout


def _emit(rows: list[dict], fmt: str, output_file: str | None) -> None:
    stream = _open_output(output_file)
    try:
        if fmt == "json":
            json.dump(rows, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        elif fmt == "csv":
            _print_csv(rows, stream)
        else:
            _print_table(rows, stream)
    finally:
        if output_file:
            stream.close()


def _run_search(args, *, api_key: str) -> int:
    from .search import ChannelSearcher

    criteria = ChannelCriteria(
        min_subscribers=args.min_subs,
        max_subscribers=args.max_subs,
        min_views=args.min_views,
        min_videos=args.min_videos,
        countries=args.country,
        required_keywords=args.require_keyword,
        excluded_keywords=args.exclude_keyword,
        max_age_days=args.max_age_days,
    )
    searcher = ChannelSearcher(api_key=api_key)
    matches = find_channels(
        args.queries,
        criteria,
        searcher=searcher,
        max_results_per_query=args.max_per_query,
        region_code=args.region,
        relevance_language=args.language,
        fetch_recent_videos=args.fetch_recent_videos,
        require_contact=args.require_contact,
    )
    rows = [_match_to_dict(m) for m in matches]
    _emit(rows, args.output, args.output_file)
    return 0 if rows else 1


def _run_discover(args, *, api_key: str) -> int:
    import anthropic
    from .contact import ContactInfo
    from .discover import discover_channels
    from .pipeline import ChannelMatch
    from .search import ChannelSearcher

    anthropic_key = args.anthropic_key or os.environ.get("ANTHROPIC_API_KEY")
    if not anthropic_key:
        print("error: ANTHROPIC_API_KEY missing. Set the env var or pass --anthropic-key.",
              file=sys.stderr)
        return 2

    searcher = ChannelSearcher(api_key=api_key)
    anthropic_client = anthropic.Anthropic(api_key=anthropic_key)

    def progress(stage: str, info=""):
        if stage == "seed":
            print(f"→ resolving seed: {info}", file=sys.stderr)
        elif stage == "seed_resolved":
            print(f"  seed = {info.title} ({info.subscriber_count:,} subs)", file=sys.stderr)
        elif stage == "plan_start":
            print("→ planning search with Claude...", file=sys.stderr)
        elif stage == "plan":
            print(f"  queries: {info.search_queries}", file=sys.stderr)
        elif stage == "query":
            print(f"→ search: {info!r}", file=sys.stderr)
        elif stage == "candidates":
            print(f"→ {len(info)} unique candidates", file=sys.stderr)
        elif stage == "filtered":
            print(f"→ {len(info)} after hard filters", file=sys.stderr)
        elif stage == "judging":
            print(f"  judging: {info.title}", file=sys.stderr)
        elif stage == "verdict":
            mark = "✓" if info.verdict.matches else "✗"
            print(f"   {mark} {info.verdict.score}/10  {info.verdict.reason}", file=sys.stderr)

    result = discover_channels(
        args.seed_url,
        args.description,
        searcher=searcher,
        anthropic_client=anthropic_client,
        max_per_query=args.max_per_query,
        max_candidates=args.max_candidates,
        min_score=args.min_score,
        fetch_recent_videos=not args.no_recent_videos,
        progress=progress,
    )

    rows = [
        _match_to_dict(
            ChannelMatch(channel=m.channel, contact=m.contact),
            score=m.verdict.score,
            reason=m.verdict.reason,
        )
        for m in result.matches
    ]
    _emit(rows, args.output, args.output_file)
    return 0 if rows else 1


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    args = _build_parser().parse_args(argv)

    api_key = args.api_key or os.environ.get("YOUTUBE_API_KEY")
    if not api_key:
        print("error: YOUTUBE_API_KEY missing. Set the env var or pass --api-key.",
              file=sys.stderr)
        return 2

    if args.command == "search":
        return _run_search(args, api_key=api_key)
    if args.command == "discover":
        return _run_discover(args, api_key=api_key)
    print(f"unknown command: {args.command}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
