"""G8 stage 1: the low-poly Glock loads through gltf_patch, has the separate parts, stays under the triangle budget."""
from pathlib import Path

import pytest
from panda3d.core import Filename, loadPrcFileData

from fps.game import gltf_patch

GLB = Path(__file__).resolve().parent.parent / 'assets/review/glock/model/glock_lowpoly.glb'
PARTS = ('Frame', 'Slide', 'Trigger', 'Mag')
TRI_BUDGET = 8000          # gun only; the M4 hands add ~4.5k, whole model stays under the M4's 14.8k


@pytest.fixture(scope='module')
def model():
    if not GLB.exists():
        pytest.skip('glock_lowpoly.glb not built')
    gltf_patch.apply()
    loadPrcFileData('', 'window-type none')
    loadPrcFileData('', 'audio-library-name null')
    from direct.showbase.ShowBase import ShowBase
    base = ShowBase()
    return base.loader.loadModel(Filename.from_os_specific(str(GLB)))


def tri_count(np_):
    n = 0
    for gn in np_.findAllMatches('**/+GeomNode'):
        for g in gn.node().getGeoms():
            n += g.getNumPrimitives() and sum(g.getPrimitive(i).getNumFaces() for i in range(g.getNumPrimitives()))
    return n


def test_parts_exist(model):
    for p in PARTS:
        assert not model.find(f'**/{p}*').isEmpty(), p


def test_triangle_budget(model):
    assert 1000 < tri_count(model) <= TRI_BUDGET


def test_real_size_in_cm(model):
    mn, mx = model.getTightBounds()
    length = mx.y - mn.y       # Panda Z-up: the length is Y
    assert 17.5 < length < 19.5     # Glock 17: 18.6 cm
