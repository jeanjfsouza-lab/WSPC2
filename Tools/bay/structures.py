"""The bridges and tunnels of the Bay city: where each one begins and ends, and what it is made of. Not run on
its own. Bridges first; tunnels are described further down, above TUNNELS.

A bridge is one edge of the road network (class "bridge"). Its ends over land are ordinary road, built by the
sector they lie in, on an abutment: a platform of ground square to the bridge's axis that reaches out past
the sea wall. From one abutment face to the other the deck is a structure of its own, built by span_mesh.py.

  at        a point on the bridge (metres, east/north): the nearest "bridge" edge of the network is the one meant
  faces     two points, one near each abutment face; each is projected on the bridge's axis. The deck spans
            the stretch between them.
  approach  per face, in the same order: "sector" (the sector there builds the road up to the face, on the
            platform below) or "solid" (no sector there yet: the bridge mesh carries a walled ramp back to the
            junction, so the deck never ends in the air)
  wings     per face, optional (default True): whether the bridge mesh builds the parapet around the abutment
            platform. False where the sector's own terrace parapet already closes the drop.
  main      lengths of the main spans, placed around the middle of the deck (metres)
  side      target length of every other span
Platform: PLATFORM_HALF_M to each side of the axis, PLATFORM_BACK_M long behind the face. sector_prep.py adds it
to the land of any sector it touches, so the sea wall goes around it.
"""
import math

import numpy as np

import roadgeom

PLATFORM_HALF_M = 14.0
PLATFORM_BACK_M = 18.5

STRUCTURES = {
    # Ponte Central da Baia: 560 m of deck from the Centro Civico bridgehead (sector CC2) north to the city
    # hall shore. Four lanes and two sidewalks on a steel box girder; nine spans, the middle three (70, 110,
    # 70 m) deeper over their piers, with about 20 m of clearance at the crest for the ships of the bay.
    # North face: the south wall of the city hall's terrace (sector PF1), which carries its own parapet, so the
    # bridge builds no wing parapet there. South face: the abutment platform of sector CC2.
    "PCB": {"title": "Ponte Central da Baia", "at": (1778.0, 1190.0),
            "faces": [(1767.3, 1482.0), (1788.36, 912.28)],
            "approach": ["sector", "sector"], "wings": [False, True],
            # status: in the map and reviewed from both sides; the north end still lands on a walled ramp
            # ("solid") until the city hall sector there is built
            "main": [70.0, 110.0, 70.0], "side": 50.0, "status": "built"},

    # Ponte do Rio Leste: the east end of the avenue across downtown, 452 m of deck over the river to the port
    # district. Same family as the Ponte Central (four lanes, steel box girder, three deeper main spans).
    # West face: 6 m out from the quay wall of sector CC11. East face: the abutment platform of sector EP3 on the
    # port bank (until 2026-11-16 no sector stood there and the mesh carried a walled ramp on to the junction).
    "PRL": {"title": "Ponte do Rio Leste", "at": (2540.0, -61.0),
            "faces": [(2274.0, -64.0), (2726.0, -59.8)],
            "approach": ["sector", "sector"], "wings": [True, True],
            "main": [70.0, 110.0, 70.0], "side": 50.0, "status": "built"},

    # Ponte da Via Expressa: the expressway from the Centro Sul's south-east corner (CS27) over the Rio Leste, east,
    # then south along the drawn elevated road and east again to the east bank at (2698, -958); about 470 m of deck
    # in two pieces of the network (the first as traced, built along by CS12 and CS27). West face: 4 m out from
    # the quay where CS12 and CS27 meet (x = 2283); east face: the abutment platform of EP5 on the east bank.
    "PVE": {"title": "Ponte da Via Expressa", "at": [(2330.0, -800.0), (2550.0, -958.0)],
            "faces": [(2287.0, -809.0), (2688.0, -957.6)],
            "approach": ["sector", "sector"], "wings": [True, True],
            "main": [60.0, 80.0, 60.0], "side": 42.0, "status": "built"},

    # Ponte Pensil Oeste: the highway from the Ilha Oeste bluff north over the strait to the roundabout on the north shore;
    # a suspension bridge (span_mesh "suspension": towers on the two main piers, cables, hangers); its north end on the
    # roundabout's platform (sector NH1)
    "PPO": {"title": "Ponte Pensil Oeste", "at": (-1575.0, 1100.0),
            "faces": [(-1567.5, 786.0), (-1583.6, 1403.0)],
            "approach": ["sector", "sector"], "wings": [False, True], "suspension": True,
            "main": [400.0], "side": 110.0, "status": "built"},
}


