"""Corrections applied to the traced map graph by design_network.py. Not run on its own.

Each edit is a dict with an "op" and positions in metres (east, north):
  {"op": "add",    "pts": [...], "kind": ..., "cls": ..., "level": ..., "width": ..., "name": ...}
        a new centre line; each end joins a node or road within 14 m ("snap"), otherwise it starts a new node.
        A line that merely crosses another road gets no junction there: that is how an overpass is drawn.
  {"op": "remove", "at": (x, y)}                    the edge nearest to the point (within 12 m)
  {"op": "set",    "at": (x, y), "kind"/"cls"/"level"/"name"/"width": ...}   properties of the nearest edge
  {"op": "clear",  "polygon": [...]}                every edge that lies mostly inside the polygon
  {"op": "move",   "at": (x, y), "to": (x, y)}      the nearest node
"why" says where the edit comes from. Edits run in order.

Sources so far
  marks 1 (2026-11-12): the user's first review of Saved/Bay/tracado_lido.png. Green strokes = restore the
  street's continuity; white circle around Ilha Oeste = "resolve the viaduct's shape and coherent accesses".
"""

EDITS = []


def add(pts, why, kind="street", width=20.0, cls=None, level=0, name=None, snap=14.0, curve=False, **extra):
    """curve=True: the points describe a smooth curve (an oval, a loop); they are all kept and the road is
    rounded through them, instead of being reduced to a few corners joined by straights.
    extra: depth=, grade= for a tunnel with a designed profile; hold= how closely the road follows the ground
    (default: its class's value in common.SECTIONS; about 0.01 = graded evenly from junction to junction);
    quay= a street on a pier or quay built out on fill, held level at that height in metres.
    See design_network.EXTRA_KEYS."""
    EDITS.append(dict({"op": "add", "pts": pts, "kind": kind, "width": width, "cls": cls, "level": level,
                       "name": name, "snap": snap, "curve": curve, "why": why}, **extra))


def remove(at, why, within=12.0):
    EDITS.append({"op": "remove", "at": at, "within": within, "why": why})


def clear(polygon, why, share=0.5):
    EDITS.append({"op": "clear", "polygon": polygon, "share": share, "why": why})


def setp(at, why, **props):
    EDITS.append(dict({"op": "set", "at": at, "why": why}, **props))


def along(pts, why, within=12.0, share=0.75, min_width=0.0, **props):
    """Properties for every road that runs along the line `pts`; applied after the grid is straightened."""
    EDITS.append(dict({"op": "along", "pts": pts, "within": within, "share": share, "min_width": min_width,
                       "why": why, "when": "after"}, **props))


# ---------------------------------------------------------------------------------------------------------
# User marks 1: street continuity (the green strokes)
# ---------------------------------------------------------------------------------------------------------
# North highway, west of the first tunnel: the avenue stops where the drawing turns into a pale band.
add([(-190, 2262), (-130, 2258), (-70, 2251), (-15, 2246)], "marks 1: north highway into the tunnel", kind="avenue", width=40.0)
setp((250, 2247), "marks 1: this stretch follows the tunnel dashes", kind="tunnel")
remove((430, 2268), "marks 1: stub of the avenue beside the tunnel mouth")
# North highway, east mouth of the second tunnel
add([(1225, 2284), (1290, 2292)], "marks 1: tunnel mouth to the avenue", kind="avenue", width=40.0)
# Avenue under the "Tunel Norte-Aeroporto" label area
add([(2840, 1712), (2955, 1718)], "marks 1: avenue south of the tunnel label", kind="avenue", width=30.0)
# Street by the Rio Leste bank, north of the expressway
add([(2130, 70), (2119, 104)], "marks 1: street up to the ring street", kind="street", width=25.0)
# South-east, east landing of the river causeway: the two local streets meet the road at one crossing
remove((2832, -908), "marks 1: east street leaves from the crossing instead")
add([(2817, -866), (2850, -888), (2872, -893), (2905, -915)], "marks 1: east street from the crossing", kind="street", width=22.0)

# ---------------------------------------------------------------------------------------------------------
# User marks 1: Trevo Rodoviario Sul. The label hides where the triangle's legs meet the highway. Rebuilt as
# drawn: the highway straight through, a ramp ring around it (north side serves westbound, south side
# eastbound), two ramp overpasses across the highway, and the two legs up to the tunnel road.
# ---------------------------------------------------------------------------------------------------------
clear([(-912, -1652), (-800, -1640), (-700, -1447), (-655, -1447), (-555, -1640), (-423, -1650), (-423, -1832), (-912, -1832)],
      "marks 1: Trevo Sul redrawn")
add([(-915, -1710), (-785, -1707), (-572, -1700), (-420, -1695)], "Trevo Sul: highway through", kind="avenue", width=60.0, cls="freeway")
add([(-678, -1465), (-705, -1512), (-760, -1603), (-785, -1650)], "Trevo Sul: west leg", cls="ramp", width=9.0)
add([(-678, -1465), (-651, -1512), (-597, -1603), (-572, -1650)], "Trevo Sul: east leg", cls="ramp", width=9.0)
add([(-785, -1650), (-572, -1650)], "Trevo Sul: north side of the ring", cls="ramp", width=9.0)
add([(-785, -1650), (-835, -1664), (-880, -1686), (-915, -1710)], "Trevo Sul: north-west ramp", cls="ramp", width=9.0)
add([(-572, -1650), (-505, -1660), (-455, -1677), (-420, -1695)], "Trevo Sul: north-east ramp", cls="ramp", width=9.0)
add([(-915, -1710), (-872, -1744), (-830, -1765), (-785, -1778)], "Trevo Sul: south-west ramp", cls="ramp", width=9.0)
add([(-785, -1778), (-730, -1800), (-680, -1810), (-630, -1803), (-572, -1772)], "Trevo Sul: south side of the ring", cls="ramp", width=9.0)
add([(-572, -1772), (-500, -1742), (-455, -1717), (-420, -1695)], "Trevo Sul: south-east ramp", cls="ramp", width=9.0)
add([(-785, -1650), (-785, -1778)], "Trevo Sul: west overpass", cls="ramp", width=9.0, level=1, name="Trevo Sul overpass W")
add([(-572, -1650), (-572, -1772)], "Trevo Sul: east overpass", cls="ramp", width=9.0, level=1, name="Trevo Sul overpass E")

# ---------------------------------------------------------------------------------------------------------
# User marks 1: Viaduto da Ilha Oeste (white circle). Read as a diamond interchange: the viaduct from the
# island crosses over the bridge highway and lands in Centro Oeste; one ramp per quadrant joins it (or the
# streets beside it) to the highway. The drawing has all four; they were broken or doubled in the trace.
# ---------------------------------------------------------------------------------------------------------
# the highway south of the interchange was traced as two parallel lines
clear([(-1605, 45), (-1505, 45), (-1505, -190), (-1605, -190)], "Ilha Oeste: doubled highway trace")
add([(-1560, 5), (-1558, -100), (-1548, -198)], "Ilha Oeste: highway, one line", kind="bridge", width=60.0, cls="freeway")
remove((-1578, 119), "Ilha Oeste: stub off the highway")
# the viaduct itself, passing over the highway with no junction
clear([(-1812, 452), (-1800, 404), (-1600, 398), (-1500, 418), (-1500, 480), (-1545, 480), (-1600, 462), (-1750, 447)],
      "Ilha Oeste: viaduct redrawn", share=0.45)
# (2026-11-16, built as sector IO*: the island road stays at grade on its strip of land (the drawing's white band,
# y = 415..470) as far as x = -1730 and only rises there; over the highway it must clear a road that is still coming
# down from the bluff where the Ponte Pensil lands (5-6 m under the crossing): deck at 12.6 m from x = -1590 to
# x = -1530, about 6 m clear under the girder (held at 11 m all along, as first designed, it left 3.3 m), down at 9 %
# to the junction east of it. The north-west ramp leaves the island road at grade and climbs evenly over the lagoon to the bridge's
# abutment on the bluff (13 m): an elevated ramp.)
add([(-1808, 428), (-1742, 430), (-1730, 430.5)], "Ilha Oeste: island road on its strip of land, up to the viaduct",
    kind="avenue", width=24.0, cls="arterial")
add([(-1730, 430.5), (-1650, 436), (-1570, 441), (-1493, 440)], "Ilha Oeste: viaduct over the highway",
    kind="bridge", width=24.0, cls="arterial", level=1, name="Viaduto da Ilha Oeste",
    deck=[(-1730.0, 430.5, 4.6), (-1590.0, 439.4, 12.6), (-1530.0, 440.8, 12.6), (-1493.0, 440.0, 8.6)])
# north-west ramp: from the island road (at grade) up to the bridge
clear([(-1800, 436), (-1700, 440), (-1690, 520), (-1640, 560), (-1587, 583), (-1587, 652), (-1640, 652), (-1735, 600), (-1765, 500)],
      "Ilha Oeste: north-west ramp redrawn", share=0.45)
add([(-1790, 429), (-1765, 450), (-1735, 476), (-1716, 520), (-1700, 560), (-1660, 600), (-1612, 640), (-1575, 655)],
    "Ilha Oeste: north-west ramp", cls="ramp", width=9.0, name="Ilha Oeste ramp NW", level=1,
    deck=[(-1790.0, 429.0, 4.6), (-1716.0, 520.0, 5.8), (-1575.0, 655.0, 13.0)])
# south-west ramp: island to the highway southbound; the drawing doubles its start and leaves two stubs
remove((-1856, 396), "Ilha Oeste: doubled start of the south-west ramp")
remove((-1828, 300), "Ilha Oeste: stub under the south-west ramp")
remove((-1792, 267), "Ilha Oeste: stub under the south-west ramp")
remove((-1791, 288), "Ilha Oeste: stub under the south-west ramp")

# ---------------------------------------------------------------------------------------------------------
# Sector CC2 (2026-11-13). The drawing leaves one block of 170 x 215 m between the avenue, the quay and the
# bridgehead, packed with small buildings and no street through it. No downtown block is that large: a cross
# street down to the waterfront and a service alley split it in four blocks of about 75 x 95 m.
# ---------------------------------------------------------------------------------------------------------
# the loop street south of it was traced with a jog half way down its west leg (a pixel step in the drawing):
# redrawn as the clean corner it is, parallel to the grid
clear([(1640, 510), (1790, 510), (1790, 540), (1665, 540), (1665, 635), (1640, 635)], "CC2: loop street with a jog", share=0.8)
add([(1650.8, 642.5), (1653.3, 527.3), (1797.5, 525.8)], "CC2: loop street, clean corner", kind="street", width=15.7)
# the little loop where that street reaches the quay is a one-lane turning loop around a planted island, not
# a two-way street going round in a circle
setp((1621.3, 681.7), "CC2: waterfront turning loop, one lane", cls="alley", within=14.0)
add([(1791.8, 782.0), (1716.0, 783.0), (1642.0, 783.9)], "CC2: cross street to the waterfront", kind="street", width=14.0)
add([(1704.0, 674.8), (1701.6, 783.2)], "CC2: service alley, south half", kind="street", width=9.0)
add([(1701.6, 783.2), (1699.6, 872.0)], "CC2: service alley, north half", kind="street", width=9.0)

# ---------------------------------------------------------------------------------------------------------
# Sector CC3 (2026-11-13), east of the bridge avenue. The drawing has one block 480 m long between the avenue
# and the wide ring around the walled compound, with a green band along its east side and no street across.
#   * The street on its east side was traced with a 13 m jog where it meets the ring: one straight street
#     instead, along the west edge of the ring's wide band, up to the north quay.
#   * Three cross streets carry the west side's streets across the avenue (four-way junctions) to that street;
#     the northern one runs on as the ring's north side.
# ---------------------------------------------------------------------------------------------------------
clear([(1935, 385), (1970, 385), (1970, 560), (1935, 560)], "CC3: east street with a jog", share=0.8)
clear([(1945, 575), (1975, 575), (1975, 770), (2175, 770), (2175, 800), (1945, 800)], "CC3: ring west and north sides redrawn", share=0.8)
add([(1950.0, 377.7), (1945.8, 565.0), (1941.0, 780.4)], "CC3: park street, straight", kind="street", width=14.0)
add([(1941.0, 780.4), (1938.6, 890.0)], "CC3: park street on to the north quay", kind="street", width=14.0)
add([(1960.8, 567.5), (1945.8, 565.0)], "CC3: ring south side to the park street", kind="street", width=14.0)
add([(1797.5, 525.8), (1946.7, 524.2)], "CC3: cross street A", kind="street", width=14.0)
add([(1794.2, 672.6), (1943.3, 671.0)], "CC3: cross street B", kind="street", width=14.0)
add([(1791.7, 782.0), (1941.0, 780.4)], "CC3: cross street C", kind="street", width=14.0)
add([(1941.0, 780.4), (2183.1, 786.3)], "CC3: ring north side from the park street", kind="street", width=14.0)

# ---------------------------------------------------------------------------------------------------------
# Downtown grid around CC1 (2026-11-13): two links the drawing leaves out, each joining two existing junctions
# of a street that runs on at both ends (the same continuity the user's green marks asked for elsewhere).
#   * north-south street at x = 1514..1518, between the street south of CC1 and the main avenue: without it
#     the block there is 285 m long;
#   * east-west street at y = 225..228, from the bridge avenue east to the next street: without it the block
#     east of CC1 is 293 m long.
# ---------------------------------------------------------------------------------------------------------
# (class given outright: a road whose class an edit sets takes no part in the straightening, so the junctions
#  it joins, which belong to sectors already built, stay exactly where they are)
add([(1514.1, 75.8), (1518.2, -72.5)], "CC4: north-south street carried through", kind="street", width=14.0, cls="street")
add([(1804.3, 228.5), (1955.4, 224.8)], "CC6: east-west street carried through", kind="street", width=14.0, cls="street")
#   * east of the bridge avenue the drawing has no cross street for 600 m (y = -222 to 378): besides the link
#     above, the street south of CC1 and the street along y = -54 are carried across to the avenue.
add([(1807.6, 85.4), (1958.7, 103.7)], "CC6: street south of CC1 carried east", kind="street", width=14.0, cls="street")
add([(1799.4, -31.5), (1957.5, -54.2)], "CC8: road along y = -54 carried west to the avenue", kind="street", width=26.0, cls="arterial")

# ---------------------------------------------------------------------------------------------------------
# The east-west axis across downtown (2026-11-13). The drawing has an orange band (its bridge colour, on land)
# from x = 1957 along y = -54..-64 to the Rio Leste bridge, and the main avenue bends away just west of it.
# Read as one surface avenue, four lanes, level with the streets: tunnel in the west - main avenue - this band
# - bridge over the Rio Leste. (It could also be read as an elevated road; built at street level because every
# cross street of the drawing meets it, and nothing else in the drawing asks for a second level here.)
# ---------------------------------------------------------------------------------------------------------
along([(1957.5, -54.2), (1979.2, -52.5), (2102.5, -64.2), (2245.8, -64.2)], "downtown axis: east to the Rio Leste bridge",
      within=8.0, share=0.8, cls="arterial")

# ---------------------------------------------------------------------------------------------------------
# East of downtown, x = 1955..2250 (sectors CC10, CC11; 2026-11-13). The drawing has a ring street round one
# block, a Z-shaped street below it, two stubs and a little loop; read as the grid they make:
#   * the avenue's west end was traced with a 12 m jog in its first 30 m: one straight line;
#   * the ring's north and south sides become straight streets, parallel to the grid;
#   * the ring's east side runs on north to the street along y = 378 and south, straight, to the avenue (the
#     drawing has that southern stretch as a Z: 40 m east, 80 m south, 40 m back west);
#   * the ring's south-east corner gets a street east to the stub that comes off the waterfront avenue, so the
#     two meet;
#   * dropped: the loop that crosses the street at x = 1958 with no junction, the alley stub off y = 378, the
#     detour of the y = 378 street's east end (its diagonal alley is the street), and the road traced along the
#     start of the Tunel Subaquatico Leste, which is that tunnel's own approach.
# ---------------------------------------------------------------------------------------------------------
clear([(1960, -45), (2098, -45), (2098, -75), (1960, -75)], "east avenue: jog at its west end", share=0.8)
add([(1957.5, -54.2), (2102.5, -64.2)], "east avenue: west end, straight", kind="bridge", width=26.0, cls="arterial")
remove((1931.9, 87.1), "east grid: loop across the street at x = 1958", within=8.0)
clear([(1962, 70), (2105, 70), (2105, 112), (1962, 112)], "east grid: ring south side", share=0.7)
add([(1958.7, 103.7), (2111.5, 100.7)], "east grid: ring south side, straight", kind="street", width=18.0, cls="street")
#   * and the street at x = 1955..1958, which the drawing has from y = 378 down to y = 104 and again south of
#     the avenue, is carried through between the two (160 m): without it the block there is 290 m wide.
add([(1958.66, 103.72), (1957.5, -54.2)], "east grid: north-south street carried through", kind="street", width=14.0, cls="street")
clear([(1962, 185), (2108, 185), (2108, 240), (1962, 240)], "east grid: ring north side", share=0.7)
add([(1955.4, 224.8), (2111.2, 227.3)], "east grid: ring north side, straight", kind="street", width=18.0, cls="street")
add([(2110.9, 191.2), (2111.2, 227.3)], "east grid: ring east side up to its north side", kind="street", width=14.0, cls="street")
add([(2111.2, 227.3), (2111.8, 374.2)], "east grid: east street on to y = 378", kind="street", width=14.0, cls="street")
clear([(2095, -55), (2150, -55), (2150, 92), (2095, 92)], "east grid: Z-shaped street", share=0.8)
remove((2125.9, 72.6), "east grid: Z-shaped street, last piece", within=8.0)
remove((1969.2, 92.5), "east grid: ring south side, last piece", within=6.0)
add([(2111.5, 100.7), (2102.5, -64.2)], "east grid: east street on to the avenue", kind="street", width=14.0, cls="street")
remove((2070.5, 352.0), "east grid: alley stub off y = 378", within=8.0)
clear([(2143, 376), (2200, 376), (2200, 386), (2143, 386)], "east grid: detour at the east end of y = 378", share=0.5)
setp((2165.7, 361.8), "east grid: the diagonal is the street", cls="street", within=8.0)
remove((2309.2, 382.5), "east grid: road along the tunnel's start", within=8.0)
add([(2111.5, 100.7), (2205.3, 119.7)], "east grid: street to the waterfront avenue", kind="street", width=14.0, cls="street")
#   * the waterfront avenue's last 220 m before the Rio Leste bridge were traced with a sideways wobble of
#     12 m just north of the junction: one straight line.
clear([(2226, -52), (2260, -52), (2260, 146), (2226, 146)], "east grid: waterfront avenue with a wobble", share=0.8)
add([(2237.0, 154.3), (2245.8, -64.2)], "east grid: waterfront avenue, straight", kind="bridge", width=30.0, cls="arterial")

# ---------------------------------------------------------------------------------------------------------
# Sector CC9 (2026-11-13), the band south of the main avenue. Two links the drawing leaves out:
#   * the street along y = -220 carried west to the street at x = 1375 (the block there was 287 m long);
#   * the north-south street at x = 1665 carried from the avenue down to y = -220 (it exists north of the avenue
#     and south of y = -220).
# ---------------------------------------------------------------------------------------------------------
#   * and one small loop street is dropped: it leaves the avenue's junction at x = 1957 almost on top of the
#     avenue itself, goes round a block 24 m wide and comes back 80 m further south.
remove((1915.0, -100.0), "CC9: small loop street beside the avenue junction", within=10.0)
add([(1519.9, -222.4), (1374.3, -224.9)], "CC9: east-west street carried west", kind="street", width=14.0, cls="street")
add([(1663.8, -70.8), (1666.3, -219.9)], "CC9: north-south street carried through", kind="street", width=14.0, cls="street")

# ---------------------------------------------------------------------------------------------------------
# Sector CC5 (2026-11-13), west of CC1. The "alley" traced from the west street up and along the waterfront
# is the outline of the map's own label box ("CENTRO CIVICO & COMERCIAL"), not a road.
# ---------------------------------------------------------------------------------------------------------
clear([(1010, 240), (1355, 240), (1355, 350), (1010, 350)], "CC5: label box outline read as an alley", share=0.6)
# With that false alley gone, the street along y = 219 and the street down the block's west side are one road
# round a corner, and the trace wobbles 3 m either way along it: redrawn clean, parallel to the grid, keeping the
# bend at its south end as drawn.
clear([(1062, 86), (1112, 86), (1112, 205), (1215, 205), (1215, 232), (1062, 232)], "CC5: west street traced with a wobble", share=0.8)
add([(1224.18, 219.50), (1074.2, 217.07), (1074.2, 112.0), (1096.0, 96.0), (1104.13, 80.48)], "CC5: west street, clean", kind="street", width=14.0)
# The waterfront avenue west of CC1 was traced with a 9 m sideways jog at x = 1115..1130 (where the drawn band
# changes width) and a slow wobble east of it: redrawn as the smooth line it is. Its east end stays on CC1's
# junction.
clear([(765, 385), (1000, 400), (1350, 352), (1350, 392), (1000, 452), (765, 478)], "CC5: waterfront avenue with a jog", share=0.8)
add([(759.17, 420.83), (777.20, 434.66), (786.70, 440.14), (811.55, 451.17), (820.87, 453.70), (859.88, 460.52), (892.55, 460.83),
     (902.37, 459.94), (934.93, 453.80), (992.44, 434.04), (1047.44, 405.91), (1080.44, 394.20), (1129.33, 382.30), (1188.07, 372.20),
     (1362.46, 372.50)], "CC5: waterfront avenue, smooth", kind="bridge", width=26.7, cls="arterial")

# ---------------------------------------------------------------------------------------------------------
# North-east quarter of downtown, x = 1947..2300, y = 378..916 (sectors CC12..CC15; 2026-11-13). The drawing
# has the walled compound inside a wide pale ring, a triangle of streets with two ponds at its south-east
# corner, and dense small buildings east and north of it with no street at all. Read as:
#   * the compound (an old walled garrison) keeps the streets on its west, north and south; the street on its
#     east side runs on south, straight, to the street that goes down to the tunnel (the triangle and the loop
#     round the second pond are dropped: that corner becomes a small park);
#   * the street at x = 2110 runs on north to the compound's south street;
#   * a drive along the Rio Leste and along the north shore, joined to the grid by the compound's north and
#     south streets carried east and one more cross street between them, and reaching the park street's end
#     in the west: a waterfront drive round the whole quarter. The river's bank is at about x = 2330 here
#     (it bulges east, north of the tunnel's approach), so the drive runs at x = 2312, a quay walk beside it;
#   * the drive's south end turns west, north of the pale platform the drawing has around the tunnel's
#     approach, and meets the compound's east street;
#   * two short streets from the compound's north street to the north quay.
# ---------------------------------------------------------------------------------------------------------
remove((2153.0, 602.0), "NE quarter: triangle, west side", within=10.0)
remove((2208.5, 626.0), "NE quarter: triangle, east side", within=10.0)
remove((2187.0, 572.0), "NE quarter: triangle, south-east side", within=10.0)
remove((2200.0, 530.5), "NE quarter: loop round the second pond", within=10.0)
remove((2193.0, 815.0), "NE quarter: stub north-east of the compound", within=12.0)
add([(2112.1, 373.5), (2109.2, 549.5)], "NE quarter: street at x = 2110 carried north", kind="street", width=14.0, cls="street")
add([(2197.6, 654.2), (2203.5, 541.5)], "NE quarter: east street carried south", kind="street", width=14.0, cls="street")
add([(2155.3, 545.8), (2203.5, 541.5)], "NE quarter: south street carried east", kind="street", width=14.0, cls="street")
add([(2203.5, 541.5), (2206.0, 345.5)], "NE quarter: east street down to the tunnel street", kind="street", width=14.0, cls="street")
add([(2203.5, 541.5), (2312.0, 539.0)], "NE quarter: south street to the river drive", kind="street", width=14.0, cls="street")
add([(2197.6, 654.2), (2312.0, 656.0)], "NE quarter: cross street to the river drive", kind="street", width=14.0, cls="street")
add([(2183.4, 783.0), (2312.0, 785.0)], "NE quarter: north street to the river drive", kind="street", width=14.0, cls="street")
add([(2200.5, 420.0), (2312.0, 420.0)], "NE quarter: street north of the tunnel's approach", kind="street", width=14.0, cls="street")
add([(2312.0, 420.0), (2312.0, 539.0)], "NE quarter: river drive, first stretch", kind="street", width=14.0, cls="street")
add([(2312.0, 539.0), (2312.0, 656.0)], "NE quarter: river drive, second stretch", kind="street", width=14.0, cls="street")
add([(2312.0, 656.0), (2312.0, 785.0)], "NE quarter: river drive, third stretch", kind="street", width=14.0, cls="street")
add([(2312.0, 785.0), (2312.0, 893.5)], "NE quarter: river drive, north stretch", kind="street", width=14.0, cls="street")
add([(2183.4, 783.0), (2182.0, 891.5)], "NE quarter: east street carried north to the quay", kind="street", width=14.0, cls="street")
add([(2312.0, 893.5), (2182.0, 891.5)], "NE quarter: north quay street, east stretch", kind="street", width=14.0, cls="street")
add([(2060.5, 783.0), (2059.0, 890.5)], "NE quarter: short street to the north quay", kind="street", width=14.0, cls="street")
add([(2182.0, 891.5), (2059.0, 890.5)], "NE quarter: north quay street, middle stretch", kind="street", width=14.0, cls="street")
add([(2059.0, 890.5), (1937.2, 890.0)], "NE quarter: north quay street, west stretch", kind="street", width=14.0, cls="street")
# (until 2026-11-18 the garrison had a drive of its own here, gate to gate, from its south street at (2060.5, 554.5) to
# the junction where the short street leaves its north street for the quay. The compound is the campaign's stadium
# now, sectors.STADIUM, and the drive ran through the pitch: it is gone.)
# the block south of the garrison is 146 x 165 m: a lane through its middle, so its walk-up rows stand back to
# back on two blocks instead of ringing an empty yard
add([(1948.7, 472.0), (2110.6, 461.5)], "NE quarter: lane through the block south of the garrison", kind="street", width=6.0, cls="alley")

# ---------------------------------------------------------------------------------------------------------
# Banco Central block (sector CC16; 2026-11-13): south of the downtown avenue, east of the street at x = 1958.
# The drawing's street along its south side dips 27 m into a V where the street from the south meets it. It
# is drawn straight, from the corner at x = 1961 to the waterfront avenue, and the street from the south is
# carried up to it.
# ---------------------------------------------------------------------------------------------------------
remove((2060.0, -216.5), "Banco Central: south street redrawn straight (west part)", within=10.0)
remove((2200.0, -212.0), "Banco Central: south street redrawn straight (east part)", within=10.0)
add([(1961.4, -214.7), (2146.0, -213.6)], "Banco Central: south street, west stretch", kind="street", width=14.0, cls="street")
add([(2146.0, -213.6), (2244.3, -212.3)], "Banco Central: south street, east stretch", kind="street", width=14.0, cls="street")
add([(2146.0, -213.6), (2145.8, -240.8)], "Banco Central: street from the south carried up to it", kind="street", width=14.0, cls="street")
# the waterfront avenue from the bridge's junction down to the south street was traced off the edge of the
# bridge's own symbol: it wanders 3 to 6 m either side of a straight line (and leaves the junction with a 3 m
# jog). Drawn straight between its two junctions. Its first 12 m are in CC11, which is rebuilt for it.
remove((2248.0, -120.0), "Banco Central: waterfront avenue redrawn straight", within=10.0)
add([(2245.83, -64.17), (2244.29, -212.28)], "Banco Central: waterfront avenue, bridge to the south street", kind="avenue", width=30.0, cls="arterial")

