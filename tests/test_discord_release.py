import importlib.util
import io
import json
from pathlib import Path
import unittest
import tempfile
from unittest.mock import patch
from urllib.error import HTTPError, URLError

spec = importlib.util.spec_from_file_location(
    "notify_discord", Path(__file__).resolve().parents[1] / ".github/scripts/notify_discord.py"
)
notifier = importlib.util.module_from_spec(spec)
spec.loader.exec_module(notifier)


def release(tag="v1.8.0", **updates):
    return dict(tag_name=tag, html_url=f"https://github.com/sarox-dev/Nodecast/releases/tag/{tag}",
                published_at="2026-11-19T10:00:00Z", body="## Changes\n- New feature", **updates)


class DiscordReleaseTests(unittest.TestCase):
    def test_minor_and_major_versions(self):
        for tag, kind in [("v1.8.0", "minor"), ("2.0.0", "major"), ("v0.2.0", "minor")]:
            with self.subTest(tag=tag):
                self.assertEqual(notifier.release_type(release(tag)), kind)

    def test_patch_prerelease_draft_and_invalid_versions_are_skipped(self):
        for data in [release("v1.8.1"), release("v2.0.3"), release("v1.8.0-rc.1"),
                     release("v1.8"), release("latest"), release("v01.8.0"), release("v0.0.0"),
                     release(prerelease=True), release(draft=True)]:
            with self.subTest(data=data):
                self.assertIsNone(notifier.build_payload(data))

    def test_actual_release_data_and_json_are_preserved(self):
        data = release()
        data["body"] = '## Changes\n- Quotes " and Latvian ā\n## Installation\nHidden'
        payload = json.loads(json.dumps(notifier.build_payload(data)))
        embed = payload["embeds"][0]
        self.assertTrue(embed["description"].startswith("# v1.8.0\n"))
        self.assertEqual(embed["url"], data["html_url"])
        self.assertNotIn("fields", embed)
        self.assertIn('Quotes " and Latvian ā', embed["description"])
        self.assertNotIn("Hidden", embed["description"])
        self.assertEqual(payload["allowed_mentions"], {"parse": []})

    def test_long_notes_keep_release_link_and_discord_limits(self):
        data = release()
        data["body"] = "ā" * 10000
        description = notifier.build_payload(data)["embeds"][0]["description"]
        self.assertLessEqual(len(description), 3000)
        self.assertTrue(description.endswith(f"({data['html_url']})"))

    def test_generated_changelog_highlights_new_version_and_omits_release_housekeeping(self):
        data = release("v1.7.0")
        data["body"] = """## What's changed since v1.6.0

- chore: bump version to 1.7.0 (ccbcaff)
- fix: harden capture and provider security boundaries (4970629)
- feat: improve Ask workspace and account switching (ab7d29e)
- chore: update dependencies (123abcd)

## Installation
Download installers.
"""
        description = notifier.build_payload(data)["embeds"][0]["description"]
        self.assertTrue(description.startswith("# v1.7.0\nMinor release"))
        for unwanted in ("v1.6.0", "bump version", "ccbcaff", "4970629", "Installation", "Download installers"):
            self.assertNotIn(unwanted, description)
        self.assertIn("- harden capture and provider security boundaries", description)
        self.assertIn("- improve Ask workspace and account switching", description)
        self.assertIn("- chore: update dependencies", description)

    def test_only_version_bump_notes_have_neutral_fallback(self):
        data = release()
        for body in (None, "", "## What's changed since v1.7.0\n- chore(release): bump version to 1.8.0 (123abcd)"):
            with self.subTest(body=body):
                data["body"] = body
                description = notifier.build_payload(data)["embeds"][0]["description"]
                self.assertIn("Release details are available on GitHub.", description)
                self.assertNotIn("bump version", description)

    def test_everyone_only_for_major(self):
        payload = notifier.build_payload(release("v2.0.0"))
        self.assertEqual(payload["content"], "@everyone")
        self.assertEqual(payload["allowed_mentions"], {"parse": ["everyone"]})

    def test_send_waits_for_saved_message(self):
        with patch.object(notifier, "urlopen", return_value=io.BytesIO(b'{"id":"123"}')) as send:
            notifier.send_notification("https://discord.com/api/webhooks/123/secret?thread_id=42", {})
        request = send.call_args.args[0]
        self.assertIn("wait=true", request.full_url)
        self.assertIn("thread_id=42", request.full_url)
        self.assertEqual(json.loads(request.data), {})

    def test_http_and_network_errors_fail_without_leaking_credentials(self):
        url = "https://discord.com/api/webhooks/123/secret"
        for error in [HTTPError(url, 400, "bad request", {}, None),
                      HTTPError(url, 404, "missing", {}, None),
                      HTTPError(url, 429, "rate limit", {}, None), URLError(url), TimeoutError(url)]:
            with self.subTest(error=type(error).__name__), patch.object(notifier, "urlopen", side_effect=error):
                with self.assertRaises(RuntimeError) as caught:
                    notifier.send_notification(url, {})
                self.assertNotIn("secret", str(caught.exception))

    def test_missing_secret_and_missing_confirmation_fail(self):
        with self.assertRaisesRegex(RuntimeError, "secret is missing"):
            notifier.send_notification("", {})
        with patch.object(notifier, "urlopen", return_value=io.BytesIO(b'{}')):
            with self.assertRaisesRegex(RuntimeError, "did not confirm"):
                notifier.send_notification("https://discord.com/api/webhooks/123/secret", {})

    def test_tag_workflow_fetches_release_and_sends_complete_payload(self):
        data = release()
        with patch.dict(notifier.os.environ, {
            "RELEASE_TAG": "v1.8.0", "GITHUB_REPOSITORY": "sarox-dev/Nodecast",
            "GITHUB_TOKEN": "github-token", "DISCORD_WEBHOOK_URL": "webhook",
        }, clear=True), patch.object(notifier, "urlopen", return_value=io.BytesIO(json.dumps(data).encode())) as api, \
             patch.object(notifier, "send_notification") as send:
            notifier.main()
        self.assertTrue(api.call_args.args[0].full_url.endswith("/releases/tags/v1.8.0"))
        send.assert_called_once_with("webhook", notifier.build_payload(data))

    def test_published_event_uses_event_release_without_api_fetch(self):
        with tempfile.TemporaryDirectory() as directory:
            event = Path(directory) / "event.json"
            event.write_text(json.dumps({"release": release()}), encoding="utf-8")
            with patch.dict(notifier.os.environ, {
                "GITHUB_EVENT_PATH": str(event), "DISCORD_WEBHOOK_URL": "webhook",
            }, clear=True), patch.object(notifier, "urlopen") as api, \
                 patch.object(notifier, "send_notification") as send:
                notifier.main()
            api.assert_not_called()
            send.assert_called_once_with("webhook", notifier.build_payload(release()))

    def test_patch_exits_without_network_or_secret(self):
        with patch.dict(notifier.os.environ, {"RELEASE_TAG": "v1.8.1"}, clear=True), \
             patch.object(notifier, "urlopen") as send:
            notifier.main()
            send.assert_not_called()


if __name__ == "__main__":
    unittest.main()