def find_edge(net, at, cls="bridge"):
    """The edge of the given class that passes nearest to the point."""
    best, found = 1e18, None
    for e in net["edges"]:
        if e["cls"] != cls:
            continue
        pts = np.asarray(e["pts"], dtype=np.float64)[:, :2]
        a, b = pts[:-1], pts[1:]
        ab = b - a
        t = np.clip(((np.array(at) - a) * ab).sum(axis=1) / np.maximum((ab ** 2).sum(axis=1), 1e-9), 0.0, 1.0)
        d = float(np.min(np.hypot(*(a + ab * t[:, None] - np.array(at)).T)))
        if d < best:
            best, found = d, e
    return found


def station_of(road, point):
    """Distance along the road of the point of its centre line nearest to `point`."""
    a, b = road.xy[:-1], road.xy[1:]
    ab = b - a
    t = np.clip(((np.array(point) - a) * ab).sum(axis=1) / np.maximum((ab ** 2).sum(axis=1), 1e-9), 0.0, 1.0)
    d = np.hypot(*(a + ab * t[:, None] - np.array(point)).T)
    k = int(np.argmin(d))
    return float(road.s[k] + t[k] * (road.s[k + 1] - road.s[k]))


def bridge_edge(net, spec):
    """The bridge's edge: the nearest "bridge" edge to spec["at"], or, when "at" is a list of points, the edges
    nearest to each joined end to end into one (a bridge the network carries in pieces: a junction on it, or a
    stretch built as traced followed by a stretch drawn by an edit)."""
    at = spec["at"]
    if not isinstance(at[0], (list, tuple)):
        return find_edge(net, at)
    edges = [find_edge(net, p) for p in at]
    pts = [list(p) for p in edges[0]["pts"]]
    first_b = edges[0]["b"]
    # orient the first edge so that it ends where the second begins
    if edges[0]["a"] in (edges[1]["a"], edges[1]["b"]):
        pts = pts[::-1]
        first_b = edges[0]["a"]
    end = first_b
    for e in edges[1:]:
        p = [list(q) for q in e["pts"]]
        if e["a"] != end:
            p = p[::-1]
            end = e["a"]
        else:
            end = e["b"]
        pts += p[1:]
    merged = dict(edges[0])
    merged["pts"] = pts
    merged["curve"] = True                  # keep every point: the pieces are already smooth where they meet
    return merged


def layout(net, name):
    """The bridge's road and the two stations its deck runs between: (road, s_first, s_last, approaches, wings),
    with s_first < s_last along the road and `approaches` and `wings` in that order."""
    spec = STRUCTURES[name]
    road = roadgeom.Road(bridge_edge(net, spec))
    stations = [station_of(road, p) for p in spec["faces"]]
    order = sorted(range(2), key=lambda i: stations[i])
    wings = spec.get("wings", [True, True])
    return road, stations[order[0]], stations[order[1]], [spec["approach"][i] for i in order], [wings[i] for i in order]


def platform_rings(net):
    """Abutment platforms of every bridge as [(name, ring)], ring counter-clockwise in metres."""
    rings = []
    for name in STRUCTURES:
        road, s0, s1, _, _ = layout(net, name)
        for s_face, back in ((s0, -1.0), (s1, 1.0)):
            p_face, t, n = road.at(s_face)
            p_back, _, _ = road.at(s_face + back * PLATFORM_BACK_M)
            ring = [tuple(p_back + n * PLATFORM_HALF_M), tuple(p_back - n * PLATFORM_HALF_M),
                    tuple(p_face - n * PLATFORM_HALF_M), tuple(p_face + n * PLATFORM_HALF_M)]
            area = sum(ring[i][0] * ring[(i + 1) % 4][1] - ring[(i + 1) % 4][0] * ring[i][1] for i in range(4))
            rings.append((name, [(float(x), float(y)) for x, y in (ring if area > 0 else ring[::-1])]))
    return rings


def near_platform(rings, x, y, reach=1.2):
    """True when the point lies on or beside the edge of an abutment platform (its parapet stands there)."""
    for _, ring in rings:
        for i in range(len(ring)):
            (ax, ay), (bx, by) = ring[i], ring[(i + 1) % len(ring)]
            dx, dy = bx - ax, by - ay
            t = max(0.0, min(1.0, ((x - ax) * dx + (y - ay) * dy) / max(dx * dx + dy * dy, 1e-9)))
            if math.hypot(x - ax - t * dx, y - ay - t * dy) <= reach:
                return True
    return False