# ---------------------------------------------------------------------------------------------------------
# South of downtown, first row of blocks (sectors CS1 and CS2; 2026-11-13): between the streets along
# y = -220 and y = -375.
#   * The street on their south side steps 10 m north and back between x = 1665 and x = 1815: the drawing's
#     wobble, drawn straight.
#   * The street at x = 1958 is drawn thin between y = -215 and y = -363 and came out as a one-lane alley, but
#     it is the middle of a street that runs from the avenue to y = -790: a street like the rest of it.
# ---------------------------------------------------------------------------------------------------------
remove((1740.0, -372.0), "CS row 1: south street redrawn straight", within=10.0)
add([(1664.5, -377.9), (1815.5, -379.9)], "CS row 1: south street, middle stretch", kind="street", width=14.0, cls="street")
setp((1959.0, -290.0), "CS row 1: the street at x = 1958 is a street here too", cls="street", within=8.0)

# ---------------------------------------------------------------------------------------------------------
# South of downtown, second row (sector CS4; 2026-11-13): the long block between x = 1522 and x = 1955 and
# the streets round it. The street along its south side is drawn with a dip where the street from the south
# meets it and a wobble further east; its east side bends in its last 50 m. Drawn as straight runs between
# the junctions: the street from the south is carried 16 m on to meet the straight line.
# ---------------------------------------------------------------------------------------------------------
remove((1585.0, -527.0), "CS row 2: south street redrawn straight (west of the dip)", within=10.0)
remove((1735.0, -523.0), "CS row 2: south street redrawn straight (east of the dip)", within=10.0)
remove((1885.0, -507.0), "CS row 2: south street redrawn straight (east stretch)", within=10.0)
remove((1953.0, -430.0), "CS row 2: east street redrawn straight", within=10.0)
add([(1523.31, -522.09), (1821.32, -517.23)], "CS row 2: south street, straight to the hill junction", kind="street", width=14.0, cls="street")
add([(1648.83, -535.83), (1650.2, -520.0)], "CS row 2: street from the south carried on to it", kind="street", width=14.0, cls="street")
add([(1821.32, -517.23), (1945.83, -497.50)], "CS row 2: south street, east stretch", kind="street", width=14.0, cls="street")
add([(1959.09, -362.63), (1945.83, -497.50)], "CS row 2: east street, straight", kind="street", width=14.0, cls="street")

# ---------------------------------------------------------------------------------------------------------
# The block south of the Banco Central's (sector CS5; 2026-11-13). The street round its east and south sides
# comes down from the bank's south street, turns south-west and runs west to the street at x = 1958. Most of
# it lies under the map's own label, and what shows is drawn in steps. Drawn as three straight runs.
# ---------------------------------------------------------------------------------------------------------
# The street along the north side of the west block of the second row (sector CS3) is drawn with two bumps
# between x = 1190 and x = 1275: one straight run, and the corner where it turns south.
remove((1150.0, -377.2), "CS3: north street redrawn straight", within=10.0)
add([(1373.57, -369.25), (1088.0, -377.2), (1080.65, -419.06)], "CS3: north street, straight, and its corner", kind="street", width=14.0,
    cls="street")

# ---------------------------------------------------------------------------------------------------------
# South of downtown, third row, on the plateau (x = 1084..1523, y = -525..-820; 2026-11-13).
#   * The north-south street at x = 1378 is drawn with a small loop round a marker at y = -650 and wanders
#     on south to the street along y = -815: one street, the loop dropped, its south half straight.
#   * The cross street from x = 1233 is drawn with a jog of 30 m to meet it: straight, to the junction at
#     y = -668.
#   * The lane along y = -674 between x = 1090 and x = 1233 carries on that cross street: a street.
# ---------------------------------------------------------------------------------------------------------
remove((1404.0, -648.0), "CS row 3: loop round the marker", within=8.0)
remove((1330.0, -642.5), "CS row 3: cross street redrawn straight", within=8.0)
remove((1397.0, -740.0), "CS row 3: north-south street redrawn straight", within=12.0)
remove((1378.5, -730.0), "CS row 3: north-south street redrawn straight (its second trace)", within=8.0)
remove((1381.0, -695.0), "CS row 3: north-south street redrawn straight (north piece of the old trace)", within=6.0)
remove((1411.0, -795.0), "CS row 3: north-south street redrawn straight (south piece of the old trace)", within=8.0)
add([(1232.7, -674.2), (1380.3, -667.7)], "CS row 3: cross street, straight", kind="street", width=14.0, cls="street")
add([(1380.3, -667.7), (1419.2, -819.5)], "CS row 3: north-south street, south half", kind="street", width=14.0, cls="street")
setp((1160.0, -674.2), "CS row 3: the lane along y = -674 is a street", cls="street", within=8.0)
#   * The street at x = 1650..1672 leaves the second row's south street with a 17 m stub and a diagonal before
#     it turns south: one straight run from that junction to the cross street at y = -667.
remove((1649.5, -527.5), "CS row 3: stub at the head of the street at x = 1660", within=6.0)
remove((1662.0, -600.0), "CS row 3: street at x = 1660 redrawn straight", within=10.0)
add([(1650.19, -518.94), (1671.6, -666.6)], "CS row 3: street at x = 1660, straight", kind="street", width=14.0, cls="street")
#   * At x = 1810, y = -668 the cross street, the street south and two dead-end courts meet in two junctions
#     14 m apart: one junction of four arms, at the courts' corner.
remove((1740.0, -670.0), "CS row 3: cross street to the courts' corner (old run)", within=8.0)
remove((1813.5, -750.0), "CS row 3: street south from the courts' corner (old run)", within=8.0)
remove((1811.2, -668.0), "CS row 3: link between the two junctions", within=5.0)
add([(1673.98, -666.69), (1815.11, -662.53)], "CS row 3: cross street to the courts' corner", kind="street", width=14.0, cls="street")
add([(1815.11, -662.53), (1819.58, -823.02)], "CS row 3: street south from the courts' corner", kind="street", width=14.0, cls="street")
#   * The cross street along y = -667 exists from x = 1233 to x = 1381 and from x = 1674 to x = 1815; the two
#     blocks between are 145 x 295 m, twice the grid's. Carried through (across the street at x = 1523), so
#     the row has one continuous cross street and blocks of the grid's size. It dips 19 m into the valley of
#     the street at x = 1523 and climbs out again, at up to 13%.
add([(1381.31, -667.71), (1525.0, -668.0)], "CS row 3: cross street carried east to x = 1523", kind="street", width=14.0, cls="street")
add([(1525.0, -668.0), (1674.0, -667.47)], "CS row 3: cross street carried east to x = 1674", kind="street", width=14.0, cls="street")
#   * ...and its east end, a dead-end court 51 m long, carried on 98 m to the street at x = 1964: the cross
#     street then runs the whole row, from x = 1090 to x = 1964. (The court that leaves the same corner
#     northwards stays a court: the street it points at, 84 m up the hill, is 14 m higher across a gully.)
#     The street it reaches (x = 1964) is drawn with a wiggle of 6 m just there, between y = -660 and
#     y = -700: redrawn straight from its dogleg at the north end (kept as drawn: the corner at y = -498 is
#     18 m west of the street's line) down to the junction at y = -792.
remove((1964.0, -600.0), "CS row 3: street at x = 1964 redrawn without its wiggle", within=8.0)
add([(1945.83, -497.50), (1961.0, -511.0), (1964.0, -519.0), (1964.0, -664.5)], "CS row 3: street at x = 1964, north part", kind="street",
    width=14.0, cls="street")
add([(1964.0, -664.5), (1967.47, -792.5)], "CS row 3: street at x = 1964, south part", kind="street", width=14.0, cls="street")
add([(1865.83, -664.17), (1964.0, -664.5)], "CS row 3: east court carried on to the street at x = 1964", kind="street", width=14.0, cls="street")
#   * At the row's south-east corner a lane leaves the street at x = 1967 for the junction 90 m east, 20 to
#     40 m south of a street that goes to the same junction (east along y = -791, then south): dropped.
remove((2014.0, -826.0), "CS row 3: lane east from x = 1967", within=6.0)

remove((2070.0, -345.0), "CS5: street round the block redrawn", within=12.0)
add([(2145.83, -240.83), (2146.0, -300.0), (2110.0, -338.0), (1959.09, -362.63)], "CS5: street round the block, three straight runs",
    kind="street", width=14.0, cls="street")

# ---------------------------------------------------------------------------------------------------------
# East strip of the Centro Sul, from the street at x = 1964 to the Rio Leste, y = -213..-815 (sectors CS12 to
# CS14; 2026-11-13). The drawing has: the waterfront avenue going underground 85 m south of the Banco
# Central's street and coming up again 470 m further south (dashed blue, with a portal symbol), 15 m from
# the river; a park 135 m wide west of it; rows of small buildings between the park and the street at
# x = 1964, with no street among them; and, at the tunnel's south end, a triangle of short streets where the
# freeway's bridge lands. Read as:
#   * Tunel da Orla Leste: one straight tunnel from 26 m south of the bank's street to y = -765, a
#     cut-and-cover underpass 6.4 m deep under the riverside promenade; the short service lanes the drawing
#     has beside its north mouth and the fragments the tracing left of it are dropped;
#   * at its south end the avenue comes up and meets, at one junction, the road off the freeway's bridge
#     (east), the avenue going on south, and a new street along the park's south side (west), instead of the
#     triangle;
#   * a street along the park's west side (x = 2100), from the street round the block south of the bank down
#     to the park's south street; the rows of buildings west of it get two cross streets, carrying on the
#     cross streets of the third row (from the corner at y = -498, and along y = -664).
# ---------------------------------------------------------------------------------------------------------
clear([(2212.0, -226.0), (2300.0, -226.0), (2300.0, -846.0), (2212.0, -846.0)], "east strip: tunnel fragments and the triangle redrawn")
add([(2244.29, -212.28), (2245.06, -238.27)], "east strip: waterfront avenue down to the tunnel's mouth", kind="avenue", width=30.0, cls="arterial")
add([(2245.06, -238.27), (2260.60, -765.00)], "east strip: Tunel da Orla Leste", kind="tunnel", width=17.5, cls="tunnel",
    name="Tunel da Orla Leste", depth=6.4, grade=0.08)
add([(2260.60, -765.00), (2262.02, -812.98)], "east strip: avenue from the tunnel's south mouth", kind="avenue", width=30.0, cls="arterial")
add([(2262.02, -812.98), (2259.17, -840.83)], "east strip: avenue on south", kind="avenue", width=30.0, cls="arterial")
add([(2262.02, -812.98), (2280.83, -810.83)], "east strip: road off the freeway's bridge", kind="avenue", width=30.0, cls="arterial")
remove((2010.0, -792.5), "east strip: park's south street redrawn", within=8.0)
remove((2067.0, -841.5), "east strip: the old diagonal's last 29 m", within=6.0)
add([(1967.47, -792.50), (2052.0, -793.0)], "east strip: street along y = -792, to its fork", kind="street", width=14.0, cls="street")
add([(2052.0, -793.0), (2079.17, -849.17)], "east strip: fork, branch to the south-east", kind="street", width=14.0, cls="street")
add([(2052.0, -793.0), (2262.02, -812.98)], "east strip: street along the park's south side", kind="street", width=14.0, cls="street")
add([(2106.0, -338.6), (2100.0, -797.6)], "east strip: street along the park's west side", kind="street", width=14.0, cls="street")
add([(1945.83, -497.50), (2104.09, -485.0)], "east strip: cross street from the corner at y = -498", kind="street", width=14.0, cls="street")
add([(1964.0, -664.5), (2101.74, -664.5)], "east strip: cross street along y = -664", kind="street", width=14.0, cls="street")

# ---------------------------------------------------------------------------------------------------------
# South of downtown, fourth row (y = -812..-975, x = 1093..1967; sectors CS15 to CS17; 2026-11-13).
# Between the third row's south street and the next street south (along y = -975 in the west, y = -950 in the
# east) the drawing has one block 580 m long (x = 1093 to 1676, most of it under the map's own label) and one
# of 290 m. The street south of them is drawn with jogs and lay-bys and, at the Plato Sudeste marker, with a V
# of 16 m round the marker's dot. Read as:
#   * that street is one street, in straight runs from junction to junction;
#   * the north-south streets of the third row (x = 1093, 1237, 1419, 1526, 1817) carry on south to it, so
#     the row has blocks of the grid's size (107 to 182 m). The first two meet, at the same junctions, the
#     streets that go on south across the plateau's top (x = 1086 and x = 1232.5): two streets now run from
#     the second row to the far side of the plateau;
#   * dropped: the two service lanes drawn 25 m north of that street, the 26 m stub at the row's north-west
#     corner, the 33 m stub at x = 1735 and the lay-by on the street at x = 1967.
# The plateau's top was a pit in the terrain as first read (see REPAIRS in terrain_base.py); these streets
# were designed after that was mended.
# ---------------------------------------------------------------------------------------------------------
remove((1075.3, -954.2), "CS row 4: service lane north of the street (west)", within=6.0)
remove((1215.8, -949.2), "CS row 4: service lane north of the street (east)", within=6.0)
remove((1115.8, -975.5), "CS row 4: street along y = -975 redrawn straight (x = 1086 to 1146)", within=5.0)
remove((1194.2, -974.3), "CS row 4: street along y = -975 redrawn straight (west arm of the V)", within=5.0)
remove((1265.0, -972.4), "CS row 4: street along y = -975 redrawn straight (east arm of the V)", within=5.0)
remove((1148.3, -974.6), "CS row 4: 5 m left between the two lanes' ends", within=4.0)
add([(1085.83, -976.36), (1289.17, -972.50)], "CS row 4: street along y = -975, x = 1086 to 1289", kind="street", width=14.0, cls="street", snap=6.0)
remove((1232.5, -1056.0), "CS row 4: the plateau's street at x = 1232.5 redrawn from the new junction", within=6.0)
add([(1232.50, -973.58), (1232.50, -1122.50)], "CS row 4: the plateau's street at x = 1232.5, from the street along y = -975", kind="street",
    width=14.0, cls="street", snap=6.0)
remove((1504.8, -969.4), "CS row 4: street along y = -975..-952 redrawn straight (x = 1289 to 1679)", within=8.0)
add([(1289.17, -972.50), (1419.18, -965.75)], "CS row 4: street along y = -975..-966, x = 1289 to 1419", kind="street", width=14.0, cls="street", snap=6.0)
# from x = 1419 east this street leaves the plateau for the valley, 24 m lower. Following the ground as read
# from the map it would drop 14 m in 80 m, flatten, and meet the street at x = 1526 on a bump; and that street
# would climb 6 m over the plateau's shoulder only to fall 15 m beyond. Both are graded evenly instead
# (hold=0.01): 9% down the flank, as a street laid out across a hillside is.
add([(1419.18, -965.75), (1678.77, -952.26)], "CS row 4: street along y = -966..-952, x = 1419 to 1679", kind="street", width=14.0, cls="street",
    snap=6.0, hold=0.01)
remove((1859.2, -964.2), "CS row 4: street along y = -952 redrawn straight (x = 1730 to 1965)", within=8.0)
remove((1707.8, -953.4), "CS row 4: street along y = -952 redrawn straight (x = 1679 to 1730)", within=5.0)
add([(1678.77, -952.26), (1965.26, -947.50)], "CS row 4: street along y = -952, x = 1679 to 1965", kind="street", width=14.0, cls="street", snap=6.0)
remove((1084.3, -820.0), "CS row 4: stub at the north-west corner", within=10.0)
remove((1734.0, -941.8), "CS row 4: stub at x = 1735", within=5.0)
remove((1994.1, -871.4), "CS row 4: lay-by on the street at x = 1967", within=6.0)
add([(1093.42, -810.88), (1085.83, -976.36)], "CS row 4: street at x = 1090 carried south", kind="street", width=14.0, cls="street", snap=6.0)
add([(1237.68, -809.99), (1232.50, -973.58)], "CS row 4: street at x = 1235 carried south", kind="street", width=14.0, cls="street", snap=6.0)
add([(1419.18, -819.46), (1419.18, -965.75)], "CS row 4: street at x = 1419 carried south", kind="street", width=14.0, cls="street", snap=6.0)
add([(1526.19, -814.07), (1526.19, -960.19)], "CS row 4: street at x = 1526 carried south", kind="street", width=14.0, cls="street", snap=6.0,
    hold=0.01)
add([(1817.51, -815.49), (1817.51, -949.95)], "CS row 4: street at x = 1817 carried south", kind="street", width=14.0, cls="street", snap=6.0)

# ---------------------------------------------------------------------------------------------------------
# The top of the Plato Sudeste (y = -975..-1130, x = 942..1562; sectors CS18 to CS20; 2026-11-13).
# The drawing has a ring of streets here, parted by the streets at x = 1086 and x = 1232.5, with large
# white-roofed buildings standing loose in the blocks; at its west end a second, inner street 50 m inside the
# ring; and from the ring's south-east corner a street that wanders 300 m east (with a 15 m jog along a
# widened stretch) to a round white area 70 m across at the highest point, beside the "Crista Sul / Represa"
# marker. Read as:
#   * the ring in straight runs (west side at x = 942.5); the inner street at its west end dropped: the block
#     it cut off was 52 m wide;
#   * the street east from the ring's corner straight, ending 12 m short of the round area, which is the
#     covered reservoir's roof: a round terrace at the top of the bluff (sector CS20), not a road;
#   * the street at x = 1419, which the fourth row brought down to y = -966, carried on up to that street: it
#     now runs from the third row to the reservoir, and the 300 m block east of x = 1232.5 is cut in two.
# ---------------------------------------------------------------------------------------------------------
remove((992.8, -1053.9), "plateau top: inner street at the ring's west end", within=6.0)
remove((1048.3, -977.4), "plateau top: ring redrawn (north side, x = 1011 to 1086)", within=6.0)
remove((952.9, -982.6), "plateau top: ring redrawn (north-west corner)", within=6.0)
remove((941.1, -1112.2), "plateau top: ring redrawn (west side and south-west corner)", within=6.0)
remove((1040.0, -1126.7), "plateau top: ring redrawn (south side, x = 994 to 1086)", within=6.0)
add([(1085.83, -977.50), (942.50, -981.03), (942.50, -1129.08), (1085.83, -1125.83)], "plateau top: ring west of x = 1086, three straight runs",
    kind="street", width=14.0, cls="street", snap=6.0)
remove((1382.6, -1106.8), "plateau top: street to the reservoir redrawn straight", within=8.0)
add([(1232.50, -1122.50), (1478.00, -1119.71)], "plateau top: street to the reservoir, straight", kind="street", width=14.0, cls="street", snap=6.0)
add([(1419.18, -965.75), (1419.18, -1120.38)], "plateau top: street at x = 1419 carried up to the reservoir street", kind="street", width=14.0,
    cls="street", snap=6.0)

# ---------------------------------------------------------------------------------------------------------
# South of the fourth row, east of the plateau (x = 1526..1965, y = -950..-1075; sectors CS21 and CS22;
# 2026-11-13). The drawing fills this with small buildings in rows, three and four deep, and no street at all
# for 440 m. Its west half (to x = 1800) lies at the foot of the bluff under the reservoir: only the first
# row, along the fourth row's street, stands on level ground; the rows behind it would stand on a slope of
# one in two. Read as:
#   * west of x = 1817: one row of buildings along the street, the bluff behind them left as it is;
#   * east of x = 1817, where the ground is level down to y = -1080: the streets at x = 1817 and x = 1965
#     carried south to a new street along y = -1075, at the foot of the hill south of it. One block of the
#     grid's size (148 x 125 m).
# ---------------------------------------------------------------------------------------------------------
add([(1817.51, -949.89), (1817.51, -1075.00), (1965.23, -1075.00), (1965.23, -947.50)], "SE of the plateau: streets round the block south of y = -950",
    kind="street", width=14.0, cls="street", snap=6.0)

# ---------------------------------------------------------------------------------------------------------
# The plateau's north-west corner (x = 897..1093, y = -760..-995; sector CS24; 2026-11-13).
#   * Two "avenues" traced here, from (919, -932) to (1000, -782) and from (836, -862) to (826, -946), are not
#     on the map: the tracer took the brown contour line along the plateau's edge for an avenue's colour.
#     Both dropped, and with them the lane that only led to the first (to a dead end at (868, -1009)).
#   * The drawing widens the corner of the streets at (1093, -811) to the west, where buildings stand in a
#     small grid with no street: a street west from that corner, ending in a turning circle at x = 960.
# ---------------------------------------------------------------------------------------------------------
remove((934.2, -842.5), "plateau NW: avenue traced from a contour line", within=6.0)
remove((867.1, -909.6), "plateau NW: second avenue traced from a contour line", within=6.0)
remove((887.5, -962.5), "plateau NW: lane to the first one", within=6.0)
add([(1093.42, -810.88), (960.00, -811.00)], "plateau NW: street west from the corner at (1093, -811)", kind="street", width=14.0,
    cls="street", snap=6.0)

# ---------------------------------------------------------------------------------------------------------
# The south-east corner of the Centro Sul (x = 1967..2290, y = -793..-1075; sectors CS25 to CS27; 2026-11-14).
# The drawing has here a paved area with a bent street, a cul-de-sac that ends at a pale blue square (a pond),
# an alley that ends at the same square, scattered small buildings, a row of buildings along the waterfront
# avenue, and, by the river, the freeway's bridge coming down onto the avenue. Read as:
#   * the fourth row's south street (y = -947.5) carried east, straight, to the waterfront avenue: one street
#     from the plateau to the river (the bent street, the cul-de-sac and the alley dropped);
#   * two streets south from the park's south street, at x = 2079 (carrying on the diagonal from the fork at
#     (2052, -793)) and x = 2180, down to a street along the foot of the hill (y = -1075), which carries on the
#     street round the block of sector CS22. Four blocks of the grid's size and a strip along the avenue;
#   * the pond square becomes a small park (block x = 2079..2180 south of y = -947.5): ponds are not made;
#   * the avenue from the tunnel's south mouth runs on south and becomes the freeway at the junction with the
#     new street. The stub where the drawing lands the freeway's bridge is dropped: the bridge, when it is
#     built, comes down at the junction at the tunnel's south mouth, as sector CS12 already has it.
# ---------------------------------------------------------------------------------------------------------
remove((2031.0, -931.0), "SE corner: bent street dropped", within=4.0)
remove((2131.6, -912.0), "SE corner: cul-de-sac to the pond dropped", within=4.0)
remove((2006.0, -964.0), "SE corner: alley to the pond dropped", within=4.0)
remove((2266.8, -942.4), "SE corner: stub of the freeway's bridge landing dropped", within=4.0)
add([(1979.17, -947.50), (2257.77, -952.20)], "SE corner: fourth row's south street carried to the avenue", kind="street", width=14.0,
    cls="street", snap=6.0)
add([(1965.23, -1075.00), (2180.00, -1075.00)], "SE corner: street along the foot of the hill", kind="street", width=14.0, cls="street",
    snap=6.0)
add([(2079.17, -849.17), (2079.17, -949.19)], "SE corner: street at x = 2079, north part", kind="street", width=14.0, cls="street", snap=6.0)
add([(2079.17, -949.19), (2079.17, -1075.00)], "SE corner: street at x = 2079, south part", kind="street", width=14.0, cls="street", snap=6.0)
add([(2180.00, -805.18), (2180.00, -950.89)], "SE corner: street at x = 2180, north part", kind="street", width=14.0, cls="street", snap=6.0)
add([(2180.00, -950.89), (2180.00, -1075.00)], "SE corner: street at x = 2180, south part", kind="street", width=14.0, cls="street", snap=6.0)

# ---------------------------------------------------------------------------------------------------------
# The Delegacia Central (sector CW1; 2026-11-14). The map marks the central police station at the T where the
# north shore's road, drawn orange, ends against a road that climbs south onto a knoll (9.6 m), round whose
# foot a loop road runs. The tracing broke the shore road into pieces (two of them doubled, two read as tunnel
# from the marker's own dot) and left a 72 m gap between it and the waterfront avenue that comes from the
# Centro Civico (sector CC5). Read as:
#   * the waterfront avenue carried on, in one piece, from where the tracing left it to the T;
#   * the road up the knoll kept straight (the detour the tracing took round the yard east of it dropped).
# ---------------------------------------------------------------------------------------------------------
clear([(474.0, 340.0), (722.0, 340.0), (722.0, 400.0), (474.0, 400.0)], "CW1: shore road's broken and doubled pieces")
add([(759.17, 420.83), (700.0, 388.0), (600.0, 370.0), (470.83, 347.50)], "CW1: waterfront avenue carried on to the Delegacia's T",
    kind="avenue", width=30.0, cls="arterial", snap=6.0)
remove((490.8, 254.2), "CW1: detour round the yard", within=4.0)
# West of the Delegacia (sector CW2): between the street at x = 192 and the curving street at x = 340..385 the
# drawing has two blocks, the northern one 300 m long with no street through it. The T's west arm (y = 347),
# which stopped at the curving street, carried on west to the street at x = 192: two blocks of 150 m. Of the two
# short diagonals the tracing drew from the shore street down to (331, 459), the eastern one dropped.
add([(385.00, 349.17), (188.59, 347.00)], "CW2: the Delegacia's west arm carried on to x = 192", kind="street", width=14.0, cls="street",
    snap=6.0)
remove((315.0, 487.6), "CW2: second diagonal from the shore street", within=4.0)

# ---------------------------------------------------------------------------------------------------------
# Centro Oeste, the band between the streets along y = 40 and y = -404, from the boulevard (x = -75) to the
# street along the valley's edge (x = 345); sectors CW3 to CW5; 2026-11-14.
#   * The drawing has a boulevard 25 m wide at x = -94 (from y = 230 down to a small pond at y = -330); the
#     tracing ran a crooked line down it and into the pond. One straight avenue from the top street (carried
#     west 10 m to meet it) down to the cross street along y = -262; the pond south of that is a lawn (ponds are
#     not made). The bulge the tracing drew on the top street round (-110, 70) and the diagonal across the paved
#     square west of the boulevard dropped. (First built at x = -75 by a misreading, 2026-11-14 02:40; moved.)
#   * The street along y = -100 comes from the tunnel's west mouth and bends down onto the street at x = 55,
#     traced as four pieces and a 95 m spur: straight on to x = 55, and the street at x = 55 carried north to the
#     top street (it ended 150 m short).
#   * The block between x = 55 and the street along the valley's edge is 290 x 295 m with no street: cut in four
#     by the street at x = 200 carried south and a cross street along y = -250.
# ---------------------------------------------------------------------------------------------------------
remove((-90.0, -20.0), "CW5: crooked trace along the boulevard (north)", within=4.0)
remove((-93.0, -163.0), "CW5: crooked trace along the boulevard (south)", within=4.0)
remove((-100.0, -297.0), "CW5: trace into the pond", within=4.0)
remove((-211.0, -67.0), "CW5: diagonal across the paved square", within=4.0)
remove((-113.0, 53.0), "CW5: bulge round (-110, 70) on the top street", within=4.0)
add([(-87.79, 33.81), (-94.00, 33.62)], "CW5: top street carried west to the boulevard", kind="street", width=14.0, cls="street",
    snap=6.0)
