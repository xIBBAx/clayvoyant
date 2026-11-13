"""The body's physical rules: how a person of given proportions sits on a given seat, and how much room a body needs.

No bpy here (only math), so the film, the contact checks and the tests all share one definition, and the tests run
without Blender. Distances are set units (a person stands about 3.4 tall; one unit is about half a metre). Seats are
measured from the built set by the film (film.py: measure_seat); this module only reasons about the numbers.

Seat frame: `u` runs forward, the way a sitter faces, from the seat's origin (the middle of the seat); `z` is height
above the floor of the room. A seat is a dict:

    top         height of the sitting surface (measured: lumps and bevels included)
    soft        how far its cushion gives under a sitter (0 for wood and plastic)
    front       u of the seat's front edge
    base_front  u of the furthest-forward solid thing under the seat at the height of a heel and a calf (the front of
                a sofa's base): heels and calves stay in front of it
    base_front_at  the same, lane by lane: [(sideways from the sitter's middle, u)]; where it is given, only the lanes
                the feet are in count (a chair's legs stand out at the sides: feet can draw in under it)
    back        u of the backrest's front face, or None for a stool or a bench without one
    under       height of the underside of whatever is above the knees (a table top), or None
    ahead       u of the first solid thing in front of the seat at the height of the thighs (a desk's panel), or None
    feet_ahead  [(sideways from the sitter's middle, u)] of the first solid thing in front of the seat at the height of
                the feet (a table's foot, a rail between a desk's legs): the toes stop short of it
    floor       height of the floor in front of the seat (a rug is a little higher than the boards)

A body is a dict (Body.from_meta builds it from the sculpt's numbers):

    hip         height of the pelvis pivot above the soles, standing
    joint       height of the hip joints above the pelvis pivot
    thigh, shin segment lengths of the leg
    thigh_r, knee_r, shin_r     how thick the trouser leg is near the hip, at the knee and down the shin
    seat_drop   how far below the hip joints the body rests on a seat: the thighs' own thickness, so the thighs lie
                on the seat (the seat of the trousers below that is pressed flat, see puppet.Puppet._deform)
    pelvis_back how far behind the hip joints the seat of the trousers reaches
    ankle       height of the ankle above the sole; heel and toe: how far the shoe reaches behind and ahead of it
    hipw        how far apart the hip joints are, each side of the middle
"""
import math

CLEAR = .004        # a body resting on something sits this far above it: touching, never inside
KNEE_ROOM = .03     # the back of the knee clears the seat's front edge by this much
HEEL_ROOM = .05     # a heel stays this far in front of whatever is under the seat
SHIN_LEAN = .42     # radians a seated shin may lean forward from upright before the knees come up instead
THIGH_SLOPE = (-.21, .55)   # radians the thighs may slope from level: down toward the knees, and up
RECLINE_MAX = .17   # radians someone settles back into a soft seat with a backrest
TURN_ROOM = .68     # how far from anything at floor level a body needs to stand to turn round: a shoe swings that wide
TOE_ROOM = .03      # the toes stop this far short of whatever stands on the floor in front of a seat
TUCK = -.35         # radians a seated shin may lean back, the feet drawn in under the knees


def _clamp(v, a, b):
    return max(a, min(b, v))


class Body(dict):
    """A body's measurements, from the puppet's sculpt numbers and its measured torso."""

    @staticmethod
    def from_meta(m, torso_back=.24, shoe=(.166, .389)):
        hip = float(m['hip'])
        lr = (float(m['hw']) / .35) ** .8
        legl = (hip - .13) / 2 * 1.015
        thigh_r = .183 * lr
        return Body(hip=hip, joint=.09, thigh=legl, shin=legl, thigh_r=thigh_r, knee_r=.125 * lr, shin_r=.122 * lr,
                    seat_drop=thigh_r + .02, pelvis_back=float(torso_back), ankle=.27, heel=shoe[0], toe=shoe[1],
                    hipw=.178 if float(m['hw']) > .34 else .16, shoulder=float(m.get('sw', .42)), hw=float(m['hw']))

    def footprint(self):
        """How far from its centre a standing body reaches across the floor: hips and trouser legs, planted feet."""
        return max(.36, self['hipw'] + self['thigh_r'] + .06, self['hw'] + .08)


