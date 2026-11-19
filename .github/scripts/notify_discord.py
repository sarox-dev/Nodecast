"""Announce stable major/minor releases; never log webhook credentials."""
import json
import os
import re
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen


VERSION = re.compile(r"v?(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)")


def release_type(release):
    match = VERSION.fullmatch(release["tag_name"])
    if release.get("draft") or release.get("prerelease") or not match:
        return None
    major, minor, patch = map(int, match.groups())
    if patch or (major, minor) == (0, 0):
        return None
    return "major" if minor == 0 else "minor"


def clean_release_notes(body):
    lines = []
    for line in (body or "").splitlines():
        if re.match(r"^#{1,6}\s+Installation\b", line, re.IGNORECASE):
            break
        # The new version is the headline; omit the generated previous-version heading.
        if re.match(r"^#{1,6}\s+(?:what['’]s changed(?: since .*)?|changes|changelog)\s*$",
                    line, re.IGNORECASE):
            continue
        if re.match(r"^[-*]\s+(?:chore(?:\([^)]*\))?:\s*)?bump version(?:\s+to)?\s+v?\d+\.\d+\.\d+\b",
                    line, re.IGNORECASE):
            continue
        if re.match(r"^[-*]\s+", line):
            line = re.sub(r"\s+\([0-9a-f]{7,40}\)\s*$", "", line, flags=re.IGNORECASE)
            line = re.sub(r"^([-*]\s+)(?:feat|fix|perf)(?:\([^)]*\))?!?:\s*", r"\1", line)
        lines.append(line)
    return "\n".join(lines).strip()


def build_payload(release):
    kind = release_type(release)
    if kind is None:
        return None
    version = release["tag_name"].removeprefix("v")
    url = release["html_url"]
    major = kind == "major"
    notes = clean_release_notes(release.get("body"))
    notes = notes or "Release details are available on GitHub."
    heading = f"# v{version}\n{kind.title()} release\n\n**What's new**\n"
    link = f"\n\n[View release notes →]({url})"
    description = heading + notes[:3000 - len(heading) - len(link)] + link
    return {
        "content": "@everyone" if major else "",
        "allowed_mentions": {"parse": ["everyone"] if major else []},
        "embeds": [{
            "title": f"{'🚀' if major else '⭐'} Nodecast update",
            "url": url,
            "color": 10181046 if major else 4886754,
            "description": description,
            "footer": {"text": "Nodecast — Personal Knowledge Layer"},
            "timestamp": release["published_at"],
        }],
    }


def send_notification(webhook, payload):
    if not webhook:
        raise RuntimeError("DISCORD_WEBHOOK_URL secret is missing")
    parts = urlsplit(webhook)
    query = dict(parse_qsl(parts.query))
    query["wait"] = "true"
    url = urlunsplit(parts._replace(query=urlencode(query)))
    request = Request(url, data=json.dumps(payload).encode(), headers={
        "Content-Type": "application/json", "User-Agent": "Nodecast-Release-Notifier/1.0",
    })
    try:
        with urlopen(request, timeout=30) as response:
            message = json.load(response)
    except HTTPError as error:
        raise RuntimeError(f"Discord rejected notification (HTTP {error.code})") from None
    except (URLError, TimeoutError):
        raise RuntimeError("Discord request failed or timed out") from None
    if not message.get("id"):
        raise RuntimeError("Discord did not confirm a saved message")
    print(f"Discord confirmed message {message['id']}")


def main():
    event = {}
    if os.environ.get("GITHUB_EVENT_PATH"):
        with open(os.environ["GITHUB_EVENT_PATH"], encoding="utf-8") as file:
            event = json.load(file)
    release = event.get("release")
    if release is None:
        tag = os.environ["RELEASE_TAG"]
        # Reject patch/prerelease tags before API or webhook access.
        if release_type({"tag_name": tag}) is None:
            print(f"Skipping non-major/minor release: {tag}")
            return
        from urllib.parse import quote
        api = os.environ.get("GITHUB_API_URL", "https://api.github.com")
        repo = os.environ["GITHUB_REPOSITORY"]
        request = Request(f"{api}/repos/{repo}/releases/tags/{quote(tag, safe='')}", headers={
            "Accept": "application/vnd.github+json", "User-Agent": "Nodecast-Release-Notifier/1.0",
            "Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}",
        })
        with urlopen(request, timeout=30) as response:
            release = json.load(response)
    payload = build_payload(release)
    if payload is None:
        print(f"Skipping non-major/minor release: {release['tag_name']}")
        return
    send_notification(os.environ.get("DISCORD_WEBHOOK_URL", ""), payload)


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, HTTPError, URLError, TimeoutError, ValueError, KeyError) as error:
        # Do not print request URLs or credentials in Actions logs.
        message = str(error) if isinstance(error, RuntimeError) else type(error).__name__
        print(f"::error::Release notification failed: {message}", file=sys.stderr)
        sys.exit(1)
