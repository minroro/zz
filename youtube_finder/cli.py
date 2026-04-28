"""Command-line interface for the YouTube channel contact finder."""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys

from dotenv import load_dotenv

from .criteria import ChannelCriteria
from .pipeline import ChannelMatch, find_channels
from .search import ChannelSearcher


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="yt-finder",
        description="Find YouTube channels matching criteria and extract their contacts.",
    )
    parser.add_argument(
        "queries",
        nargs="+",
        help="One or more search keywords (each runs as a separate YouTube search).",
    )
    parser.add_argument("--max-per-query", type=int, default=25, help="Max channels per query (default: 25).")
    parser.add_argument("--region", help="Bias search to a region code, e.g. US, KR, JP.")
    parser.add_argument("--language", help="Bias search to a language code, e.g. en, ko, ja.")

    parser.add_argument("--min-subs", type=int, default=0, help="Minimum subscriber count.")
    parser.add_argument("--max-subs", type=int, default=None, help="Maximum subscriber count.")
    parser.add_argument("--min-views", type=int, default=0, help="Minimum total view count.")
    parser.add_argument("--min-videos", type=int, default=0, help="Minimum uploaded video count.")
    parser.add_argument(
        "--country",
        action="append",
        default=[],
        help="Allowed country code (repeatable).",
    )
    parser.add_argument(
        "--require-keyword",
        action="append",
        default=[],
        help="Require this keyword in the channel title/description/keywords (repeatable).",
    )
    parser.add_argument(
        "--exclude-keyword",
        action="append",
        default=[],
        help="Drop channels containing this keyword (repeatable).",
    )
    parser.add_argument("--max-age-days", type=int, default=None, help="Drop channels older than N days.")

    parser.add_argument(
        "--fetch-recent-videos",
        action="store_true",
        help="Pull recent video descriptions when channel description has no contact.",
    )
    parser.add_argument(
        "--require-contact",
        action="store_true",
        help="Skip matches with no contact info found.",
    )
    parser.add_argument(
        "--output",
        choices=["table", "json", "csv"],
        default="table",
        help="Output format (default: table).",
    )
    parser.add_argument("--output-file", help="Write output to file instead of stdout.")
    parser.add_argument(
        "--api-key",
        default=None,
        help="YouTube Data API v3 key (defaults to YOUTUBE_API_KEY env var).",
    )
    return parser


def _match_to_dict(match: ChannelMatch) -> dict:
    c = match.channel
    return {
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


def _print_table(rows: list[dict], stream) -> None:
    if not rows:
        stream.write("No matching channels found.\n")
        return
    for row in rows:
        stream.write(f"\n=== {row['title']} ===\n")
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
    fieldnames = [
        "channel_id",
        "title",
        "url",
        "country",
        "subscribers",
        "views",
        "videos",
        "published_at",
        "emails",
        "websites",
        "socials",
    ]
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


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    args = _build_parser().parse_args(argv)

    api_key = args.api_key or os.environ.get("YOUTUBE_API_KEY")
    if not api_key:
        print(
            "error: YouTube Data API key missing. Set YOUTUBE_API_KEY or pass --api-key.",
            file=sys.stderr,
        )
        return 2

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

    if args.output_file:
        stream = open(args.output_file, "w", encoding="utf-8", newline="")
    else:
        stream = sys.stdout

    try:
        if args.output == "json":
            json.dump(rows, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        elif args.output == "csv":
            _print_csv(rows, stream)
        else:
            _print_table(rows, stream)
    finally:
        if args.output_file:
            stream.close()

    return 0 if rows else 1


if __name__ == "__main__":
    sys.exit(main())
