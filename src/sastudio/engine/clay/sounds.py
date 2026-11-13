"""What makes a sound in a scene, read from the scene's own plan (film.py runs this in its 'events' mode).

Nothing here poses a puppet or draws: the plan already knows where every foot comes down, when a body arrives on a
seat or leaves it, when a door opens and when it shuts, when a laptop's lid closes, when a chair is drawn in and when
hands are on a keyboard. Each of those is reported once for the whole scene, on the scene's own clock (frames from its
start), with what it happens on and who does it. sastudio.sound turns the reports into sound.

Run inside Blender with film.py's names in G; returns a list of plain dicts (kind, frame, who, thing, pos, surface
object, params)."""

import math


def _floor_under(G, x, y):
    """The name of what a foot standing at (x, y) stands on (a rug, a plank, a tile...), or None."""
    hit = G['surface_under'](x, y, .35, .6, which=True)
    return hit[1].name if hit and hit[1] is not None else None


def _in_room(G, x, y):
    half = (G['STG'].get('half') or 9.5) + .5
    return abs(x) <= half


def footfalls(G, a, frames):
    """Every frame where one of a's feet comes down: its lift was above the floor at the frame before and is on it now.
    Walks, turns on the spot and changes of mind are all steps of the same plan (acting.Actor.locate)."""
    A = G['A']
    out = []
    prev = None
    st = a.st['stance']
    for f in frames:
        pos, feet, _yaw, amt = a.locate(f)
        if feet:
            mv, sd, side, lift = feet[:4]
            now = {side: (mv, float(lift)), -side: (sd, 0.0)}
        else:
            psi = a.stance(f)
            now = {s: (A.standing_foot(pos, s, psi, st), 0.0) for s in (-1, 1)}
        if prev is not None:
            for s in (-1, 1):
                (p0, l0), (p1, l1) = prev[1][s], now[s]
                if l0 > 1e-4 and l1 <= 1e-4:
                    x, y = float(p1[0]), float(p1[1])
                    if not _in_room(G, x, y):
                        continue            # behind a wall, out of the set: not heard
                    speed = math.hypot(pos[0] - prev[0][0], pos[1] - prev[0][1]) / max(1e-6, a.st.get('speed', .075))
                    out.append(dict(kind='footstep', frame=f, who=a.name, pos=[round(x, 3), round(y, 3), 0.0],
                                    surface_obj=_floor_under(G, x, y), params=dict(side='L' if s < 0 else 'R',
                                                                                   speed=round(min(2.0, speed), 3))))
        prev = (pos, now)
    return out


def seat_moments(G, a, frames):
    """A body arriving on its seat (sitting reaches nine tenths of the way down) and leaving it (back up past that)."""
    out = []
    last = None
    for f in frames:
        s = a.seat_amt(f)
        if last is not None:
            ST = a.seat_info(f) if hasattr(a, 'seat_info') else None
            if last < .9 <= s:
                kind = 'sit'
            elif s < .9 <= last:
                kind = 'stand'
            else:
                kind = None
            if kind:
                p = a.locate(f)[0]
                soft = float(ST.get('soft', 0.0)) if isinstance(ST, dict) else 0.0
                wood = isinstance(ST, dict) and ST.get('kind') in ('chair', 'bench', 'stool')
                out.append(dict(kind=kind, frame=f, who=a.name, thing=(ST or {}).get('name') if isinstance(ST, dict) else None,
                                pos=[round(float(p[0]), 3), round(float(p[1]), 3), 0.0], params=dict(soft=soft, wood=wood)))
        last = s
    return out


def chair_moves(G, frames):
    """A chair drawn in under somebody or pushed back as they stand: the frames it moves, how far and on what (where
    film.chair_off puts it, the same as the picture)."""
    out = []
    for ch in G.get('CHAIRS') or []:
        offs = [G['chair_off'](ch, f) for f in frames]
        moving = None
        for i in range(1, len(offs)):
            d = abs(offs[i] - offs[i - 1])
            if d > 1e-3 and moving is None:
                moving = i - 1
            elif d <= 1e-3 and moving is not None:
                dist = abs(offs[i - 1] - offs[moving])
                if dist > .02:
                    x, y = ch['pos']
                    out.append(dict(kind='scrape', frame=frames[moving], frames=frames[i - 1] - frames[moving], thing='chair',
                                    pos=[round(float(x), 3), round(float(y), 3), 0.0], surface_obj=_floor_under(G, x, y),
                                    params=dict(distance=round(dist, 3))))
                moving = None
    return out


