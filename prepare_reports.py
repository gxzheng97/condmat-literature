"""Prepare pinned CJK report fonts without apt or administrator privileges.

Only Python's standard library is required. Fonts come from the official Noto
CJK Sans 2.004 release, pinned to its immutable Git commit and SHA256 digests.
"""

from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from urllib.error import URLError
from urllib.request import Request, urlopen


FONT_REVISION = "523d033d6cb47f4a80c58a35753646f5c3608a78"
FONT_BASE_URL = (
    "https://raw.githubusercontent.com/notofonts/noto-cjk/"
    f"{FONT_REVISION}/Sans/OTF/SimplifiedChinese"
)
MAX_FONT_BYTES = 32 * 1024 * 1024
CHUNK_SIZE = 1024 * 1024


@dataclass(frozen=True)
class FontAsset:
    filename: str
    url: str
    sha256: str


FONTS = (
    FontAsset(
        "NotoSansCJKsc-Regular.otf",
        f"{FONT_BASE_URL}/NotoSansCJKsc-Regular.otf",
        "2c76254f6fc379fddfce0a7e84fb5385bb135d3e399294f6eeb6680d0365b74b",
    ),
    FontAsset(
        "NotoSansCJKsc-Bold.otf",
        f"{FONT_BASE_URL}/NotoSansCJKsc-Bold.otf",
        "b5f0d1a190a7f9b43c310a8850630af12553df32c4c050543f9059732d9b4c0a",
    ),
)


class FontSetupError(RuntimeError):
    """A report font could not be downloaded and verified."""


def default_font_dir() -> Path:
    return Path.home() / ".local" / "share" / "fonts" / "condmat"


def _matches_hash(path: Path, expected: str) -> bool:
    try:
        digest = hashlib.sha256()
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(CHUNK_SIZE), b""):
                digest.update(chunk)
        return digest.hexdigest() == expected
    except OSError:
        return False


def ensure_font(
    font_dir: Path,
    asset: FontAsset,
    *,
    timeout: float = 30,
    attempts: int = 3,
) -> bool:
    """Verify or download one font; return whether its file was replaced.

    Downloads stay in a temporary sibling until their hash is verified. Thus a
    failed request, truncated response, or bad digest cannot overwrite a font.
    A verified cache hit needs no network access.
    """
    if timeout <= 0 or attempts < 1:
        raise ValueError("timeout must be positive and attempts must be at least 1")
    font_dir = Path(font_dir)
    target = font_dir / asset.filename
    if _matches_hash(target, asset.sha256):
        return False
    font_dir.mkdir(parents=True, exist_ok=True)
    for attempt in range(attempts):
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(
                prefix=f".{asset.filename}.", suffix=".tmp", dir=font_dir, delete=False
            ) as output:
                temporary = Path(output.name)
                request = Request(
                    asset.url,
                    headers={"User-Agent": "condmat-literature-report-fonts/1.0"},
                )
                digest = hashlib.sha256()
                downloaded = 0
                with urlopen(request, timeout=timeout) as response:
                    while chunk := response.read(CHUNK_SIZE):
                        downloaded += len(chunk)
                        if downloaded > MAX_FONT_BYTES:
                            raise FontSetupError("font response exceeds the size limit")
                        output.write(chunk)
                        digest.update(chunk)
                if digest.hexdigest() != asset.sha256:
                    raise FontSetupError("downloaded font failed SHA256 verification")
            os.replace(temporary, target)
            return True
        except (OSError, URLError, FontSetupError) as error:
            if attempt == attempts - 1:
                raise FontSetupError(
                    f"Could not prepare {asset.filename} after {attempts} attempt(s): {error}"
                ) from error
            time.sleep(min(2 ** attempt, 4))
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
    return False  # The loop either returns or raises.


def refresh_font_cache(font_dir: Path) -> bool:
    """Refresh a Linux fontconfig cache when the executable is available."""
    if not sys.platform.startswith("linux"):
        return False
    executable = shutil.which("fc-cache")
    if executable is None:
        return False
    try:
        subprocess.run(
            [executable, "-f", str(font_dir)], check=True, timeout=60
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise FontSetupError(f"Font cache refresh failed: {error}") from error
    return True


def prepare_fonts(
    font_dir: Path,
    *,
    timeout: float = 30,
    attempts: int = 3,
    refresh_cache: bool = True,
) -> list[Path]:
    font_dir = Path(font_dir).expanduser().resolve()
    for asset in FONTS:
        ensure_font(font_dir, asset, timeout=timeout, attempts=attempts)
    # Run even after a download-cache hit: CI may restore the font files without
    # restoring fontconfig's separately stored cache.
    if refresh_cache:
        refresh_font_cache(font_dir)
    return [font_dir / asset.filename for asset in FONTS]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--font-dir", type=Path, default=default_font_dir())
    parser.add_argument("--timeout", type=float, default=30, help="HTTP timeout in seconds")
    parser.add_argument("--attempts", type=int, default=3, help="Maximum attempts per font")
    parser.add_argument("--skip-font-cache", action="store_true")
    args = parser.parse_args(argv)
    if args.timeout <= 0 or args.attempts < 1:
        parser.error("--timeout must be positive and --attempts must be at least 1")
    try:
        paths = prepare_fonts(
            args.font_dir,
            timeout=args.timeout,
            attempts=args.attempts,
            refresh_cache=not args.skip_font_cache,
        )
    except (OSError, FontSetupError) as error:
        print(f"Report font preparation failed: {error}", file=sys.stderr)
        return 1
    print(f"Report fonts verified: {len(paths)} in {paths[0].parent}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
