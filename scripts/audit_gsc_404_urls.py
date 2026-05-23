from __future__ import annotations

import csv
import json
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse


ROOT = Path(__file__).resolve().parents[1]
DOCS_DIR = ROOT / "docs"
DEBUG_DIR = ROOT / "debug"
INPUT_PATH = DEBUG_DIR / "gsc_404_urls.csv"
SITEMAP_PATH = DOCS_DIR / "sitemap.xml"
SCHEDULE_FUTURE_PATH = DOCS_DIR / "data" / "schedule_future.json"

OUT_JSON = DEBUG_DIR / "gsc_404_url_audit.json"
OUT_SUMMARY = DEBUG_DIR / "gsc_404_url_audit_summary.md"
OUT_BY_FAMILY = DEBUG_DIR / "gsc_404_by_family.csv"
OUT_MISSING_SITEMAP = DEBUG_DIR / "gsc_404_missing_in_sitemap.csv"
OUT_MISSING_LINKS = DEBUG_DIR / "gsc_404_missing_internal_links.csv"
OUT_MISSING_DATA = DEBUG_DIR / "gsc_404_missing_data_references.csv"

URL_RE = re.compile(r"https?://[^\s,\"'<>]+|/[A-Za-z0-9._~!$&'()*+,;=:@%/?#-]+")
HREF_RE = re.compile(r"""(?:href|src)\s*=\s*["']([^"']+)["']""", re.IGNORECASE)
HTML_PATH_RE = re.compile(r"""(?:https?://[^"' <>)]+)?(/[A-Za-z0-9._~!$&'()*+,;=:@%/-]+\.html)(?:\?[^"' <>)]+)?""")


@dataclass
class UrlAudit:
    original_url: str
    full_url: str
    path: str
    query: str
    local_expected_file: str | None
    family: str
    likely_cause: str
    exists_local: bool
    in_sitemap: bool
    internal_link_count: int
    internal_link_sources: list[str]
    data_reference_count: int
    data_reference_sources: list[str]
    in_schedule_future: bool
    issue_buckets: list[str]


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def normalize_path(raw: str) -> tuple[str, str, str]:
    raw = raw.strip().strip('"').strip("'")
    parsed = urlparse(raw)
    if parsed.scheme and parsed.netloc:
        full_url = raw
        path = parsed.path or "/"
        query = parsed.query
    else:
        path_part = raw if raw.startswith("/") else "/" + raw
        parsed = urlparse(path_part)
        path = parsed.path or "/"
        query = parsed.query
        full_url = path + (f"?{query}" if query else "")
    path = unquote(path)
    return full_url, path, query


def extract_urls_from_csv_or_text(path: Path) -> list[str]:
    text = read_text(path)
    found: list[str] = []

    try:
        sample = text[:4096]
        dialect = csv.Sniffer().sniff(sample, delimiters=",\t")
        rows = list(csv.reader(text.splitlines(), dialect))
    except csv.Error:
        rows = []

    if rows:
        header = [cell.strip().lower() for cell in rows[0]]
        url_indexes = [idx for idx, name in enumerate(header) if name in {"url", "page", "source url", "not found url"}]
        if url_indexes:
            for row in rows[1:]:
                for idx in url_indexes:
                    if idx < len(row):
                        found.extend(URL_RE.findall(row[idx]))
        else:
            for row in rows:
                for cell in row:
                    found.extend(URL_RE.findall(cell))

    if not found:
        found = URL_RE.findall(text)

    deduped = []
    seen = set()
    for url in found:
        cleaned = url.strip().rstrip(".,);]")
        if cleaned.lower() in {"url", "page"}:
            continue
        if cleaned not in seen:
            seen.add(cleaned)
            deduped.append(cleaned)
    return deduped


def expected_file_for_path(path: str) -> Path | None:
    if not path or path == "/":
        return DOCS_DIR / "index.html"
    clean = path.lstrip("/")
    if clean.endswith("/"):
        return DOCS_DIR / clean / "index.html"
    return DOCS_DIR / clean


def classify_family(path: str, query: str) -> str:
    if re.fullmatch(r"/classes/\d+\.html", path):
        return "class_numeric"
    if re.fullmatch(r"/classes/session_[^/]+\.html", path):
        return "class_session_slug"
    if re.fullmatch(r"/courses/[^/]+\.html", path):
        return "course"
    if re.fullmatch(r"/fliers/[^/]+\.html", path):
        return "flier"
    if re.fullmatch(r"/locations/[^/]+\.html", path):
        return "location"
    if re.fullmatch(r"/landers/job/[^/]+\.html", path):
        return "job_lander"
    if path == "/which-class.html" and "near=" in parse_qs(query):
        return "which_class_near"
    return "other"


