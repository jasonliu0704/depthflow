#!/usr/bin/env python3
"""
Render one input image through several DepthFlow mode/effect combinations.

Example:
    python scripts/test_image_effects.py ./image.png --modes gentle tour drift \
        --effects none zoom orbit dolly --height 720 --time 4

If depth estimation is slow, render or provide a depth map with --depth so each
combination can reuse it.
"""
from __future__ import annotations

import argparse
import math
import sys
from collections.abc import Iterable
from dataclasses import dataclass, replace
from pathlib import Path
from types import MethodType
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


EFFECTS = ("none", "zoom", "orbit", "dolly", "horizontal", "vertical")
MODES = ("gentle", "tour", "drift", "custom")


@dataclass(frozen=True)
class ModeProfile:
    height_landscape: float
    height_portrait: float
    isometric_landscape: float
    isometric_portrait: float
    offset_x: float
    offset_y: float
    zoom_in: float
    zoom_out: float
    zoom_static: float | None
    steady: float
    focus: float
    center_x: float
    center_y: float
    origin_x: float
    origin_y: float
    invert: float


MODE_PROFILES = {
    "gentle": ModeProfile(
        height_landscape=0.14,
        height_portrait=0.16,
        isometric_landscape=0.16,
        isometric_portrait=0.22,
        offset_x=0.05,
        offset_y=-0.012,
        zoom_in=0.008,
        zoom_out=0.010,
        zoom_static=None,
        steady=0.18,
        focus=0.05,
        center_x=0.0,
        center_y=0.0,
        origin_x=0.0,
        origin_y=0.0,
        invert=0.0,
    ),
    "tour": ModeProfile(
        height_landscape=0.20,
        height_portrait=0.24,
        isometric_landscape=0.24,
        isometric_portrait=0.32,
        offset_x=0.12,
        offset_y=0.03,
        zoom_in=0.015,
        zoom_out=0.025,
        zoom_static=None,
        steady=0.18,
        focus=0.05,
        center_x=0.0,
        center_y=0.0,
        origin_x=0.0,
        origin_y=0.0,
        invert=0.0,
    ),
    "drift": ModeProfile(
        height_landscape=0.18,
        height_portrait=0.20,
        isometric_landscape=0.22,
        isometric_portrait=0.28,
        offset_x=0.085,
        offset_y=0.035,
        zoom_in=0.013,
        zoom_out=0.015,
        zoom_static=None,
        steady=0.18,
        focus=0.05,
        center_x=0.0,
        center_y=0.0,
        origin_x=0.0,
        origin_y=0.0,
        invert=0.0,
    ),
    "custom": ModeProfile(
        height_landscape=0.12,
        height_portrait=0.12,
        isometric_landscape=0.55,
        isometric_portrait=0.55,
        offset_x=0.04,
        offset_y=0.015,
        zoom_in=0.0,
        zoom_out=0.0,
        zoom_static=0.92,
        steady=0.35,
        focus=0.0,
        center_x=0.0,
        center_y=0.0,
        origin_x=0.0,
        origin_y=0.0,
        invert=0.0,
    ),
}


def parse_items(values: list[str], choices: Iterable[str], label: str) -> list[str]:
    allowed = set(choices)
    items: list[str] = []
    for value in values:
        items.extend(part.strip() for part in value.split(",") if part.strip())

    invalid = sorted(set(items) - allowed)
    if invalid:
        raise argparse.ArgumentTypeError(
            f"unknown {label}: {', '.join(invalid)}; choose from {', '.join(sorted(allowed))}"
        )
    return items


def add_pair(left: tuple[float, float], right: tuple[float, float]) -> tuple[float, float]:
    return (left[0] + right[0], left[1] + right[1])


def profile_for_mode(args: argparse.Namespace, mode: str) -> ModeProfile:
    profile = MODE_PROFILES[mode]

    updates: dict[str, float] = {}
    for field in (
        "zoom_in",
        "zoom_out",
        "height_landscape",
        "height_portrait",
        "isometric_landscape",
        "isometric_portrait",
        "offset_x",
        "offset_y",
        "zoom_static",
        "steady",
        "focus",
        "center_x",
        "center_y",
        "origin_x",
        "origin_y",
        "invert",
    ):
        global_value = getattr(args, field)
        mode_value = getattr(args, f"{mode}_{field}")
        if global_value is not None:
            updates[field] = global_value
        if mode_value is not None:
            updates[field] = mode_value

    return replace(profile, **updates)


def zoom_value(cycle: float, profile: ModeProfile) -> float:
    if profile.zoom_static is not None:
        return profile.zoom_static
    zoom_phase = (1 - math.cos(cycle)) / 2
    return 1 - profile.zoom_out + (profile.zoom_in + profile.zoom_out) * zoom_phase