def seated(body, seat, prefer=None, recline=True):
    """Where everything goes when this body sits on this seat. Returns a dict:

        u, z        the pelvis pivot (the actor's root) along the seat, and its height (the root's z)
        joint_z     height of the hip joints
        alpha       slope of the thighs (radians, positive: knees up); theta, the shins' forward lean
        knee        (u, z) of the knees
        ankle       (u, z) of the ankles: z is above the floor by the ankle's height, more when the feet cannot reach
        lift        how far the soles are off the floor (0 with the feet down)
        toe         how far the feet point their toes down toward the floor, radians (positive: toes down)
        lean        how far the torso settles back toward the backrest (negative is back), radians
        notes       what had to give, in words, for the log

    prefer: a u the scene would like the pelvis at (a mark's own spot): kept unless the knees, the backrest or the
    front edge say otherwise. Nothing here fails: an odd seat gives an odd but solid pose, and the notes say why."""
    notes = []
    soft = seat.get('soft', 0.0)
    top = seat['top']
    floor = seat.get('floor', 0.0)
    joint_z = top - soft + CLEAR + body['seat_drop']        # the thighs lie on the (pressed) seat
    root_z = joint_z - body['hip'] - body['joint']
    thigh, shin, kr = body['thigh'], body['shin'], body['knee_r']
    foot_z = floor + body['ankle']                          # an ankle above a sole that is on the floor
    knee_cap = None
    if seat.get('under') is not None:
        knee_cap = seat['under'] - .03 - kr                 # the knees fit under the table

    def place(alpha):
        """Knee height and the shin's lean for thighs at this slope, with the feet on the floor if they reach."""
        kz = joint_z + thigh * math.sin(alpha)
        drop = kz - foot_z
        if drop >= shin:
            return kz, 0.0, drop - shin
        return kz, math.acos(_clamp(drop / shin, -1, 1)), 0.0

    # level thighs if the feet reach the floor with the shins near upright; sloping down if they do not; the knees
    # up if the seat is so low that the feet would have to go far forward
    reach = joint_z - foot_z
    alpha = 0.0
    if reach > shin:
        alpha = -math.asin(min(1.0, (reach - shin) / thigh))
    elif reach < shin * math.cos(SHIN_LEAN):
        alpha = math.asin(_clamp((shin * math.cos(SHIN_LEAN) - reach) / thigh, 0, 1))
        notes.append('a low seat: knees up')
    alpha = _clamp(alpha, THIGH_SLOPE[0], THIGH_SLOPE[1])
    if knee_cap is not None and joint_z + thigh * math.sin(alpha) > knee_cap:
        alpha = max(THIGH_SLOPE[0], math.asin(_clamp((knee_cap - joint_z) / thigh, -1, 1)))
        notes.append('knees lowered to fit under the table')

    # along the seat: the backs of the knees past the front edge, the pelvis against the backrest or short of it
    def where(alpha):
        u = seat['front'] + kr + KNEE_ROOM - thigh * math.cos(alpha)
        if prefer is not None:
            u = max(u, prefer)
        if seat.get('back') is not None:
            u = max(u, seat['back'] + body['pelvis_back'] + .02)
        if seat.get('ahead') is not None:
            # the knees stop short of whatever is in front (a desk's panel): sit further back if the seat allows
            u = min(u, seat['ahead'] - .03 - kr - thigh * math.cos(alpha))
        return min(u, seat['front'] - .16)
    u = where(alpha)
    # a thigh sloping down must still clear the seat's front edge (a cushion gives a little there too)
    edge_r = body['thigh_r'] * .9
    for _ in range(12):
        under_edge = joint_z + (seat['front'] - u) * math.tan(alpha) - edge_r / math.cos(alpha)
        if alpha >= 0 or under_edge >= top - soft * .6 + CLEAR:
            break
        alpha = min(0.0, alpha + .02)
        u = where(alpha)
    if u >= seat['front'] - .16 - 1e-9 and seat['front'] + kr + KNEE_ROOM - thigh * math.cos(alpha) > u:
        notes.append('the seat is deeper than these thighs are long: sitting forward on it')
    if seat.get('ahead') is not None and u + thigh * math.cos(alpha) + kr > seat['ahead'] - .01:
        notes.append(f"no room for the knees: something stands {seat['ahead'] - seat['front']:.2f} in front of the seat")
    if seat.get('back') is not None and u < seat['back'] + body['pelvis_back']:
        notes.append('the seat is too shallow for this body: pressed against the backrest')
    knee_z, theta, lift = place(alpha)
    knee_u = u + thigh * math.cos(alpha)
    if theta > SHIN_LEAN + 1e-6:
        theta = SHIN_LEAN
        lift = max(0.0, knee_z - shin * math.cos(theta) - foot_z)
    # the ankles: forward of the knees by the shins' lean, and the heels clear of whatever stands under the seat
    span = body['hipw'] + .035
    if seat.get('base_front_at') is not None:
        # measured lane by lane: only what stands under the seat where these feet go keeps the heels forward
        under_ = [u_ for dl, u_ in seat['base_front_at'] if abs(abs(dl) - span) <= SHOE[2] + .04]
        heel_need = (max(under_) + body['heel'] + HEEL_ROOM) if under_ else -1e9
    else:
        heel_need = seat.get('base_front', seat['front']) + body['heel'] + HEEL_ROOM
    ankle_u = knee_u + shin * math.sin(theta)
    if ankle_u < heel_need:
        theta = min(SHIN_LEAN * 1.25, math.asin(_clamp((heel_need - knee_u) / shin, -1, 1)))
        ankle_u = knee_u + shin * math.sin(theta)
        notes.append('feet forward of what is under the seat')
    # the toes stop short of whatever stands on the floor in front of the seat (a table's foot), where the feet are
    stops = [u_ for dl, u_ in seat.get('feet_ahead') or () if abs(abs(dl) - span) <= SHOE[2] + .06]
    if stops:
        lim = min(stops) - body['toe'] - TOE_ROOM
        if ankle_u > lim:
            # as far back as the toes need, no further: flat on the floor if the shins leaning back as far as they
            # leaned forward is enough (a foot on the floor is as far behind the knee as it was ahead of it), and
            # otherwise further, on the toes, the heels lifted
            want = math.asin(_clamp((lim - knee_u) / shin, -1, 1))
            drop = knee_z - foot_z
            flat = -math.acos(_clamp(drop / shin, -1, 1)) if drop < shin else None
            back_ = flat if flat is not None and flat <= want else want
            au_ = knee_u + shin * math.sin(back_)
            ok = back_ >= TUCK - 1e-9 and au_ <= lim + 1e-9 and au_ >= heel_need - 1e-9
            if ok:
                theta = back_
                ankle_u = knee_u + shin * math.sin(theta)
                notes.append('feet drawn back from what stands in front of them')
            else:
                notes.append(f'no room for the feet: something stands on the floor {min(stops) - seat["front"]:.2f} in front of the seat')
    ankle_z = knee_z - shin * math.cos(theta)
    lift = max(0.0, ankle_z - foot_z)
    if lift > .002:
        notes.append(f'feet {lift:.2f} off the floor: toes down')
    toe = min(.6, math.atan2(min(lift, body['toe'] * .7), body['toe'])) if lift > .002 else 0.0
    lean = 0.0
    if recline and seat.get('back') is not None and soft > 0:
        gap = (u - body['pelvis_back']) - seat['back']
        if gap > .04:
            lean = -min(RECLINE_MAX, math.atan2(gap - .04, .9))
    return dict(u=u, z=root_z, joint_z=joint_z, alpha=alpha, theta=theta, knee=(knee_u, knee_z), ankle=(ankle_u, ankle_z),
                lift=lift, toe=toe, lean=lean, notes=notes)


