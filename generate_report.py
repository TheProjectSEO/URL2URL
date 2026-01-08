"""
Generate HTML report from matches CSV.
"""

import json
import argparse
from pathlib import Path
from datetime import datetime
from jinja2 import Environment, FileSystemLoader


def load_matches(csv_path: str) -> list[dict]:
    """Load matches from CSV file."""
    import pandas as pd
    df = pd.read_csv(csv_path)

    matches = []
    for _, row in df.iterrows():
        # Parse top_5_candidates if present
        top_5 = []
        if pd.notna(row.get('top_5_candidates', '')):
            try:
                top_5 = json.loads(row['top_5_candidates'])
            except (json.JSONDecodeError, TypeError):
                pass

        matches.append({
            'source_url': row.get('source_url', ''),
            'source_title': row.get('source_title', ''),
            'source_brand': row.get('source_brand', ''),
            'best_match_url': row.get('best_match_url', ''),
            'best_match_title': row.get('best_match_title', ''),
            'match_brand': row.get('match_brand', ''),
            'confidence': int(row.get('confidence', 0)),
            'confidence_label': row.get('confidence_label', ''),
            'raw_score': float(row.get('raw_score', 0)),
            'why_not_100': row.get('why_not_100', ''),
            'needs_review': row.get('needs_review', False),
            'top_5_candidates': top_5[:5] if top_5 else [],
        })

    return matches


def calculate_stats(matches: list[dict]) -> dict:
    """Calculate summary statistics."""
    stats = {
        'exact_match': 0,
        'high_confidence': 0,
        'good_match': 0,
        'likely_match': 0,
        'manual_review': 0,
        'no_match': 0,
    }

    for m in matches:
        conf = m['confidence']
        if conf >= 100:
            stats['exact_match'] += 1
        elif conf >= 90:
            stats['high_confidence'] += 1
        elif conf >= 80:
            stats['good_match'] += 1
        elif conf >= 70:
            stats['likely_match'] += 1
        elif conf >= 50:
            stats['manual_review'] += 1
        else:
            stats['no_match'] += 1

    return stats


def generate_report(
    matches_csv: str,
    output_path: str,
    source_name: str = "Site A",
    target_name: str = "Site B",
    source_count: int = 0,
    target_count: int = 0,
):
    """Generate HTML report from matches CSV."""

    # Load matches
    matches = load_matches(matches_csv)

    # Calculate stats
    stats = calculate_stats(matches)

    # Sort by confidence (review items first, then by score desc)
    matches.sort(key=lambda x: (not x['needs_review'], -x['confidence'], -x['raw_score']))

    # Load template
    template_dir = Path(__file__).parent
    env = Environment(loader=FileSystemLoader(template_dir))
    template = env.get_template('report_template.html')

    # Render
    html = template.render(
        report_date=datetime.now().strftime("%Y-%m-%d %H:%M"),
        source_name=source_name,
        target_name=target_name,
        source_count=source_count or len(matches),
        target_count=target_count,
        stats=stats,
        matches=matches,
    )

    # Write output
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(html, encoding='utf-8')

    print(f"Report generated: {output_file}")
    print(f"\nSummary:")
    print(f"  100% Exact Match:  {stats['exact_match']}")
    print(f"  90% High Conf:     {stats['high_confidence']}")
    print(f"  80% Good Match:    {stats['good_match']}")
    print(f"  70% Likely Match:  {stats['likely_match']}")
    print(f"  50% Manual Review: {stats['manual_review']}")
    print(f"  No Match:          {stats['no_match']}")

    return output_file


def main():
    parser = argparse.ArgumentParser(description='Generate HTML report from matches CSV')
    parser.add_argument('--matches', '-m', required=True, help='Path to matches CSV')
    parser.add_argument('--out', '-o', default='output/report.html', help='Output HTML path')
    parser.add_argument('--source-name', default='Nykaa', help='Source site name')
    parser.add_argument('--target-name', default='Purplle', help='Target site name')
    parser.add_argument('--source-count', type=int, default=0, help='Source product count')
    parser.add_argument('--target-count', type=int, default=0, help='Target product count')

    args = parser.parse_args()

    generate_report(
        matches_csv=args.matches,
        output_path=args.out,
        source_name=args.source_name,
        target_name=args.target_name,
        source_count=args.source_count,
        target_count=args.target_count,
    )


if __name__ == '__main__':
    main()