def local_refs_for_url(path: str, query: str) -> set[str]:
    refs = {path}
    if query:
        refs.add(f"{path}?{query}")
    refs.add(path.lstrip("/"))
    if query:
        refs.add(f"{path.lstrip('/')}?{query}")
    return refs


def load_sitemap_refs() -> set[str]:
    if not SITEMAP_PATH.exists():
        return set()
    text = read_text(SITEMAP_PATH)
    refs = set()
    for url in URL_RE.findall(text):
        _, path, query = normalize_path(url)
        refs.update(local_refs_for_url(path, query))
    return refs


def scan_html_links() -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    refs: dict[str, set[str]] = defaultdict(set)
    missing: dict[str, set[str]] = defaultdict(set)
    for html_file in DOCS_DIR.rglob("*.html"):
        rel_source = html_file.relative_to(ROOT).as_posix()
        text = read_text(html_file)
        for link in HREF_RE.findall(text):
            if link.startswith(("http://", "https://", "mailto:", "tel:", "#", "javascript:")):
                if link.startswith(("http://", "https://")):
                    _, path, query = normalize_path(link)
                else:
                    continue
            else:
                joined = (html_file.parent / link.split("#", 1)[0].split("?", 1)[0]).resolve()
                try:
                    rel = "/" + joined.relative_to(DOCS_DIR.resolve()).as_posix()
                except ValueError:
                    rel = "/" + link.lstrip("/")
                _, path, query = normalize_path(rel + (("?" + link.split("?", 1)[1].split("#", 1)[0]) if "?" in link else ""))

            for ref in local_refs_for_url(path, query):
                refs[ref].add(rel_source)

            expected = expected_file_for_path(path)
            if expected and path.endswith(".html") and not expected.exists():
                missing[path].add(rel_source)
    return refs, missing


def scan_json_refs() -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    refs: dict[str, set[str]] = defaultdict(set)
    missing: dict[str, set[str]] = defaultdict(set)
    data_dir = DOCS_DIR / "data"
    if not data_dir.exists():
        return refs, missing
    for json_file in data_dir.rglob("*.json"):
        rel_source = json_file.relative_to(ROOT).as_posix()
        text = read_text(json_file)
        for match in HTML_PATH_RE.findall(text):
            _, path, query = normalize_path(match)
            for ref in local_refs_for_url(path, query):
                refs[ref].add(rel_source)
            expected = expected_file_for_path(path)
            if expected and not expected.exists():
                missing[path].add(rel_source)
    return refs, missing


def load_schedule_future_text() -> str:
    if SCHEDULE_FUTURE_PATH.exists():
        return read_text(SCHEDULE_FUTURE_PATH)
    return ""


def present_in_schedule_future(path: str, family: str, schedule_text: str) -> bool:
    if not schedule_text:
        return False
    if family == "class_numeric":
        match = re.search(r"/classes/(\d+)\.html", path)
        return bool(match and re.search(rf"\b{re.escape(match.group(1))}\b", schedule_text))
    if family == "class_session_slug":
        slug = Path(path).stem
        return slug in schedule_text or slug.removeprefix("session_") in schedule_text
    return path in schedule_text or path.lstrip("/") in schedule_text


def bucket_and_cause(
    family: str,
    exists_local: bool,
    in_sitemap: bool,
    link_sources: set[str],
    data_sources: set[str],
    in_schedule_future: bool,
) -> tuple[list[str], str]:
    buckets = []
    if exists_local:
        buckets.append("exists_now")
    if not exists_local and in_sitemap:
        buckets.append("missing_but_in_sitemap")
    if not exists_local and link_sources:
        buckets.append("missing_but_in_internal_links")
    if not exists_local and data_sources:
        buckets.append("missing_but_in_data_json")
    if not exists_local and in_schedule_future:
        buckets.append("missing_but_in_schedule_future")
    if not exists_local and not in_sitemap and not link_sources and not data_sources and not in_schedule_future:
        buckets.append("missing_and_not_referenced_locally")

    if not exists_local and in_sitemap:
        buckets.append("likely_stale_sitemap")
        cause = "likely_stale_sitemap"
    elif not exists_local and link_sources:
        buckets.append("likely_stale_internal_link")
        cause = "likely_stale_internal_link"
    elif not exists_local and (data_sources or in_schedule_future):
        buckets.append("likely_generator_gap")
        cause = "likely_generator_gap"
    elif not exists_local and family in {"which_class_near", "other"}:
        buckets.append("route_or_rewrite_needed")
        cause = "route_or_rewrite_needed"
    elif not exists_local:
        buckets.append("likely_old_google_memory")
        cause = "likely_old_google_memory"
    else:
        cause = "exists_now"
    return list(dict.fromkeys(buckets)), cause


