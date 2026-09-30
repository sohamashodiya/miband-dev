"""Where the calibration kits read and write (shared by measure.py and ../face-calib/measure_face.py).

The kits ship inside the miband-dev plugin, which is read-only: nothing is ever written next to
this file. Everything a kit writes goes into the user's WORKSPACE (their repo with devices/,
apps/, faces/, signing/):

    <workspace>/devices/<model>/profile.json       the profile (your calibration)
    <workspace>/devices/<model>/evidence/          per-photo results, quick-app kit
    <workspace>/devices/<model>/evidence-face/     per-photo results, face kit
    <workspace>/devices/<model>/results/           annotated rectified photos (gitignored)

The workspace is --workspace, else $MIBAND_WORKSPACE, else the nearest folder above the current
directory (then above this file) that has a devices/ folder, else the current directory.

Reading a profile: the workspace's devices/<model>/profile.json when it exists, else the default
shipped with the plugin (<plugin>/data/profiles/<model>/profile.json). The first write for a
model copies the shipped default into the workspace, so your measurements are added on top of it.
"""
import os
import shutil

HERE = os.path.dirname(os.path.abspath(__file__))
# Shipped defaults: <plugin>/data/profiles when the kit runs from the plugin (tools/vela-calib).
DEFAULTS_DIR = os.path.normpath(os.path.join(HERE, '..', '..', 'data', 'profiles'))


def _find_up(start):
    d = os.path.abspath(start)
    while True:
        if os.path.isdir(os.path.join(d, 'devices')):
            return d
        up = os.path.dirname(d)
        if up == d:
            return None
        d = up


def root(explicit=None):
    """The workspace root."""
    if explicit:
        return os.path.abspath(explicit)
    env = os.environ.get('MIBAND_WORKSPACE')
    if env:
        return os.path.abspath(env)
    return _find_up(os.getcwd()) or _find_up(HERE) or os.getcwd()


def devices_dir(explicit=None):
    return os.path.join(root(explicit), 'devices')


def default_profile(model):
    return os.path.join(DEFAULTS_DIR, model, 'profile.json')


def read_profile_path(model, explicit=None):
    """Workspace profile if present, else the shipped default (which may not exist either)."""
    mine = os.path.join(devices_dir(explicit), model, 'profile.json')
    if os.path.exists(mine):
        return mine
    shipped = default_profile(model)
    return shipped if os.path.exists(shipped) else mine


def write_profile_path(model, explicit=None, seed=True):
    """The workspace profile. With seed, a missing one starts as a copy of the shipped default."""
    mine = os.path.join(devices_dir(explicit), model, 'profile.json')
    shipped = default_profile(model)
    if seed and not os.path.exists(mine) and os.path.exists(shipped):
        os.makedirs(os.path.dirname(mine), exist_ok=True)
        shutil.copyfile(shipped, mine)
        print('seeded %s from the shipped default profile' % mine)
    return mine


def is_default(path):
    return os.path.abspath(path).startswith(DEFAULTS_DIR + os.sep)
