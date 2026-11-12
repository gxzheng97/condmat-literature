"""Regression tests for report font preparation; no network or font install."""

import hashlib
import io
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import URLError

import prepare_reports as reports


class PrepareReportsTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.font_dir = Path(self.temporary.name)
        self.content = b"verified font fixture"
        self.asset = reports.FontAsset(
            "fixture.otf",
            "https://example.invalid/immutable/fixture.otf",
            hashlib.sha256(self.content).hexdigest(),
        )
        self.target = self.font_dir / self.asset.filename

    def assert_only_target_remains(self):
        self.assertEqual(list(self.font_dir.iterdir()), [self.target])

    def test_verified_cache_uses_no_network(self):
        self.target.write_bytes(self.content)
        with patch.object(reports, "urlopen") as request, patch.object(reports.time, "sleep") as sleep:
            changed = reports.ensure_font(self.font_dir, self.asset)
        self.assertFalse(changed)
        request.assert_not_called()
        sleep.assert_not_called()
        self.assertEqual(self.target.read_bytes(), self.content)
        self.assert_only_target_remains()

    def test_verified_download_replaces_old_file_only_after_validation(self):
        self.target.write_bytes(b"old font")
        actual_replace = reports.os.replace

        def replace_verified(source, target):
            self.assertEqual(self.target.read_bytes(), b"old font")
            self.assertEqual(Path(source).read_bytes(), self.content)
            return actual_replace(source, target)

        with patch.object(reports, "urlopen", return_value=io.BytesIO(self.content)) as request, patch.object(
            reports.os, "replace", side_effect=replace_verified
        ):
            changed = reports.ensure_font(self.font_dir, self.asset, timeout=7)
        self.assertTrue(changed)
        self.assertEqual(request.call_args.kwargs, {"timeout": 7})
        self.assertEqual(self.target.read_bytes(), self.content)
        self.assert_only_target_remains()

    def test_timeout_retries_are_bounded_and_preserve_old_file(self):
        self.target.write_bytes(b"old font")
        with patch.object(reports, "urlopen", side_effect=TimeoutError("timed out")) as request, patch.object(
            reports.time, "sleep"
        ) as sleep:
            with self.assertRaisesRegex(reports.FontSetupError, "after 3 attempt"):
                reports.ensure_font(self.font_dir, self.asset, timeout=2, attempts=3)
        self.assertEqual(request.call_count, 3)
        self.assertEqual(sleep.call_count, 2)
        self.assertEqual(self.target.read_bytes(), b"old font")
        self.assert_only_target_remains()

    def test_bad_hash_cannot_overwrite_old_file(self):
        self.target.write_bytes(b"old font")
        with patch.object(reports, "urlopen", side_effect=lambda *a, **k: io.BytesIO(b"bad data")) as request, patch.object(
            reports.time, "sleep"
        ), patch.object(reports.os, "replace") as replace:
            with self.assertRaisesRegex(reports.FontSetupError, "SHA256"):
                reports.ensure_font(self.font_dir, self.asset, attempts=2)
        self.assertEqual(request.call_count, 2)
        replace.assert_not_called()
        self.assertEqual(self.target.read_bytes(), b"old font")
        self.assert_only_target_remains()

    def test_failure_creates_no_partial_font(self):
        with patch.object(reports, "urlopen", side_effect=URLError("offline")), patch.object(reports.time, "sleep"):
            with self.assertRaises(reports.FontSetupError):
                reports.ensure_font(self.font_dir, self.asset, attempts=1)
        self.assertEqual(list(self.font_dir.iterdir()), [])

    def test_oversize_response_preserves_old_file(self):
        self.target.write_bytes(b"old font")
        with patch.object(reports, "MAX_FONT_BYTES", 1), patch.object(
            reports, "urlopen", return_value=io.BytesIO(self.content)
        ):
            with self.assertRaisesRegex(reports.FontSetupError, "size limit"):
                reports.ensure_font(self.font_dir, self.asset, attempts=1)
        self.assertEqual(self.target.read_bytes(), b"old font")
        self.assert_only_target_remains()

    def test_invalid_retry_configuration_never_downloads(self):
        for options in ({"attempts": 0}, {"timeout": 0}, {"timeout": -1}):
            with self.subTest(options=options), patch.object(reports, "urlopen") as request:
                with self.assertRaises(ValueError):
                    reports.ensure_font(self.font_dir, self.asset, **options)
                request.assert_not_called()

    def test_font_cache_is_not_run_on_other_platforms(self):
        with patch.object(reports.sys, "platform", "win32"), patch.object(
            reports.shutil, "which"
        ) as which, patch.object(reports.subprocess, "run") as run:
            self.assertFalse(reports.refresh_font_cache(self.font_dir))
        which.assert_not_called()
        run.assert_not_called()

    def test_linux_font_cache_is_optional_and_has_timeout(self):
        with patch.object(reports.sys, "platform", "linux"), patch.object(
            reports.shutil, "which", return_value=None
        ), patch.object(reports.subprocess, "run") as run:
            self.assertFalse(reports.refresh_font_cache(self.font_dir))
            run.assert_not_called()
        with patch.object(reports.sys, "platform", "linux"), patch.object(
            reports.shutil, "which", return_value="/usr/bin/fc-cache"
        ), patch.object(reports.subprocess, "run") as run:
            self.assertTrue(reports.refresh_font_cache(self.font_dir))
            run.assert_called_once_with(
                ["/usr/bin/fc-cache", "-f", str(self.font_dir)], check=True, timeout=60
            )

    def test_linux_font_cache_failure_is_reported(self):
        with patch.object(reports.sys, "platform", "linux"), patch.object(
            reports.shutil, "which", return_value="/usr/bin/fc-cache"
        ), patch.object(reports.subprocess, "run", side_effect=subprocess.TimeoutExpired("fc-cache", 60)):
            with self.assertRaisesRegex(reports.FontSetupError, "Font cache refresh failed"):
                reports.refresh_font_cache(self.font_dir)

    def test_prepare_refreshes_fontconfig_even_with_restored_cached_fonts(self):
        self.target.write_bytes(self.content)
        with patch.object(reports, "FONTS", (self.asset,)), patch.object(
            reports, "urlopen"
        ) as request, patch.object(reports, "refresh_font_cache") as refresh:
            paths = reports.prepare_fonts(self.font_dir)
        self.assertEqual(paths, [self.target])
        request.assert_not_called()
        refresh.assert_called_once_with(self.font_dir.resolve())

    def test_cli_custom_directory_does_not_install_to_default(self):
        custom = self.font_dir / "custom"
        with patch.object(reports, "prepare_fonts", return_value=[custom / self.asset.filename]) as prepare, patch(
            "sys.stdout", new_callable=io.StringIO
        ):
            self.assertEqual(reports.main(["--font-dir", str(custom), "--skip-font-cache"]), 0)
        prepare.assert_called_once_with(custom, timeout=30, attempts=3, refresh_cache=False)


if __name__ == "__main__":
    unittest.main()