add([(-94.00, 33.62), (-102.61, -259.14)], "CW5: the boulevard at x = -94 (its south end is moved onto the line below)", kind="avenue", width=30.0, cls="arterial", snap=6.0)
EDITS.append({"op": "move", "at": (-102.61, -259.14), "to": (-94.00, -259.14), "within": 3.0, "when": "after",
              "why": "CW5: the boulevard's south end on its line"})
remove((105.6, -140.6), "CW4: lane of the bend at (54, -122)", within=4.0)
remove((116.0, -111.0), "CW4: bend at (54, -122) redrawn", within=9.0)
remove((54.0, -136.0), "CW4: piece of the bend at (54, -122)", within=4.0)
remove((31.0, -114.0), "CW4: spur from the bend at (54, -122)", within=4.0)
add([(154.16, -103.86), (54.60, -107.40)], "CW4: street along y = -100 straight on to x = 55", kind="street", width=14.0, cls="street",
    snap=6.0)
add([(51.01, 40.29), (54.60, -107.40)], "CW3: street at x = 55 carried north to the top street", kind="street", width=14.0, cls="street",
    snap=6.0)
add([(54.60, -107.40), (54.47, -150.17)], "CW4: street at x = 55, its old start joined", kind="street", width=14.0, cls="street", snap=6.0)
add([(55.15, -250.00), (347.32, -250.00)], "CW4: cross street along y = -250", kind="street", width=14.0, cls="street", snap=6.0)
add([(200.65, -102.14), (200.33, -250.00)], "CW4: street at x = 200 carried south (north part)", kind="street", width=14.0, cls="street",
    snap=6.0)
add([(200.33, -250.00), (200.00, -399.50)], "CW4: street at x = 200 carried south (south part)", kind="street", width=14.0, cls="street",
    snap=6.0)
#   * The street at x = 55 is part traced (straightened on a slant of its own) and part added (straight lines
#     between given points): it came out zigzagging by 3 to 4 m. Its two middle junctions are put on the line
#     between its junctions at y = -107 and y = -404, after the straightening (which would undo it otherwise).
EDITS.append({"op": "move", "at": (51.09, -150.27), "to": (55.32, -150.27), "within": 1.0, "when": "after",
              "why": "CW4: street at x = 55 straightened (junction at y = -150)"})
EDITS.append({"op": "move", "at": (54.42, -250.03), "to": (56.98, -250.03), "within": 1.0, "when": "after",
              "why": "CW4: street at x = 55 straightened (junction at y = -250)"})

# ---------------------------------------------------------------------------------------------------------
# Centro Oeste west of the boulevard (sector CW6; 2026-11-14). The drawing has a paved square 180 x 95 m
# against the boulevard, reached from the north by the street at x = -250 (which ends at it) and from the top
# street by a short street at x = -293. The tracing ran two loops along the square's edges. Read as:
#   * the two loops dropped;
#   * the street at x = -293 from the top street down the square's west side;
#   * a street along the square's south side, from the street at x = -383 to the boulevard: the square gets a
#     frontage and the block south of it a street on its north side (it would be 290 x 160 m without).
# ---------------------------------------------------------------------------------------------------------
remove((-225.0, 33.0), "CW6: loop round the corner of the square", within=4.0)
remove((-264.0, -11.0), "CW6: loop along the square's north-west edge", within=4.0)
add([(-383.50, -100.00), (-94.00, -100.00)], "CW6: street along the square's south side", kind="street", width=14.0, cls="street",
    snap=6.0)
add([(-293.00, 37.00), (-293.00, -100.00)], "CW6: short street down the square's west side", kind="street", width=14.0, cls="street",
    snap=6.0)
remove((-275.0, -3.5), "CW6: spur left of the loops, into the square", within=4.0)
# the street along the square's south side met the boulevard before the boulevard's south end was moved onto
# its line (above): that junction is put on the line too
EDITS.append({"op": "move", "at": (-97.83, -99.89), "to": (-94.00, -100.00), "within": 2.0, "when": "after",
              "why": "CW6: the boulevard's junction with the square's south street on its line"})

# ---------------------------------------------------------------------------------------------------------
# Centro Oeste between the top street (y = 40) and the street along y = 185 (sector CW8; 2026-11-14). The
# tracing drew the street at x = 48 and the street along y = 185 as one line with a 30 m bump where the
# boulevard's band crosses north of it. The boulevard itself stops at the top street and starts again north of
# y = 185, with a block of 290 x 145 m between. Read as: the L redrawn straight, and the boulevard carried
# through from the top street to the street along y = 185 (it splits that block in two of about 150 m).
# ---------------------------------------------------------------------------------------------------------
remove((-188.0, 183.0), "CW8: the L with the bump (x = 48 and y = 185)", within=4.0)
add([(50.93, 41.55), (45.50, 186.00), (-240.73, 180.24)], "CW8: the L, straight: x = 48 up, y = 185 west", kind="street", width=14.0,
    cls="street", snap=6.0)
add([(-94.00, 33.62), (-94.00, 183.19)], "CW8: the boulevard carried north to the street along y = 185", kind="avenue", width=30.0,
    cls="arterial", snap=6.0)

# ---------------------------------------------------------------------------------------------------------
# Centro Oeste south of the cross street along y = -262 (sector CW7; 2026-11-14). The street at x = -235 runs
# straight from y = -262 to y = -565, except where the street along y = -410 meets it: there the drawing widens
# the gap between the blocks (a notch in the block west of it) and the tracing jogged the street 15 m west and
# back. The block west of it is one block 590 m long from y = -262 to y = -860, where the streets along
# y = -410 (from the east) and y = -565 (from the west and the east) all end at its sides. Read as:
#   * the street at x = -235 straight, its junction with the street along y = -410 on that street's line;
#   * the street along y = -410 carried west across the long block to the street at x = -383 (it meets it at the
#     junction of the lane from x = -480), so the block's first 150 m are a block of their own;
#   * the street along y = -565 carried across the long block too (the next 150 m).
# ---------------------------------------------------------------------------------------------------------
remove((-245.3, -394.3), "CW7: street at x = -235, jog west (north part)", within=3.0)
remove((-240.0, -440.0), "CW7: street at x = -235, jog west (south part)", within=3.0)
EDITS.append({"op": "move", "at": (-249.2, -412.5), "to": (-233.33, -413.00), "within": 2.0,
              "why": "CW7: the junction at y = -410 back on the line of the street at x = -235"})
add([(-235.86, -263.37), (-233.33, -413.00)], "CW7: street at x = -235 straight (north part)", kind="street", width=14.0,
    cls="street", snap=6.0)
add([(-233.33, -413.00), (-230.83, -562.50)], "CW7: street at x = -235 straight (south part)", kind="street", width=14.0,
    cls="street", snap=6.0)
add([(-233.33, -413.00), (-392.50, -440.80)], "CW7: street along y = -410 carried west to x = -383", kind="street", width=14.0,
    cls="street", snap=10.0)
add([(-379.20, -565.80), (-230.83, -562.50)], "CW9: street along y = -565 carried across the long block", kind="street",
    width=14.0, cls="street", snap=6.0)
# the straightening puts the junction on the line of the street along y = -410 (CW5's south side), a few
# centimetres off: it is put exactly where the street at x = -235 crosses that line
EDITS.append({"op": "move", "at": (-233.33, -413.00), "to": (-233.33, -413.00), "within": 2.0, "when": "after",
              "why": "CW7: junction of x = -235 and y = -410 exactly on both lines"})

# ---------------------------------------------------------------------------------------------------------
# The funnel south of the block between x = -235 and x = 55 (sector CW10; 2026-11-14). The drawing opens the
# street at x = 55 into a Y at y = -518: one arm sweeps south-west to the street that runs south at x = -86,
# the other east; the street along y = -565 sweeps round the block's south-west side to the same point. The
# tracing drew both sweeps as straight pieces with 35 to 50 degree kinks (one arm also a 3 m hook at its
# start) and a slip lane round a small island. Read as two smooth curves meeting the street south at
# (-86, -611); the slip lane and its island dropped.
# ---------------------------------------------------------------------------------------------------------
remove((-215.0, -563.0), "CW10: street along y = -565, east end (redrawn as a curve)", within=2.0)
remove((-164.0, -581.0), "CW10: slip lane round the island", within=6.0)
remove((-156.0, -561.0), "CW10: south-west sweep, kinked", within=2.0)
remove((-107.0, -605.0), "CW10: south-west sweep, last piece", within=6.0)
remove((-27.0, -556.0), "CW10: arm of the Y towards x = -86, kinked", within=2.0)
add([(-230.80, -562.50), (-205.0, -562.3), (-180.0, -562.0), (-158.0, -565.0), (-138.0, -575.0), (-120.0, -590.0),
     (-104.0, -602.0), (-85.80, -610.80)], "CW10: the south-west sweep, smooth", kind="street", width=14.0, cls="street",
    snap=6.0, curve=True)
add([(70.80, -517.50), (45.0, -533.0), (22.0, -545.0), (0.0, -552.0), (-25.0, -557.0), (-48.0, -565.0), (-66.0, -577.0),
     (-78.0, -590.0), (-84.0, -601.0), (-85.80, -610.80)], "CW10: the Y's arm towards x = -86, smooth", kind="street",
    width=14.0, cls="street", snap=6.0, curve=True)

# ---------------------------------------------------------------------------------------------------------
# East of the funnel, between the street at x = 55 and the street along the valley's edge (sector CW11;
# 2026-11-14). (1) The street at x = 200 (CW4) stops at the street along y = -400 and starts again 6 m further
# east at y = -551, running south from there: a gap of 150 m with nothing but a block between. Joined: one
# street at x = 200 from the tunnel street down past y = -700, and the block of 285 x 145 m cut in two.
# (2) The Y's east arm was traced in pieces round a small island (a slip lane on each side): one smooth curve
# from the Y to the junction at (206, -551), the island dropped.
# ---------------------------------------------------------------------------------------------------------
remove((100.0, -527.0), "CW11: Y's east arm, first piece", within=4.0)
remove((132.0, -525.0), "CW11: slip lane north of the island", within=3.0)
remove((150.0, -551.5), "CW11: slip lane south of the island", within=3.0)
remove((190.0, -548.4), "CW11: Y's east arm, last piece", within=3.0)
add([(70.83, -517.50), (90.0, -524.0), (115.0, -533.0), (140.0, -541.0), (165.0, -547.0), (190.0, -550.0), (205.83, -550.83)],
    "CW11: the Y's east arm, smooth", kind="street", width=14.0, cls="street", snap=6.0, curve=True)
add([(200.00, -399.42), (205.83, -550.83)], "CW11: street at x = 200 carried south to y = -551", kind="street", width=14.0,
    cls="street", snap=6.0)

# ---------------------------------------------------------------------------------------------------------
# Centro Oeste between the street along y = 185 and the shore street (y = 480 to 490), from x = -241 to the
# street at x = 190 (sectors CW12 onwards; 2026-11-14). The drawing fills 430 x 300 m with a fine grid of
# buildings and no street at all; its only opening is a paved square north of the boulevard's end, which the
# street at x = 48 also reaches. Read as the grid carried north:
#   * the boulevard on to the shore street, ending where the drawing's pier (the orange stub) leaves it: the
#     axis turns 4.5 degrees at the street along y = 185 and runs from the pond to the bay;
#   * the streets at x = -241 and x = 45 (CW8's two sides) up to the shore street;
#   * the street along y = 185 carried east from x = 45 to the street at x = 190 (the block east of x = 48
#     would be 140 x 300 m otherwise);
#   * a cross street along y = 341, from the street at x = 190 (where the Delegacia's west arm, y = 347, meets
#     it) west to x = -241: blocks of about 150 m.
# ---------------------------------------------------------------------------------------------------------
add([(-94.01, 184.30), (-117.43, 484.18)], "CW12: the boulevard carried north to the shore street", kind="avenue", width=30.0,
    cls="arterial", snap=6.0)
add([(-240.73, 180.24), (-240.73, 479.30)], "CW12: street at x = -241 carried north to the shore", kind="street", width=14.0,
    cls="street", snap=6.0)
add([(45.50, 186.00), (45.50, 487.81)], "CW12: street at x = 45 carried north to the shore", kind="street", width=14.0,
    cls="street", snap=6.0)
add([(45.50, 186.00), (192.49, 195.75)], "CW12: street along y = 185 carried east to x = 190", kind="street", width=14.0,
    cls="street", snap=6.0)
add([(188.36, 346.65), (45.50, 344.76)], "CW12: cross street along y = 341 (east part)", kind="street", width=14.0,
    cls="street", snap=6.0)
add([(45.50, 344.76), (-106.38, 342.75)], "CW12: cross street along y = 341 (middle part)", kind="street", width=14.0,
    cls="street", snap=6.0)
add([(-106.38, 342.75), (-240.73, 340.98)], "CW12: cross street along y = 341 (west part)", kind="street", width=14.0,
    cls="street", snap=6.0)

# ---------------------------------------------------------------------------------------------------------
# South of the funnel, between the streets at x = -233 and x = 205 (sectors CW17 onwards; 2026-11-14). The
# street that runs south from the funnel's tip (x = -85) ends at y = -802 in two diagonals, one to the
# south-west and one to the east-south-east, each with a second road below it round a triangular island; the
# streets along y = -700 (from x = 205) and y = -858 (from the west) stop short of it. Read as the grid:
#   * the street at x = -85 carried straight on south to a street along y = -857, which runs from the street
#     at x = -233 to the junction at (62, -840) where the street along y = -843 carries on east;
#   * the two diagonals and the roads below them dropped (the triangles become block ground);
#   * the street along y = -700 carried west across to the street at x = -233 (meets it where the lane into
#     the long block leaves it): blocks of about 150 m instead of 290 x 300 m.
# ---------------------------------------------------------------------------------------------------------
remove((-59.2, -802.5), "CW17: diagonal to the east-south-east (first part)", within=2.0)
remove((10.0, -827.7), "CW17: diagonal to the east-south-east (second part)", within=2.0)
remove((-37.5, -828.0), "CW17: road below the east-south-east diagonal", within=1.0)
remove((-145.0, -824.5), "CW17: diagonal to the south-west", within=2.0)
remove((-86.6, -820.0), "CW17: road below the south-west diagonal", within=2.0)
# the traced street from the funnel's tip down to the diagonals' start is redrawn with its extension as one
# straight street (a traced piece and an added piece would leave a stray node where they meet)
remove((-85.0, -750.0), "CW17: street at x = -85 as traced", within=2.0)
add([(-85.83, -610.83), (-83.75, -857.00)], "CW17: street at x = -85 from the funnel's tip to y = -857", kind="street",
    width=14.0, cls="street", snap=6.0)
add([(-187.50, -857.50), (-83.75, -857.00)], "CW17: street along y = -857 (west part)", kind="street", width=14.0,
    cls="street", snap=6.0)
add([(-83.75, -857.00), (62.20, -840.00)], "CW17: street along y = -857 (east part, up to y = -843)", kind="street",
    width=14.0, cls="street", snap=6.0)
add([(-230.83, -684.17), (-85.07, -700.00)], "CW17: street along y = -700 carried west to x = -233", kind="street",
    width=14.0, cls="street", snap=6.0)
add([(-85.07, -700.00), (62.50, -702.50)], "CW17: street along y = -700 (middle part)", kind="street", width=14.0,
    cls="street", snap=6.0)

# ---------------------------------------------------------------------------------------------------------
# Centro Oeste west of CW6 and CW8 (sectors CW20 onwards; 2026-11-14). The street at x = -383 (CW6's west
# side) bends into the top street at (-379, 24) and stops; west of it a block of 150 x 290 m runs from the
# street along y = -115 to the street along y = 177; north of y = 177 the grid of CW13-CW16 has no streets
# west of x = -241 (the drawing: buildings, a green patch and a paved loop with islands, a bus or parking yard).
# Read as the grid carried on:
#   * the bend made a junction: the street at x = -383 straight from (-384, -100) to it and on north, at
#     x = -379, across the street along y = 177 to the shore street; the top street carried straight on west
#     to the street at x = -534;
#   * the cross street along y = 341 carried west to the street at x = -536 (meets it at y = 322);
#   * the 32 m dead end south of the street along y = 177 at x = -362 and the loop roads of the paved yard
#     dropped (the yard stays a paved open space, see the sectors).
# ---------------------------------------------------------------------------------------------------------
remove((-350.0, 28.24), "CW20: the bend of x = -383 into the top street", within=3.0)
remove((-360.8, 155.0), "CW20: dead end south of the street along y = 177", within=2.0)
remove((-460.8, 280.0), "CW20: paved yard, loop", within=2.0)
remove((-440.0, 264.2), "CW20: paved yard, cross piece", within=2.0)
remove((-460.8, 244.0), "CW20: paved yard, west lane", within=2.0)
remove((-417.5, 245.0), "CW20: paved yard, east lane", within=2.0)
# a lane of 50 m from the street at x = -536 east along y = 324, where the cross street now runs
remove((-515.0, 323.8), "CW20: lane under the cross street along y = 341", within=2.0)
# the top street's last traced piece west of the junction at x = -293 is redrawn with its extension (a traced
# piece and an added one would leave a stray node where they meet)
remove((-306.0, 33.34), "CW20: top street west of x = -293 as traced", within=1.0)
add([(-384.36, -100.01), (-379.00, 24.20)], "CW20: street at x = -383 straight to the new junction", kind="street", width=14.0,
    cls="street", snap=6.0)
add([(-292.81, 34.12), (-379.00, 24.20)], "CW20: top street to the new junction", kind="street", width=14.0, cls="street",
    snap=6.0)
add([(-379.00, 24.20), (-379.00, 176.90)], "CW20: street at x = -379 north to the street along y = 177", kind="street",
    width=14.0, cls="street", snap=6.0)
add([(-379.00, 24.20), (-534.20, 6.40)], "CW20: top street carried west to x = -534", kind="street", width=14.0, cls="street",
    snap=6.0)
add([(-379.00, 176.90), (-379.00, 332.26)], "CW20: street at x = -379 north to y = 332", kind="street", width=14.0,
    cls="street", snap=6.0)
add([(-379.00, 332.26), (-379.00, 473.95)], "CW20: street at x = -379 north to the shore street", kind="street",
    width=14.0, cls="street", snap=6.0)
add([(-241.57, 340.98), (-379.00, 332.26)], "CW20: cross street along y = 341 carried west (east part)", kind="street",
    width=14.0, cls="street", snap=6.0)
add([(-379.00, 332.26), (-536.23, 322.28)], "CW20: cross street along y = 341 carried west (west part)", kind="street",
    width=14.0, cls="street", snap=6.0)

# ---------------------------------------------------------------------------------------------------------
# The north waterfront of the Centro Oeste (sector CW24; 2026-11-14). Where the boulevard reaches the shore
# street the drawing has an orange platform (legend: bridges, viaducts and elevated roads) jutting 50 m into
# the bay, L-shaped, joined to nothing else: read as a pier at the boulevard's end, at quay level. The tracing
# made it a 34 m wide "bridge" that runs up the pier and turns west. Built as a street running straight on from
# the boulevard to the pier's head, a dead end.
# ---------------------------------------------------------------------------------------------------------
remove((-117.4, 510.0), "CW24: the pier traced as a bridge", within=1.0)
add([(-117.43, 484.47), (-117.43, 540.00)], "CW24: street onto the pier, the boulevard's last stretch", kind="street",
    width=14.0, cls="street", snap=6.0)

# ---------------------------------------------------------------------------------------------------------
# The diagonal avenue south-west of CW21 (sectors CW25, CW26; 2026-11-14). The drawing has a wide band from the
# street along y = -115 at x = -584 running south-south-east to (-505, -430), with two triangular islands in it
# near its top, and at its foot a wide paved knot: a branch east along y = -430 to the street at x = -383, a
# branch south to the street along y = -568, and a diagonal band from that branch's foot north-east to the
# street at x = -383, with islands between. The tracing made it a dozen lanes and alleys. Read as:
#   * one street along the band, from the street along y = -115 to a junction at (-507, -430);
#   * from there one street south to the street along y = -568 and one east to the street at x = -383;
#   * the diagonal from the south street's foot to the junction at (-387, -434) on the street at x = -383;
#   * the street along y = -265 (CW6/CW7's south side) carried west from x = -381 to the avenue, so the block
#     east of the avenue is two of about 150 m instead of one of 310 m.
# ---------------------------------------------------------------------------------------------------------
clear([(-600.0, -135.0), (-470.0, -135.0), (-470.0, -200.0), (-395.0, -400.0), (-395.0, -560.0), (-525.0, -560.0), (-600.0, -300.0)],
      "CW25: the lanes and islands of the diagonal band and its knot", share=0.5)
add([(-584.20, -127.50), (-507.00, -430.00)], "CW25: the diagonal avenue as one street", kind="street", width=14.0, cls="street",
    snap=6.0)
add([(-507.00, -430.00), (-512.50, -565.80)], "CW26: branch south to the street along y = -568", kind="street", width=14.0,
    cls="street", snap=6.0)
add([(-507.00, -430.00), (-392.50, -440.80)], "CW26: branch east to the street at x = -383", kind="street", width=14.0,
    cls="street", snap=6.0)
add([(-512.50, -565.80), (-392.50, -440.80)], "CW26: the diagonal to the street at x = -383", kind="street", width=14.0,
    cls="street", snap=6.0)
add([(-379.20, -267.50), (-547.00, -273.30)], "CW25: street along y = -265 carried west to the avenue", kind="street",
    width=14.0, cls="street", snap=6.0)
# the street along y = -115 dips 10 m (to y = -138) between CW21's corner and the avenue's start: straightened
remove((-543.0, -127.0), "CW25: street along y = -115 with a 10 m dip", within=12.0)
add([(-515.80, -107.50), (-584.20, -127.50)], "CW25: street along y = -115 straight to the avenue", kind="street", width=14.0,
    cls="street", snap=6.0)
# North of CW27 (sector CW28; 2026-11-14): the street at x = -680 stops at the street along y = 170; 156 m
# further north a traced L comes down from the shore street at x = -686 and turns east along y = 325 to the
# street at x = -537. Joined: one street at x = -680 from y = -127 to the shore, and the 330 m block between
# x = -870 and x = -537 parted.
add([(-680.15, 169.89), (-675.80, 325.80)], "CW28: street at x = -680 carried north to the L at y = 325", kind="street",
    width=14.0, cls="street", snap=6.0)
# West of CW28 (sector CW29; 2026-11-14): between the street at x = -830 and the street at x = -684, from the
# street along y = 166 to the shore street. Where the shore street bends south-west to meet the street at
# x = -830 the tracing doubled it (a second, narrow road beside it) and cut the corner with a diagonal lane:
# both dropped. The street along y = 325 (CW28) carried west to the street at x = -830.
remove((-788.0, 494.2), "CW29: second road beside the shore street's bend (a loop to y = 494)", within=2.0)
remove((-784.0, 425.4), "CW29: diagonal lane across the shore street's bend", within=2.0)
# (the L's corner is still where it was traced when the edits run, at x = -676.4; it is put on the line of the
# street at x = -680 afterwards, below)
add([(-676.40, 324.93), (-830.49, 324.90)], "CW29: street along y = 325 carried west to x = -830", kind="street", width=14.0,
    cls="street", snap=6.0)

# South of CW29 (sector CW30; 2026-11-14): the lane at y = 22.5 that runs from the street at x = -680 into
# CW27's square carried west, as a street, to the street at x = -830: the block between y = 22 and y = 166.
# The ground south of it (down to y = -135) holds the west mouth of the tunnel and waits for it.
add([(-675.22, 22.50), (-830.00, 22.50)], "CW30: the lane at y = 22.5 carried west to x = -830", kind="street", width=14.0,
    cls="street", snap=6.0)

# The far west of the Centro Oeste, north part (sectors CW32, CW33; 2026-11-14): between the street at x = -830
# and the street at x = -1125, from the street along y = 166 to the shore street, the drawing has one block of
# 295 x 295 m: two columns of rows with a clear strip between them at x = -975, where the street coming up from
# the south (x = -971) stops at y = 163. Read as the grid carried on: that street on north to the shore street
# (at x = -978), and the street along y = 325 (CW28, CW29) on west to the street at x = -1125.
add([(-970.90, 162.90), (-976.00, 325.00)], "CW32: street at x = -975 carried north (to y = 325)", kind="street", width=14.0,
    cls="street", snap=6.0)
add([(-976.00, 325.00), (-978.00, 465.00)], "CW32: street at x = -975 carried north (to the shore street)", kind="street",
    width=14.0, cls="street", snap=6.0)
add([(-830.49, 324.90), (-976.00, 325.00)], "CW32: street along y = 325 carried west to x = -975", kind="street", width=14.0,
    cls="street", snap=6.0)
add([(-976.00, 325.00), (-1117.60, 325.00)], "CW33: street along y = 325 carried west to x = -1118", kind="street", width=14.0,
    cls="street", snap=6.0)
# (between (-944, 456) and (-884, 424) the shore street runs as a loop round a 50 x 35 m island; dropping one
# branch would join the pieces into one traced line, which the straightening then pulls straight, moving
# CW29's corner junction: the loop stays, its island a small lawn in CW32)

# The far west's west column (sectors CW35, CW36; 2026-11-14): between the street at x = -1258 (where the
# road from the Ilha Oeste lands, at (-1258, 301)) and the street at x = -1118, the drawing has one block of
# 115 x 430 m from y = 15 to y = 445. Cut twice:
#   * a street from the landing east to the street along y = 325 (CW33's): the island road carries on into
#     the district along it, turning 10 degrees at the landing;
#   * the street along y = 170 carried west from the stepped corner at x = -1114 to the street at x = -1258.
add([(-1258.40, 300.90), (-1117.65, 325.00)], "CW35: street from the island road's landing to the street along y = 325",
    kind="street", width=14.0, cls="street", snap=6.0)
add([(-1112.00, 184.50), (-1258.75, 178.00)], "CW36: street along y = 180 carried west to x = -1258", kind="street", width=14.0,
    cls="street", snap=6.0)
#   (the new junction splits the stepped street along y = 163-187 that CW33 was first generated on; its east leg
#   then reads as a straight street and is straightened into one line from (-971, 163) to the junction: CW33
#   is generated again on it)
#   * the street along the district's south edge, traced as a line with two jogs of 20 and 30 m (the centre of a
#     wide white band that meanders from (-1198, -15) to (-944, 49)), redrawn as one smooth curve;
#   * the street at x = -1118 carried on south from the corner at y = 181 to that curve: one street from the
#     shore to the south edge, and the 300 m block south of y = 180 cut in two.
remove((-1070.0, 11.4), "CW37: the south-edge street with its two jogs", within=2.0)
add([(-1198.15, -14.96), (-1160.0, -11.0), (-1120.0, 0.0), (-1080.0, 8.0), (-1040.0, 13.0), (-1005.0, 20.0), (-975.0, 33.0),
     (-944.17, 49.17)], "CW37: the south-edge street as a smooth curve", kind="street", width=14.0, cls="street", snap=6.0,
    curve=True)
add([(-1112.97, 180.89), (-1113.00, 1.40)], "CW37: street at x = -1113 carried south to the south-edge street", kind="street",
    width=14.0, cls="street", snap=6.0)