def stand_point(body, seat, sol=None):
    """u where someone stands to sit on this seat, or stands after getting up: their feet where the seated feet will
    be, so sitting is the pelvis going back and down over still feet, not a slide."""
    sol = sol or seated(body, seat)
    return max(sol['ankle'][0], seat.get('base_front', seat['front']) + body['heel'] + .08,
               seat['front'] + body['shin_r'] + .06)


def sit_path(t, stand, sit):
    """The pelvis on its way down onto a seat (t from 0 standing to 1 seated), or up from it (t from 1 to 0). stand and
    sit are (u, z). The hips go back before they go down and the chest comes forward over the feet, the way a body
    keeps its balance; getting up is the same in reverse. Returns (u, z, forward lean in radians)."""
    t = _clamp(t, 0.0, 1.0)
    back = t * t * (3 - 2 * t)
    d = _clamp((t - .15) / .85, 0, 1)
    down = d * d * (3 - 2 * d)
    u = stand[0] + (sit[0] - stand[0]) * back
    z = stand[1] + (sit[1] - stand[1]) * down
    lean = .38 * math.sin(math.pi * t) ** 1.5
    return u, z, lean


def lap(body, sol, frac=.42):
    """Where a hand rests on a seated thigh: (forward from the hip joint, height of the thigh's top) at frac of its
    length, for the actor's own frame."""
    a = sol['alpha']
    fwd = body['thigh'] * frac * math.cos(a)
    z = sol['joint_z'] + body['thigh'] * frac * math.sin(a) + body['thigh_r'] * (1 - .15 * frac) / math.cos(a)
    return fwd, z


