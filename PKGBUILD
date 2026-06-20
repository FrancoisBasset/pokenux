pkgname=pokenux
pkgver=0.0.1
pkgrel=1
pkgdesc="Pokénux is a modern Textual TUI to explore Pokémon and cards, play quizzes, and open boosters from your terminal."
arch=('any')
url="https://github.com/FrancoisBasset/pokenux"
license=('MIT')
depends=('python>=3.14')
makedepends=('python-build' 'python-installer' 'python-poetry-core')

build() {
  cd "$startdir"
  python -m build --wheel --no-isolation
}

package() {
  cd "$startdir"
  python -m installer --destdir="$pkgdir" dist/*.whl
}