# South of the south-edge street, down to the street along y = -135 (sectors CW39 to CW41; 2026-11-14). The
# drawing has one block of 380 x 130 m with a lawn in its middle and, on its south side, four bays 20 m deep
# opening off the street along y = -135 (parking courts), which the tracing made into four alleys that leave
# and rejoin the street. Read as: the bays are part of the block (the alleys dropped), and the block is cut by
# the two north-south streets carried on through it: x = -1113 down to the street along y = -135 (where it
# carries on south as x = -1109), and x = -944 (from the junction at (-944, 49)) down to it.
remove((-897.5, -114.2), "CW39: alley through the bay at x = -930", within=1.5)
remove((-937.5, -130.0), "CW39: alley stub at x = -937", within=1.0)
remove((-969.2, -117.5), "CW39: alley through the bay at x = -970", within=1.5)
remove((-1042.5, -119.2), "CW40: alley through the bay at x = -1050", within=1.5)
remove((-1082.5, -134.0), "CW40: alley stub at x = -1082", within=1.0)
remove((-1114.2, -120.8), "CW40: alley through the bay at x = -1115", within=1.5)
add([(-1113.00, 1.40), (-1109.20, -142.50)], "CW40: street at x = -1113 carried south to the street along y = -135",
    kind="street", width=14.0, cls="street", snap=6.0)
add([(-944.17, 49.17), (-937.50, -134.20)], "CW39: street at x = -944 carried south to the street along y = -135",
    kind="street", width=14.0, cls="street", snap=6.0)
# the L from CW30's corner (-829, 22) down to the street along y = -135 was traced with a 10 m jog at y = -5 and
# a cut corner: redrawn as an L with one rounded corner at (-821.5, -133), by the tunnel's west mouth
remove((-820.8, -60.0), "CW39: the L down from CW30's corner, as traced", within=1.5)
remove((-905.0, -134.2), "CW39: the L's west leg, as traced", within=1.5)
add([(-828.80, 22.48), (-821.50, -133.00), (-937.50, -134.20)], "CW39: the L down from CW30's corner, redrawn", kind="street",
    width=14.0, cls="street", snap=6.0)
# the street along y = -135 carried east from the L's corner to the corner of CW27 (where the street at x = -675
# bends into the street along y = -127): one street along y = -130 from x = -1108 to the diagonal avenue, and
# the block between it, CW30 and CW27 closed (sector CW42; the tunnel's west mouth opens at its south-west
# corner, by the L's corner, and runs south-east under the ground south of this street)
add([(-821.50, -133.00), (-672.56, -124.04)], "CW42: street along y = -130 from the L's corner to CW27's corner", kind="street",
    width=14.0, cls="street", snap=6.0)

# ---------------------------------------------------------------------------------------------------------
# The far west's south half, west of the tunnel (sectors CW43 to CW47; 2026-11-14).
#   * The ring road round the square block south of the street along y = -141 (the drawing: a wide white band
#     on three sides of a block of buildings) was traced with a step and a 6 m bump: redrawn with two clean
#     corners. On its south side the tracing made a triangle of short roads and an alley round two small islands
#     of a wide band: the ring's south side is the one street along y = -290; the triangle dropped.
#   * A street at x = -945 from the street along y = -135 (x = -944 from the north) down to the street along
#     y = -440: the drawing's block of 400 x 155 m south of y = -135 cut at the tunnel's west edge, and the
#     street that comes east along y = -296 and turned south at x = -969 meets it there instead (its corner
#     and a 3 m kink redrawn).
#   * At y = -440 the streets from the west (y = -444) and from the east (y = -432) met the north-south street
#     at two junctions 13 m apart, joined by a 39 m wide stub: one junction, both streets straight to it, and
#     the street south from it straight to the street along y = -572.
# The tunnel region east of x = -945 (the S-shaped tunnel from the L's corner to the street at x = -672) waits
# for the tunnels' answer and is not touched.
remove((-1245.8, -250.0), "CW43: ring road as traced (west and north sides)", within=2.0)
remove((-1125.0, -141.6), "CW43: ring road as traced (north side, east end)", within=2.0)
remove((-1124.2, -289.2), "CW43: ring road as traced (south side, east end)", within=1.0)
remove((-1160.0, -290.8), "CW43: ring road as traced (south side)", within=1.0)
add([(-1109.20, -142.50), (-1246.50, -148.00), (-1245.50, -289.00), (-1117.50, -282.50)], "CW43: the ring road, redrawn",
    kind="street", width=14.0, cls="street", snap=6.0)
remove((-1132.5, -300.0), "CW43: triangle south of the ring (west side)", within=1.5)
remove((-1175.8, -312.5), "CW43: triangle south of the ring (alley)", within=1.5)
remove((-1082.5, -315.8), "CW43: triangle south of the ring (east side)", within=1.5)
# the street at x = -1109 carried on south from the ring's south-east corner, over the hill, to the street along
# y = -440, where the lane at x = -1105 goes on south: one north-south street from the shore to y = -737
add([(-1117.50, -282.50), (-1105.80, -444.20)], "CW48: street at x = -1109 carried south over the hill to y = -440",
    kind="street", width=14.0, cls="street", snap=6.0)
remove((-990.0, -295.0), "CW44: street along y = -296 turning south at x = -969, as traced", within=1.5)
add([(-937.50, -134.20), (-945.00, -296.00)], "CW44: street at x = -945 from the street along y = -135 (north part)",
    kind="street", width=14.0, cls="street", snap=6.0)
add([(-1067.50, -297.50), (-945.00, -296.00)], "CW44: street along y = -296 straight to x = -945", kind="street", width=14.0,
    cls="street", snap=6.0)
add([(-945.00, -296.00), (-950.80, -435.80)], "CW44: street at x = -945 down to the street along y = -440", kind="street",
    width=14.0, cls="street", snap=6.0)
remove((-955.8, -440.0), "CW46: stub between the two junctions at y = -440", within=2.0)
remove((-1000.0, -440.8), "CW46: street along y = -444 from the west, as traced", within=1.5)
remove((-954.2, -495.8), "CW46: street south from the junction, as traced", within=1.5)
add([(-1105.80, -444.20), (-950.80, -435.80)], "CW46: street along y = -440 from the west, straight to the junction",
    kind="street", width=14.0, cls="street", snap=6.0)
add([(-950.80, -435.80), (-974.20, -569.20)], "CW46: street south from the junction to the street along y = -572",
    kind="street", width=14.0, cls="street", snap=6.0)

# ---------------------------------------------------------------------------------------------------------
# The far west's south band, between the streets along y = -576 and y = -870 (sectors CW45, CW49 to CW53;
# 2026-11-15). The drawing: a block of 440 x 285 m east of x = -970 (buildings along its north side, a green belt,
# then a dense grid of small houses), a block west of it, and the hill district beyond x = -1250. The tracing had
# no street along the south side between x = -970 and x = -665, an L from (-1102, -737) round to (-971, -862)
# with 10 m jogs, and a driveway loop round a small yard by the south street. Read as:
#   * the north-south street from the junction at (-951, -432) carried straight on south, x = -972, down to the
#     south street; the L's west leg (y = -740) meets it in a T; the L's crooked east leg dropped;
#   * the south street along y = -865 from x = -971 east to the street at x = -665 (the loop dropped);
#   * a cross street along y = -665 from x = -972 to x = -670: the 440 x 285 m block in two (houses' grid south);
#   * the street at x = -1257 carried on south from y = -592 to y = -741 (the block west of x = -1109 closed).
remove((-960.85, -790.0), "CW52: the L from (-1102, -737) to (-971, -862), as traced", within=1.5)
remove((-891.7, -876.0), "CW52: driveway loop by the south street", within=1.5)
add([(-974.20, -569.20), (-970.80, -862.50)], "CW52: street at x = -972 carried south to the south street", kind="street",
    width=14.0, cls="street", snap=6.0)
add([(-1102.50, -737.50), (-972.22, -740.00)], "CW50: street along y = -740 east to x = -972", kind="street", width=14.0,
    cls="street", snap=6.0)
add([(-973.09, -665.00), (-668.90, -665.00)], "CW51: cross street along y = -665", kind="street", width=14.0, cls="street",
    snap=6.0)
add([(-970.80, -862.50), (-664.20, -872.50)], "CW52: south street along y = -865 from x = -971 to x = -665", kind="street",
    width=14.0, cls="street", snap=6.0)
add([(-1249.20, -592.50), (-1245.80, -740.80)], "CW49: street at x = -1257 carried south to y = -741", kind="street",
    width=14.0, cls="street", snap=6.0)
# Between the street at x = -670 and the street at x = -231, from y = -567 to y = -870 (sectors CW55 to CW60;
# 2026-11-15). The drawing has an isolated orange strip (legend: bridge, viaduct, elevated road) along the street
# at x = -380 from y = -650 to y = -870, joined to nothing: the tracing made it a "bridge" edge. Built as the
# street at ground level, as the downtown's orange strip was (decision noted in the vault, can be changed): one
# straight street at x = -379 from the street along y = -567 to the street along y = -866. Also:
#   * the wide white band from (-384, -702) to (-521, -714) (the edge of a paved lot) as a straight street, and
#     carried east across the long block to the street at x = -231 (meets CW17's cross street at (-231, -684));
#   * the lane at x = -521 (a stub up to y = -652) as a street from the junction at (-512, -566), where the
#     branch south of the diagonal avenue arrives, down to y = -714: one street from the avenue to y = -869;
#   * the cross street along y = -665 (CW51/CW54) carried east from x = -669 to x = -520.
remove((-371.0, -630.0), "CW57: street at x = -380 north part, as traced", within=3.0)
remove((-377.5, -680.0), "CW57: the orange strip (traced as a bridge), north part", within=1.5)
remove((-377.5, -780.0), "CW57: the orange strip (traced as a bridge), south part", within=1.5)
remove((-450.0, -683.5), "CW57: wide band along the paved lot", within=2.0)
remove((-521.5, -680.0), "CW55: lane stub at x = -521", within=1.5)
add([(-379.20, -565.80), (-379.00, -865.80)], "CW57: street at x = -379 at ground level", kind="street", width=14.0,
    cls="street", snap=6.0)
add([(-512.50, -565.80), (-520.80, -714.20)], "CW55: street at x = -515 from the avenue's branch to y = -714", kind="street",
    width=14.0, cls="street", snap=6.0)
add([(-379.10, -703.00), (-520.80, -714.20)], "CW57: street along y = -705 west of x = -379", kind="street", width=14.0,
    cls="street", snap=6.0)
add([(-379.10, -703.00), (-230.83, -684.17)], "CW59: street along y = -695 east of x = -379 to x = -231", kind="street",
    width=14.0, cls="street", snap=6.0)
add([(-668.90, -665.00), (-517.00, -665.00)], "CW55: cross street along y = -665 carried east to x = -517", kind="street",
    width=14.0, cls="street", snap=6.0)
# the street along the long block's south side (y = -861 at x = -231) dropped to y = -884 at x = -374 and met the
# street at x = -379 through an 18 m lane: straight on along y = -863 to the junction at (-379, -866), and the
# street south from there (to the diamond at y = -985) starts at that junction
remove((-300.0, -862.6), "CW60: south side of the long block, dropping to y = -884", within=2.0)
remove((-377.5, -872.5), "CW60: lane from (-384, -866) to (-374, -884)", within=1.5)
add([(-230.80, -860.80), (-384.20, -865.80)], "CW60: south side of the long block, straight", kind="street", width=14.0,
    cls="street", snap=6.0)
add([(-384.20, -865.80), (-374.20, -884.20)], "CW60: the street south starts at the junction", kind="street", width=14.0,
    cls="street", snap=4.0)
# the straightening puts the junction of x = -379 and y = -703 where the two cross streets' lines meet, 2.7 m off
# the line of x = -379 between its frozen ends: put on that line
EDITS.append({"op": "move", "at": (-381.46, -702.96), "to": (-378.76, -702.96), "within": 2.0, "when": "after",
              "why": "CW57: junction on the line of the street at x = -379"})
EDITS.append({"op": "move", "at": (-384.17, -865.87), "to": (-378.92, -865.87), "within": 2.0, "when": "after",
              "why": "CW60: junction at y = -866 on the line of the street at x = -379"})

# South of the street along y = -866, between x = -665 and x = -225 (sectors CW61 to CW65; 2026-11-15). The
# drawing: a small diamond roundabout round a kiosk island at (-370, -997); the street at x = -517 and the
# loop round the two big blocks to the south-east, traced as 10 m lanes; the street at x = -231 stops at
# y = -861. Read as:
#   * the diamond as a plain crossing: one street at x = -372 from the junction at (-379, -866) down to
#     y = -1192, crossed by one street along y = -997 from x = -517 to x = -336;
#   * the diagonal from the tunnel's mouth at (-662, -1075) joined to the street at x = -517 at the same
#     junction as the street along y = -997 (it met it 6.5 m further south);
#   * the street at x = -231 carried south to the loop's north-east corner (-224, -994): one street from
#     y = -413 down to y = -1190; the loop, the street at x = -517 and the street along y = -1192 made streets.
remove((-373.0, -925.0), "CW62: lane at x = -372 north of the diamond", within=2.0)
remove((-352.0, -981.0), "CW62: diamond, north-east side", within=1.5)
remove((-387.0, -987.0), "CW62: diamond, north-west side", within=1.5)
remove((-384.0, -1015.0), "CW62: diamond, south-west side", within=1.5)
remove((-356.0, -1016.0), "CW62: diamond, south-east side", within=1.5)
remove((-370.5, -1110.0), "CW62: lane at x = -370 south of the diamond", within=2.0)
remove((-460.0, -998.3), "CW62: lane along y = -998 west of the diamond", within=1.5)
remove((-590.0, -1040.4), "CW61: diagonal from the tunnel's mouth, as traced", within=2.0)
remove((-517.36, -1002.5), "CW61: 6 m between the two junctions on x = -517", within=1.0)
remove((-516.0, -1100.0), "CW64: lane at x = -517 south of the diagonal", within=2.0)
add([(-374.20, -884.20), (-369.40, -1191.70)], "CW62: street at x = -372 through the diamond", kind="street", width=14.0,
    cls="street", snap=6.0)
add([(-517.40, -999.20), (-372.43, -997.50)], "CW62: street along y = -997 west of x = -372", kind="street", width=14.0,
    cls="street", snap=6.0)
add([(-372.43, -997.50), (-336.20, -995.70)], "CW62: street along y = -997 east of x = -372", kind="street", width=14.0,
    cls="street", snap=6.0)
add([(-662.30, -1075.25), (-517.40, -999.20)], "CW61: diagonal from the tunnel's mouth to x = -517", kind="street", width=14.0,
    cls="street", snap=6.0)
add([(-517.40, -999.20), (-514.93, -1194.21)], "CW64: street at x = -517 south to y = -1194", kind="street", width=14.0,
    cls="street", snap=6.0)
add([(-230.83, -860.83), (-224.20, -994.20)], "CW63: street at x = -231 carried south to the loop's corner", kind="street",
    width=14.0, cls="street", snap=6.0)
along([(-519.1, -869.1), (-517.4, -999.2)], "CW62: street at x = -517 north part (traced as a lane)", within=4.0, share=0.7,
      kind="street", cls="street", width=14.0)
along([(-336.2, -995.7), (-224.2, -994.2), (-225.8, -1182.5), (-369.2, -1191.7), (-514.9, -1194.2)],
      "CW65: the loop and the street along y = -1192 (traced as lanes)", within=5.0, share=0.7, kind="street", cls="street",
      width=14.0)

# The houses south of CW17-CW19 (sectors CW66 to CW71; 2026-11-15): from the street at x = -228 to x = 200,
# between the streets along y = -857/-843 and y = -1085, the drawing has 430 x 230 m of small houses in rows and
# no street at all, with a green gap across it at y = -975. Read as a grid: the streets at x = -84 and x = 62
# (CW17-CW19) carried south, a street at x = 200 from the corner of CW19's L, a cross street along y = -975 in
# the green gap and a street along y = -1085 on the district's south edge (open hillside beyond).
add([(-83.75, -857.00), (-84.00, -1085.00)], "CW66: street at x = -84 carried south to y = -1085", kind="street", width=14.0,
    cls="street", snap=6.0)
add([(61.67, -842.50), (62.00, -1085.00)], "CW67: street at x = 62 carried south to y = -1085", kind="street", width=14.0,
    cls="street", snap=6.0)
# (a junction on the corner of CW19's L would split it: each piece is then simplified and has no corner to round,
# and the L's built shape moves by up to 3 m. The street at x = 200 starts at the cross street instead; the block
# north of it is open on the east, towards the houses not built yet)
add([(200.00, -975.00), (200.00, -1085.00)], "CW68: street at x = 200 from the cross street south to y = -1085", kind="street",
    width=14.0, cls="street", snap=4.0)
add([(-225.11, -975.00), (-84.00, -975.00)], "CW69: cross street along y = -975 (west part)", kind="street", width=14.0,
    cls="street", snap=6.0)
add([(-84.00, -975.00), (62.00, -975.00)], "CW70: cross street along y = -975 (middle part)", kind="street", width=14.0,
    cls="street", snap=6.0)
add([(62.00, -975.00), (200.00, -975.00)], "CW71: cross street along y = -975 (east part)", kind="street", width=14.0,
    cls="street", snap=6.0)
add([(-224.98, -1085.00), (-84.00, -1085.00)], "CW69: south street along y = -1085 (west part)", kind="street", width=14.0,
    cls="street", snap=6.0)
add([(-84.00, -1085.00), (62.00, -1085.00)], "CW70: south street along y = -1085 (middle part)", kind="street", width=14.0,
    cls="street", snap=6.0)
add([(62.00, -1085.00), (200.00, -1085.00)], "CW71: south street along y = -1085 (east part)", kind="street", width=14.0,
    cls="street", snap=6.0)

# East of the streets at x = 205 and x = 350, on the valley's west edge (sectors CW72, CW73; 2026-11-15). The
# drawing has houses in two-deep rows round the edge of an L-shaped area (x = 205 to 485, y = -393 to -730) and
# a column of houses along the east side of the street at x = 205 down to y = -1050, with open ground beyond.
# No streets. Read as: a street along y = -700 from the junction at (206, -699) east to x = 485, a street along
# y = -393 from the junction at (350, -395) east to x = 485, and a street at x = 485 between them, on the
# valley's edge: one L-shaped block with houses round a green middle. The column of houses south of y = -700
# faces the street at x = 205/200; the land behind it stays open (no street, the drawing has none).
add([(205.83, -699.17), (485.00, -700.00)], "CW72: street along y = -700 east to x = 485", kind="street", width=14.0,
    cls="street", snap=4.0)
add([(350.06, -394.92), (485.00, -393.00)], "CW72: street along y = -393 east of x = 350", kind="street", width=14.0,
    cls="street", snap=4.0)
add([(485.00, -393.00), (485.00, -700.00)], "CW72: street at x = 485 on the valley's edge", kind="street", width=14.0,
    cls="street", snap=4.0)

# The north-west promontory (sectors CW74 to CW76; 2026-11-15): north of the shore street from x = -985 to the
# coast at x = -700, the drawing has a dense grid of small houses (y = 460 to 695) and, beyond, a green cape
# (to y = 860); no streets but the one at x = -982 that turns west along y = 600. Read as: that street carried
# north to y = 695, a street along y = 695 from the street at x = -1131 east to x = -720 (the edge of the cape
# park), a street at x = -720 back south to a cross street along y = 540, and a street at x = -850 between them.
add([(-985.80, 599.20), (-985.00, 695.00)], "CW74: street at x = -985 carried north to y = 695", kind="street", width=14.0,
    cls="street", snap=4.0)
add([(-985.00, 695.00), (-720.00, 695.00)], "CW74: street along y = 695 (east part)", kind="street", width=14.0, cls="street",
    snap=4.0)
add([(-1131.60, 692.00), (-985.00, 695.00)], "CW76: street along y = 695 (west part)", kind="street", width=14.0, cls="street",
    snap=4.0)
add([(-720.00, 695.00), (-720.00, 540.00)], "CW74: street at x = -720 south to y = 540", kind="street", width=14.0, cls="street",
    snap=4.0)
add([(-720.00, 540.00), (-982.10, 540.00)], "CW74: cross street along y = 540", kind="street", width=14.0, cls="street",
    snap=4.0)
add([(-850.00, 695.00), (-850.00, 540.00)], "CW74: street at x = -850", kind="street", width=14.0, cls="street", snap=4.0)

# the houses' grid south of the cross street is 300 x 205 m: cut by a street at x = -818 (the drawing has rows
# of small houses there with narrow gaps, no street)
add([(-818.00, -665.00), (-818.00, -867.54)], "CW54: street at x = -818 through the houses' grid", kind="street", width=14.0,
    cls="street", snap=6.0)

# the L's corner, now a junction, lies 7.6 m east of the line from (-680, 170) to the shore street: put on it,
# so the street at x = -680 runs straight to the shore instead of zigzagging (-680, -676, -687)
EDITS.append({"op": "move", "at": (-676.40, 324.93), "to": (-683.98, 324.93), "within": 2.0, "when": "after",
              "why": "CW28: junction on the line of the street at x = -680"})

# the junction at (-386, -434) is CW7's and CW9's corner. The traced street at x = -383 jogs 13 m west there;
# with the alleys of the knot gone nothing else fixes the junction, and the straightening puts it 7.2 m away,
# just past the reach within which frozen junctions are put back: it is put back here
EDITS.append({"op": "move", "at": (-386.80, -441.11), "to": (-386.45, -433.92), "within": 3.0, "when": "after",
              "why": "CW26: CW7/CW9's corner back where they were built"})

# ---------------------------------------------------------------------------------------------------------
# Sector PF1 (2026-11-13), the city hall at the north end of the Ponte Central da Baia. The drawing puts the
# "Prefeitura" marker on the road's own axis, on a platform that juts into the bay, and widens the road
# around it. Built as agreed with the user: the road opens into two streets around an oval square with the
# city hall in the middle, and closes again north of it.
#   * The two short arms drawn across the bridge's landing are the platform's front terrace, not streets.
#   * The street north of the square is drawn 37 m wide: a four-lane avenue, as on the bridge.
# ---------------------------------------------------------------------------------------------------------
PF1_CENTRE, PF1_A, PF1_B = (1766.0, 1571.75), 50.0, 64.25          # oval of the two streets: centre, half-axes (m)


def _oval(first_deg, last_deg, steps=12):
    """Points along the oval, angle measured from east, counter-clockwise."""
    import math
    out = []
    for k in range(steps + 1):
        a = math.radians(first_deg + (last_deg - first_deg) * k / steps)
        out.append((round(PF1_CENTRE[0] + PF1_A * math.cos(a), 2), round(PF1_CENTRE[1] + PF1_B * math.sin(a), 2)))
    return out


clear([(1688, 1478), (1848, 1478), (1848, 1504), (1688, 1504)], "PF1: terrace arms are not streets", share=0.6)
clear([(1750, 1515), (1782, 1515), (1782, 1790), (1750, 1790)], "PF1: road through the square redrawn", share=0.8)
# the bridge's north end stays exactly where the straightening used to put it (on the line of the street that
# is redrawn here), so the bridge, and the sectors built at its south end, do not move by a hair
EDITS.append({"op": "move", "at": (1770.0, 1507.5), "to": (1766.4, 1507.5), "why": "PF1: bridge end where it was"})
add([(1763.8, 1799.6), (1765.2, 1700.0), (1766.0, 1636.0)], "PF1: avenue north of the square", kind="street", width=30.0, cls="arterial")
add([(1766.4, 1507.5)] + _oval(-90, -270, 18)[1:-1] + [(1766.0, 1636.0)], "PF1: west street of the square", kind="street", width=14.0,
    cls="street", curve=True)
add([(1766.4, 1507.5)] + _oval(-90, 90, 18)[1:-1] + [(1766.0, 1636.0)], "PF1: east street of the square", kind="street", width=14.0,
    cls="street", curve=True)

# ---------------------------------------------------------------------------------------------------------
# Downtown main axis (2026-11-13). The drawing shows one road clearly wider than the streets around it
# (26-27 m against 13-16 m): from the Ponte Central da Baia south through the financial district, then west
# to the mouth of the Tunel Expresso Central; and the block of street that brings the waterfront avenue to
# it. Those are four-lane avenues, so the bridge's four lanes do not pour into a two-lane street.
# ---------------------------------------------------------------------------------------------------------
along([(1789.7, 875.8), (1794.2, 673.7), (1797.6, 525.8), (1800.9, 379.0), (1804.3, 228.5), (1807.5, 85.4),
       (1806.0, 20.0), (1799.4, -31.5), (1770.0, -52.0), (1707.5, -69.2), (1663.8, -70.8), (1518.2, -72.5), (1379.6, -74.2)],
      "downtown axis: bridge to tunnel", within=14.0, share=0.7, min_width=18.0, cls="arterial")
along([(1657.4, 226.1), (1804.3, 228.5)], "downtown axis: waterfront avenue link", within=8.0, share=0.8,
      min_width=18.0, cls="arterial")

# The hill district west of x = -1250 (sectors CW77 to CW80; 2026-11-15): a flat hilltop at 40-45 m between the
# street at x = -1250 and the edge of the slope down to the freeway (x = -1440). The drawing has an avenue round
# three sides of it, two cross streets and houses on both sides of the avenue's west leg; north of it, a big
# green park on the hill up to y = 250, reached by a short street to a car park. The tracing wandered between
# x = -1383 and x = -1398 on the west leg and met the cross street along y = -595 in a Y 26 m east of the leg.
# Read as: the west leg straight along x = -1393 from the corner at (-1381, -456) down to y = -890, round the
# south-west corner and east along y = -890 to the junction at (-1246, -891); the two cross streets straight
# from their junctions on x = -1250 to the leg (T junctions). The loop is the hilltop's own street (it leads
# nowhere else: streets at both ends), so it is built as a street, not as the four-lane avenue the drawing's
# width suggests; the short street up to the park's car park too.
remove((-1392.15, -538.98), "CW77: the avenue's west leg, north part, as traced", within=1.5)
remove((-1397.56, -678.35), "CW78: the avenue's west leg, middle part, as traced", within=1.5)
remove((-1374.91, -887.68), "CW79: the avenue's west leg and south side, as traced", within=1.5)
remove((-1310.02, -594.68), "CW77: cross street along y = -595, as traced", within=1.5)
remove((-1316.84, -749.74), "CW78: cross street along y = -750, as traced", within=8.0)
add([(-1381.20, -456.20), (-1393.00, -505.00), (-1393.00, -597.00)], "CW77: the avenue's west leg, north part",
    kind="street", width=14.0, cls="street", snap=4.0)
add([(-1393.00, -597.00), (-1393.00, -759.00)], "CW78: the avenue's west leg, middle part", kind="street", width=14.0,
    cls="street", snap=4.0)
add([(-1393.00, -759.00), (-1393.00, -889.50), (-1245.83, -890.83)], "CW79: the avenue's west leg and south side",
    kind="street", width=14.0, cls="street", snap=4.0)
add([(-1248.17, -592.47), (-1393.00, -597.00)], "CW77: cross street along y = -595", kind="street", width=14.0,
    cls="street", snap=4.0)
add([(-1245.83, -740.83), (-1393.00, -759.00)], "CW78: cross street along y = -750", kind="street", width=14.0,
    cls="street", snap=4.0)
# (it keeps the avenue's gentle profile, which CW48 was built against: a street's own would climb 17 % off its corner)
along([(-1257.69, -440.96), (-1381.20, -456.20)], "CW77: the loop's north side, a street like the rest of it", within=4.0,
      share=0.8, kind="street", cls="street", width=14.0, hold=0.07, grade=0.09)
along([(-1381.20, -456.20), (-1386.10, -400.90)], "CW80: street up to the hill park's car park", within=4.0, share=0.8,
      kind="street", cls="street", width=14.0)