# ---------------------------------------------------------------------------------------------------------
# Tunnels. A tunnel is one edge of the network of class "tunnel" that carries a designed profile (a "depth":
# see design_network.py). Its mesh, built by tunnel_mesh.py, runs the edge's whole length: an open ramp between
# retaining walls at each end, and a box (floor, walls, roof) where the road is deep enough for a roof to
# fit under the ground. The road that leads to it ends square at the edge's first point, level with it.
#
# What the rest of the pipeline takes from here:
#   void_rings()   the footprint of each open ramp. A sector's ground mesh leaves a hole there (sector_mesh.py)
#                  and no building stands on it (plan_lots.py). The ground above the covered part is the
#                  sector's own, untouched.
#   the tunnel's whole length must lie under built sectors, on land: the landscape is lowered under all of
#   it (build_surface.py reads the carve.npz that tunnel_mesh.py writes), and only a sector's ground hides that.
#
#   at        a point on the tunnel (metres, east/north): the nearest "tunnel" edge is the one meant
#   clear     headroom over the road (default TUNNEL_CLEAR_M)
# ---------------------------------------------------------------------------------------------------------
TUNNEL_CLEAR_M = 4.9            # headroom
TUNNEL_ROOF_M = 0.8             # roof slab
TUNNEL_COVER_M = 0.25           # least ground over the roof slab, at a portal
TUNNEL_SHOULDER_M = 0.6         # raised strip between the carriageway and each wall
TUNNEL_WALL_M = 0.6
TUNNEL_PARAPET_M = 1.05         # the walls of an open ramp stand this far above the ground beside them
TUNNEL_HEAD_M = 0.8             # thickness of the wall over a portal, counted into the covered part

TUNNELS = {
    # Tunel da Orla Leste: the waterfront avenue under the riverside promenade south of the Banco Central,
    # 527 m from mouth to mouth, about 345 m of it covered. Four lanes; floor 6.4 m below the promenade.
    "TOL": {"title": "Tunel da Orla Leste", "at": (2253.0, -500.0), "status": "built"},
    # Tunel em S: under the Centro Oeste, from the street along y = -133 (x = -821) to the street along y = -437
    # (x = -672), 410 m in an S under the houses of CW95 to CW98; two lanes, 7 m deep (the user, 2026-11-16: every
    # dashed stretch of the drawing is a real tunnel).
    "TS": {"title": "Tunel em S", "at": (-760.0, -283.0), "status": "built"},
    # Tunel do Trevo Sul: the street at x = -665 under green land south of the Centro Oeste to the Trevo Rodoviario
    # Sul, 388 m; its north mouth is a junction built at 0.6 m, so it is designed 9 m deep (floor -5 m).
    "TTS": {"title": "Tunel do Trevo Sul", "at": (-664.0, -1250.0), "status": "built"},
    # Tunel Expresso Central: downtown's main avenue under the valley between downtown and the Centro Oeste, straight
    # from (1299, -83) to (389, -95), 910 m; four lanes, 16.5 m deep (floor about -13 m, as the drawing's -12.7 m).
    "TEC": {"title": "Tunel Expresso Central", "at": (845.0, -89.0), "status": "built"},
    # Tunel do Vale: the drawing's second tunnel (the light blue band) from the plaza at (1004, 72) down the valley
    # to the junction by CS6 at (1090, -683), 1193 m, 7 m under the valley floor, crossing over the first.
    "TV": {"title": "Tunel do Vale", "at": (745.0, -330.0), "status": "built"},
    # Tunel Subaquatico Leste: from the end of the waterfront avenue on the west bank (CC14) under the Rio Leste to
    # the big curved street of the port on the east bank, 690 m, floor about -18 m (the drawing: -12.1 m), ramps of
    # 12 %. Under the river it lies in the bed ("under_water"): no hole in the sea there, and the bed is raised
    # over it where it would be shallower than the roof.
    "TSL": {"title": "Tunel Subaquatico Leste", "at": (2600.0, 383.0), "status": "built", "under_water": True},
    # Tunel da Orla Norte: the north freeway from the coastal causeway's junction (x = -14) along the north edge under two
    # spurs and the Encosta Sinuosa's ridge to its east foot (x = 1250), about 1.27 km; and its branch south under the
    # ridge's flank to the square at (1032, 2064)
    "TN": {"title": "Tunel da Orla Norte", "at": (600.0, 2258.0), "status": "built"},
    "TNB": {"title": "Tunel da Orla Norte - ramal sul", "at": (1196.0, 2200.0), "status": "built"},
    # Distrito Norte: the avenue under the district's centre (floor -6.2 m, as the drawing labels it), and the dashed
    # roads west: from the square at the Tunel da Orla Norte's branch down to the shore, and from the shore up to the
    # little square at (1635, 1986)
    "TNA": {"title": "Tunel Norte-Aeroporto", "at": (2686.0, 1866.0), "status": "built"},
    "TDN1": {"title": "Tunel do Distrito Norte - oeste", "at": (1180.0, 1850.0), "status": "built"},
    "TDN2": {"title": "Tunel do Distrito Norte - leste", "at": (1543.0, 1833.0), "status": "built"},
}
TUNNEL_BURY_M = 1.0             # least river bed over the roof of a tunnel's stretch under the water