def csv_write(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def generated_html_files() -> set[str]:
    return {
        "/" + path.relative_to(DOCS_DIR).as_posix()
        for path in DOCS_DIR.rglob("*.html")
        if path.is_file()
    }


def build_summary(audits: list[UrlAudit], reverse: dict[str, Any]) -> str:
    family_counts = Counter(a.family for a in audits)
    missing = [a for a in audits if not a.exists_local]
    exists_count = len(audits) - len(missing)
    missing_sitemap = [a for a in missing if a.in_sitemap]
    missing_links = [a for a in missing if a.internal_link_count]
    missing_data = [a for a in missing if a.data_reference_count]

    source_counts = Counter()
    for audit in missing_links:
        source_counts.update(audit.internal_link_sources)

    do_not_validate = bool(missing_sitemap or missing_links)

    lines = [
        "# GSC 404 URL Audit Summary",
        "",
        f"- Total URLs loaded: {len(audits)}",
        f"- Total that exist now: {exists_count}",
        f"- Total still missing: {len(missing)}",
        f"- Missing URLs still in sitemap: {len(missing_sitemap)}",
        f"- Missing URLs still internally linked: {len(missing_links)}",
        f"- Missing URLs still referenced in data JSON: {len(missing_data)}",
        "",
        "## Totals By URL Family",
        "",
    ]
    for family, count in sorted(family_counts.items()):
        lines.append(f"- {family}: {count}")

    lines.extend(["", "## Top Local Files Creating Bad Links", ""])
    if source_counts:
        for source, count in source_counts.most_common(15):
            lines.append(f"- {source}: {count}")
    else:
        lines.append("- None found.")

    lines.extend(["", "## Reverse Audit Totals", ""])
    lines.append(f"- Sitemap URLs pointing to missing docs files: {len(reverse['sitemap_missing_files'])}")
    lines.append(f"- Internal links pointing to missing docs files: {len(reverse['internal_missing_links'])}")
    lines.append(f"- Data JSON references pointing to missing docs files: {len(reverse['data_missing_refs'])}")
    lines.append(f"- Generated docs HTML files not present in sitemap: {len(reverse['generated_files_not_in_sitemap'])}")
    lines.append(f"- Generated docs HTML files not internally linked: {len(reverse['generated_files_not_linked'])}")

    lines.extend(["", "## Recommended Fix By Family", ""])
    recommendations = {
        "class_numeric": "If referenced by schedule data, regenerate or restore class detail pages; otherwise remove stale sitemap/internal references.",
        "class_session_slug": "Check schedule/session ID generation; regenerate session pages when still in schedule data.",
        "course": "Restore course pages or remove stale hub/sitemap references.",
        "flier": "Restore expected flier asset/page or remove local references.",
        "location": "Restore location landing pages or remove stale local links.",
        "job_lander": "Restore job lander pages or remove stale campaign/internal links.",
        "which_class_near": "Confirm route/rewrite support for query landing pages before validating.",
        "other": "Review individually; old Google memory is likely only when no local references remain.",
    }
    for family in sorted(family_counts):
        lines.append(f"- {family}: {recommendations.get(family, recommendations['other'])}")

    if do_not_validate:
        lines.extend(["", "## Search Console Validation", "", "**DO NOT CLICK VALIDATE FIX YET**"])
        lines.append("")
        lines.append("At least one missing URL is still present in the sitemap or internal links.")
    else:
        lines.extend(["", "## Search Console Validation", "", "No missing audited URLs were found in sitemap or internal links. Review data references before validating."])

    return "\n".join(lines) + "\n"


def main() -> int:
    DEBUG_DIR.mkdir(parents=True, exist_ok=True)
    if not INPUT_PATH.exists():
        message = (
            f"Missing input file: {INPUT_PATH}\n"
            "Place the Google Search Console 404 export at debug/gsc_404_urls.csv and rerun this script.\n"
        )
        sys.stderr.write(message)
        return 2

    urls = extract_urls_from_csv_or_text(INPUT_PATH)
    sitemap_refs = load_sitemap_refs()
    html_refs, internal_missing_links = scan_html_links()
    json_refs, data_missing_refs = scan_json_refs()
    schedule_future_text = load_schedule_future_text()

    audits: list[UrlAudit] = []
    for original in urls:
        full_url, path, query = normalize_path(original)
        local_file = expected_file_for_path(path)
        family = classify_family(path, query)
        refs = local_refs_for_url(path, query)
        link_sources = set().union(*(html_refs.get(ref, set()) for ref in refs))
        data_sources = set().union(*(json_refs.get(ref, set()) for ref in refs))
        in_sitemap = bool(refs & sitemap_refs)
        exists_local = bool(local_file and local_file.exists())
        in_schedule_future = present_in_schedule_future(path, family, schedule_future_text)
        buckets, cause = bucket_and_cause(
            family,
            exists_local,
            in_sitemap,
            link_sources,
            data_sources,
            in_schedule_future,
        )
        audits.append(
            UrlAudit(
                original_url=original,
                full_url=full_url,
                path=path,
                query=query,
                local_expected_file=str(local_file.relative_to(ROOT)) if local_file else None,
                family=family,
                likely_cause=cause,
                exists_local=exists_local,
                in_sitemap=in_sitemap,
                internal_link_count=len(link_sources),
                internal_link_sources=sorted(link_sources),
                data_reference_count=len(data_sources),
                data_reference_sources=sorted(data_sources),
                in_schedule_future=in_schedule_future,
                issue_buckets=buckets,
            )
        )

    generated = generated_html_files()
    sitemap_missing_files = sorted(
        ref for ref in sitemap_refs
        if ref.startswith("/") and ref.endswith(".html") and not (DOCS_DIR / ref.lstrip("/")).exists()
    )
    generated_not_in_sitemap = sorted(path for path in generated if path not in sitemap_refs)
    linked_paths = {ref for ref in html_refs if ref.startswith("/") and ref.endswith(".html")}
    generated_not_linked = sorted(path for path in generated if path not in linked_paths and path != "/index.html")

    reverse = {
        "sitemap_missing_files": sitemap_missing_files,
        "internal_missing_links": {path: sorted(sources) for path, sources in sorted(internal_missing_links.items())},
        "data_missing_refs": {path: sorted(sources) for path, sources in sorted(data_missing_refs.items())},
        "generated_files_not_in_sitemap": generated_not_in_sitemap,
        "generated_files_not_linked": generated_not_linked,
    }

    payload = {
        "input": str(INPUT_PATH.relative_to(ROOT)),
        "total_urls_loaded": len(audits),
        "sitemap_present": SITEMAP_PATH.exists(),
        "schedule_future_present": SCHEDULE_FUTURE_PATH.exists(),
        "audits": [asdict(audit) for audit in audits],
        "reverse_audits": reverse,
    }
    OUT_JSON.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    OUT_SUMMARY.write_text(build_summary(audits, reverse), encoding="utf-8")

    csv_write(
        OUT_BY_FAMILY,
        [
            {
                "url": audit.full_url,
                "path": audit.path,
                "query": audit.query,
                "family": audit.family,
                "likely_cause": audit.likely_cause,
                "exists_local": audit.exists_local,
                "in_sitemap": audit.in_sitemap,
                "internal_link_count": audit.internal_link_count,
                "data_reference_count": audit.data_reference_count,
                "in_schedule_future": audit.in_schedule_future,
                "issue_buckets": "|".join(audit.issue_buckets),
            }
            for audit in audits
        ],
        [
            "url",
            "path",
            "query",
            "family",
            "likely_cause",
            "exists_local",
            "in_sitemap",
            "internal_link_count",
            "data_reference_count",
            "in_schedule_future",
            "issue_buckets",
        ],
    )
    csv_write(
        OUT_MISSING_SITEMAP,
        [{"path": path} for path in sitemap_missing_files],
        ["path"],
    )
    csv_write(
        OUT_MISSING_LINKS,
        [
            {"path": path, "sources": "|".join(sources)}
            for path, sources in sorted(reverse["internal_missing_links"].items())
        ],
        ["path", "sources"],
    )
    csv_write(
        OUT_MISSING_DATA,
        [
            {"path": path, "sources": "|".join(sources)}
            for path, sources in sorted(reverse["data_missing_refs"].items())
        ],
        ["path", "sources"],
    )

    print(f"Loaded {len(audits)} URLs from {INPUT_PATH}")
    print(f"Wrote {OUT_JSON}")
    print(f"Wrote {OUT_SUMMARY}")
    print(f"Wrote {OUT_BY_FAMILY}")
    print(f"Wrote {OUT_MISSING_SITEMAP}")
    print(f"Wrote {OUT_MISSING_LINKS}")
    print(f"Wrote {OUT_MISSING_DATA}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