def doors(G):
    """A door's latch as it starts to open, and its panel and latch as it shuts (film.door_at: 12 frames to open, 14 to
    close)."""
    leaf = G['STG'].get('door')
    if leaf is None:
        return []
    x, y = float(leaf.location.x), float(leaf.location.y)
    out = []
    for o, c in G.get('DOORS') or []:
        out.append(dict(kind='door_open', frame=int(o), frames=12, thing='door', pos=[round(x, 3), round(y, 3), 0.0]))
        out.append(dict(kind='door_close', frame=int(c) + 13, thing='door', pos=[round(x, 3), round(y, 3), 0.0]))
    return out


def props(G):
    """Things that move on a track (direction.props): a lid that closes is heard as it comes down, one that opens as it
    lifts; a thing slid across a table is heard while it slides."""
    out = []
    for o, lid, loc0, _rot0, _lid0, moves in (G.get('TRACKS') or {}).values():
        x, y = float(loc0.x), float(loc0.y)
        for mv in moves:
            n = int(mv.get('frames', 14))
            name = mv.get('thing')
            if mv['do'] == 'close' and lid is not None:
                out.append(dict(kind='laptop_close', frame=int(mv['frame']) + n - 1, thing=name, pos=[round(x, 3), round(y, 3), 0.0]))
            elif mv['do'] == 'open' and lid is not None:
                out.append(dict(kind='laptop_open', frame=int(mv['frame']), thing=name, pos=[round(x, 3), round(y, 3), 0.0]))
            elif mv['do'] == 'slide':
                out.append(dict(kind='scrape', frame=int(mv['frame']), frames=n, thing=name, pos=[round(x, 3), round(y, 3), 0.0],
                                surface_obj='table', params=dict(light=True)))
    return out


def typing(G, a, frames):
    """Hands on a keyboard: from the frame the gesture says 'typing' while seated at a desk, until it says something
    else or the person gets up."""
    out = []
    start = None
    for f in frames:
        cur = a.state(f)[1][1]
        on = cur.get('g') == 'typing' and a.seat_amt(f) > .98
        if on and start is None:
            start = f
        elif not on and start is not None:
            out.append(dict(kind='typing', frame=start, frames=f - start, who=a.name))
            start = None
    if start is not None:
        out.append(dict(kind='typing', frame=start, frames=frames[-1] - start + 1, who=a.name))
    return out


def scene_events(G):
    """Everything in the scene that makes a sound, in frame order."""
    frames = G['FRAMES']
    out = []
    shoes = {}
    for a in G['PERF'].actors.values():
        if getattr(a.P, 'guest', False):
            shoes[a.name] = 'hard'
        else:
            m = getattr(a.P, 'm', {}) or {}
            shoes[a.name] = m.get('shoe_style', 'flat')
        out += footfalls(G, a, frames)
        if getattr(a, 'body', None) is not None:
            out += seat_moments(G, a, frames)
            out += typing(G, a, frames)
    out += chair_moves(G, frames)
    out += doors(G)
    out += props(G)
    for e in out:
        if e.get('who') in shoes:
            e.setdefault('params', {})['shoe'] = shoes[e['who']]
            bm = getattr(G['PERF'].actors[e['who']].P, 'm', {}) or {}
            # how heavy a body is, from its build: hip width and shoulders against an average body's
            e['params']['weight'] = round(max(.6, min(1.6, (float(bm.get('hw', .35)) / .35) ** 1.5 * (float(bm.get('hip', 1.45)) / 1.45))), 3)
    return sorted(out, key=lambda e: (e['frame'], e['kind'], e.get('who') or ''))