def tunnel_half_width(road):
    """From the tunnel's axis to the outer face of its walls."""
    return road.half + TUNNEL_SHOULDER_M + TUNNEL_WALL_M


def tunnel_layout(net, name):
    """The tunnel's road and the two stations between which it is covered: (road, s_north, s_south), named
    for the order along the road, not for the compass. The roof begins where the road is deep enough below
    the line between the two mouths for headroom, roof slab and cover to fit."""
    spec = TUNNELS[name]
    edge = find_edge(net, spec["at"], "tunnel")
    if edge is None or not edge.get("depth"):
        raise ValueError("tunnel %s: no tunnel edge with a designed profile near %s" % (name, spec["at"]))
    road = roadgeom.Road(edge)
    need = spec.get("clear", TUNNEL_CLEAR_M) + TUNNEL_ROOF_M + TUNNEL_COVER_M
    s = np.linspace(0.0, road.length, int(road.length / 0.25) + 2)
    z = np.interp(s, road.s, road.z)
    line = road.z[0] + (road.z[-1] - road.z[0]) * s / road.length
    deep = np.nonzero(line - z >= need)[0]
    if not len(deep):
        raise ValueError("tunnel %s never gets %.1f m below its mouths: nothing to cover" % (name, need))
    return road, float(s[deep[0]]), float(s[deep[-1]])


def void_rings(net, extra=0.0):
    """Footprints of the open ramps of every tunnel as [(name, ring)], ring counter-clockwise in metres: from
    each mouth to the back of the wall over the portal, as wide as the outer faces of the retaining walls.
    extra: metres added to each side and beyond the portal (for whoever has to keep clear of the parapets)."""
    rings = []
    for name in TUNNELS:
        road, s_a, s_b = tunnel_layout(net, name)
        w = tunnel_half_width(road) + extra
        for s0, s1 in ((0.0, s_a + TUNNEL_HEAD_M + extra), (s_b - TUNNEL_HEAD_M - extra, road.length)):
            rings.append((name, strip_ring(road, s0, s1, w)))
    return rings


def strip_ring(road, s0, s1, w):
    """Outline of the strip w metres to each side of the road between two stations, counter-clockwise."""
    left, right = [], []
    for s in [s0] + [float(v) for v in road.s if s0 < v < s1] + [s1]:
        p, _, n = road.at(s)
        left.append((float(p[0] + n[0] * w), float(p[1] + n[1] * w)))
        right.append((float(p[0] - n[0] * w), float(p[1] - n[1] * w)))
    ring = left + right[::-1]
    area = sum(ring[i][0] * ring[(i + 1) % len(ring)][1] - ring[(i + 1) % len(ring)][0] * ring[i][1] for i in range(len(ring)))
    return ring if area > 0 else ring[::-1]