# The houses south of the hill (sectors CW82 to CW88; 2026-11-16): south of the streets along y = -890 and y = -865,
# from the hill's slope (x = -1345) to the street at x = -665, the drawing has small houses in two bands (y = -900
# to -1000 and y = -1035 to -1130) with a green gap between them and no street at all; open parkland south of
# y = -1140. Read as a grid: the streets at x = -1246, x = -971 and x = -818 carried south to a south street along
# y = -1140; a cross street in the green gap along y = -1020, from x = -1345 to the street at x = -665 (it meets
# that street at CW61's corner, 50 m before the tunnel's mouth); and a street at x = -1345 straight down the
# hill's slope from the loop's south side (14 % on average, like the steep streets of such cities), which
# turns east into the south street. The slope west of it is CW80's (a wooded slope down to the freeway).
add([(-1345.00, -889.93), (-1345.00, -1140.00), (-1246.00, -1140.00)], "CW82: street down the slope at x = -1345 and the south street's west part (CW86)",
    kind="street", width=14.0, cls="street", snap=4.0)
add([(-1245.83, -890.83), (-1246.00, -1140.00)], "CW83: street at x = -1246 carried south to y = -1140", kind="street",
    width=14.0, cls="street", snap=4.0)
add([(-970.83, -862.50), (-971.00, -1140.00)], "CW84: street at x = -971 carried south to y = -1140", kind="street",
    width=14.0, cls="street", snap=4.0)
add([(-818.00, -867.48), (-818.00, -1140.00), (-971.00, -1140.00)], "CW88: street at x = -818 carried south, and the south street's east part",
    kind="street", width=14.0, cls="street", snap=4.0)
add([(-1246.00, -1140.00), (-971.00, -1140.00)], "CW87: south street along y = -1140 (middle part)", kind="street",
    width=14.0, cls="street", snap=4.0)
add([(-1345.00, -1020.00), (-1246.00, -1020.00)], "CW82: cross street along y = -1020 (west part)", kind="street",
    width=14.0, cls="street", snap=4.0)
add([(-1246.00, -1020.00), (-971.00, -1020.00)], "CW83: cross street along y = -1020 (middle part)", kind="street",
    width=14.0, cls="street", snap=4.0)
add([(-971.00, -1020.00), (-818.00, -1020.00)], "CW84: cross street along y = -1020 (east part)", kind="street",
    width=14.0, cls="street", snap=4.0)
add([(-818.00, -1020.00), (-663.14, -1020.00)], "CW85: cross street along y = -1020 to the street at x = -665", kind="street",
    width=14.0, cls="street", snap=6.0)
# The complex south of CW64/CW65 (sectors CW89 to CW93; 2026-11-16): south of the street along y = -1192 the
# drawing has a rectangle of avenues round three blocks (x = -515 to -105, y = -1332 to -1488): two paved blocks
# with a few big buildings and a green one in the east, a divided boulevard down the middle from the street at
# x = -372 to a small diamond roundabout on the south side, and above the rectangle a plain grey block and a row
# of houses. The tracing made the boulevard's two carriageways two lanes that cross, a Y at each end, a diagonal
# and a loop round the diamond. Read as: the street at x = -372 carried on south as a four-lane avenue straight
# down the middle to the south side (a T, no roundabout); the rectangle's north, west and south sides straight
# streets (they only serve the complex); the lane at x = -513 a street.
clear([(-405.0, -1200.0), (-333.0, -1200.0), (-333.0, -1515.0), (-405.0, -1515.0)], "CW91: the boulevard's lanes, Ys, diagonal and diamond, as traced", share=0.5)
remove((-454.0, -1333.0), "CW91: rectangle's north side, west part, as traced", within=4.0)
remove((-267.0, -1330.0), "CW92: rectangle's north side, east part, as traced", within=4.0)
remove((-516.0, -1402.0), "CW91: rectangle's west and south side, as traced", within=4.0)
remove((-262.0, -1485.0), "CW92: rectangle's south side, east part, as traced", within=4.0)
add([(-514.76, -1335.42), (-369.17, -1331.71)], "CW91: rectangle's north side, west part", kind="street", width=14.0,
    cls="street", snap=6.0)
add([(-369.17, -1331.71), (-204.17, -1327.50)], "CW92: rectangle's north side, east part", kind="street", width=14.0,
    cls="street", snap=6.0)
add([(-514.76, -1335.42), (-515.00, -1487.50), (-369.17, -1487.00)], "CW91: rectangle's west side and south side, west part",
    kind="street", width=14.0, cls="street", snap=6.0)
add([(-369.17, -1487.00), (-199.17, -1484.28)], "CW92: rectangle's south side, east part", kind="street", width=14.0,
    cls="street", snap=6.0)
add([(-369.17, -1191.67), (-369.17, -1331.71)], "CW89: the boulevard from the street along y = -1192 to the rectangle",
    kind="avenue", width=22.0, cls="arterial", snap=4.0)
add([(-369.17, -1331.71), (-369.17, -1487.00)], "CW91: the boulevard down the middle of the rectangle", kind="avenue",
    width=22.0, cls="arterial", snap=4.0)
along([(-512.86, -1194.18), (-514.76, -1335.42)], "CW89: lane at x = -513, a street", within=5.0, share=0.7, kind="street",
      cls="street", width=14.0)
# The street along y = -890 over the knoll, between the junctions at (-971, -863) and (-1246, -891) (CW53's south
# side; 2026-11-16): traced with a 6 m S-shaped jog at x = -1016..-1033 and a 4 m V-shaped dip at x = -1105..-1130
# (pixel steps of the drawing's white band). With the jog the street had no lane paint for 40 m and its surface
# folded by 0.6 m over the knoll. Redrawn through the same ends as one gentle line. It leaves the junction at
# (-971, -863) westward, at 80 degrees to the street at x = -971 carried south (CW84): first redrawn with the traced
# bend out of the junction, it left it 25 degrees off that street and the junction was a 25 m wedge of asphalt with
# no kerb. CW53 and CW83 are planned again on it.
remove((-1060.0, -886.4), "CW83: street along y = -890 over the knoll, as traced", within=4.0)
add([(-970.83, -862.50), (-990.00, -866.00), (-1020.00, -875.00), (-1050.00, -882.50), (-1104.55, -887.40), (-1130.28, -887.62),
     (-1245.83, -890.83)], "CW83: street along y = -890 over the knoll, without the jog and the dip",
    kind="street", width=14.0, cls="street", snap=4.0, curve=True)
# The Distrito Portuario Leste around the landing of the Ponte do Rio Leste (sectors CE1 to CE5; 2026-11-16).
# The drawing: blocks of about 140 m with small buildings, white streets, the bridge's axis carried east along
# y = -60 to the avenue at x = 3565 (yellow beyond x = 3245), and a yellow U round the block x = 3265..3415. The
# tracing: the bridge ends 5 m short of the junction of the coast street (two junctions), the U a knot of four
# pieces (one 53 m "wide" and a loop through the block), a dead end into the pond block, and the avenue along
# y = -211 wavering by 12 m. Read as: one junction at the bridge's end, the coast street and the axis meeting it;
# the axis a four-lane avenue from the bridge to x = 3565, like the bridge; the U a plain rectangle of streets
# (its top along y = 86, its legs at x = 3265 and x = 3415); the dead end dropped; the avenue along y = -211
# straight.
remove((2834.5, -60.0), "CE1: 5 m link between the bridge's end and the coast street's junction", within=3.0)
remove((2900.0, -61.5), "CE1: axis from the coast street to x = 2979, as traced", within=3.0)
remove((2834.0, -200.0), "CE6: coast street south of the bridge, as traced", within=3.0)
remove((3157.0, -95.0), "CE3: dead end into the pond block", within=7.0)
remove((3216.0, 87.0), "CE3: top of the U block, west part, as traced", within=4.0)
remove((3340.0, 88.0), "CE4: top of the U, as traced", within=4.0)
remove((3346.0, 19.0), "CE4: loop through the U block", within=4.0)
remove((3401.0, 53.0), "CE4: 31 m piece of the U's right leg", within=3.0)
remove((3411.0, -10.0), "CE4: the U's right leg, as traced", within=8.0)
remove((3480.0, 87.0), "CE5: top of the block east of the U, as traced", within=4.0)
remove((3422.0, -199.0), "CE9: avenue along y = -211, wavering", within=6.0)
add([(2832.50, -59.17), (2979.20, -61.98)], "CE1: the bridge's axis from its end to x = 2979", kind="avenue", width=22.0,
    cls="arterial", snap=4.0)
add([(2832.50, -59.17), (2831.00, -361.00)], "CE6: coast street south from the bridge's end", kind="street", width=14.0,
    cls="street", snap=6.0)
add([(3123.39, 86.19), (3265.00, 86.50)], "CE3: street along y = 86 to the U's west leg", kind="street", width=14.0, cls="street",
    snap=4.0)
add([(3265.00, 86.50), (3415.00, 86.20)], "CE4: the U's top", kind="street", width=14.0, cls="street", snap=4.0)
add([(3415.00, 86.20), (3556.47, 85.75)], "CE5: street along y = 86 east of the U", kind="street", width=14.0, cls="street",
    snap=4.0)
add([(3265.00, 86.50), (3269.99, -62.22)], "CE4: the U's west leg", kind="street", width=14.0, cls="street", snap=9.0)
add([(3415.00, 86.20), (3423.09, -60.97)], "CE4: the U's east leg", kind="street", width=14.0, cls="street", snap=4.0)
add([(3293.91, -211.74), (3564.98, -210.83)], "CE9: avenue along y = -211, straight", kind="avenue", width=22.0,
    cls="arterial", snap=9.0)
along([(2979.2, -62.0), (3125.9, -63.1), (3152.2, -63.2), (3270.0, -62.2), (3423.1, -61.0), (3564.8, -59.8)],
      "CE1: the bridge's axis, a four-lane avenue to x = 3565", within=5.0, share=0.7, kind="avenue", cls="arterial", width=22.0)
# The Distrito Portuario Leste south of the bridge's axis (sectors CE6 to CE9; 2026-11-16): the block between the
# coast street and the street at x = 2980 is 285 m long (y = -60 to -359): a cross street along y = -210, where
# the drawing's coast street shows a mouth. The 25 m stub west from (3261, -298) into the block dropped.
add([(2829.40, -210.00), (2980.90, -210.00)], "CE6: cross street along y = -210 in the long block by the coast", kind="street",
    width=14.0, cls="street", snap=6.0)
remove((3249.0, -294.0), "CE8: 25 m stub into the block", within=3.0)
# The Distrito Portuario Leste's south rows (sectors CE10 to CE15; 2026-11-16), from the street along y = -358 to
# the avenue along y = -658. The drawing: a block of 285 x 292 m (x = 2985 to 3270) packed with small houses in a
# grid and no street; the street at x = 2985 traced as a diagonal with a sliver island and a little loop south of
# y = -490; a lens of two streets at (3260, -630). Read as: the street at x = 2985 straight down to the avenue;
# the street along y = -505 carried east across the big block to the street at x = 3279, and a street at x = 3125
# from y = -357 down to the avenue (the line of the street at x = 3125 north of the bridge's axis): four blocks of
# about 140 m; the lens as one corner.
remove((2980.0, -467.0), "CE12: street at x = 2985, south end as traced", within=4.0)
remove((2986.0, -531.0), "CE12: diagonal at x = 2985", within=4.0)
remove((2988.0, -573.0), "CE14: diagonal at x = 2985, south part", within=4.0)
remove((3005.0, -587.0), "CE14: sliver island's lane", within=4.0)
remove((3002.0, -607.0), "CE14: link to the little loop", within=3.0)
remove((2982.0, -624.0), "CE14: street at x = 2985 down to the avenue, as traced", within=3.0)
remove((3022.0, -636.0), "CE14: the little loop's east side", within=3.0)
remove((2922.0, -507.0), "CE10: street along y = -505, west part, as traced", within=4.0)
remove((3284.0, -620.0), "CE15: the lens's east side", within=4.0)
remove((3247.0, -618.0), "CE15: the lens's west side", within=4.0)
add([(2985.10, -358.82), (2981.59, -651.96)], "CE12: street at x = 2985 straight down to the avenue", kind="street", width=14.0,
    cls="street", snap=6.0)
add([(3125.00, -357.00), (3124.17, -660.83)], "CE13: street at x = 3125 through the big block", kind="street", width=14.0,
    cls="street", snap=6.0)
add([(2842.53, -509.17), (2983.80, -507.00)], "CE10: street along y = -505, west part", kind="street", width=14.0, cls="street",
    snap=6.0)
add([(2983.80, -507.00), (3124.80, -506.50)], "CE12: street along y = -505 across the big block, west half", kind="street",
    width=14.0, cls="street", snap=4.0)
add([(3124.80, -506.50), (3279.33, -505.76)], "CE13: street along y = -505 across the big block, east half", kind="street",
    width=14.0, cls="street", snap=6.0)
add([(3275.69, -602.49), (3277.00, -658.00), (3245.83, -657.50)], "CE15: the lens as one corner", kind="street", width=14.0,
    cls="street", snap=6.0)
# The Mirante Leste (sectors CE16 to CE18; 2026-11-16): the hilltop east of the port district, the map's spot
# height +60.8 m at its south-east corner. The drawing: a yellow rectangle of streets on top (x = 3423 to 3565,
# y = -360 to -508) round a paved yard with a small square inside its north-east corner, the summit marker by the
# street's south-east bend; west of it a block of houses on the slope down to the street at x = 3270. The tracing:
# the rectangle's north side wavering 6 m, its west side a crooked line, the little square traced as a street
# that turns round it, and a 7 m stub up to the marker. Read as: the rectangle straight (north side along
# y = -360, west side at x = 3423) and the stub dropped; inside it a lookout park (the yard), the little square
# kept as the lookout's paved terrace.
remove((3452.0, -360.0), "CE17: the rectangle's north side, as traced", within=5.0)
remove((3508.0, -392.0), "CE17: the street round the little square", within=4.0)
remove((3533.0, -491.0), "CE17: stub to the summit marker", within=4.0)
remove((3536.0, -362.0), "CE17: the rectangle's north side, east part, as traced", within=3.0)
add([(3422.51, -508.35), (3423.00, -360.00), (3565.14, -360.39)], "CE17: the rectangle's west and north sides", kind="street",
    width=14.0, cls="street", snap=8.0)
# the rectangle's east and south sides were traced with a 3.5 m jog at y = -420 (where the street round the little
# square used to join): redrawn through the same corners
remove((3567.5, -470.0), "CE17: the rectangle's east and south sides, as traced", within=4.0)
remove((3565.2, -392.0), "CE17: the east side's north part, as traced", within=2.0)
remove((3484.0, -509.2), "CE17: the south side's east part, as traced", within=2.0)
add([(3565.14, -360.39), (3567.00, -440.00), (3567.00, -509.00), (3422.48, -509.77)], "CE17: the rectangle's east and south sides",
    kind="street", width=14.0, cls="street", snap=4.0)
# the straightening pulls the corner of the street at x = 3565 and the rectangle's north side 4 m east (the street
# further south was traced bending east): back on the line of the street at x = 3565
EDITS.append({"op": "move", "at": (3569.49, -360.73), "to": (3565.14, -360.39), "within": 2.0, "when": "after",
              "why": "CE17: corner on the line of the street at x = 3565"})
# The Distrito Portuario Leste's row north of the street along y = 86, east of the street at x = 3121 (sectors CE18
# to CE20; 2026-11-16): in the drawing one block of 430 x 150 m up to the avenue along y = 236, with no street. The
# U's legs (x = 3265, x = 3415) carried north to the avenue: three blocks of about 145 m. The alley along y = 149
# west of x = 3121 (hidden under the district's label in the drawing) and its 47 m stub east of it dropped: the
# street at x = 3121 runs on from y = 86 to the curve at y = 229 with no junction between. (The part west of
# x = 3121, round the east mouth of the Tunel Subaquatico Leste, waits for the tunnels.)
remove((3011.0, 149.0), "CE18: alley along y = 149 west of x = 3121", within=4.0)
remove((3146.0, 149.0), "CE18: alley stub east of x = 3121", within=3.0)
add([(3265.00, 86.50), (3268.45, 235.24)], "CE19: the U's west leg carried north to the avenue", kind="street", width=14.0,
    cls="street", snap=4.0)
add([(3415.00, 86.20), (3416.50, 236.90)], "CE20: the U's east leg carried north to the avenue", kind="street", width=14.0,
    cls="street", snap=10.0)
# The Distrito Portuario Leste between the avenue along y = 236 and the street along y = 532, east of the street at
# x = 3265 (sectors CE21 to CE24; 2026-11-16). The drawing: a yellow street at x = 3405 from y = 532 down to a white
# paved patch at y = 340..410 by the street along y = 386; houses all round. The tracing: x = 3405 ending in a little
# loop round the patch and a link to the street along y = 386. Read as: one street from the junction at (3406, 532)
# straight down to the avenue along y = 236 at x = 3416 (the line of the street through the U), the street along
# y = 386 meeting it; and a cross street along y = 386 east of it to the avenue at x = 3551, so that the blocks east
# of it are not 300 m long.
remove((3420.0, 396.0), "CE24: little loop round the paved patch", within=6.0)
remove((3398.0, 400.0), "CE23: link from the loop to the street along y = 386", within=7.0)
remove((3405.0, 463.0), "CE23: street at x = 3405, as traced", within=4.0)
add([(3405.85, 532.26), (3416.46, 235.78)], "CE23: street at x = 3405..3416 from y = 532 down to the avenue along y = 236",
    kind="street", width=14.0, cls="street", snap=6.0)
add([(3389.79, 386.85), (3411.00, 386.80)], "CE21: street along y = 386 to the street at x = 3411", kind="street", width=14.0,
    cls="street", snap=6.0)
add([(3411.00, 386.80), (3551.30, 386.00)], "CE22: cross street along y = 386 east to the avenue", kind="street", width=14.0,
    cls="street", snap=6.0)
# the new junction on the avenue at x = 3551 comes out 4 m east of the avenue's line: put on it
EDITS.append({"op": "move", "at": (3556.66, 386.08), "to": (3552.45, 386.00), "within": 2.0, "when": "after",
              "why": "CE22: junction on the avenue's line"})
# The Distrito Portuario Leste between the streets along y = 532 and y = 829 (sectors CE25 to CE29; 2026-11-16). The
# tracing: the street along y = 532 dipping 15 m to a junction at (3120, 517) where the street from the tunnel's
# plaza arrives; the yellow street at x = 3397 starting from a little loop round a paved patch at (3410, 680) and
# not reaching y = 532; the street along y = 681 ending 18 m short of it. Read as: the street along y = 532
# straight, the street from the plaza carried on north across it to y = 681 (a block of 290 m in two, the line of
# the street at x = 3121 south of the plaza); the street at x = 3397 straight from the junction at (3406, 532) to
# the one at (3397, 828), the street along y = 681 meeting it, and carried on east to the avenue at x = 3547 (a
# block of 300 m in two). The little loop dropped.
remove((3040.0, 534.0), "CE25: street along y = 532 dipping to (3120, 517), west part", within=4.0)
remove((3201.0, 532.0), "CE26: street along y = 532 dipping to (3120, 517), east part", within=4.0)
remove((3414.0, 659.0), "CE27: little loop round the paved patch", within=4.0)
remove((3390.0, 694.0), "CE27: link from the loop to the street along y = 681", within=7.0)
remove((3397.0, 760.0), "CE29: the yellow street at x = 3397, as traced", within=3.0)
add([(2967.50, 532.50), (3120.00, 531.70)], "CE25: street along y = 532 straight, west part", kind="street", width=14.0,
    cls="street", snap=4.0)
add([(3120.00, 531.70), (3259.77, 530.94)], "CE26: street along y = 532 straight, east part", kind="street", width=14.0,
    cls="street", snap=4.0)
add([(3119.94, 517.45), (3120.00, 531.70)], "CE25: the street from the tunnel's plaza up to the street along y = 532",
    kind="street", width=14.0, cls="street", snap=4.0)
add([(3120.00, 531.70), (3120.50, 681.06)], "CE25: the same street carried on north to y = 681", kind="street", width=14.0,
    cls="street", snap=4.0)
add([(3405.82, 532.26), (3396.67, 828.33)], "CE27: street at x = 3397..3406 from y = 532 to y = 828", kind="street",
    width=14.0, cls="street", snap=6.0)
add([(3383.45, 681.00), (3401.10, 681.00)], "CE27: street along y = 681 to the street at x = 3401", kind="street", width=14.0,
    cls="street", snap=4.0)
add([(3401.10, 681.00), (3547.70, 681.00)], "CE28: street along y = 681 carried east to the avenue", kind="street", width=14.0,
    cls="street", snap=6.0)
# The Distrito Portuario Leste north of the street along y = 681, west of the yellow loop (sectors CE30 to CE32;
# 2026-11-16). The drawing: a dense grid of small houses from y = 690 up to the bay's shore (y = 880..900 west of
# x = 3140) with no street; east of it the yellow loop, whose south side carries on the street along y = 829. Read
# as: the street at x = 3120 and a street at x = 3255 carried north from y = 681 to a waterfront street along
# y = 860, 20 m back from the shore (from the bridge's landing at (2961, 871) east to x = 3255; at y = 870 its north
# half stood over the water by the landing), and the loop's south side carried west to
# the street at x = 3255. Blocks of about 150 m. (North of y = 870 east of the bay, and the loop's own block, later.)
remove((2983.0, 869.0), "CE30: the bridge's little hook east of its landing (the waterfront street takes its place)", within=3.0)
add([(3120.50, 680.62), (3120.60, 860.00)], "CE30: street at x = 3120 carried north to the waterfront street", kind="street",
    width=14.0, cls="street", snap=4.0)
add([(3255.38, 680.65), (3255.50, 836.00)], "CE31: street at x = 3255 north to the loop's south side", kind="street",
    width=14.0, cls="street", snap=4.0)
add([(3255.50, 836.00), (3255.50, 860.00)], "CE31: street at x = 3255 north to the waterfront street", kind="street",
    width=14.0, cls="street", snap=4.0)
add([(2960.83, 870.83), (2992.00, 860.00), (3120.60, 860.00)], "CE30: waterfront street along y = 860, west part", kind="street", width=14.0,
    cls="street", snap=4.0)
add([(3120.60, 860.00), (3255.50, 860.00)], "CE31: waterfront street along y = 860, east part", kind="street", width=14.0,
    cls="street", snap=4.0)
add([(3255.50, 836.00), (3292.00, 837.00)], "CE32: the loop's south side carried west to x = 3255", kind="street", width=14.0,
    cls="street", snap=6.0)
# The yellow loop of the Distrito Portuario Leste and the block east of it (sectors CE34, CE35; 2026-11-16): the
# drawing's loop is a D-shaped ring street round a block of houses, its south side carrying on the street along
# y = 829; east of it houses up to the avenue at x = 3545, with no street for 150 m. A street along y = 976 from the
# avenue's junction at (3547, 976) (where the street to the east starts) west to the loop's east side.
add([(3546.51, 975.94), (3395.00, 976.00)], "CE35: street along y = 976 from the avenue to the loop", kind="street",
    width=14.0, cls="street", snap=6.0)
along([(3396.7, 828.3), (3307.0, 834.0), (3292.6, 835.3), (3269.0, 875.0), (3266.0, 928.0), (3291.0, 963.0), (3343.0, 973.0),
       (3393.4, 972.5), (3395.0, 912.0), (3396.0, 851.0), (3396.7, 828.3)],
      "CE34: the loop, a street like the rest (it serves its own block only)", within=5.0, share=0.7, kind="street", cls="street",
      width=14.0)
# The U of houses north of the yellow loop (sectors CE36 to CE39; 2026-11-16): from the waterfront street and the
# loop up to y = 1160 (open hills beyond), between the bay's shore (x = 3135) and the street along y = 976. The
# drawing: houses in a U (a column along the shore, a row along the north edge, a column at x = 3430..3490) round a
# green middle, and no street. Read as: a street at x = 3175 from the waterfront street north to y = 1100, a street
# along y = 1100 east to x = 3470, and streets at x = 3330 (from the loop's top) and x = 3470 (from the street along
# y = 976) up to it. The green middle stays green: a lawn inside the block west of x = 3330.
add([(3175.00, 860.00), (3175.00, 1100.00)], "CE37: street at x = 3175 from the waterfront street north", kind="street",
    width=14.0, cls="street", snap=4.0)
add([(3175.00, 1100.00), (3330.00, 1100.00)], "CE37: street along y = 1100, west part", kind="street", width=14.0, cls="street",
    snap=4.0)
add([(3330.00, 1100.00), (3470.00, 1100.00)], "CE38: street along y = 1100, east part", kind="street", width=14.0, cls="street",
    snap=4.0)
add([(3330.00, 972.30), (3330.00, 1100.00)], "CE37: street at x = 3330 from the loop's top", kind="street", width=14.0,
    cls="street", snap=6.0)
add([(3470.00, 974.30), (3470.00, 1100.00)], "CE38: street at x = 3470 from the street along y = 976", kind="street",
    width=14.0, cls="street", snap=6.0)
# The Aeroporto Leste district (sectors CA1 to CA15; 2026-11-16): a grid of yellow avenues (x = 3815, 3960, 4110 and
# y = 973, 1413, 1700) with blocks of 145 x 440 m and 145 x 290 m, warehouses and houses scattered in them, and west
# of the avenue at x = 3815 a long double row of buildings (x = 3650..3720) down to the street along y = 973. Read as:
# cross streets along y = 1192 and y = 1560 through every column; a street at x = 3740 from the street along y = 973
# north to the avenue that comes down from the north-west, with the cross streets (and the avenue along y = 1413)
# carried west to it; the double row faces it. The little loop south of the street along y = 973 and the 43 m stub
# south of (3684, 974) dropped.
remove((3745.0, 946.0), "CA1: little loop south of the street along y = 973", within=4.0)
remove((3685.0, 950.0), "CA1: stub south of (3684, 974)", within=3.0)
add([(3740.00, 974.10), (3740.00, 1192.00)], "CA1: street at x = 3740, south part", kind="street", width=14.0, cls="street", snap=6.0)
add([(3740.00, 1192.00), (3740.00, 1414.00)], "CA2: street at x = 3740, second part", kind="street", width=14.0, cls="street", snap=4.0)
add([(3740.00, 1414.00), (3740.00, 1560.00)], "CA3: street at x = 3740, third part", kind="street", width=14.0, cls="street", snap=4.0)
add([(3740.00, 1560.00), (3740.00, 1714.00)], "CA4: street at x = 3740 up to the avenue from the north-west", kind="street",
    width=14.0, cls="street", snap=8.0)
add([(3740.00, 1192.00), (3822.20, 1192.00)], "CA1: cross street along y = 1192, west part", kind="street", width=14.0, cls="street",
    snap=6.0)
add([(3822.20, 1192.00), (3967.10, 1192.00)], "CA5: cross street along y = 1192, middle part", kind="street", width=14.0,
    cls="street", snap=6.0)
add([(3967.10, 1192.00), (4112.30, 1190.00)], "CA6: cross street along y = 1192, east part", kind="street", width=14.0,
    cls="street", snap=6.0)
add([(3740.00, 1414.00), (3814.64, 1414.16)], "CA2: the avenue along y = 1413 carried west as a street", kind="street",
    width=14.0, cls="street", snap=4.0)
add([(3740.00, 1560.00), (3810.40, 1560.00)], "CA3: cross street along y = 1560, west part", kind="street", width=14.0, cls="street",
    snap=6.0)
add([(3810.40, 1560.00), (3954.30, 1560.00)], "CA9: cross street along y = 1560, middle part", kind="street", width=14.0,
    cls="street", snap=6.0)
