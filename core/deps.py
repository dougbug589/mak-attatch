"""System dependencies for mak-attatch.

Single source of truth for the distro -> package-manager mapping and the
exact install commands. Used both at runtime (TUI/GUI/CLI dependency gate)
and by setup.sh (invoked as ``python3 core/deps.py ...``).
"""

import shutil
import sys

# binary name -> package name on Debian/Ubuntu
BINARY_PACKAGES = {
    "ffmpeg": "ffmpeg",
    "ffprobe": "ffmpeg",
    "mkvpropedit": "mkvtoolnix",
    "yazi": "yazi",
    "chafa": "chafa",
    "curl": "curl",
}

APT_PACKAGES = ["ffmpeg", "mkvtoolnix", "chafa", "yazi", "curl"]
PACMAN_PACKAGES = ["ffmpeg", "mkvtoolnix-cli", "chafa", "yazi", "curl"]
DNF_PACKAGES = ["ffmpeg", "mkvtoolnix", "chafa", "yazi", "curl"]

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


def packages() -> list[str]:
    pm = package_manager()
    if pm == "pacman":
        return PACMAN_PACKAGES
    if pm == "dnf":
        return DNF_PACKAGES
    return APT_PACKAGES


def missing_binaries() -> list[str]:
    """Return the names of required binaries not on PATH."""
    return [b for b in BINARY_PACKAGES if shutil.which(b) is None]


def install_command() -> str:
    """Return the exact package-manager command for the required binaries."""
    pm = package_manager()
    pkgs = " ".join(packages())
    if pm == "apt":
        return f"sudo apt install -y {pkgs}"
    if pm == "pacman":
        return f"sudo pacman -S --needed {pkgs}"
    if pm == "dnf":
        return f"sudo dnf install -y {pkgs}"
    return ""


def yazi_keyring_commands() -> list[str]:
    """Commands to enable the yazi apt repository (Debian/Ubuntu only)."""
    if package_manager() != "apt":
        return []
    return [
        "curl -fsSL https://yazi-rs.github.io/builds/yazi-keyring.gpg "
        "| sudo tee /usr/share/keyrings/yazi-keyring.gpg >/dev/null",
        "echo 'deb [signed-by=/usr/share/keyrings/yazi-keyring.gpg] "
        "https://yazi-rs.github.io/builds/ stable main' "
        "| sudo tee /etc/apt/sources.list.d/yazi.list >/dev/null",
    ]


def hint(missing: list[str] | None = None) -> str:
    """Human-readable install hint for the runtime dependency gate."""
    missing = missing if missing is not None else missing_binaries()
    if not missing:
        return ""
    cmd = install_command()
    if not cmd:
        return f"Install: {', '.join(missing)}"
    lines = [f"Install with: {cmd}"]
    if "yazi" in missing and package_manager() == "apt":
        lines.append("yazi also needs its apt repository keyring first:")
        lines.extend(f"  {c}" for c in yazi_keyring_commands())
    return "\n".join(lines)


def _main() -> int:
    arg = sys.argv[1] if len(sys.argv) > 1 else ""
    if arg == "--distro":
        print(distro_id())
    elif arg == "--pm":
        print(package_manager())
    elif arg == "--packages":
        print(" ".join(packages()))
    elif arg == "--missing":
        print("\n".join(missing_binaries()))
    elif arg == "--install-cmd":
        print(install_command())
    elif arg == "--yazi-keyring":
        print("\n".join(yazi_keyring_commands()))
    elif arg == "--hint":
        print(hint())
    else:
        print(__doc__)
        print("Usage: python3 core/deps.py "
              "[--distro|--pm|--packages|--missing|--install-cmd|--yazi-keyring|--hint]")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(_main())
