# Capturing a real venue

Everything shipped in `assets/` is generated. This is how you replace it
with the real thing, in the order that actually works.

## 1. Geometry first, pixels second
Get the floor plan. Tape-measure every reservable table: centre position
relative to two fixed walls, dimensions, seat count, chair positions.
Type it into `tools/venue_gen.py`, re-run `python3 run.py --rebuild`.
Set `verification` to `MEASURED`. You now have a correct booking system
with placeholder art, which is worth more than beautiful art over wrong
geometry.

## 2. 360 panoramas per table
The single highest-value capture, and the cheapest.

- Camera: Insta360 X4/X5 or Ricoh Theta X. Roughly £300-500.
- Tripod at **seated eye height: 1.15-1.20 m**, not standing height. This
  is the detail everyone gets wrong and it is the whole point.
- One shot per table, tripod on the table's centre. Optionally one per
  chair for the premium tables.
- Shoot at service lighting, evening, candles lit, before guests arrive.
  Shoot a daytime set too.
- Export equirectangular JPG, 4096x2048 or better.
- Drop in as `assets/panoramas/t14.jpg`. Set that table's seats to
  `PHOTOGRAPH_VERIFIED`. Nothing else changes.

Note each seat's real yaw while you're there — the angle from the chair
toward the table centre. That is what makes the seat picker feel right.

## 3. The illustrated map
Either commission an illustrator to paint over your measured plan at the
same 720x1280 coordinate space, or block the room out in Blender from the
plan and render one top-down orthographic frame. Save as
`assets/map/ground.png`. The hotspots are read from `tables.json`, so they
land correctly on any artwork drawn to the same coordinate space.

## 4. Gaussian splatting (later)
Only worth it once 1-3 are done and the booking flow is live.

- Capture: **Scaniverse** (free, processes on-device in 60-90s, exports PLY
  and SPZ) or **Polycam** (LiDAR on iPhone 12 Pro and later, which matters
  enormously for white walls, dark floors and mirrors, where camera-only
  photogrammetry produces noise or holes).
- Walk slowly, overlapping, at two heights. Kill autofocus hunting by
  keeping distance steady.
- Render on the web with **Spark** (World Labs) — actively developed, THREE.js
  integration, 98%+ WebGL2 coverage, mobile and WebXR, PLY/SPZ/SPLAT/KSPLAT/SOG,
  LoD trees, streaming by HTTP range requests. Do not start with
  mkkellogg/GaussianSplats3D; its author has stopped developing it and points
  people at Spark.
- Drop the file in `assets/splats/` and add a splat layer to `static/js/`.
  The booking flow must never wait on it.

## 5. What you cannot do
You cannot take a restaurant's existing Matterport or Kuula tour and edit it.
Matterport's developer tools are private-use; commercial use requires a
business-development agreement, typically revenue-share, and sandbox SDK keys
only work on localhost. Google Street View imagery may be embedded through
Google's viewers and not downloaded or modified. Any venue's published tour
is copyrighted work belonging to whoever paid for the shoot.

Embedding is allowed and this app supports it — see the Google section of
the README. Editing is not. Capture your own.

## Rough budget for one venue
- 360 camera + tripod: £350-550 one-off
- One evening of shooting: 3-4 hours
- Measuring: half a day
- Illustration: £300-900 commissioned, or free if you render it yourself
- LiDAR phone for splats: only if you go to step 4