def apply_resize_compat(scene: Any) -> None:
    original_resize = scene.resize

    def compat_resize(self: Any, *args: Any, **kwargs: Any) -> Any:
        if args:
            if len(args) > 2:
                raise TypeError("resize accepts at most width and height as positional arguments")
            if "width" not in kwargs and len(args) >= 1:
                kwargs["width"] = args[0]
            if "height" not in kwargs and len(args) >= 2:
                kwargs["height"] = args[1]
        return original_resize(**kwargs)

    scene.resize = MethodType(compat_resize, scene)


def install_motion_profile(scene: Any, mode: str, effect: str, profile: ModeProfile) -> None:
    from depthflow.scene import DepthScene

    image_width, image_height = scene.image.size
    portrait = image_height >= image_width

    def update(self: Any) -> None:
        DepthScene.update(self)
        cycle = self.cycle

        self.state.steady = profile.steady
        self.state.focus = profile.focus
        self.state.dolly = 0.0
        self.state.center = (profile.center_x, profile.center_y)
        self.state.origin = (profile.origin_x, profile.origin_y)
        if hasattr(self.state, "invert"):
            self.state.invert = profile.invert

        if mode == "custom":
            self.state.height = profile.height_portrait if portrait else profile.height_landscape
            self.state.isometric = profile.isometric_portrait if portrait else profile.isometric_landscape
            self.state.offset = (
                profile.offset_x * math.sin(cycle),
                profile.offset_y * math.cos(cycle),
            )
            self.state.zoom = zoom_value(cycle, profile)

        elif mode == "gentle":
            self.state.height = profile.height_portrait if portrait else profile.height_landscape
            self.state.isometric = profile.isometric_portrait if portrait else profile.isometric_landscape
            self.state.offset = (
                profile.offset_x * math.sin(cycle),
                profile.offset_y * math.cos(cycle),
            )
            self.state.zoom = zoom_value(cycle, profile)

        elif mode == "drift":
            self.state.height = profile.height_portrait if portrait else profile.height_landscape
            self.state.isometric = profile.isometric_portrait if portrait else profile.isometric_landscape
            self.state.offset = (
                profile.offset_x * math.sin(cycle),
                profile.offset_y * math.sin(cycle * 0.5 - math.pi / 6),
            )
            self.state.zoom = zoom_value(cycle, profile)

        else:
            self.state.height = profile.height_portrait if portrait else profile.height_landscape
            self.state.isometric = profile.isometric_portrait if portrait else profile.isometric_landscape
            self.state.offset = (
                profile.offset_x * math.sin(cycle),
                profile.offset_y * math.sin(cycle * 0.5 - math.pi / 8),
            )
            self.state.zoom = zoom_value(cycle, profile)

        if effect == "zoom":
            self.state.zoom += 0.035 * (1 - math.cos(cycle)) / 2
            self.state.focus = 0.12

        elif effect == "orbit":
            self.state.offset = add_pair(
                self.state.offset,
                (0.055 * math.cos(cycle), 0.055 * math.sin(cycle)),
            )
            self.state.steady = 0.25

        elif effect == "dolly":
            self.state.dolly = 0.9 * (1 - math.cos(cycle)) / 2
            self.state.focus = 0.20
            self.state.zoom += 0.018 * math.sin(cycle)

        elif effect == "horizontal":
            self.state.offset = add_pair(
                self.state.offset,
                (0.10 * math.sin(cycle), 0.0),
            )

        elif effect == "vertical":
            self.state.offset = add_pair(
                self.state.offset,
                (0.0, 0.07 * math.sin(cycle)),
            )

    scene.update = MethodType(update, scene)


