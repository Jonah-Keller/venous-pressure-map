"""Build the app's real-anatomy 3D example from one open-data head CT angiogram.

Source: TopBrain 2025 challenge release (University Hospital Zurich), Zenodo
record 16878417, case topcow_ct_<ID>. Terms: open non-commercial use with
attribution. The expert labels cover the superior sagittal sinus (40), straight
sinus (36), vein of Galen (35), internal cerebral veins (37) and basal veins
(38/39) but not the transverse/sigmoid sinuses, so those are grown here from the
labelled sinuses through contrast-filled voxels:

  1. Resample to 1 mm, canonical RAS orientation.
  2. Candidate venous voxels = 110-480 HU, not cortical bone (>650 HU, +1 mm),
     not the labelled arteries (+2 mm).
  3. Keep what is connected to the labelled sinuses; smooth; marching cubes.
  4. Trace each side's drainage path (SSS -> torcula -> transverse -> sigmoid ->
     jugular bulb) as a minimum-cost route through the sinus mask, and record for
     every mesh vertex which path point it belongs to. The app uses this to paint
     pressures along the real sinus.
  5. Also save a skull surface and a 2 mm CT volume (for the movable slices).

Run (needs nibabel, scikit-image, scipy, fast-simplification; not the app):
    python tools/build_example_scan.py IMAGE.nii.gz LABELS.nii.gz \
        --out venous/data/example_scan.npz --preview /tmp/preview
"""
from __future__ import annotations

import argparse
from pathlib import Path

import fast_simplification
import nibabel as nib
import numpy as np
from scipy import ndimage as ndi
from skimage import measure
from skimage.graph import route_through_array

VENOUS_LABELS = [35, 36, 37, 38, 39, 40]
SSS, STRAIGHT = 40, 36
ARTERY_LABELS = range(1, 35)


def load_1mm(img_path: Path, lab_path: Path):
    img = nib.as_closest_canonical(nib.load(img_path))
    lab = nib.as_closest_canonical(nib.load(lab_path))
    zooms = np.array(img.header.get_zooms()[:3])
    ct = ndi.zoom(np.asarray(img.dataobj, np.float32), zooms, order=1)
    lb = ndi.zoom(np.asarray(lab.dataobj, np.int16), zooms, order=0)
    return ct, lb


def segment_sinuses(ct, lb):
    seeds = np.isin(lb, VENOUS_LABELS)
    bone = ndi.binary_dilation(ct > 650, iterations=1)
    arteries = ndi.binary_dilation(np.isin(lb, list(ARTERY_LABELS)), iterations=2)
    cand = (ct > 110) & (ct < 480) & ~bone & ~arteries
    cand = ndi.binary_opening(cand, iterations=1) | seeds
    grown = ndi.binary_propagation(seeds, mask=cand)
    labels, n = ndi.label(grown)
    keep = np.unique(labels[seeds])
    mask = np.isin(labels, keep[keep > 0])
    mask = ndi.binary_closing(mask, iterations=1)
    return ndi.binary_fill_holes(mask)


def surface(mask_or_vol, level, sigma, faces_target, spacing=1.0):
    vol = ndi.gaussian_filter(mask_or_vol.astype(np.float32), sigma)
    verts, faces, _, _ = measure.marching_cubes(vol, level, spacing=(spacing,) * 3)
    ratio = max(0.0, 1 - faces_target / len(faces))
    if ratio > 0:
        verts, faces = fast_simplification.simplify(verts.astype(np.float32),
                                                    faces.astype(np.int64), ratio)
    return verts.astype(np.float32), faces.astype(np.int32)


def drainage_paths(mask, lb):
    """Minimum-cost routes from the front of the SSS to the lowest point of the
    sinus on each side, preferring the middle of the vessel."""
    dist = ndi.distance_transform_edt(mask)
    cost = np.where(mask, 1.0 / (dist + 0.5) ** 2, 1e6)
    sss = np.argwhere(lb == SSS)
    start = tuple(sss[np.argmax(sss[:, 1] + 0.3 * sss[:, 2])])     # most anterior/superior
    xs = np.argwhere(mask)
    mid_x = np.median(sss[:, 0])
    paths = {}
    for side, sign in (("Left", -1), ("Right", 1)):                 # RAS: +x is patient's right
        lateral = xs[(xs[:, 0] - mid_x) * sign > 25]
        if not len(lateral):
            continue
        end = tuple(lateral[np.argmin(lateral[:, 2])])                # lowest lateral voxel
        route, _ = route_through_array(cost, start, end, fully_connected=True, geometric=True)
        p = ndi.gaussian_filter1d(np.array(route, float), 3, axis=0)  # smooth staircase
        paths[side] = p
    return paths, mid_x