add([(3954.30, 1560.00), (4099.00, 1560.00)], "CA10: cross street along y = 1560, east part", kind="street", width=14.0,
    cls="street", snap=8.0)
# the avenue from the north-west down to (3740, 1710) was traced as a staircase of 5 m steps (x = 3600..3690): redrawn
# as the smooth curve it is, through the same ends
remove((3632.5, 1757.5), "CA4: the avenue from the north-west, as traced", within=3.0)
add([(3424.33, 1855.77), (3481.00, 1852.00), (3530.00, 1834.00), (3580.00, 1803.00), (3625.00, 1765.00), (3665.00, 1735.00),
     (3700.00, 1718.50), (3739.81, 1709.67)], "CA4: the avenue from the north-west, smooth", kind="avenue", width=20.0,
    cls="arterial", snap=4.0, curve=True)
# (the street along y = 975 east of the avenue at x = 3547, joined into one road with its 60 m of avenue past the stub
# dropped above, keeps the street's width and class it was built with in CE41)
along([(3546.51, 975.94), (3640.00, 975.00), (3737.86, 974.41)], "CA13: street along y = 975 east of x = 3547 stays a street",
      within=4.0, share=0.7, kind="street", cls="street", width=16.7)
# The houses north of the Aeroporto Leste's avenue (sectors CA16, CA17; 2026-11-16): north of the avenue from the
# north-west, between x = 3640 and x = 3990, the drawing has a dense block of small houses (y = 1730 to 1900) in two
# halves either side of a gap at x = 3785, and no street. Read as: a street along y = 1900 on its north edge from
# x = 3640 to x = 3932, and streets at x = 3640, x = 3785 and x = 3932 from the avenue up to it (x = 3932 meets the avenue
# at the junction that is already there: a junction further east would split the avenue's round north-east corner).
add([(3640.00, 1748.00), (3640.00, 1900.00)], "CA16: street at x = 3640 from the avenue north", kind="street", width=14.0,
    cls="street", snap=10.0)
add([(3640.00, 1900.00), (3785.00, 1900.00)], "CA16: street along y = 1900, west part", kind="street", width=14.0, cls="street",
    snap=4.0)
add([(3785.00, 1900.00), (3932.05, 1900.00)], "CA17: street along y = 1900, east part", kind="street", width=14.0, cls="street",
    snap=4.0)
add([(3785.00, 1706.50), (3785.00, 1900.00)], "CA16: street at x = 3785 from the avenue north", kind="street", width=14.0,
    cls="street", snap=8.0)
add([(3932.05, 1697.94), (3932.05, 1900.00)], "CA17: street at x = 3932 from the avenue north", kind="street", width=14.0,
    cls="street", snap=12.0)
# The freeway's north loop south of the houses of CW66-CW71 (sectors CB1, CB2; 2026-11-16): north of the freeway
# between x = 266 and x = 793 the drawing has a loop road off it (traced wavering by up to 8 m), houses inside it and
# a scatter of houses outside. Redrawn as the smooth curve it is; a street (it serves the houses only), meeting the
# freeway at both ends as traced.
remove((532.0, -1248.0), "CB1: the freeway's north loop, as traced", within=5.0)
remove((321.0, -1299.0), "CB1: the loop's west end, a second traced line beside it", within=4.0)
remove((358.0, -1285.0), "CB1: the rest of that second line", within=4.0)
remove((351.0, -1258.0), "CB1: a hook of the traced loop north of it", within=3.0)
add([(265.84, -1397.50), (300.00, -1352.00), (335.00, -1310.00), (380.00, -1278.00), (440.00, -1258.00), (520.00, -1250.00),
     (600.00, -1251.00), (665.00, -1258.00), (710.00, -1282.00), (745.00, -1325.00), (775.00, -1365.00), (792.53, -1388.66)],
    "CB1: the freeway's north loop, smooth", kind="street", width=14.0, cls="street", snap=6.0, curve=True)
# The Peninsula Noroeste's land part (sectors PN1 to PN4; 2026-11-16): north of its piers, between the pier loop
# (x = -2118) and the avenue at x = -1596. The drawing: one main road along y = 1748 (orange west of x = -1880, read
# as a surface street like the other orange on land; yellow east of it), a row of houses north of it below the
# hill, and south of it three land blocks down to the water (y = 1600), split by a street at x = -1880 (that goes on
# south as the comb pier) and by a paved strip at x = -1745 (that goes on south as a pier). The tracing: the main road
# in four pieces with a jog down to y = 1724 and an 80 m wide "street" (the paved strip's edge), an alley through the
# row of houses, short "freeway" pieces on the streets at x = -1880, two alleys and a link round the west end. Read
# as: the main road straight from the pier loop's corner (-2054, 1751) to the avenue (-1596, 1763), an avenue; the
# streets at x = -1880 and x = -1745 from it down to the piers' roots. (The piers, the pier loop and the bridge
# interchange south of it wait: they are structures.)
for at, why, within in [((-2024.0, 1752.0), "PN2: main road, west part, as traced", 3.0),
                         ((-1934.0, 1754.0), "PN2: main road jogging down to y = 1724", 3.0),
                         ((-1842.0, 1725.0), "PN3: 80 m wide strip edge traced as a street", 4.0),
                         ((-1773.0, 1752.0), "PN3: main road, middle part, as traced", 3.0),
                         ((-1672.0, 1760.0), "PN4: main road, east part, as traced", 3.0),
                         ((-2028.0, 1730.0), "PN2: alley south of the main road", 3.0),
                         ((-2083.0, 1738.0), "PN2: alley to the pier loop's corner", 8.0),
                         ((-2055.0, 1741.0), "PN2: link at the pier loop's corner", 2.0),
                         ((-1888.0, 1714.0), "PN3: street at x = -1880 traced as freeway, north piece", 3.0),
                         ((-1884.0, 1661.0), "PN3: street at x = -1880 traced as freeway", 3.0),
                         ((-1923.0, 1691.0), "PN2: stub into block A", 3.0),
                         ((-1741.0, 1720.0), "PN4: alley at x = -1741", 3.0),
                         ((-1732.0, 1822.0), "PN1: alley through the row of houses", 3.0)]:
    remove(at, why, within=within)
add([(-2054.17, 1750.83), (-1880.00, 1749.00), (-1745.00, 1756.50), (-1596.11, 1762.87)], "PN1: the peninsula's main road",
    kind="avenue", width=20.0, cls="arterial", snap=6.0)
add([(-1880.00, 1749.00), (-1882.50, 1597.50)], "PN2: street at x = -1880 down to the comb pier", kind="street", width=14.0,
    cls="street", snap=6.0)
add([(-1745.00, 1756.50), (-1741.36, 1674.61)], "PN3: street at x = -1745 down to the pier", kind="street", width=14.0,
    cls="street", snap=6.0)
remove((-1774.0, 1705.0), "PN3: diagonal across the paved strip", within=3.0)
# The piers south of it (the loop round the basin, the comb pier at x = -1876, the pier at x = -1741 and its link west)
# were traced as bridges and a freeway: read as streets on the quays, as the north waterfront's pier (CW24). As
# bridges their decks rose to 23 m and pulled the main road up to 12.6 m at its west end.
along([(-2118.4, 1744.7), (-2256.0, 1738.0), (-2263.0, 1607.0), (-2261.0, 1467.0), (-2092.0, 1459.0), (-2023.0, 1458.0),
       (-1971.0, 1456.0), (-1918.0, 1452.0), (-1872.5, 1450.8)], "PN: the pier loop round the basin, a street on the quay",
      within=8.0, share=0.6, kind="street", cls="street", width=14.0, level=0)
along([(-1882.5, 1597.5), (-1877.5, 1569.2), (-1875.8, 1532.5), (-1872.5, 1450.8)], "PN: the comb pier, a street",
      within=6.0, share=0.6, kind="street", cls="street", width=14.0, level=0)
along([(-1741.7, 1674.9), (-1736.0, 1631.0), (-1736.0, 1578.0), (-1731.0, 1528.0), (-1729.2, 1467.5)], "PN: the pier at x = -1741, a street",
      within=6.0, share=0.6, kind="street", cls="street", width=14.0, level=0)
along([(-1729.2, 1467.5), (-1757.0, 1440.0), (-1799.0, 1429.0), (-1841.0, 1434.0), (-1872.5, 1450.8)], "PN: the quay road west of it, a street",
      within=6.0, share=0.6, kind="street", cls="street", width=14.0, level=0)
along([(-2054.2, 1750.8), (-2117.0, 1750.0), (-2165.0, 1729.0), (-2213.0, 1742.0), (-2269.0, 1738.0), (-2283.0, 1685.0), (-2269.0, 1632.0),
       (-2262.0, 1579.0), (-2277.0, 1533.0), (-2270.0, 1476.0), (-2217.0, 1459.0), (-2154.0, 1459.0), (-2075.8, 1459.2)],
      "PN: the pier loop round the basin, a street on the quay (its traced line)", within=8.0, share=0.6, kind="street", cls="street",
      width=14.0, level=0)
along([(-2075.8, 1562.5), (-2076.0, 1499.0), (-2075.8, 1459.2)], "PN: the Y pier's stem, a street", within=6.0, share=0.6,
      kind="street", cls="street", width=14.0, level=0)
# The Peninsula Noroeste's piers (sectors PP1 to PP3; 2026-11-16). The user's answer: the piers are fill, with quay
# streets and sea walls, as the boulevard's pier (CW24). The pier loop round the west basin was traced wandering by
# up to 20 m (x = -2263..-2284): redrawn along the drawing's road, the north side along y = 1752, the west leg at
# x = -2284, the south side along y = 1462 to the Y pier's foot. The comb pier's teeth (traced as 22 m stubs) are
# part of the fill, not streets. Every pier street is held at quay level (4.5 m, as the land behind).
remove((-2283.0, 1692.0), "PP1: the pier loop, as traced", within=6.0)
remove((-1898.0, 1568.0), "PP2: a tooth of the comb pier traced as a street", within=3.0)
remove((-1896.0, 1532.0), "PP2: a tooth of the comb pier traced as a street", within=3.0)
remove((-1899.0, 1605.0), "PP2: a tooth of the comb pier traced as a street", within=3.0)
add([(-2105.77, 1749.84), (-2284.00, 1752.00), (-2284.00, 1462.00), (-2075.83, 1459.17)], "PP1: the pier loop round the west basin",
    kind="street", width=14.0, cls="street", snap=6.0, quay=4.5)
for pts, why in [([(-2075.8, 1459.2), (-2076.0, 1499.0), (-2075.8, 1562.5)], "PP2: the Y pier's stem"),
                 ([(-2075.8, 1562.5), (-2086.0, 1571.0), (-2099.2, 1612.5)], "PP2: the Y pier's north-west arm"),
                 ([(-2075.8, 1562.5), (-2049.2, 1570.8)], "PP2: the Y pier's north-east arm"),
                 ([(-2075.8, 1459.2), (-1971.0, 1456.0), (-1872.5, 1450.8)], "PP2: the south quay"),
                 ([(-1882.5, 1597.5), (-1877.5, 1569.2), (-1875.8, 1532.5), (-1872.5, 1450.8)], "PP2: the comb pier"),
                 ([(-1872.5, 1450.8), (-1841.0, 1434.0), (-1799.0, 1429.0), (-1757.0, 1440.0), (-1729.2, 1467.5)], "PP3: the south quay, east part"),
                 ([(-1740.8, 1675.8), (-1735.8, 1641.0), (-1735.8, 1582.0), (-1731.0, 1528.0), (-1729.2, 1467.5)], "PP3: the pier at x = -1741")]:
    along(pts, why + ": at quay level", within=5.0, share=0.6, quay=4.5)
along([(-1962.5, 1539.2), (-1985.0, 1540.0), (-2008.0, 1541.0), (-2038.0, 1569.0)], "PP2: the lane to the paved apron: at quay level",
      within=5.0, share=0.6, quay=4.5)
# The Tunel em S under the Centro Oeste and the blocks over it (sectors CW94 to CW98; 2026-11-16). The user's answer:
# every dashed stretch is a real tunnel. The drawing: a tunnel in an S from the street along y = -133 (at x = -821)
# to the street along y = -437 (at x = -672), under a block of 385 x 300 m that runs east to the diagonal avenue,
# packed with houses and no street. The tracing: the tunnel starting 6 m off the street junction, and at its south
# end a little loop and a lane. Read as: one tunnel from the junction (-821.5, -133.0) to the junction
# (-672.2, -437.3), 7 m deep with 8 % ramps (as the Tunel da Orla Leste); the block cut by a street at x = -875, a
# cross street along y = -240 from it to the avenue (it crosses the tunnel's north leg 110 m from the mouth, where the tunnel
# is covered: at y = -215 it would have crossed the open ramp), the street at x = -672 carried on south from y = -128 to it, and a street at x = -760 from it down to
# the street along y = -432 (over the tunnel's deepest part).
remove((-801.0, -246.0), "CW95: the S tunnel, as traced", within=4.0)
remove((-665.0, -399.0), "CW98: the tunnel's south loop", within=3.0)
remove((-679.0, -408.0), "CW98: lane beside the tunnel's south mouth", within=7.0)
remove((-814.0, -156.0), "CW95: a piece of the traced tunnel beside the new one", within=4.0)
remove((-829.0, -152.0), "CW95: a lane traced in the tunnel's north ramp", within=3.0)
add([(-821.50, -133.00), (-820.50, -160.00), (-818.00, -195.00), (-806.00, -243.00), (-778.00, -274.00), (-725.00, -286.00),
     (-692.00, -300.00), (-677.00, -335.00), (-672.50, -380.00), (-672.22, -437.34)], "CW95: Tunel em S", kind="tunnel", width=17.5,
    cls="tunnel", name="Tunel em S", depth=7.0, grade=0.08, curve=True, snap=6.0)
# the street along y = -432 between (-951, -432) and the tunnel's south mouth, as it was built (CW47): two straight
# pieces meeting at (-687, -428). Left to the straightening, with the lane at its corner gone, it came out as one
# straight line 4.6 m off where CW47 was built
remove((-800.0, -424.0), "CW47: street along y = -432, as traced", within=4.0)
remove((-682.0, -431.0), "CW47: its last piece to the mouth, as traced", within=3.0)
add([(-950.93, -432.31), (-940.00, -432.15)], "CW47: street along y = -432 as built, from the junction", kind="street", width=26.7,
    cls="street", snap=6.0)
add([(-940.00, -432.15), (-687.06, -428.43)], "CW47: street along y = -432 as built", kind="street", width=26.7, cls="street", snap=0.5)
add([(-687.06, -428.43), (-672.22, -437.34)], "CW47: its last piece to the tunnel's south mouth as built", kind="street", width=26.7,
    cls="street", snap=8.0)
add([(-875.00, -133.70), (-875.00, -431.70)], "CW94: street at x = -875 through the block", kind="street", width=14.0, cls="street",
    snap=6.0)
add([(-875.00, -240.00), (-760.00, -240.00)], "CW95: cross street along y = -240, west part", kind="street", width=14.0,
    cls="street", snap=4.0)
add([(-760.00, -240.00), (-672.00, -240.00)], "CW95: cross street along y = -240, middle part", kind="street", width=14.0,
    cls="street", snap=4.0)
add([(-672.00, -240.00), (-555.50, -240.00)], "CW96: cross street along y = -240 to the diagonal avenue", kind="street",
    width=14.0, cls="street", snap=8.0)
add([(-671.65, -127.84), (-672.00, -240.00)], "CW96: street at x = -672 carried south to y = -240", kind="street", width=14.0,
    cls="street", snap=6.0)
add([(-760.00, -240.00), (-760.00, -430.20)], "CW97: street at x = -760 down to the street along y = -432", kind="street",
    width=14.0, cls="street", snap=6.0)
add([(-672.22, -437.34), (-507.00, -430.00)], "CW99: street along y = -433 from the tunnel's south mouth east to the avenue", kind="street",
    width=14.0, cls="street", snap=6.0)
# The tunnel at x = -665 south of the Centro Oeste (sectors CW100 to CW103; 2026-11-16). The user's answer: every
# dashed stretch is a real tunnel. The drawing: a tunnel from the end of the street at x = -665 (where the diagonal
# from x = -517 meets it) south under green land with scattered houses to the Trevo Rodoviario Sul, whose two legs
# start at its south mouth. Read as one tunnel of 388 m with a designed profile (7 m deep, 8 % ramps), named
# "Tunel do Trevo Sul". Its north mouth is a frozen junction at 0.6 m (CW61 and CW85 were built down to it), 2 m below the
# road floor the profile is measured from (2.6 m), so it is designed 9 m deep to get 6 m of headroom and cover. The
# land over it gets streets: the street at x = -818 carried on south from the corner of the street along y = -1140 to
# a cross street along y = -1260 (over the tunnel's covered middle) that runs east to the street at x = -513; streets
# at x = -740 (from the street along y = -1020) and x = -600 (from the diagonal) down to it.
remove((-664.7, -1212.6), "CW101: the tunnel at x = -665, as traced", within=4.0)
remove((-661.2, -1122.5), "CW101: a north piece of the traced tunnel", within=4.0)
remove((-660.8, -1383.8), "CW101: a south piece of the traced tunnel", within=4.0)
clear([(-685.0, -1078.0), (-645.0, -1078.0), (-645.0, -1455.0), (-685.0, -1455.0)], "CW101: the rest of the traced tunnel's pieces", share=0.5)
add([(-662.37, -1070.88), (-664.00, -1150.00), (-665.00, -1300.00), (-665.83, -1459.17)], "CW101: Tunel do Trevo Sul", kind="tunnel",
    width=17.5, cls="tunnel", name="Tunel do Trevo Sul", depth=9.0, grade=0.08, snap=4.0)
add([(-818.00, -1140.00), (-818.00, -1260.00)], "CW100: street at x = -818 carried south to y = -1260", kind="street", width=14.0,
    cls="street", snap=4.0)
add([(-818.00, -1260.00), (-740.00, -1260.00)], "CW100: cross street along y = -1260, west part", kind="street", width=14.0,
    cls="street", snap=4.0)
add([(-740.00, -1260.00), (-600.00, -1260.00)], "CW101: cross street along y = -1260 over the tunnel", kind="street", width=14.0,
    cls="street", snap=4.0)
add([(-600.00, -1260.00), (-513.70, -1260.00)], "CW102: cross street along y = -1260, east part", kind="street", width=14.0,
    cls="street", snap=6.0)
add([(-740.00, -1020.00), (-740.00, -1260.00)], "CW100: street at x = -740 from the street along y = -1020", kind="street",
    width=14.0, cls="street", snap=4.0)
add([(-600.00, -1040.30), (-600.00, -1260.00)], "CW102: street at x = -600 from the diagonal", kind="street", width=14.0,
    cls="street", snap=6.0)
# The Tunel Expresso Central valley between the Centro Oeste and downtown (sectors CW104 to CW106; 2026-11-16). The
# user's answer: every dashed stretch is a real tunnel, underground crossings too. The drawing: the Tunel Expresso
# Central straight from the Centro Oeste (x = 389) to downtown (x = 1299) along y = -90, 12.7 m below the sea at its
# lowest; a second tunnel (light blue band) from the plaza at (1004, 72) south-west to the valley floor at (814, 0),
# then down the valley to y = -680 and east to the junction at (1090, -683) by CS6, crossing over the first; a short
# spur from (814, 0) up to (782, 84); the valley itself a park with scattered buildings, rows of houses in the east.
# The tracing: both tunnels in pieces with stubs, the banks of the second traced as alleys, loops at the mouths.
# Read as: the Tunel Expresso Central one tunnel of 910 m, 16.5 m deep (floor about -13 m), four lanes; the "Tunel do
# Vale" one tunnel of about 1300 m from the plaza to the junction by CS6, 7 m deep, passing over the first (3.5 m of
# ground between them); the spur dropped (it would make an underground junction to lead to a dead end at the valley
# top). Over them: a street along y = -250 across the valley from the Centro Oeste (347, -250) to downtown
# (1375, -225), and a street at x = 1050 from it north to the plaza's south street.
clear([(720.0, 100.0), (840.0, 100.0), (840.0, -705.0), (720.0, -705.0)], "CW104: the second tunnel and its banks along the valley, as traced", share=0.5)
clear([(825.0, -660.0), (1088.0, -660.0), (1088.0, -705.0), (825.0, -705.0)], "CW106: the second tunnel's south run, as traced", share=0.5)
clear([(800.0, 40.0), (1000.0, 40.0), (1000.0, 105.0), (800.0, 105.0)], "CW104: the second tunnel's north-east branch and the plaza's north loop, as traced", share=0.5)
clear([(392.0, -110.0), (1301.0, -110.0), (1301.0, -60.0), (392.0, -60.0)], "CW104: the Tunel Expresso Central and the loops at its mouths, as traced", share=0.5)
remove((1330.0, -69.0), "CW105: alley beside the Tunel Expresso Central's east mouth", within=4.0)
add([(389.15, -95.17), (1299.23, -83.32)], "CW104: Tunel Expresso Central", kind="tunnel", width=17.5, cls="tunnel",
    name="Tunel Expresso Central", depth=16.5, grade=0.08, snap=4.0)
add([(1004.17, 72.50), (990.00, 64.00), (950.00, 63.00), (898.00, 63.00), (860.00, 57.00), (835.00, 40.00), (818.00, 12.00),
     (809.00, -25.00), (796.00, -60.00), (790.00, -95.00), (788.00, -125.00), (778.00, -150.00), (782.00, -185.00), (772.00, -235.00),
     (758.00, -285.00), (745.00, -330.00), (734.00, -385.00), (740.00, -440.00), (757.00, -495.00), (774.00, -530.00), (793.00, -565.00),
     (810.00, -600.00), (813.00, -645.00), (830.00, -677.00), (870.00, -683.00), (1000.00, -683.00), (1090.13, -682.52)],
    "CW104: Tunel do Vale", kind="tunnel", width=17.5, cls="tunnel", name="Tunel do Vale", depth=7.0, grade=0.08, snap=4.0, curve=True)
add([(347.63, -250.00), (1374.84, -224.88)], "CW106: street along y = -250 across the valley", kind="street", width=14.0, cls="street",
    snap=4.0)
add([(1050.00, -232.84), (1045.00, 58.50)], "CW105: street at x = 1050 from it north to the plaza's south street", kind="street",
    width=14.0, cls="street", snap=4.0)
# the Tunel Expresso Central's east approach: downtown's main avenue carried on straight from its junction with the
# street at x = 1378 (1379.6, -74.3) to the tunnel's east mouth (the tracing had a street, a 7 m tunnel stub and a
# second junction for those 80 m); the plaza's alley parallel to its south street dropped
remove((1369.0, -79.0), "CW105: tunnel stub east of the Tunel Expresso Central's mouth", within=3.0)
remove((1330.0, -81.0), "CW105: street from the stub to the mouth", within=3.0)
remove((1032.0, 79.0), "CW104: the plaza's alley beside its south street", within=3.0)
add([(1379.61, -74.25), (1299.19, -82.80)], "CW105: downtown's main avenue to the Tunel Expresso Central's east mouth", kind="avenue",
    width=26.7, cls="arterial", snap=10.0)
# ...with the stub and its junction at (1375.5, -87.1) gone, the street that runs south from the avenue (x = 1375, the west
# side of CC4 and CC9) took its traced line again, up to 8 m west of where it was built: put back as built, two straight
# pieces meeting at (1375.52, -87.06)
remove((1368.3, -118.2), "CW105: street at x = 1375, as traced", within=4.0)
remove((1382.5, -78.3), "CW105: its first 8 m from the avenue, as traced", within=3.0)
add([(1379.61, -74.25), (1375.52, -87.06), (1374.84, -224.88)], "CW105: street at x = 1375 as built", kind="street", width=14.4,
    cls="street", snap=10.0, when="after")
# The Tunel Subaquatico Leste (2026-11-16): the drawing has it from the end of the waterfront avenue on the west bank
# (x = 2243, CC14) under the Rio Leste, 12.1 m below the sea, to a portal at (2915, 395) on the east bank, where it
# meets the big curved street of the port. The tracing stopped it 20 m short of the east quay, inside the river, and
# went on with a 48 m tunnel stub and a loop of street round the mouth. Read as one tunnel from junction to junction,
# 21 m below the line between its mouths (floor about -18 m: the river bed is 12 m deep in the middle and the roof
# needs a metre of it), with ramps of 12 %: the east portal is only 100 m from the quay, and at 8 % the roof would
# come out of the river there. Its stretch under the water is buried in the river bed (structures.py "under_water").
clear([(2785.0, 360.0), (2916.0, 360.0), (2916.0, 420.0), (2785.0, 420.0)], "TSL: the tunnel stub and the loop round its east mouth, as traced", share=0.5)
remove((2600.0, 382.5), "TSL: the tunnel as traced, ending in the river", within=4.0)
add([(2243.30, 333.50), (2263.10, 334.50), (2307.70, 350.30), (2351.90, 363.10), (2389.20, 372.50), (2433.40, 378.20),
     (2476.90, 381.00), (2521.50, 382.50), (2615.70, 382.50), (2710.00, 382.50), (2804.20, 382.50), (2860.00, 388.00),
     (2924.20, 394.20)], "TSL: Tunel Subaquatico Leste", kind="tunnel", width=17.5, cls="tunnel", name="Tunel Subaquatico Leste",
    depth=21.0, grade=0.12, snap=8.0, curve=True)
# The east bank of the Rio Leste between the bridge's head (CE1) and the bay (sectors EP1, EP2; 2026-11-16): the drawing
# has a band of houses 100 to 130 m deep along the river, between the quay and the port's streets (x = 2954 to 2973),
# with no street in it. Read as: a street along the river south of the tunnel (x = 2850, both ends closed) joined to the
# big curved street at y = 300; north of the tunnel a street at x = 2880 (the quay is 30 m further east there) from a
# cross street at y = 470 up to y = 790, joined to the port's grid at y = 680.6. The street south of the tunnel stops
# short of it; nothing crosses the open ramp.
add([(2850.00, 340.00), (2850.00, 110.00)], "EP2: street along the river south of the Tunel Subaquatico", kind="street", width=14.0,
    cls="street", snap=4.0)
add([(2973.70, 300.00), (2850.00, 300.00)], "EP2: cross street at y = 300 from the curved street to the river", kind="street",
    width=14.0, cls="street", snap=4.0)
add([(2954.20, 470.00), (2880.00, 470.00), (2880.00, 790.00)], "EP1: cross street at y = 470 and the street along the river north of the tunnel",
    kind="street", width=14.0, cls="street", snap=4.0)
add([(2965.90, 680.60), (2880.00, 680.60)], "EP1: cross street at y = 680.6 from the port's grid to the river", kind="street", width=14.0,
    cls="street", snap=6.0)
# The south highway's turn north beside the Rio Leste (sector FW5, 2026-11-16): the tracing had it leave its straight
# line for an arterial dog-leg round a point at (2271, -1161), with a loop of street either side (the edges of the
# drawn band) and an 37 m stub to the west. Read as the highway straight on from (2256, -1174) to (2260, -1108); loops,
# dog-leg and stub dropped.
remove((2193.0, -1140.0), "FW5: the loop west of the highway, as traced", within=6.0)
remove((2266.0, -1135.0), "FW5: the dog-leg's north arm", within=4.0)
remove((2263.0, -1168.0), "FW5: the dog-leg's south arm", within=4.0)
remove((2300.0, -1222.0), "FW5: the loop east of the highway, as traced", within=8.0)
remove((2232.0, -1200.0), "FW5: the stub west of the junction", within=4.0)
add([(2255.60, -1174.40), (2260.00, -1107.50)], "FW5: the highway straight on to the north", kind="avenue", width=50.0,
    cls="freeway", snap=6.0)
