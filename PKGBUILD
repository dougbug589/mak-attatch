# Maintainer: yourname <youremail>
pkgname=poster-attacher
pkgver=1.0.0
pkgrel=1
pkgdesc="Attach cover art posters to video files"
arch=('x86_64' 'aarch64')
url="https://github.com/dougbug589/poster-attacher"
license=('MIT')
depends=('python' 'python-pyqt6' 'python-requests' 'python-guessit' 'ffmpeg' 'mkvtoolnix-cli')
makedepends=('python-virtualenv')
options=(!strip)
source=()
sha256sums=()

build() {
    cd "$startdir"
    python -m venv --system-site-packages buildenv
    buildenv/bin/pip install -r requirements.txt
}

package() {
    cd "$startdir"
    install -Ddm755 "$pkgdir/usr/lib/$pkgname"
    cp -r core ui config.py main.py requirements.txt P.png "$pkgdir/usr/lib/$pkgname/"
    cp -r buildenv "$pkgdir/usr/lib/$pkgname/.venv"

    install -Dm755 /dev/stdin "$pkgdir/usr/bin/$pkgname" <<EOF
#!/bin/sh
exec /usr/lib/$pkgname/.venv/bin/python /usr/lib/$pkgname/main.py "\$@"
EOF

    install -Dm644 poster-attacher.desktop "$pkgdir/usr/share/applications/poster-attacher.desktop"
}
