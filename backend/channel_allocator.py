"""
channel_allocator.py
Assigns each TRACK a MIDI channel (0-15) such that no two tracks that are
declared to play SIMULTANEOUSLY (i.e. grouped inside the same PARALLEL
block) ever share a channel.

THIS IS THE SAME ALGORITHM FAMILY AS REGISTER ALLOCATION IN REAL COMPILERS.
Real compilers must assign a small number of physical CPU registers to
many variables, making sure two variables that are "alive" at the same
time never get the same register. They solve this with GRAPH COLORING:
    1. Build an "interference graph": one node per variable (here: per
       track), with an edge between two nodes if they're alive at the
       same time (here: declared to play simultaneously).
    2. Color the graph so that connected nodes never share a color.
       Each distinct color = one register (here: one MIDI channel).

We use a simple GREEDY coloring algorithm: real compilers often use more
sophisticated coloring (Chaitin's algorithm, Briggs' optimistic coloring),
but greedy coloring demonstrates the exact same underlying idea and is
easy to verify by hand for a report.

Channel 9 is reserved for percussion by the General MIDI standard, so any
track named "Drums" is pinned to channel 9 up front and excluded from the
graph coloring process entirely (it can't conflict with anything else
since it's on its own dedicated channel).
"""

from ast_nodes import ParallelBlock, TrackStmt, InstrumentStmt
from instruments import is_percussion

DRUM_CHANNEL = 9
AVAILABLE_CHANNELS = [c for c in range(16) if c != DRUM_CHANNEL]  # 15 usable channels


class ChannelConflictError(Exception):
    pass


def _is_drum_track(track_stmt: TrackStmt) -> bool:
    if is_percussion(track_stmt.name):
        return True
    for s in track_stmt.body:
        if isinstance(s, InstrumentStmt) and is_percussion(s.name):
            return True
    return False


def collect_parallel_groups(program):
    """Scans the top-level program statements and returns a list of
    track-name-groups, one list per PARALLEL block found.
    Example return: [['Piano', 'Bass', 'Drums'], ['Flute', 'Cello']]
    """
    groups = []
    for stmt in program.statements:
        if isinstance(stmt, ParallelBlock):
            groups.append([t.name for t in stmt.tracks])
        elif isinstance(stmt, TrackStmt):
            # A standalone TRACK (not in any PARALLEL block) doesn't
            # conflict with anything - it's its own group of one.
            groups.append([stmt.name])
    return groups


def build_interference_graph(groups):
    """
    Builds the interference graph as an adjacency dict: track_name -> set
    of other track names it conflicts with (i.e. must NOT share a channel).

    Two tracks interfere if and only if they appear together in the SAME
    group (i.e. the same PARALLEL block).
    """
    graph = {}

    def ensure_node(name):
        if name not in graph:
            graph[name] = set()

    for group in groups:
        for name in group:
            ensure_node(name)
        # Every pair of tracks within the same group interferes.
        for i in range(len(group)):
            for j in range(len(group)):
                if i != j:
                    graph[group[i]].add(group[j])

    return graph


def greedy_color(graph):
    """
    Greedy graph coloring: process nodes one at a time (here, in a fixed
    order), and assign each one the LOWEST-numbered channel not already
    used by any of its neighbors.

    Returns a dict: track_name -> channel_number.
    "Drums" is handled specially beforehand and is never passed in here.
    """
    channel_of = {}
    # Sort nodes by how many neighbors they have (most-constrained first) -
    # a common, simple heuristic that tends to produce fewer total colors.
    nodes_by_degree = sorted(graph.keys(), key=lambda n: -len(graph[n]))

    for node in nodes_by_degree:
        used_by_neighbors = {channel_of[n] for n in graph[node] if n in channel_of}
        for channel in AVAILABLE_CHANNELS:
            if channel not in used_by_neighbors:
                channel_of[node] = channel
                break
        else:
            raise ChannelConflictError(
                f"Ran out of MIDI channels while coloring track '{node}' - "
                f"too many simultaneous tracks (max {len(AVAILABLE_CHANNELS)})"
            )

    return channel_of


def allocate_channels(program):
    """
    Full pipeline: AST -> interference graph -> greedy coloring -> channel map.
    Automatically pins any track named 'Drums' (or using percussion instruments) to the reserved channel 9.
    """
    drum_tracks = set()
    for stmt in program.statements:
        if isinstance(stmt, ParallelBlock):
            for t in stmt.tracks:
                if _is_drum_track(t):
                    drum_tracks.add(t.name)
        elif isinstance(stmt, TrackStmt):
            if _is_drum_track(stmt):
                drum_tracks.add(stmt.name)

    groups = collect_parallel_groups(program)

    filtered_groups = []
    for group in groups:
        filtered = [name for name in group if name not in drum_tracks]
        if filtered:
            filtered_groups.append(filtered)

    graph = build_interference_graph(filtered_groups)
    channel_map = greedy_color(graph)

    for name in drum_tracks:
        channel_map[name] = DRUM_CHANNEL

    return channel_map, graph


def print_allocation_report(groups, graph, channel_map):
    print("PARALLEL groups found:")
    for g in groups:
        print(" ", g)

    print("\nInterference graph (who conflicts with whom):")
    for node, neighbors in graph.items():
        print(f"  {node}: conflicts with {sorted(neighbors) if neighbors else '(none)'}")

    print("\nFinal channel assignment:")
    for name, ch in sorted(channel_map.items(), key=lambda kv: kv[1]):
        print(f"  {name:10s} -> channel {ch}")

    # Verification: confirm no two conflicting tracks share a channel.
    print("\nVerifying no conflicts share a channel...")
    ok = True
    for node, neighbors in graph.items():
        for neighbor in neighbors:
            if channel_map.get(node) == channel_map.get(neighbor):
                print(f"  ❌ CONFLICT: {node} and {neighbor} both got channel {channel_map[node]}")
                ok = False
    if ok:
        print("  ✅ No conflicts - allocation is valid.")


if __name__ == "__main__":
    from lexer import Lexer
    from parser import Parser

    sample = """
    PARALLEL
        TRACK Piano
            PLAY C4 quarter;
        ENDTRACK
        TRACK Bass
            PLAY C2 quarter;
        ENDTRACK
        TRACK Drums
            PLAY C1 quarter;
        ENDTRACK
    ENDPARALLEL

    PARALLEL
        TRACK Flute
            PLAY E4 quarter;
        ENDTRACK
        TRACK Cello
            PLAY G2 quarter;
        ENDTRACK
    ENDPARALLEL
    """

    tokens, _ = Lexer(sample).tokenize()
    ast, errs = Parser(tokens).parse()
    print("Parse errors:", errs)
    print()

    groups = collect_parallel_groups(ast)
    channel_map, graph = allocate_channels(ast)
    print_allocation_report(groups, graph, channel_map)