def render_combo(
    image: Path,
    depth: Path | None,
    output: Path,
    mode: str,
    effect: str,
    args: argparse.Namespace,
) -> None:
    from depthflow.scene import DepthScene
    from shaderflow.scene import WindowBackend

    scene = DepthScene(backend=WindowBackend.Headless)
    try:
        apply_resize_compat(scene)
        scene.initialize()
        scene.input(image=image, depth=str(depth) if depth else None)
        install_motion_profile(scene, mode, effect, profile_for_mode(args, mode))

        main_kwargs = {
            "output": output,
            "fps": args.fps,
            "time": args.time,
        }
        for key in ("width", "height", "quality", "ssaa"):
            value = getattr(args, key)
            if value is not None:
                main_kwargs[key] = value

        scene.main(**main_kwargs)
    finally:
        destroy = getattr(scene, "destroy", None)
        if destroy is not None:
            destroy()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Render test clips for one image across DepthFlow modes and effects.",
    )
    parser.add_argument("image", type=Path, help="input image path")
    parser.add_argument("--depth", type=Path, help="optional depth-map path to reuse")
    parser.add_argument("--output-dir", type=Path, default=Path("effect-mode-tests"))
    parser.add_argument("--modes", nargs="+", default=list(MODES), help=f"modes: {', '.join(MODES)}")
    parser.add_argument("--effects", nargs="+", default=["none", "zoom", "orbit", "dolly"], help=f"effects: {', '.join(EFFECTS)}")
    parser.add_argument("--time", type=float, default=4.0, help="seconds per clip")
    parser.add_argument("--fps", type=int, default=24)
    parser.add_argument("--width", type=int)
    parser.add_argument("--height", type=int)
    parser.add_argument("--quality", type=int)
    parser.add_argument("--ssaa", type=float)
    parser.add_argument("--zoom-in", type=float, help="override max zoom-in amount for all modes")
    parser.add_argument("--zoom-out", type=float, help="override max zoom-out amount for all modes")
    parser.add_argument("--zoom-static", type=float, help="set a constant zoom value for all modes")
    parser.add_argument("--height-landscape", type=float, help="override landscape height for all modes")
    parser.add_argument("--height-portrait", type=float, help="override portrait height for all modes")
    parser.add_argument("--isometric-landscape", type=float, help="override landscape isometric for all modes")
    parser.add_argument("--isometric-portrait", type=float, help="override portrait isometric for all modes")
    parser.add_argument("--offset-x", type=float, help="override horizontal offset strength for all modes")
    parser.add_argument("--offset-y", type=float, help="override vertical offset strength for all modes")
    parser.add_argument("--steady", type=float, help="override focal depth for offsets for all modes")
    parser.add_argument("--focus", type=float, help="override focal depth for perspective changes for all modes")
    parser.add_argument("--center-x", type=float, help="override center x for all modes")
    parser.add_argument("--center-y", type=float, help="override center y for all modes")
    parser.add_argument("--origin-x", type=float, help="override origin x for all modes")
    parser.add_argument("--origin-y", type=float, help="override origin y for all modes")
    parser.add_argument("--invert", type=float, help="set invert if this DepthFlow version exposes it")
    for mode in MODES:
        parser.add_argument(f"--{mode}-zoom-in", dest=f"{mode}_zoom_in", type=float)
        parser.add_argument(f"--{mode}-zoom-out", dest=f"{mode}_zoom_out", type=float)
        parser.add_argument(f"--{mode}-zoom-static", dest=f"{mode}_zoom_static", type=float)
        parser.add_argument(f"--{mode}-height-landscape", dest=f"{mode}_height_landscape", type=float)
        parser.add_argument(f"--{mode}-height-portrait", dest=f"{mode}_height_portrait", type=float)
        parser.add_argument(f"--{mode}-isometric-landscape", dest=f"{mode}_isometric_landscape", type=float)
        parser.add_argument(f"--{mode}-isometric-portrait", dest=f"{mode}_isometric_portrait", type=float)
        parser.add_argument(f"--{mode}-offset-x", dest=f"{mode}_offset_x", type=float)
        parser.add_argument(f"--{mode}-offset-y", dest=f"{mode}_offset_y", type=float)
        parser.add_argument(f"--{mode}-steady", dest=f"{mode}_steady", type=float)
        parser.add_argument(f"--{mode}-focus", dest=f"{mode}_focus", type=float)
        parser.add_argument(f"--{mode}-center-x", dest=f"{mode}_center_x", type=float)
        parser.add_argument(f"--{mode}-center-y", dest=f"{mode}_center_y", type=float)
        parser.add_argument(f"--{mode}-origin-x", dest=f"{mode}_origin_x", type=float)
        parser.add_argument(f"--{mode}-origin-y", dest=f"{mode}_origin_y", type=float)
        parser.add_argument(f"--{mode}-invert", dest=f"{mode}_invert", type=float)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--dry-run", action="store_true", help="print planned outputs without rendering")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.modes = parse_items(args.modes, MODES, "mode")
    args.effects = parse_items(args.effects, EFFECTS, "effect")

    image = args.image.expanduser().resolve()
    depth = args.depth.expanduser().resolve() if args.depth else None
    if not image.exists():
        parser.error(f"image not found: {image}")
    if depth and not depth.exists():
        parser.error(f"depth map not found: {depth}")

    output_dir = args.output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    for mode in args.modes:
        profile = profile_for_mode(args, mode)
        for effect in args.effects:
            output = output_dir / f"{image.stem}__{mode}__{effect}.mp4"
            if output.exists() and not args.overwrite:
                print(f"skip existing: {output}")
                continue

            print(
                "render: "
                f"mode={mode} effect={effect} "
                f"zoom={profile.zoom_static if profile.zoom_static is not None else 'motion'} "
                f"zoom_out={profile.zoom_out:g} zoom_in={profile.zoom_in:g} "
                f"height={profile.height_landscape:g}/{profile.height_portrait:g} "
                f"offset={profile.offset_x:g}/{profile.offset_y:g} "
                f"-> {output}"
            )
            if not args.dry_run:
                render_combo(image, depth, output, mode, effect, args)


if __name__ == "__main__":
    main()