def personal_space(a, b):
    """How close the centres of two standing people may come: both footprints and a hand's width between."""
    return a.footprint() + b.footprint() + .08


# ---------------------------------------------------------------- feet on the floor
SHOE = (.166, .389, .14)     # a shoe from its ankle: back to the heel, forward to the toe, half its width (shoe.npz)


def _seg_dist(p1, q1, p2, q2):
    """The shortest distance between two line segments in the floor's plane -> (distance, nearest on the first,
    nearest on the second)."""
    d1 = (q1[0] - p1[0], q1[1] - p1[1])
    d2 = (q2[0] - p2[0], q2[1] - p2[1])
    r = (p1[0] - p2[0], p1[1] - p2[1])
    a, e = d1[0] * d1[0] + d1[1] * d1[1], d2[0] * d2[0] + d2[1] * d2[1]
    f = d2[0] * r[0] + d2[1] * r[1]
    if a < 1e-12 and e < 1e-12:
        s = t = 0.0
    elif a < 1e-12:
        s, t = 0.0, _clamp(f / e, 0.0, 1.0)
    else:
        c = d1[0] * r[0] + d1[1] * r[1]
        if e < 1e-12:
            t, s = 0.0, _clamp(-c / a, 0.0, 1.0)
        else:
            b = d1[0] * d2[0] + d1[1] * d2[1]
            den = a * e - b * b
            s = _clamp((b * f - c * e) / den, 0.0, 1.0) if den > 1e-12 else 0.0
            t = (b * s + f) / e
            if t < 0:
                t, s = 0.0, _clamp(-c / a, 0.0, 1.0)
            elif t > 1:
                t, s = 1.0, _clamp((b - c) / a, 0.0, 1.0)
    c1 = (p1[0] + d1[0] * s, p1[1] + d1[1] * s)
    c2 = (p2[0] + d2[0] * t, p2[1] + d2[1] * t)
    return math.hypot(c1[0] - c2[0], c1[1] - c2[1]), c1, c2


def footprint(c, yaw, shoe=SHOE):
    """A shoe on the floor as a capsule: the line from heel to toe it is drawn round, and its half width. c is the
    ankle; a foot points (sin yaw, -cos yaw)."""
    heel, toe, hw = shoe
    fx, fy = math.sin(yaw), -math.cos(yaw)
    return (c[0] - fx * (heel - hw), c[1] - fy * (heel - hw)), (c[0] + fx * (toe - hw), c[1] + fy * (toe - hw)), hw