# ---------------------------------------------------------------------------------------------------------
# Viaducts. A viaduct is one edge of the network's level 1 (an overpass across a freeway, a flyover ramp of an
# interchange, an elevated stretch) over land, built by viaduct_mesh.py: deck, girder, piers, and a walled fill
# under each end. The roads at its two ends are ordinary level-0 roads, built by the sectors on the ground; the
# sectors under it build plain ground there, and no building stands on its footprint (viaduct_rings, plan_lots.py).
#   at   a point on the viaduct (metres, east/north): the nearest edge of level 1 is the one meant
# ---------------------------------------------------------------------------------------------------------
VIADUCTS = {
    # Trevo Rodoviario Sul (network_edits, "User marks 1: Trevo Rodoviario Sul"): the two ramp overpasses that carry
    # the ring of ramps across the highway, west and east of the tunnel road's legs
    "VTS1": {"title": "Trevo Rodoviario Sul - viaduto oeste", "at": (-785.0, -1714.0), "status": "built"},
    "VTS2": {"title": "Trevo Rodoviario Sul - viaduto leste", "at": (-572.0, -1711.0), "status": "built"},
    # Ilha Oeste (network_edits, "User marks 1: Viaduto da Ilha Oeste"): the island road over the highway, and the
    # north-west ramp climbing over the north lagoon from the island road to the Ponte Pensil's abutment
    "VIO": {"title": "Viaduto da Ilha Oeste", "at": (-1650.0, 436.0), "status": "built"},
    "VIOR": {"title": "Ilha Oeste - alca noroeste", "at": (-1700.0, 560.0), "status": "built"},
}


def viaduct_edge(net, name):
    """The level-1 edge of the network nearest to the viaduct's "at" point."""
    at = np.array(VIADUCTS[name]["at"], dtype=np.float64)
    best, found = 1e18, None
    for e in net["edges"]:
        if e.get("level", 0) != 1:
            continue
        pts = np.asarray(e["pts"], dtype=np.float64)[:, :2]
        a, b = pts[:-1], pts[1:]
        ab = b - a
        t = np.clip(((at - a) * ab).sum(axis=1) / np.maximum((ab ** 2).sum(axis=1), 1e-9), 0.0, 1.0)
        d = float(np.min(np.hypot(*(a + ab * t[:, None] - at).T)))
        if d < best:
            best, found = d, e
    if found is None:
        raise ValueError("viaduct %s: no edge of level 1 near %s" % (name, VIADUCTS[name]["at"]))
    return found


def viaduct_rings(net, extra=0.0):
    """Footprints of every viaduct as [(name, ring)], ring counter-clockwise: the deck's whole length, `extra` metres
    wider on each side than its barriers. Nothing is built there (plan_lots.py)."""
    from common import SECTIONS
    rings = []
    for name in VIADUCTS:
        e = viaduct_edge(net, name)
        road = roadgeom.Road(e)
        w = road.half + SECTIONS[e["cls"]]["sidewalk"] + 0.45 + extra
        rings.append((name, strip_ring(road, 0.0, road.length, w)))
    return rings


def wet_span(net, name):
    """For a tunnel marked "under_water": the stations (s0, s1) between which its axis runs over water (the
    terrain base's water mask), else None. Under the water the tunnel lies in the bed: no hole in the sea, no
    landscape lowered (tunnel_mesh.py writes a strip that raises the bed over the roof instead)."""
    if not TUNNELS[name].get("under_water"):
        return None
    from common import data_path, to_pixel
    road, _, _ = tunnel_layout(net, name)
    water = np.load(data_path("terrain_base.npz"))["water"]
    s = np.arange(0.0, road.length, 1.0)
    pts = np.array([road.at(float(v))[0][:2] for v in s])
    u, v = to_pixel(pts[:, 0], pts[:, 1])
    u = np.clip(np.round(u).astype(int), 0, water.shape[1] - 1)
    v = np.clip(np.round(v).astype(int), 0, water.shape[0] - 1)
    wet = np.nonzero(water[v, u])[0]
    if not len(wet):
        return None
    return float(s[wet[0]]), float(s[wet[-1]])


def tunnel_rings(net, extra=0.0):
    """Footprint of every tunnel from mouth to mouth as [(name, ring)], ring counter-clockwise in metres, `extra`
    metres wider on each side than the outer faces of its walls. The sea has a hole there (sea_mesh.py). A tunnel
    under water gives the two stretches under its banks only."""
    rings = []
    for name in TUNNELS:
        road, _, _ = tunnel_layout(net, name)
        w = tunnel_half_width(road) + extra
        wet = wet_span(net, name)
        if wet is None:
            rings.append((name, strip_ring(road, 0.0, road.length, w)))
        else:
            rings += [(name, strip_ring(road, 0.0, wet[0], w)), (name, strip_ring(road, wet[1], road.length, w))]
    return rings


def tunnel_mouths(net):
    """Positions of the two mouths of every tunnel (where a road runs on into one): [(x, y), ...]."""
    out = []
    for name in TUNNELS:
        road, _, _ = tunnel_layout(net, name)
        out += [(float(road.xy[0][0]), float(road.xy[0][1])), (float(road.xy[-1][0]), float(road.xy[-1][1]))]
    return out