# The expressway's crossing of the Rio Leste south of the port (2026-11-16): the drawing has one elevated road (orange)
# from the south-east corner of the Centro Sul (CS27's quay, (2281, -811)) east over the river to x = 2410, south to
# y = -960 and east again to the east bank at (2698, -958), with a platform and a square drawn on it. The tracing
# had it in five pieces, a stub to the platform and two parallel pieces round the square. Read as one bridge: its
# first piece as traced (CS12 and CS27 are built along it), then a smooth curve through the drawn corners to the east
# bank (structures.STRUCTURES "PVE" takes the two pieces as one deck).
remove((2417.0, -780.0), "PVE: the stub to the platform, as traced", within=3.0)
remove((2436.0, -926.0), "PVE: one piece round the square, as traced", within=3.0)
remove((2427.0, -959.0), "PVE: the other piece round the square, as traced", within=3.0)
remove((2404.0, -880.0), "PVE: the run south, as traced", within=3.0)
remove((2580.0, -958.0), "PVE: the east run, as traced", within=3.0)
add([(2385.80, -799.20), (2404.00, -810.00), (2410.00, -840.00), (2410.00, -900.00), (2414.00, -940.00), (2432.00, -956.00),
     (2462.00, -958.00), (2550.00, -958.00), (2640.00, -958.00), (2697.50, -957.50)],
    "PVE: Ponte da Via Expressa, south and east over the Rio Leste", kind="bridge", width=23.3, cls="bridge",
    name="Ponte da Via Expressa", snap=4.0, curve=True)
# the rows of houses the drawing has in the valley's south-east corner, between the Tunel do Vale's south run and the
# paved yard of the loop street, had no street: a street along y = -610 from the street at x = 1088 (CS6's west
# side) west to a turning circle at x = 905
add([(1087.59, -610.00), (905.00, -610.00)], "CW107: street along y = -610 into the houses of the valley's south-east corner",
    kind="street", width=14.0, cls="street", snap=4.0)
# (the new junction comes out 1.3 m west of the built street's line, where the tracing had it: put back on the line)
EDITS.append({"op": "move", "at": (1086.30, -609.90), "to": (1087.59, -610.00), "within": 2.0, "when": "after",
              "why": "CW107: the junction of the street along y = -610 on the line of the built street at x = 1088"})
# The Mirante's south side and the road along y = -810 east of the Rio Leste (sector SE1, 2026-11-16): the drawing has a
# grid of small houses on the Mirante's south-west flank (x = 3290..3525, y = -560..-745) with no street through it,
# houses along both sides of the road, a 33 m arterial stub south of the road at x = 3800 ending in a paved yard, and a
# lay-by loop of alley 25 m south of the road between x = 3873 and x = 3952 (two junctions 80 m apart on the road).
# Read as: a street at x = 3422.5 continuing the west side of the Mirante's park (CE17) south down to the road, and a
# cross street at y = -602 from the east street of the port's last row (CE15) to it; stub and loop dropped (the houses
# there face the road). The base ground under the drawn houses reads the lowest land level (4 m) in the middle of a
# 20-50 m hillside, so the two new streets are graded evenly between their junctions (hold=0.01), not to that ground.
remove((3800.0, -829.4), "SE: the arterial stub south of the road at x = 3800", within=6.0)
remove((3910.0, -835.0), "SE: the lay-by loop of alley south of the road", within=8.0)
add([(3422.48, -509.77), (3422.50, -812.10)], "SE1: street at x = 3422.5 from the Mirante's park down to the road",
    kind="street", width=14.0, cls="street", snap=4.0, hold=0.01)
add([(3282.88, -602.00), (3422.50, -602.00)], "SE1: cross street at y = -602 from CE15's east street", kind="street",
    width=14.0, cls="street", snap=4.0, hold=0.01)# (with the stub and the lay-by gone, the road from the new junction at x = 3422.5 round the south-east corner and up the
# east valley to the Aeroporto Leste is one edge, too bent to be straightened, and it kept the notches of the drawn band
# (jogs of 10-14 m south). Redrawn after the straightening: straight along the band to a curve of 50 m radius at the
# corner, then up the valley along its drawn line, smoothed.)
EDITS.append({"op": "remove", "at": (3700.0, -818.0), "within": 12.0, "when": "after",
              "why": "SE: the road east of x = 3422.5 and up the east valley, as traced (notched)"})
add([(3422.52, -813.70), (3750.00, -811.30), (4080.50, -809.00), (4099.63, -805.19), (4115.86, -794.36),
     (4126.69, -778.13), (4130.50, -759.00), (4131.20, -678.00), (4136.50, -551.00), (4137.50, -426.00), (4135.00, -237.00),
     (4131.50, -50.00), (4131.00, 150.00), (4128.00, 400.00), (4122.00, 600.00), (4122.00, 850.00), (4119.76, 969.96)],
    "SE: the road east to the corner and up the east valley to the Aeroporto Leste, redrawn", kind="avenue", width=15.0,
    cls="street", snap=4.0, curve=True, when="after")
# ---------------------------------------------------------------------------------------------------------
# Ilha Oeste (sectors IO*, 2026-11-16). The drawing: a low island (2-4 m) of dense blocks with canals between them
# (too narrow for the water mask, which reads the blocks as one piece of land); three streets (the island road along
# y = 435, a cross street along y = 275 and a street at x = -1980 between them, on south to y = 136); a ring of
# elevated road (orange) round three lagoons on the island's west side, with two cross pieces; a north loop and a
# south-west curve along the shore; and the link from the island road over the south lagoon down to the highway at
# y = 232. Read as: the island road an arterial (it carries the viaduct's traffic) and its little knot where the
# street at x = -1980 meets it (two parallel pieces round a triangle) one T junction; the ring, the north loop, the
# south-west curve, the two cross pieces and the link as causeways on fill with quay walls at 4.5 m (as the
# Peninsula Noroeste's piers); the ring redrawn clean (traced, it wobbled 5-10 m round its junctions) as an
# arterial, the cross pieces as streets; the stubs into the lagoons and the second line traced beside the
# south-west curve dropped.
# ---------------------------------------------------------------------------------------------------------
for _at, _w, _why in [((-1967.5, 439.6), 5.0, "the knot's north piece"), ((-1940.8, 436.5), 3.0, "the knot's east piece"),
                      ((-1960.2, 413.5), 4.0, "the knot's diagonal"), ((-1986.9, 416.6), 4.0, "the knot's west piece"),
                      ((-1919.2, 425.8), 4.0, "the island road east of the knot, as traced"),
                      ((-2272.5, 425.8), 3.0, "a short piece at the north loop's west end"),
                      ((-2280.6, 406.1), 3.0, "a loop of street at the north loop's west end"),
                      ((-2399.2, 77.5), 3.0, "a stub into the south-west lagoon"),
                      ((-2270.0, 131.7), 3.0, "a stub into the west lagoon"),
                      ((-2131.1, -20.6), 4.0, "a second line traced beside the south-west curve"),
                      ((-2304.7, 425.8), 3.0, "the ring, as traced (north end)"),
                      ((-2410.8, 359.2), 4.0, "the ring, as traced (north-west)"),
                      ((-2412.5, 180.0), 4.0, "the ring, as traced (west)"),
                      ((-2408.9, 91.5), 4.0, "the ring, as traced (south-west corner)"),
                      ((-2355.8, -32.5), 4.0, "the ring, as traced (south)"),
                      ((-2338.2, 269.3), 4.0, "the ring's north cross piece, as traced"),
                      ((-2341.3, 126.1), 4.0, "the ring's south cross piece, as traced")]:
    EDITS.append({"op": "remove", "at": _at, "within": _w, "when": "after", "why": "Ilha Oeste: " + _why})
add([(-1897.5, 424.2), (-1994.2, 433.4)], "Ilha Oeste: the island road through the knot", kind="avenue", width=24.0,
    cls="arterial", snap=3.0, when="after")
add([(-1979.5, 399.8), (-1980.6, 432.2)], "Ilha Oeste: the street at x = -1980 up to the island road (a T)", kind="street",
    width=14.0, cls="street", snap=4.0, when="after")
add([(-2289.2, 429.2), (-2312.5, 424.2), (-2360.0, 421.0), (-2395.0, 410.0), (-2410.5, 385.0), (-2411.0, 282.5)],
    "Ilha Oeste: the ring, north-west corner", kind="avenue", width=24.0, cls="arterial", snap=3.0, curve=True, quay=4.5,
    when="after")
add([(-2411.0, 282.5), (-2410.8, 119.2)], "Ilha Oeste: the ring, west side", kind="avenue", width=24.0, cls="arterial",
    snap=3.0, quay=4.5, when="after")
add([(-2410.8, 119.2), (-2409.0, 40.0), (-2402.0, 0.0), (-2385.0, -22.0), (-2355.0, -30.0), (-2300.0, -27.0), (-2260.0, -21.0),
     (-2210.8, -20.8)], "Ilha Oeste: the ring, south-west corner", kind="avenue", width=24.0, cls="arterial", snap=3.0,
    curve=True, quay=4.5, when="after")
add([(-2411.0, 282.5), (-2269.2, 270.4)], "Ilha Oeste: the ring's north cross piece", kind="street", width=14.0, cls="street",
    snap=3.0, quay=4.5, when="after")
add([(-2277.5, 142.5), (-2410.8, 119.2)], "Ilha Oeste: the ring's south cross piece", kind="street", width=14.0, cls="street",
    snap=3.0, quay=4.5, when="after")
# The blocks the drawing packs between canals had no street to face: the street at x = -1980 carried north of the
# island road to a street along the north shore (y = 612), which ends at the north loop in the west and in a turning
# circle in the east; and carried south of the south-west curve to a street along y = -50 (the canal line between the
# south blocks), from the ring's south-west corner to a turning circle in the east.
add([(-1980.6, 432.2), (-1980.0, 612.0)], "Ilha Oeste: the street at x = -1980 north to the north shore", kind="street",
    width=14.0, cls="street", snap=4.0, when="after")
add([(-1980.0, 612.0), (-2150.0, 612.0), (-2186.0, 571.0)], "Ilha Oeste: street along the north shore, west part",
    kind="street", width=14.0, cls="street", snap=6.0, when="after")
add([(-1835.0, 612.0), (-1980.0, 612.0)], "Ilha Oeste: street along the north shore, east part", kind="street", width=14.0,
    cls="street", snap=4.0, when="after")
add([(-1981.5, 135.7), (-1985.0, -50.0)], "Ilha Oeste: the street at x = -1980 south to the south blocks", kind="street",
    width=14.0, cls="street", snap=4.0, when="after")
add([(-2210.8, -20.8), (-2150.0, -45.0), (-1985.0, -50.0)], "Ilha Oeste: street along y = -50, west part", kind="street",
    width=14.0, cls="street", snap=4.0, when="after")
add([(-1985.0, -50.0), (-1835.0, -54.0)], "Ilha Oeste: street along y = -50, east part", kind="street", width=14.0,
    cls="street", snap=4.0, when="after")
along([(-1807.5, 429.3), (-1867.5, 427.4), (-1897.5, 424.2)], "Ilha Oeste: the island road east of the knot, an arterial",
      within=4.0, share=0.6, cls="arterial", kind="avenue")
for _pts, _why in [([(-1994.2, 433.4), (-2077.5, 435.8), (-2124.7, 470.3), (-2140.8, 549.2), (-2210.2, 570.5), (-2269.2, 527.5),
                     (-2283.8, 448.3), (-2289.2, 429.2)], "the north loop"),
                   ([(-2210.8, -20.8), (-2189.6, -13.3), (-2170.5, -1.5), (-2152.5, 12.5), (-2138.5, 30.5), (-2126.4, 48.6),
                     (-2120.8, 60.8), (-2114.2, 79.2), (-2106.2, 108.5), (-2082.4, 120.8), (-2053.4, 127.5), (-2027.3, 135.0),
                     (-2001.3, 140.7), (-1981.5, 135.7)], "the south-west curve"),
                   ([(-1555.8, 232.5), (-1617.5, 267.5), (-1685.4, 285.7), (-1760.4, 292.3), (-1812.5, 330.8), (-1862.0, 370.3),
                     (-1895.8, 417.5), (-1897.5, 424.2)], "the link over the south lagoon to the highway"),
                   ([(-2269.2, 270.4), (-2269.6, 246.7), (-2270.0, 222.9), (-2270.3, 199.2), (-2270.7, 175.4), (-2276.4, 156.9),
                     (-2277.5, 142.5)], "the street along the west lagoon's east shore")]:
    along(_pts, "Ilha Oeste: " + _why + ", a causeway at quay level", within=5.0, share=0.6, quay=4.5,
          cls="street" if "west lagoon" in _why else "arterial", kind="street" if "west lagoon" in _why else "avenue")
along([(-1486.05, 440.0), (-1459.5, 440.93), (-1265.58, 447.73)], "Ilha Oeste: the street east of the viaduct graded evenly down to "
      "the Centro Oeste (it took the viaduct's last 4 m in 26 m)", within=4.0, share=0.6, hold=0.01)# the loop road round the hill north of the Centro Oeste's west end: at its north-west corner the tracing left an alley
# beside it (a second line round a corner) and a stub of alley down the slope: both dropped (2026-11-16, IOX4)
for _at, _why in [((-1377.4, 719.1), "an alley beside the loop road's north-west corner"), ((-1349.3, 728.0), "a stub of alley down the slope")]:
    EDITS.append({"op": "remove", "at": _at, "within": 3.0, "when": "after", "why": "IOX4: " + _why})# Ponte Pensil Oeste (2026-11-16): the bridge was one edge from the roundabout at its north end down to the junction on
# the Ilha Oeste bluff (y = 652), its deck arching over the bluff's top too, where the bluff (13 m) stands above where the
# girder would run. Split where the bluff ends: the highway on the bluff up to y = 780 (built by the sector there, IOX2),
# the bridge from there over the strait to the roundabout, a suspension bridge (structures "PPO") with a designed deck:
# 15 m at the south face, up at 4.3 % to a crest of 27.1 m (a 150 m vertical curve, first drawn as a sharp peak at 29 m),
# down at 5.8 % to 11.5 m at the north face.
EDITS.append({"op": "remove", "at": (-1575.0, 1100.0), "within": 8.0, "when": "after",
              "why": "PPO: the bridge as one edge from the roundabout to the bluff's junction"})
add([(-1564.17, 652.5), (-1565.6, 700.0), (-1567.3, 780.0)], "PPO: the highway on the bluff up to the bridge", kind="avenue",
    width=30.0, cls="freeway", snap=4.0, when="after")
add([(-1567.3, 780.0), (-1584.17, 1426.67)], "PPO: Ponte Pensil Oeste", kind="bridge", width=23.3, cls="bridge",
    name="Ponte Pensil Oeste", snap=4.0, when="after",
    deck=[(-1567.30, 780.00, 15.00), (-1573.78, 1028.32, 25.75), (-1574.43, 1053.31, 26.62), (-1575.08, 1078.30, 27.07),
          (-1575.73, 1103.29, 27.10), (-1576.39, 1128.28, 26.71), (-1577.04, 1153.27, 25.89), (-1577.69, 1178.26, 24.65),
          (-1583.60, 1404.99, 11.50), (-1584.17, 1426.67, 10.90)])# The Ponte Pensil Oeste's north head (sector NH1, 2026-11-17): the drawing has a roundabout round the bridge's end with
# the main road carried straight through its middle (a "through-about"), traced as a lopsided diamond of freeway, 30 m
# wide. Read as: the ring an ellipse through its four junctions (52 x 45 m), an arterial like the bridge; the ring and
# the road through it on a platform at 10.5 m, the height the bridge lands at (the roads round it are high too: the
# road north climbs to the hill at 14 m, the shore road east is drawn elevated); the road north of it an arterial all
# the way (two short pieces of it were freeway).
for _at, _why in [((-1628.0, 1497.0), "north-west"), ((-1616.1, 1438.5), "south-west"), ((-1544.2, 1440.8), "south-east"),
                  ((-1551.1, 1505.0), "north-east")]:
    EDITS.append({"op": "remove", "at": _at, "within": 4.0, "when": "after", "why": "NH1: the roundabout's %s quarter, as traced" % _why})
EDITS.append({"op": "move", "at": (-1642.5, 1469.2), "to": (-1637.2, 1472.1), "within": 8.0, "when": "after",
              "why": "NH1: the roundabout's west junction on the ellipse"})
EDITS.append({"op": "move", "at": (-1525.8, 1474.2), "to": (-1533.2, 1472.1), "within": 9.0, "when": "after",
              "why": "NH1: the roundabout's east junction on the ellipse"})
for _pts, _why in [([(-1584.17, 1426.67), (-1611.2, 1432.78), (-1630.23, 1449.4), (-1637.2, 1472.1)], "south-west"),
                   ([(-1637.2, 1472.1), (-1630.23, 1494.8), (-1611.2, 1511.42), (-1586.3, 1517.5)], "north-west"),
                   ([(-1586.3, 1517.5), (-1559.2, 1511.42), (-1540.17, 1494.8), (-1533.2, 1472.1)], "north-east"),
                   ([(-1533.2, 1472.1), (-1540.17, 1449.4), (-1559.2, 1432.78), (-1584.17, 1426.67)], "south-east")]:
    add(_pts, "NH1: the roundabout's %s quarter" % _why, kind="avenue", width=24.0, cls="arterial", snap=4.0, curve=True,
        quay=10.5, when="after")
along([(-1586.3, 1517.5), (-1585.6, 1487.2), (-1584.17, 1426.67)], "NH1: the road through the roundabout, on its platform",
      within=4.0, share=0.6, cls="arterial", kind="avenue", quay=10.5)
along([(-1586.3, 1517.5), (-1590.7, 1626.5), (-1596.3, 1766.5), (-1590.8, 1779.2), (-1590.0, 1821.7)],
      "NH1: the road north of the roundabout, an arterial", within=4.0, share=0.6, cls="arterial", kind="avenue")# The coast east of the Ponte Pensil's north head (sectors NH2, NH3, 2026-11-17): the drawing has a road on an orange
# band along y = 1490, about 140 m out in the water (the lagoons behind it and the bay in front are both water in the
# mask), from the roundabout's east arm to x = -860, with a link north at x = -1150 to the foot of the Falesia Norte; it
# was traced as bridges arching up to 17 m over the water, with a triangle of three short roads where the road north
# (x = -1440) meets it. Read as the island ring was: a causeway on fill with quay walls at 4.5 m, an arterial (it
# carries the roundabout's traffic east); the triangle a T (its lower side dropped); the link north a street that
# climbs from the causeway to the foot of the cliff.
EDITS.append({"op": "remove", "at": (-1431.0, 1460.0), "within": 6.0, "when": "after",
              "why": "NH3: the lower side of the triangle where the road north meets the causeway"})
along([(-1464.2, 1475.8), (-1444.0, 1477.0), (-1431.8, 1491.9), (-1399.2, 1489.2), (-1360.0, 1486.0), (-1269.0, 1482.0),
       (-1188.0, 1484.0), (-1149.5, 1492.5), (-1072.0, 1482.0), (-981.0, 1482.0), (-886.0, 1485.0), (-862.5, 1485.8)],
      "NH3: the causeway along y = 1490, at quay level", within=6.0, share=0.6, cls="arterial", kind="avenue", quay=4.5)
along([(-1533.2, 1472.1), (-1495.0, 1474.0), (-1464.2, 1475.8)], "NH1/NH3: the roundabout's east arm, an arterial", within=4.0,
      share=0.6, cls="arterial", kind="avenue")
along([(-1149.5, 1492.5), (-1154.0, 1525.0), (-1155.0, 1585.0), (-1144.0, 1638.0), (-1129.2, 1659.2)],
      "NH3: the link from the causeway north to the foot of the cliff, a street", within=5.0, share=0.6, cls="street", kind="street")# (the arm had been built (NH1) dipping to 7.4 m between the roundabout's platform and a junction held at 12.9 m by the
# coastal road's old arch: its held heights let go (unfreeze.py) and the arm laid out evenly from the platform down to
# the causeway, 6 m in 69 m)
along([(-1533.2, 1472.1), (-1495.0, 1474.0), (-1464.2, 1475.8)], "NH1/NH3: the roundabout's east arm, evenly down to the causeway",
      within=4.0, share=0.6, deck=[(-1533.2, 1472.1, 10.5), (-1464.2, 1475.8, 4.6)])# The coastal road from the causeway's east end (x = -862) round the bay to the north freeway (417, x = -14): drawn as an
# orange band, traced as a bridge arching up to 40 m. It runs over water but for a small headland at x = -500 (15-17 m)
# and its north end on land: the freeway's ring round the Falesia Norte plateau. Read as a freeway causeway at quay level
# 4.5 m like the coast west of it (the headland cut through) (2026-11-17, FN sectors).
along([(-835.0, 1487.0), (-752.0, 1506.0), (-668.0, 1536.0), (-600.0, 1586.0), (-544.0, 1649.0), (-482.0, 1714.0), (-422.0, 1759.0),
       (-342.0, 1794.0), (-249.0, 1807.0), (-154.0, 1820.0), (-60.0, 1838.0), (-6.0, 1882.0), (-8.0, 1971.0), (-10.0, 2066.0),
       (-12.0, 2160.0), (-14.0, 2242.0)], "FN: the coastal road round the bay, a freeway causeway", within=6.0, share=0.6,
      cls="freeway", kind="avenue", quay=4.5)
# The Falesia Norte town (sectors FN*): the drawing packs the plateau with small buildings in a grid and draws no street
# but two stubs at its west end, and the north freeway cuts diagonally through it. The ground under the drawn buildings
# reads the lowest land level (a hole) in the east part. Read as two quarters, as the ground allows: the west part on the
# plateau's top (85-90 m), reached by the stub from the freeway (x = -1034) climbing to the street already drawn on the
# top, carried on east along y = 1945 with two short cross streets; the east part down by the inner bay, about 50 m
# below, a grid of three streets along it (the shore street held at 5 m) and four across, graded evenly between their
# junctions, two of them up to the freeway and the long ones out to the coastal road; and a street along y = 2075 for
# the houses north-west of the freeway.
add([(-1034.0, 1888.0), (-1010.0, 1862.0), (-975.0, 1858.0), (-950.0, 1880.0), (-946.2, 1913.4)],
    "FN: the climb from the freeway's stub up to the plateau's street", kind="street", width=14.0, cls="street", snap=4.0,
    curve=True, when="after")
add([(-871.1, 1941.6), (-760.0, 1945.0), (-650.0, 1947.0), (-560.0, 1950.0)], "FN: the plateau's street along y = 1945",
    kind="street", width=14.0, cls="street", snap=4.0, when="after")
for _x in (-760.0, -650.0):
    add([(_x, 1898.0), (_x, 1945.0 if _x == -760.0 else 1947.0)], "FN: cross street on the plateau, south", kind="street",
        width=14.0, cls="street", snap=4.0, when="after")
    add([(_x, 1945.0 if _x == -760.0 else 1947.0), (_x, 1968.0)], "FN: cross street on the plateau, north", kind="street",
        width=14.0, cls="street", snap=4.0, when="after")
add([(-540.0, 2020.0), (-470.0, 2020.0), (-360.0, 2020.0), (-250.0, 2020.0), (-140.0, 2020.0), (-9.0, 2020.0)],
    "FN: the shore street along the inner bay", kind="street", width=14.0, cls="street", snap=6.0, when="after", quay=5.0)
add([(-540.0, 2080.0), (-470.0, 2080.0), (-360.0, 2080.0), (-250.0, 2080.0), (-140.0, 2080.0), (-10.0, 2080.0)],
    "FN: street along y = 2080", kind="street", width=14.0, cls="street", snap=6.0, when="after", hold=0.01)
add([(-470.0, 2140.0), (-360.0, 2140.0), (-250.0, 2140.0), (-140.0, 2140.0), (-11.0, 2140.0)],
    "FN: street along y = 2140", kind="street", width=14.0, cls="street", snap=6.0, when="after", hold=0.01)
for _x, _top in ((-470.0, 2140.0), (-360.0, 2216.0), (-250.0, 2140.0), (-140.0, 2262.0)):
    add([(_x, 2020.0), (_x, 2080.0)], "FN: cross street x = %.0f, shore to y = 2080" % _x, kind="street", width=14.0, cls="street",
        snap=4.0, when="after", hold=0.01)
    add([(_x, 2080.0), (_x, 2140.0)], "FN: cross street x = %.0f, y = 2080 to 2140" % _x, kind="street", width=14.0,
        cls="street", snap=4.0, when="after", hold=0.01)
    if _top > 2140.0:
        add([(_x, 2140.0), (_x, _top)], "FN: cross street x = %.0f up to the freeway" % _x, kind="street", width=14.0,
            cls="street", snap=8.0, when="after", hold=0.01)
add([(-1000.0, 2075.0), (-850.0, 2075.0), (-700.0, 2075.0), (-628.0, 2076.0)], "FN: street along y = 2075, north-west of the freeway",
    kind="street", width=14.0, cls="street", snap=8.0, when="after")# The hilltop village north of the Falesia Norte's west end (sectors FN0, FN6, 2026-11-17): two short pieces of it were
# traced as arterial (the stub west at y = 2087 and a 15 m link at x = -1464 between two of its streets): streets
along([(-1469.0, 2087.4), (-1490.0, 2086.4), (-1512.5, 2085.3)], "FN6: the stub west at y = 2087, a street", within=4.0, share=0.6,
      cls="street", kind="street")
along([(-1463.2, 2222.2), (-1464.1, 2207.5)], "FN6: the short link at x = -1464, a street", within=3.0, share=0.6, cls="street",
      kind="street")# The north freeway east of the Falesia Norte (tunnels TN and TNB, sectors CN*, 2026-11-17): the drawing has it dashed (a
# tunnel) all along the coast from the coastal causeway's junction (x = -14) to x = 1250, under two spurs (20 m) and the
# ridge of the Encosta Sinuosa (40-44 m) where it reaches the north edge, with a dashed "Z" at x = 1150-1250 where a dashed
# branch leaves it south under the ridge's flank to a small paved square at (1032, 2064); a local street (yellow) runs on
# the surface beside it at x = 489-779. The tracing cut it in five pieces with junctions under the hills (three surface
# streets ending on it, and the branch meeting it 40 m under the ridge). Read as: one tunnel (Tunel da Orla Norte) from
# the causeway's junction to the ridge's east foot (x = 1250), 12 m below the line between its mouths, ramps of 6 %; the
# branch's junction there, on the surface, where the coast avenue east begins; the branch a tunnel of its own south under
# the ridge's flank to the square; the surface street beside the tunnel carried on east to the street that climbs the
# Encosta Sinuosa (no longer ending on the tunnel).
for _at, _why in [((409.3, 2253.7), "west"), ((638.1, 2259.3), "under the surface street"), ((849.2, 2265.0), "middle"),
                  ((1046.1, 2273.9), "under the ridge"), ((1198.1, 2289.2), "east"), ((1136.7, 2130.8), "branch south")]:
    EDITS.append({"op": "remove", "at": _at, "within": 4.0, "when": "after", "why": "TN: the north freeway's tunnel, as traced (%s)" % _why})
EDITS.append({"op": "move", "at": (1225.8, 2289.2), "to": (1250.0, 2290.0), "within": 3.0, "when": "after",
              "why": "TN: the branch's junction at the ridge's east foot, on the surface"})