def feet_gap(c1, y1, c2, y2, shoe=SHOE):
    """How far apart two shoes on the floor are (below zero: one is in the other) -> (gap, from the second towards
    the first)."""
    a1, b1, r = footprint(c1, y1, shoe)
    a2, b2, _ = footprint(c2, y2, shoe)
    d, p, q = _seg_dist(a1, b1, a2, b2)
    n = ((p[0] - q[0]) / d, (p[1] - q[1]) / d) if d > 1e-9 else (0.0, 0.0)
    return d - 2 * r, n


def _ang(a):
    return (a + math.pi) % (2 * math.pi) - math.pi


OUT_MAX = .25       # a stepping foot goes at most this far out of its way round the other one (12 cm)


def swing(A, B, ya, yb, O, yo, s, margin=.02, shoe=SHOE):
    """Where a stepping foot is at s (0..1 of its way from A to B, turning from pointing ya to yb) as it goes past the
    other foot standing at O (pointing yo): straight when it clears that foot by margin all the way, and otherwise out
    round it, furthest out where it would have come nearest. The feet never touch, cross or pass through each other.
    A step that would end on the other foot's far side cannot go round it this way; the engine never plans one (each
    foot keeps to its own side of the body walking and turning). -> (x, y, z), with z as A's."""
    z = A[2] if len(A) > 2 else 0.0
    ts = [i / 32 for i in range(1, 32)]

    def at(t, out=0.0, nw=(0.0, 0.0), tw=.5):
        h = math.sin(.5 * math.pi * (t / tw if t <= tw else (1 - t) / (1 - tw)))
        return (A[0] + (B[0] - A[0]) * t + nw[0] * out * h, A[1] + (B[1] - A[1]) * t + nw[1] * out * h), h

    def gaps(out=0.0, nw=(0.0, 0.0), tw=.5):
        return [(t,) + feet_gap(at(t, out, nw, tw)[0], ya + _ang(yb - ya) * t, O, yo, shoe) for t in ts]
    goal = margin + .004            # a little more than asked, so that it holds between the points measured too
    # never more room on the way than where the step starts and ends already have (a foot set down close beside the
    # other leaves close beside it): the way is kept clear of the other foot, not the feet of each other
    ends = min(feet_gap(A, ya, O, yo, shoe)[0], feet_gap(B, yb, O, yo, shoe)[0])
    goal = min(goal, ends - .001)
    margin = min(margin, goal)
    g0 = gaps()
    worst = min(g0, key=lambda g: g[1])
    if worst[1] >= margin:
        p = at(s)[0]
        return (p[0], p[1], z)
    tw = worst[0]
    # out to the side of the step's line away from the other foot (the side it starts on, if it heads straight at it):
    # never across its heel or its toe to get round it
    dx, dy = B[0] - A[0], B[1] - A[1]
    L = math.hypot(dx, dy) or 1.0
    left = (-dy / L, dx / L)
    side = (O[0] - A[0]) * left[0] + (O[1] - A[1]) * left[1]          # > 0: the other foot is on the step's left
    if abs(side) < .02:
        # heading straight at it: round it on the side of it the foot starts on (by that foot's own right)
        lat = (A[0] - O[0]) * math.cos(yo) + (A[1] - O[1]) * math.sin(yo)
        side = -(left[0] * math.cos(yo) + left[1] * math.sin(yo)) * (1 if lat >= 0 else -1)
    nw = (-left[0], -left[1]) if side > 0 else left
    # out until every point of the way clears it: measured on the way as it now goes, a few times over
    out, cur = 0.0, g0
    for _ in range(8):
        bad = [(t, g) for t, g, _n in cur if g < goal]
        if not bad or out >= OUT_MAX:
            break
        out = min(OUT_MAX, out + max((goal - g) / max(at(t, 1.0, nw, tw)[1], .2) for t, g in bad) * 1.05)
        cur = gaps(out, nw, tw)
    p = at(s, out, nw, tw)[0]
    return (p[0], p[1], z)