def landmarks(path, mid_x):
    """Indices of torcula, transverse-sigmoid junction and path end."""
    off = np.abs(path[:, 0] - mid_x)
    torc = int(np.argmax(off > 8))                                   # leaves the midline
    tail = path[torc:]
    # TSJ: the most lateral point before the route turns down into the sigmoid
    drop = np.r_[0, np.cumsum(np.maximum(0, -np.diff(tail[:, 2])))]
    tsj = torc + int(np.argmax(np.abs(tail[:, 0] - mid_x) - 0.6 * drop))
    return {"torcula": torc, "tsj": tsj, "end": len(path) - 1}


def build(img_path, lab_path, out, preview=None, case="topcow_ct_012"):
    ct, lb = load_1mm(img_path, lab_path)
    mask = segment_sinuses(ct, lb)
    paths, mid_x = drainage_paths(mask, lb)

    verts, faces = surface(mask, 0.5, 0.8, 60000)
    deep = ndi.binary_dilation(np.isin(lb, [35, 36, 37, 38, 39]), iterations=3)
    vi = np.clip(np.round(verts).astype(int), 0, np.array(mask.shape) - 1)
    is_deep = deep[vi[:, 0], vi[:, 1], vi[:, 2]]

    # nearest path point per vertex (brute force in chunks; ~1e5 x 1e3)
    v_side = np.full(len(verts), -1, np.int8)
    v_idx = np.zeros(len(verts), np.int32)
    best = np.full(len(verts), np.inf)
    for s_i, side in enumerate(("Left", "Right")):
        if side not in paths:
            continue
        p = paths[side]
        for a in range(0, len(verts), 20000):
            d = np.linalg.norm(verts[a:a + 20000, None, :] - p[None], axis=2)
            j = d.argmin(1); dj = d[np.arange(len(j)), j]
            upd = dj < best[a:a + 20000]
            best[a:a + 20000][upd] = dj[upd]
            v_side[a:a + 20000][upd] = s_i
            v_idx[a:a + 20000][upd] = j[upd]
    v_side[is_deep] = 2

    skull_v, skull_f = surface(ndi.zoom(ct, 0.5, order=1) > 350, 0.5, 1.0, 24000, spacing=2.0)
    small = ndi.zoom(ct, 1 / 2.0, order=1)
    vol8 = np.clip((small + 20) / 160 * 255, 0, 255).astype(np.uint8)  # brain-ish window

    centre = np.array(mask.shape) / 2.0
    lm = {s: landmarks(p, mid_x) for s, p in paths.items()}
    np.savez_compressed(
        out,
        verts=(verts - centre).astype(np.float32), faces=faces,
        v_side=v_side, v_idx=v_idx,
        skull_verts=(skull_v - centre).astype(np.float32), skull_faces=skull_f,
        vol=vol8, vol_spacing=np.float32(2.0), vol_origin=(-centre).astype(np.float32),
        path_left=(paths["Left"] - centre).astype(np.float32),
        path_right=(paths["Right"] - centre).astype(np.float32),
        lm_left=np.array([lm["Left"][k] for k in ("torcula", "tsj", "end")], np.int32),
        lm_right=np.array([lm["Right"][k] for k in ("torcula", "tsj", "end")], np.int32),
        source=np.array(f"TopBrain 2025 challenge data (University Hospital Zurich), {case}; "
                        "Zenodo 10.5281/zenodo.16878417; non-commercial use with attribution."),
    )
    print(f"mask {mask.sum() / 1000:.1f} ml | mesh {len(verts)} v / {len(faces)} f | "
          f"skull {len(skull_f)} f | paths L {len(paths['Left'])} R {len(paths['Right'])} | "
          f"landmarks {lm} | {Path(out).stat().st_size / 1e6:.1f} MB")
    if preview:
        _preview(ct, mask, paths, Path(preview))


def _preview(ct, mask, paths, outdir):
    """Small maximum-intensity projections of the mask for checking by eye."""
    from PIL import Image, ImageDraw
    outdir.mkdir(parents=True, exist_ok=True)
    for ax, name in ((0, "lateral"), (1, "frontal"), (2, "top")):
        mip = mask.max(axis=ax).astype(np.uint8) * 255
        im = Image.fromarray(np.rot90(mip)).convert("RGB")
        d = ImageDraw.Draw(im)
        keep = [a for a in range(3) if a != ax]
        for side, colour in (("Left", (255, 80, 80)), ("Right", (80, 160, 255))):
            p = paths[side][:, keep]
            h = mip.shape[1]
            d.line([(q[0], h - 1 - q[1]) for q in p], fill=colour, width=2)
        im.save(outdir / f"mip_{name}.png")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("image"); ap.add_argument("labels")
    ap.add_argument("--out", default="venous/data/example_scan.npz")
    ap.add_argument("--preview")
    ap.add_argument("--case", default="topcow_ct_012")
    a = ap.parse_args()
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    build(a.image, a.labels, a.out, a.preview, a.case)