add([(-14.2, 2242.5), (169.6, 2247.4), (409.3, 2253.7), (638.1, 2259.3), (849.2, 2264.0), (1046.1, 2272.0), (1191.1, 2286.0),
     (1250.0, 2290.0)], "TN: Tunel da Orla Norte", kind="tunnel", width=30.0, cls="tunnel", name="Tunel da Orla Norte",
    depth=12.0, grade=0.06, curve=True, snap=3.0, when="after")
# (2026-11-18: the branch's south mouth stands 22 m back from the square. The tunnel used to begin at the square's
# junction itself, its walls rising from the middle of the street: nothing else could join there, and the street met it
# at a square corner. Its last 22 m are now a plain avenue, built by the sector, at the heights they were built with: the
# new mouth is one of the old road's own height samples, so the tunnel's profile stays as it was.)
add([(1250.0, 2290.0), (1238.0, 2252.0), (1196.0, 2200.0), (1155.0, 2150.0), (1095.0, 2104.0), (1051.25, 2076.14)],
    "TNB: the north freeway's branch south, a tunnel under the ridge's flank", kind="tunnel", width=17.5, cls="tunnel",
    name="Tunel da Orla Norte - ramal sul", depth=9.0, grade=0.08, curve=True, snap=3.0, when="after")
add([(1051.25, 2076.14), (1032.5, 2064.2)], "TNB: the avenue from the branch's south mouth to the square", kind="avenue",
    width=24.2, cls="arterial", snap=3.0, when="after")
add([(779.2, 2262.5), (849.0, 2270.0), (919.2, 2267.5)], "CN: the surface street beside the tunnel, on east to the climb",
    kind="street", width=14.0, cls="street", snap=3.0, when="after")
add([(1032.5, 2064.2), (1050.0, 2030.0), (1064.2, 1994.2)], "CN2: the square between the branch's mouth and the next tunnel's",
    kind="street", width=14.0, cls="street", snap=4.0, when="after")

# ---------------------------------------------------------------------------------------------------------
# Distrito Norte (sectors DN*, 2026-11-17). The user, asked how to read the orange "Y"s on flat ground: "Passagem
# inferior". Read as:
#   * the avenue along y = 1866 (the north-airport road) dives under the district's centre in a short underpass, the
#     Tunel Norte-Aeroporto (TNA), from x = 2399 to x = 2973, its floor at -6.2 m as the drawing labels it; the
#     legs of the loop north (the "U" round the paved square) come down to a street along the north side of the
#     trench (the "Y"s' inner arms joined over the covered part), whose outer arms meet the avenue at grade at the
#     two mouths. The loop an arterial all round; its diagonal drive into the square a street.
#   * the dashed roads west (all dashed = tunnels): from the square at the Tunel da Orla Norte's branch (1064, 1994)
#     south under the ridge's foot to the shore (TDN1), a street along the shore where the loop road comes down, and
#     from the shore north-east under the blocks to the little square at (1635, 1986) (TDN2). The dashed branch west
#     to a loop in the islet's lagoon dropped (an underground fork; the islet stays green).
#   * the orange diamond by the shore (2200-2350, 1570-1710): a gyratory round its block, at grade (nothing crosses
#     it); its inner lanes dropped. The coast road from it east an arterial.
#   * at the east end the freeway to the airport forks off the avenue (x = 3324): one carriageway down to the
#     airport's grid, the coast road meeting it at grade; a connector beside the fork, the west line of a doubled
#     stretch and a ramp duplicating the coast road's junction dropped.
#   * smaller: a shortcut and a stub by the Prefeitura's road, stubs into the waterfront square, an alley along the
#     jagged quay, a turning loop round an island and a triangle at a car park dropped.
# ---------------------------------------------------------------------------------------------------------
for _at, _why in [((1170.28, 1949.72), "the dashed road south from the square, as traced (north piece)"),
                  ((1209.84, 1722.16), "the dashed road south from the square, as traced (south piece)"),
                  ((1086.73, 1837.76), "the dashed branch west to the islet's loop"),
                  ((1374.21, 1697.50), "the dashed piece along the shore"),
                  ((1543.24, 1833.43), "the dashed road north-east from the shore, as traced"),
                  ((1747.12, 1861.31), "a shortcut beside the junction north of the Prefeitura"),
                  ((1781.11, 1800.57), "a stub east of the Prefeitura's road"),
                  ((2695.83, 1850.83), "the avenue between the Y's, as traced (lower line)"),
                  ((2917.74, 1855.99), "the avenue at the east Y, as traced"),
                  ((2891.31, 1888.69), "the east Y's west arm, as traced"),
                  ((2946.40, 1888.94), "the east Y's east arm, as traced"),
                  ((2510.28, 1881.39), "the west Y's foot, as traced"),
                  ((2451.41, 1857.35), "the avenue at the west Y, as traced"),
                  ((2443.08, 1890.74), "the west Y's west arm, as traced"),
                  ((2803.73, 2099.33), "a second diagonal at the loop's north-east corner"),
                  ((2922.18, 1599.51), "a stub into the waterfront square"),
                  ((2954.31, 1594.58), "another stub into the waterfront square"),
                  ((2497.81, 1545.08), "an alley along the jagged quay"),
                  ((2324.05, 1631.88), "a lane into the diamond's block"),
                  ((2300.80, 1666.60), "an alley into the diamond's block"),
                  ((3409.98, 1819.78), "a connector beside the freeway's fork"),
                  ((3381.49, 1627.35), "a ramp duplicating the coast road's junction"),
                  ((3165.55, 1819.90), "a side of the triangle at the car park"),
                  ((3392.50, 1736.94), "the west line of the freeway's doubled stretch"),
                  ((3230.83, 1715.83), "a turning loop round an island")]:
    EDITS.append({"op": "remove", "at": _at, "within": 3.0, "when": "after", "why": "DN: " + _why})
# (2026-11-18: this tunnel's west mouth stands 32 m back from the square's south end, for the same reason as the Tunel
# da Orla Norte's branch: see there. Its first 32 m are a plain avenue at the heights they were built with.)
add([(1064.2, 1994.2), (1095.23, 1987.63)], "TDN1: the avenue from the square's south end to the tunnel's west mouth",
    kind="avenue", width=24.2, cls="arterial", snap=3.0, when="after")
add([(1095.23, 1987.63), (1103.0, 1986.0), (1140.0, 1976.0), (1169.0, 1958.0), (1173.0, 1919.0), (1176.0, 1881.0), (1182.0, 1830.0),
     (1188.0, 1800.0), (1194.0, 1758.0), (1210.0, 1722.0), (1244.0, 1708.0), (1285.0, 1700.0), (1323.4, 1694.1)],
    "TDN1: tunnel from the square south under the ridge's foot to the shore", kind="tunnel", width=17.5, cls="tunnel",
    name="Tunel do Distrito Norte - oeste", depth=9.0, grade=0.08, curve=True, snap=3.0, when="after")
add([(1323.4, 1694.1), (1342.0, 1689.0), (1374.0, 1698.0), (1396.0, 1699.0), (1432.0, 1696.0)], "DN1: the street along the shore",
    kind="street", width=14.0, cls="street", snap=3.0, curve=True, when="after")
add([(1432.0, 1696.0), (1464.0, 1749.0), (1469.0, 1819.0), (1543.0, 1833.0), (1592.0, 1859.0), (1605.0, 1930.0), (1635.0, 1986.0)],
    "TDN2: tunnel from the shore north-east under the blocks to the little square", kind="tunnel", width=17.5, cls="tunnel",
    name="Tunel do Distrito Norte - leste", depth=9.0, grade=0.08, curve=True, snap=3.0, when="after")
add([(2399.3, 1863.8), (2600.0, 1865.5), (2800.0, 1866.5), (2972.5, 1866.7)], "TNA: Tunel Norte-Aeroporto, the avenue under the district's centre",
    kind="tunnel", width=17.5, cls="tunnel", name="Tunel Norte-Aeroporto", depth=10.2, grade=0.07, snap=3.0, when="after")
add([(2504.2, 1895.8), (2450.0, 1880.0), (2399.3, 1863.8)], "DN5: the west Y's outer arm, down to the avenue at the west mouth",
    kind="street", width=14.0, cls="street", snap=3.0, when="after")
add([(2504.2, 1895.8), (2600.0, 1893.5), (2700.0, 1893.5), (2850.0, 1897.0), (2927.5, 1905.8)],
    "DN5: the street along the north side of the trench, joining the two Y's", kind="street", width=14.0, cls="street",
    snap=3.0, when="after")
add([(2927.5, 1905.8), (2950.0, 1885.0), (2972.5, 1866.7)], "DN5: the east Y's outer arm, down to the avenue at the east mouth",
    kind="street", width=14.0, cls="street", snap=3.0, when="after")
along([(2504.2, 1895.8), (2501.0, 2111.0), (2506.0, 2120.0), (2539.0, 2146.0), (2621.0, 2144.0), (2770.0, 2142.0), (2813.0, 2142.0),
       (2855.0, 2131.0), (2899.0, 2104.0), (2928.0, 1906.0)], "DN5: the loop round the square, an arterial", within=5.0,
      share=0.6, cls="arterial", kind="avenue")
along([(2621.0, 2144.0), (2700.0, 2075.0), (2767.0, 2014.0)], "DN5: the drive into the square, a street", within=6.0, share=0.6,
      cls="street", kind="street")
along([(2204.0, 1709.0), (2293.0, 1695.0), (2341.0, 1639.0), (2349.0, 1566.0), (2230.0, 1600.0), (2204.0, 1709.0)],
      "DN4: the gyratory round the diamond's block", within=6.0, share=0.6, cls="arterial", kind="avenue")
along([(2349.0, 1566.0), (2421.0, 1566.0), (2499.0, 1581.0)], "DN4: the coast road east of the diamond", within=5.0, share=0.6,
      cls="arterial", kind="avenue")
along([(3175.8, 1705.8), (3200.8, 1687.5), (3219.2, 1662.5), (3229.3, 1561.6)], "DN7: the road along y = 1700 on down to the coast",
      within=5.0, share=0.6, cls="arterial", kind="avenue")
along([(3324.2, 1847.5), (3359.9, 1815.6), (3396.6, 1779.8), (3423.5, 1733.8), (3419.2, 1694.2), (3441.2, 1643.7), (3460.1, 1600.3)],
      "DN8: the freeway forking off the avenue towards the airport", within=6.0, share=0.6, cls="freeway", kind="avenue")
along([(3324.2, 1847.5), (3373.0, 1851.0), (3424.3, 1855.8)], "DN8: the avenue east of the fork, an arterial", within=5.0,
      share=0.6, cls="arterial", kind="avenue")
along([(2620.9, 2144.5), (2627.9, 2101.1), (2634.2, 2061.5), (2649.2, 2025.3), (2680.6, 2011.7), (2727.7, 2013.0), (2767.0, 2014.1)],
      "DN5: the drive into the square, a street (as traced)", within=4.0, share=0.6, cls="street", kind="street")
along([(2500.6, 2111.0), (2485.2, 2085.6), (2482.5, 2050.8), (2485.8, 2011.7), (2489.2, 1972.5), (2504.2, 1949.8), (2504.2, 1911.2),
       (2504.2, 1895.8)], "DN5: the loop's west leg, an arterial like the rest of the loop", within=4.0, share=0.6, cls="arterial",
      kind="avenue")
along([(1639.0, 2036.3), (1636.4, 2007.7), (1634.5, 1986.3)], "DN2: the 50 m from the little square to the tunnel's mouth, a street",
      within=3.0, share=0.6, cls="street", kind="street")

# ---------------------------------------------------------------------------------------------------------
# Campaign (2026-11-17): the training ground, "Pista de Treinamento" of operations 01 and 04 (sector PT1).
# The campaign's model (ASSETS TO USE/bay_city_3d) has a copy of the same paved yard for each of the two layouts,
# south of the east bank of the Rio Leste, reached from the shore road's spur; the user asked for one yard whose
# layout changes with the operation. The spur used to end at (2850.83, -1255.83). It now turns south (a 35 m arc)
# and runs straight down the hillside along x = 2879.37 to the yard's gate at y = -1705: over the knoll (18 m at
# y = -1585), then down a designed sag curve to the yard's level at the gate (9.64 m: the yard is a plane rising
# 1.2 % to the east, z = 9.9 + 0.012 (x - 2901), cut into the slope). Inside the gate a drive without kerbs runs on
# to the asphalt. All added after the straightening, each with its class, so nothing built moves.
# ---------------------------------------------------------------------------------------------------------
# (One edge from the spur's end to the gate: two edges meeting on the straight left a gap in the lane paint where they
# met. Its profile is designed all along: the heights the solver gave the road over the natural ground as far as the
# knoll's top, then the sag curve.)
_PT_NATURAL = [(2850.83, -1255.83, 17.35), (2862.12, -1260.06, 17.04), (2871.31, -1267.88, 16.67), (2877.29, -1278.35, 16.29),
               (2879.37, -1290.23, 15.96), (2879.37, -1298.12, 15.81), (2879.37, -1306.01, 15.68), (2879.37, -1313.90, 15.56),
               (2879.37, -1321.78, 15.44), (2879.37, -1329.67, 15.34), (2879.37, -1337.56, 15.24), (2879.37, -1345.45, 15.14),
               (2879.37, -1353.34, 15.05), (2879.37, -1361.23, 14.97), (2879.37, -1369.12, 14.90), (2879.37, -1377.01, 14.84),
               (2879.37, -1384.89, 14.79), (2879.37, -1392.78, 14.77), (2879.37, -1400.67, 14.76), (2879.37, -1408.56, 14.78),
               (2879.37, -1416.45, 14.84), (2879.37, -1424.34, 14.92), (2879.37, -1432.23, 15.05), (2879.37, -1440.12, 15.21),
               (2879.37, -1448.00, 15.39), (2879.37, -1455.89, 15.59), (2879.37, -1463.78, 15.80), (2879.37, -1471.67, 16.01),
               (2879.37, -1479.56, 16.20), (2879.37, -1487.45, 16.38), (2879.37, -1495.34, 16.54), (2879.37, -1503.22, 16.68),
               (2879.37, -1511.11, 16.80), (2879.37, -1519.00, 16.92), (2879.37, -1526.89, 17.04), (2879.37, -1534.78, 17.16),
               (2879.37, -1542.67, 17.29), (2879.37, -1550.56, 17.42), (2879.37, -1558.45, 17.54), (2879.37, -1566.33, 17.64),
               (2879.37, -1574.22, 17.71), (2879.37, -1582.11, 17.73), (2879.37, -1590.00, 17.70)]
# The shore road itself (EP5: from the east end of the Ponte da Via Expressa south along the quay, then east up the bank
# to that old dead end) is redrawn with it, as one road from the bridge to the gate. As traced, its corner was a hook:
# the line overshot 6 m to the south and came back heading north-east (27 degrees) before settling east, and on the
# inside of that hook the surface stood up to 0.54 m off the road's own height (the built-sector check had reported it
# since 2026-11-16). Now: the quay leg as it was, a 22 m arc, a straight leg up the bank through the old dead end, the
# 35 m arc to the south. Heights as built on the quay leg and up the bank (the bank's own 17 % at its steepest), with
# the grade building up evenly round the first arc.
EDITS.append({"op": "remove", "at": (2698.4, -1100.0), "within": 3.0, "when": "after",
              "why": "EP5: the shore road as traced, with the hooked corner (redrawn below)"})
_PT_SHORE = [(2697.50, -957.50, 11.50), (2697.55, -965.31, 11.08), (2697.60, -973.12, 10.31), (2697.64, -980.93, 9.59),
             (2697.69, -988.74, 8.89), (2697.74, -996.55, 8.21), (2697.79, -1004.36, 7.53), (2697.83, -1012.17, 6.85),
             (2697.88, -1019.98, 6.18), (2697.93, -1027.78, 5.51), (2697.98, -1035.59, 4.84), (2698.02, -1043.40, 4.17),
             (2698.07, -1051.21, 3.94), (2698.12, -1059.02, 3.93), (2698.17, -1066.83, 3.92), (2698.22, -1074.64, 3.92),
             (2698.26, -1082.45, 3.91), (2698.31, -1090.26, 3.91), (2698.36, -1098.07, 3.91), (2698.41, -1105.88, 3.90),
             (2698.45, -1113.69, 3.90), (2698.50, -1121.50, 3.90), (2698.55, -1129.31, 3.89), (2698.60, -1137.12, 3.88),
             (2698.65, -1144.93, 3.87), (2698.69, -1152.74, 3.85), (2698.74, -1160.55, 3.83), (2698.79, -1168.35, 3.81),
             (2698.84, -1176.16, 3.78), (2698.88, -1183.97, 3.74), (2698.93, -1191.78, 3.69), (2698.98, -1199.59, 3.61),
             (2699.03, -1207.40, 3.51), (2698.99, -1209.63, 3.48), (2699.22, -1212.66, 3.49), (2699.86, -1215.63, 3.52),
             (2700.91, -1218.48, 3.58), (2702.34, -1221.16, 3.67), (2704.12, -1223.62, 3.78), (2706.23, -1225.81, 3.92),
             (2708.62, -1227.69, 4.08), (2711.25, -1229.22, 4.27), (2714.06, -1230.37, 4.49), (2717.00, -1231.13, 4.73),
             (2720.28, -1233.06, 4.99), (2728.05, -1233.61, 5.78), (2735.83, -1234.17, 6.75), (2743.50, -1235.61, 7.91),
             (2751.16, -1237.06, 9.22), (2758.83, -1238.50, 10.55), (2766.50, -1239.95, 11.87), (2774.16, -1241.39, 13.18),
             (2781.83, -1242.83, 14.33), (2789.50, -1244.28, 15.26), (2797.16, -1245.72, 15.97), (2804.83, -1247.17, 16.48),
             (2812.50, -1248.61, 16.83), (2820.16, -1250.05, 17.06), (2827.83, -1251.50, 17.21), (2835.50, -1252.94, 17.30),
             (2843.16, -1254.39, 17.34)]
add([(2697.50, -957.50), (2698.99, -1209.63), (2699.22, -1212.66), (2699.86, -1215.63), (2700.91, -1218.48), (2702.34, -1221.16),
     (2704.12, -1223.62), (2706.23, -1225.81), (2708.62, -1227.69), (2711.25, -1229.22), (2714.06, -1230.37), (2717.00, -1231.13),
     (2850.72, -1255.81), (2856.57, -1257.42), (2862.05, -1260.02), (2867.00, -1263.53), (2871.27, -1267.84), (2874.73, -1272.82),
     (2877.28, -1278.32), (2878.84, -1284.19), (2879.37, -1290.23), (2879.37, -1705.0)],
    "EP5, PT1: the shore road from the bridge, round the quay's corner, up the bank and down to the training ground's gate",
    kind="street", width=14.0, cls="street", snap=3.0, curve=True, when="after",
    deck=_PT_SHORE + _PT_NATURAL + [(2879.37, round(-1590.0 - 5.75 * k, 2),
                                     round(17.70 - 8.06 * (3.0 * (k / 20.0) ** 2 - 2.0 * (k / 20.0) ** 3), 3)) for k in range(1, 21)])
add([(2879.37, -1705.0), (2879.37, -1772.0)], "PT1: the drive from the gate across the service yard on to the asphalt",
    kind="street", width=7.0, cls="alley", snap=3.0, when="after",
    deck=[(2879.37, -1705.0, 9.64), (2879.37, -1772.0, 9.64)])

# ---------------------------------------------------------------------------------------------------------
# Campaign (2026-11-17): the park drive south of the boulevard (operations 10 and 18). The campaign's routes run on
# from the boulevard's south end to the street along y = -410 (the ambulance in 10, the robbers in 18); the drawing has
# a narrow light strip there, beside the pond, and the Bay had lawn: the way round was 450 m instead of 165. A drive
# without kerbs, 6 m wide, on the boulevard's own axis (x = -94, the seam between CW5 and CW7), through the lawn.
# ---------------------------------------------------------------------------------------------------------
add([(-94.0, -259.14), (-94.0, -408.54)], "CW5/CW7: the park drive from the boulevard's end to the street along y = -410",
    kind="street", width=7.0, cls="alley", snap=3.0, when="after")

# ---------------------------------------------------------------------------------------------------------
# The surface streets round the two tunnel mouths (sectors CN2 and DN0 made again, 2026-11-18). The user, asked whether
# the campaign's operation 02 should bring the dashed roads here to the surface: "Manter tuneis"; and, of these two sectors
# and the ground between them: "refaca as areas circuladas", "de uma forma natural e realista". The drawing has small
# buildings all along the dashed roads, a dashed spur west to a teardrop loop at (1000-1075, 1812-1862), and the avenue
# ending where the dashed road passes. Read as: the tunnels are the through road and stay as built; on the surface, the
# neighbourhood's own streets follow the same lines beside and over them, and those are what the operation drives:
#   * from the square (1032, 2064) straight on north, round the branch's mouth, along the ramp's north-west side, over
#     the tunnel beyond its portal and into the avenue's end at (1174, 2135) along the avenue's own line;
#   * off the square's street 20 m north of the other tunnel's mouth, along that ramp's north side (the south side is
#     the hill, 15-18 m), round the outside of the tunnel's bend and south beside the covered tunnel to (1197.9, 1842);
#   * the spur from there west to the loop, an oval round a small green; and the street on south to the waterfront.
# Every curve is an arc of at least 18 m on the centre line, met by straights along its tangents.
# ---------------------------------------------------------------------------------------------------------
_OP02_S1 = [(1032.50, 2064.20), (1030.65, 2068.30), (1028.79, 2072.40), (1027.37, 2077.32), (1027.39, 2082.45),
            (1028.85, 2087.36), (1031.64, 2091.66), (1035.52, 2095.00), (1040.32, 2098.06), (1045.12, 2101.11),
            (1049.92, 2104.17), (1054.72, 2107.23), (1059.52, 2110.29), (1064.32, 2113.35), (1069.12, 2116.40),
            (1073.92, 2119.46), (1078.72, 2122.52), (1083.52, 2125.58), (1088.32, 2128.63), (1093.06, 2131.22),
            (1098.11, 2133.15), (1103.38, 2134.38), (1108.76, 2134.88), (1114.35, 2135.03), (1119.94, 2135.18),
            (1125.52, 2135.32), (1131.11, 2135.47), (1136.70, 2135.62), (1142.28, 2135.76), (1147.87, 2135.91),
            (1153.46, 2136.05), (1159.04, 2136.20), (1163.98, 2136.18), (1168.90, 2135.85), (1173.80, 2135.22)]
_OP02_S2 = [(1055.93, 2012.39), (1059.57, 2014.04), (1063.22, 2015.69), (1068.58, 2017.61), (1074.18, 2018.63),
            (1079.88, 2018.73), (1085.51, 2017.90), (1091.36, 2016.55), (1097.21, 2015.20), (1103.05, 2013.85),
            (1108.90, 2012.50), (1114.74, 2011.15), (1120.59, 2009.80), (1126.44, 2008.45), (1132.28, 2007.10),
            (1138.13, 2005.75), (1143.98, 2004.40), (1149.82, 2003.06), (1155.28, 2001.43), (1160.50, 1999.15),
            (1165.40, 1996.23), (1169.89, 1992.74), (1173.93, 1988.71), (1177.43, 1984.22), (1180.35, 1979.33),
            (1182.64, 1974.12), (1184.28, 1968.66), (1185.22, 1963.04), (1185.97, 1955.92), (1186.72, 1948.80),
            (1187.47, 1941.68), (1188.22, 1934.56), (1188.96, 1927.44), (1189.71, 1920.32), (1190.46, 1913.20),
            (1191.21, 1906.08), (1191.96, 1898.96), (1192.71, 1891.84), (1193.45, 1884.72), (1194.20, 1877.60),
            (1194.95, 1870.48), (1195.70, 1863.36), (1196.45, 1856.24), (1197.20, 1849.12), (1197.94, 1842.00)]
_OP02_S2_SOUTH = [(1197.94, 1842.00), (1198.65, 1835.24), (1199.37, 1828.47), (1200.08, 1821.71), (1200.79, 1814.95),
                  (1201.50, 1808.19), (1202.21, 1801.42), (1202.92, 1794.66), (1203.63, 1787.90), (1204.34, 1781.14),
                  (1205.05, 1774.37)]
_OP02_SPUR = [(1197.94, 1842.00), (1139.00, 1840.00), (1080.00, 1838.00)]
_OP02_LOOP_N = [(1080.00, 1838.00), (1079.26, 1842.99), (1077.06, 1847.76), (1073.51, 1852.11), (1068.75, 1855.84),
                (1063.00, 1858.78), (1056.51, 1860.83), (1049.55, 1861.87), (1042.45, 1861.87), (1035.49, 1860.83),
                (1029.00, 1858.78), (1023.25, 1855.84), (1018.49, 1852.11), (1014.94, 1847.76), (1012.74, 1842.99),
                (1012.00, 1838.00)]
_OP02_LOOP_S = [(1012.00, 1838.00), (1012.74, 1833.01), (1014.94, 1828.24), (1018.49, 1823.89), (1023.25, 1820.16),
                (1029.00, 1817.22), (1035.49, 1815.17), (1042.45, 1814.13), (1049.55, 1814.13), (1056.51, 1815.17),
                (1063.00, 1817.22), (1068.75, 1820.16), (1073.51, 1823.89), (1077.06, 1828.24), (1079.26, 1833.01),
                (1080.00, 1838.00)]
_OP02_S2_DECK = [(1055.93, 2012.39, 5.91), (1062.31, 2015.28, 6.02), (1073.21, 2018.45, 6.45), (1084.54, 2018.04, 6.95), (1095.86, 2015.51, 7.35), (1107.16, 2012.90, 7.55), (1118.47, 2010.29, 7.45), (1129.77, 2007.68, 7.00), (1141.07, 2005.08, 6.35), (1152.14, 2002.37, 5.70), (1163.79, 1997.19, 5.15), (1175.61, 1986.56, 4.80), (1184.60, 1966.74, 4.65), (1188.49, 1931.96, 4.70), (1191.62, 1902.13, 4.60), (1194.76, 1872.29, 4.40), (1197.94, 1842.00, 4.15)]
add(_OP02_S1, "CN2: the street from the square round the branch's mouth to the avenue's end", kind="street", width=14.0,
    cls="street", snap=3.0, curve=True, when="after")
# its profile is designed (_OP02_S2_DECK): over the low rise north of the ramp in a cut of 3 m at most (the ground there
# reaches 10.5 m), never steeper than 6 %. Left to follow the ground it left the square's street with a kink of 14 % in
# its first 3 m. Its bend stands 8 m further east than first drawn: with the tunnel's mouth set back the ramp's portal
# moved to (1162.4, 1960.3), and the street has to pass clear of it before it runs on beside the covered tunnel.
add(_OP02_S2, "DN0: the street from the square along the ramp and south beside the tunnel", kind="street", width=14.0,
    cls="street", snap=3.0, curve=True, when="after", deck=_OP02_S2_DECK)
add(_OP02_S2_SOUTH, "DN0: the street on south to the waterfront", kind="street", width=14.0, cls="street", snap=3.0,
    curve=True, when="after")
add(_OP02_SPUR, "DN0: the spur west to the loop", kind="street", width=14.0, cls="street", snap=3.0, curve=True, when="after")
add(_OP02_LOOP_N, "DN0: the loop's north half", kind="street", width=14.0, cls="street", snap=3.0, curve=True, when="after")
add(_OP02_LOOP_S, "DN0: the loop's south half", kind="street", width=14.0, cls="street", snap=3.0, curve=True, when="after")
