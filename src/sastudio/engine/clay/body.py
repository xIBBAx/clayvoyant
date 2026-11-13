"""The body's physical rules: how a person of given proportions sits on a given seat, and how much room a body needs.

No bpy here (only math), so the film, the contact checks and the tests all share one definition, and the tests run
without Blender. Distances are set units (a person stands about 3.4 tall; one unit is about half a metre). Seats are
measured from the built set by the film (film.py: measure_seat); this module only reasons about the numbers.

Seat frame: `u` runs forward, the way a sitter faces, from the seat's origin (the middle of the seat); `z` is height
above the floor of the room. A seat is a dict:

    top         height of the sitting surface (measured: lumps and bevels included)
    soft        how far its cushion gives under a sitter (0 for wood and plastic)
    front       u of the seat's front edge
    base_front  u of the furthest-forward solid thing under the seat (the front of a sofa's base, a chair's front
                legs): heels and calves stay in front of it
    back        u of the backrest's front face, or None for a stool or a bench without one
    under       height of the underside of whatever is above the knees (a table top), or None
    ahead       u of the first solid thing in front of the seat at the height of the thighs (a desk's panel), or None
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
    heel_need = seat.get('base_front', seat['front']) + body['heel'] + HEEL_ROOM
    ankle_u = knee_u + shin * math.sin(theta)
    if ankle_u < heel_need:
        theta = min(SHIN_LEAN * 1.25, math.asin(_clamp((heel_need - knee_u) / shin, -1, 1)))
        ankle_u = knee_u + shin * math.sin(theta)
        notes.append('feet forward of what is under the seat')
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
