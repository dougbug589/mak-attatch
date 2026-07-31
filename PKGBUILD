# Maintainer: yourname <youremail>
pkgname=mak-attatch
pkgver=1.0.0
pkgrel=4
pkgdesc="Attach cover art posters to video files"
arch=('x86_64' 'aarch64')
url="https://github.com/dougbug589/mak-attatch"
license=('MIT')
depends=('python' 'python-pyqt6' 'python-requests' 'python-guessit' 'ffmpeg' 'mkvtoolnix-cli')
optdepends=('python-textual: TUI interface' 'yazi: TUI file browser' 'chafa: TUI image preview')
makedepends=('python-virtualenv')
options=(!strip)
source=("$url/archive/refs/tags/v$pkgver.tar.gz")
sha256sums=('46b8f53f6c618ed5fc26f78aa657e302c6f5d8279df4bc5905eff8b09d57f9b3')

build() {
    cd "$startdir"
    python -m venv --system-site-packages buildenv
    buildenv/bin/pip install -r requirements.txt
}

package() {
    cd "$startdir"
    install -Ddm755 "$pkgdir/usr/lib/$pkgname"
    cp -r core ui poster_tui config.py main.py requirements.txt assets "$pkgdir/usr/lib/$pkgname/"
    cp -r buildenv "$pkgdir/usr/lib/$pkgname/.venv"

    install -Dm755 /dev/stdin "$pkgdir/usr/bin/$pkgname" <<EOF
#!/bin/sh
exec /usr/lib/$pkgname/.venv/bin/python /usr/lib/$pkgname/main.py "\$@"
EOF

    install -Dm755 /dev/stdin "$pkgdir/usr/bin/$pkgname-tui" <<EOF
#!/bin/sh
exec /usr/lib/$pkgname/.venv/bin/python /usr/lib/$pkgname/poster-tui "\$@"
EOF

    install -Dm644 mak-attatch.desktop "$pkgdir/usr/share/applications/mak-attatch.desktop"
    install -Dm644 assets/logo.png "$pkgdir/usr/share/pixmaps/mak-attatch.png"
}
