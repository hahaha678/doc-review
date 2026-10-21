import argparse
import json
import sys
from pathlib import Path

from .core import ReviewError, acknowledge, markdown_report, scan


def main(argv=None):
    parser = argparse.ArgumentParser(prog="doc-review", description="Track review of human-maintained Markdown translations")
    sub = parser.add_subparsers(dest="command", required=True)
    scan_cmd = sub.add_parser("scan", help="Report document pairs needing human review")
    scan_cmd.add_argument("--config", default="doc-review.json")
    scan_cmd.add_argument("--format", choices=("text", "json", "markdown"), default="text")
    scan_cmd.add_argument("--output", help="Write report to this file")
    scan_cmd.add_argument("--fail-on-review", action="store_true", help="Exit 2 when review is needed")
    ack_cmd = sub.add_parser("ack", help="Record explicit human review of one pair")
    ack_cmd.add_argument("id", help="Pair id from config")
    ack_cmd.add_argument("--config", default="doc-review.json")
    ack_cmd.add_argument("--reviewer", required=True)
    ack_cmd.add_argument("--reason", required=True, help="What was checked or updated")
    args = parser.parse_args(argv)
    try:
        if args.command == "ack":
            path = acknowledge(args.config, args.id, args.reviewer, args.reason)
            print("Recorded review in {}".format(path))
            return 0
        report = scan(args.config)
        if args.format == "json":
            content = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
        elif args.format == "markdown":
            content = markdown_report(report)
        else:
            lines = ["{} pair(s) need review".format(report["action_required"])]
            for item in report["pairs"]:
                suffix = " [{}]".format(", ".join(item["changed_sections"])) if item["changed_sections"] else ""
                lines.append("{}: {}{}".format(item["id"], item["status"], suffix))
            content = "\n".join(lines) + "\n"
        if args.output:
            path = Path(args.output)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            print("Wrote {}".format(path))
        else:
            print(content, end="")
        return 2 if args.fail_on_review and report["action_required"] else 0
    except ReviewError as exc:
        print("doc-review: {}".format(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
