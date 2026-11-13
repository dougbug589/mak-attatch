"""System dependencies for mak-attatch.

Single source of truth for the distro -> package-manager mapping and the
exact install commands. Used both at runtime (TUI/GUI/CLI dependency gate)
and by setup.sh (invoked as ``python3 mak_attatch/core/deps.py ...``).
"""

import shutil
import sys

# Needed by every interface. binary -> package name per package manager.
REQUIRED_BINARIES = ("ffmpeg", "ffprobe", "mkvpropedit", "mkvmerge")
# Only the TUI uses these, and it runs without them (no file browser / no
# image previews), so they are opt-in for setup.
TUI_BINARIES = ("yazi", "chafa")

_PACKAGE_FOR = {
    "ffmpeg": {"apt": "ffmpeg", "pacman": "ffmpeg", "dnf": "ffmpeg"},
    "ffprobe": {"apt": "ffmpeg", "pacman": "ffmpeg", "dnf": "ffmpeg"},
    "mkvpropedit": {"apt": "mkvtoolnix", "pacman": "mkvtoolnix-cli", "dnf": "mkvtoolnix"},
    "mkvmerge": {"apt": "mkvtoolnix", "pacman": "mkvtoolnix-cli", "dnf": "mkvtoolnix"},
    "yazi": {"apt": "yazi", "pacman": "yazi", "dnf": "yazi"},
    "chafa": {"apt": "chafa", "pacman": "chafa", "dnf": "chafa"},
}

# apt family distro ids that can use the yazi apt repository
APT_DISTROS = ("ubuntu", "debian", "linuxmint", "pop", "zorin")
PACMAN_DISTROS = ("arch", "manjaro", "endeavouros", "cachyos", "garuda", "arcolinux")
DNF_DISTROS = ("fedora", "rocky", "centos", "rhel")


def distro_id() -> str:
    """Return the distro id from /etc/os-release (lowercase, no quotes)."""
    try:
        with open("/etc/os-release", encoding="utf-8") as f:
            for line in f:
                if line.startswith("ID="):
                    return line.split("=", 1)[1].strip().strip('"').lower()
    except OSError:
        pass
    return "unknown"


def package_manager() -> str:
    d = distro_id()
    if d in APT_DISTROS:
        return "apt"
    if d in PACMAN_DISTROS:
        return "pacman"
    if d in DNF_DISTROS:
        return "dnf"
    # Fall back to whichever package manager is actually installed.
    if shutil.which("apt-get"):
        return "apt"
    if shutil.which("pacman"):
        return "pacman"
    if shutil.which("dnf"):
        return "dnf"
    return "unknown"


def _binaries(include_tui: bool = False) -> tuple[str, ...]:
    return REQUIRED_BINARIES + (TUI_BINARIES if include_tui else ())


def _packages_for(binaries, pm: str) -> list[str]:
    pkgs: list[str] = []
    for b in binaries:
        name = _PACKAGE_FOR[b].get(pm, _PACKAGE_FOR[b]["apt"])
        if name not in pkgs:
            pkgs.append(name)
    return pkgs


def packages(include_tui: bool = False) -> list[str]:
    return _packages_for(_binaries(include_tui), package_manager())


def missing_binaries(include_tui: bool = False) -> list[str]:
    """Names of needed binaries not on PATH (TUI extras only if asked)."""
    return [b for b in _binaries(include_tui) if shutil.which(b) is None]


def _install_for(pkgs: list[str]) -> str:
    pm = package_manager()
    joined = " ".join(pkgs)
    if pm == "apt":
        return f"sudo apt install -y {joined}"
    if pm == "pacman":
        return f"sudo pacman -S --needed {joined}"
    if pm == "dnf":
        return f"sudo dnf install -y {joined}"
    return ""


def install_command(include_tui: bool = False) -> str:
    """Exact package-manager command for the required (and optionally TUI) tools."""
    return _install_for(packages(include_tui))


def yazi_keyring_commands() -> list[str]:
    """Commands to enable the yazi apt repository (Debian/Ubuntu only).

    The keyring is downloaded to a temp file and must be non-empty before it
    is installed, so a failed download can never leave an empty keyring plus
    a registered source that breaks every later ``apt update``. Each line is
    meant to run with ``set -euo pipefail``.
    """
    if package_manager() != "apt":
        return []
    return [
        "command -v curl >/dev/null || sudo apt-get install -y curl",
        "tmp=$(mktemp) && curl -fsSL https://yazi-rs.github.io/builds/yazi-keyring.gpg"
        " -o \"$tmp\" && test -s \"$tmp\""
        " && sudo install -m 644 \"$tmp\" /usr/share/keyrings/yazi-keyring.gpg"
        " && rm -f \"$tmp\"",
        "echo 'deb [signed-by=/usr/share/keyrings/yazi-keyring.gpg] "
        "https://yazi-rs.github.io/builds/ stable main' "
        "| sudo tee /etc/apt/sources.list.d/yazi.list >/dev/null",
        "sudo apt-get update",
    ]


def yazi_copr_commands() -> list[str]:
    """Commands to enable the yazi COPR repository (Fedora/EL only)."""
    if package_manager() != "dnf":
        return []
    return ["sudo dnf copr enable -y lihaohong/yazi"]


def hint(missing: list[str] | None = None) -> str:
    """Human-readable install hint for the runtime dependency gate."""
    missing = missing if missing is not None else missing_binaries()
    if not missing:
        return ""
    known = [b for b in missing if b in _PACKAGE_FOR]
    cmd = _install_for(_packages_for(known, package_manager())) if known else ""
    if not cmd:
        return f"Install: {', '.join(missing)}"
    lines = [f"Install with: {cmd}"]
    if "yazi" in missing and package_manager() == "apt":
        lines.append("yazi also needs its apt repository first:")
        lines.extend(f"  {c}" for c in yazi_keyring_commands())
    if "yazi" in missing and package_manager() == "dnf":
        lines.append("yazi also needs its COPR repository enabled first:")
        lines.extend(f"  {c}" for c in yazi_copr_commands())
    return "\n".join(lines)


def _main() -> int:
    arg = sys.argv[1] if len(sys.argv) > 1 else ""
    with_tui = "--with-tui" in sys.argv[2:]
    if arg == "--distro":
        print(distro_id())
    elif arg == "--pm":
        print(package_manager())
    elif arg == "--packages":
        print(" ".join(packages(with_tui)))
    elif arg == "--missing":
        print("\n".join(missing_binaries(with_tui)))
    elif arg == "--install-cmd":
        print(install_command(with_tui))
    elif arg == "--yazi-keyring":
        print("\n".join(yazi_keyring_commands()))
    elif arg == "--yazi-copr":
        print("\n".join(yazi_copr_commands()))
    elif arg == "--hint":
        print(hint(missing_binaries(with_tui)))
    else:
        print(__doc__)
        print("Usage: python3 mak_attatch/core/deps.py "
              "[--distro|--pm|--packages|--missing|--install-cmd"
              "|--yazi-keyring|--yazi-copr|--hint] [--with-tui]")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(_main())
