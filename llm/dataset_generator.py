import json
import random
import sys


NOTES = [
    "C3", "D3", "E3", "F3", "G3", "A3", "B3",
    "C4", "D4", "E4", "F4", "G4", "A4", "B4",
    "C5", "D5", "E5", "F5", "G5", "A5", "B5"
]

DURATIONS = [
    "whole",
    "half",
    "quarter",
    "eighth",
    "sixteenth"
]

MELODY_DURATIONS = [
    "half",
    "quarter",
    "eighth"
]

RHYTHM_DURATIONS = [
    "quarter",
    "eighth",
    "sixteenth"
]

INSTRUMENTS = [
    "Piano",
    "Guitar",
    "Violin",
    "Flute",
    "Drums",
    "Bass",
    "Trumpet",
    "Cello",
    "Clarinet",
    "Saxophone",
    "Synth",
    "Organ"
]

TEMPOS = [60, 80, 90, 100, 110, 120, 130, 140, 160, 180]


def play_description(note, duration):
    return random.choice([
        f"Play {note} for a {duration} note.",
        f"Play a {note} {duration} note.",
        f"Add {note} with {duration} duration.",
        f"Use {note} for one {duration} note.",
        f"Play {note}, lasting one {duration} note."
    ])


def rest_description(duration):
    return random.choice([
        f"Rest for a {duration} note.",
        f"Add a {duration} rest.",
        f"Pause for a {duration} note.",
        f"Leave a {duration} note of silence.",
        f"Add silence for one {duration} note."
    ])


def tempo_description(tempo):
    return random.choice([
        f"Set the tempo to {tempo} BPM.",
        f"Use {tempo} BPM.",
        f"Set the music speed to {tempo} BPM.",
        f"Play at {tempo} beats per minute.",
        f"Set the song to {tempo} BPM."
    ])


def instrument_description(instrument):
    return random.choice([
        f"Use {instrument} for the music.",
        f"Play using {instrument}.",
        f"Choose {instrument} as the instrument.",
        f"Use the {instrument} instrument.",
        f"Set the instrument to {instrument}."
    ])


def variable_name(prefix):
    return prefix + str(random.randint(1, 99))


def generate_simple():
    statements = []
    descriptions = []

    instrument = random.choice(INSTRUMENTS)
    tempo = random.choice(TEMPOS)

    statements.append(f"INSTRUMENT {instrument};")
    descriptions.append(instrument_description(instrument))

    statements.append(f"TEMPO {tempo};")
    descriptions.append(tempo_description(tempo))

    count = random.randint(2, 4)

    for _ in range(count):
        note = random.choice(NOTES)
        duration = random.choice(MELODY_DURATIONS)

        statements.append(f"PLAY {note} {duration};")
        descriptions.append(play_description(note, duration))

    return statements, descriptions


def generate_melody():
    statements = []
    descriptions = []

    instrument = random.choice([
        "Piano",
        "Guitar",
        "Violin",
        "Flute",
        "Cello",
        "Synth"
    ])

    tempo = random.choice(TEMPOS)

    statements.append(f"INSTRUMENT {instrument};")
    descriptions.append(instrument_description(instrument))

    statements.append(f"TEMPO {tempo};")
    descriptions.append(tempo_description(tempo))

    count = random.randint(3, 7)

    for _ in range(count):
        note = random.choice(NOTES)
        duration = random.choice(MELODY_DURATIONS)

        statements.append(f"PLAY {note} {duration};")
        descriptions.append(play_description(note, duration))

    return statements, descriptions


def generate_rhythm():
    statements = []
    descriptions = []

    tempo = random.choice(TEMPOS)

    statements.append(f"TEMPO {tempo};")
    descriptions.append(tempo_description(tempo))

    count = random.randint(4, 8)

    for _ in range(count):
        if random.random() < 0.30:
            duration = random.choice(RHYTHM_DURATIONS)

            statements.append(f"REST {duration};")
            descriptions.append(rest_description(duration))
        else:
            note = random.choice(NOTES)
            duration = random.choice(RHYTHM_DURATIONS)

            statements.append(f"PLAY {note} {duration};")
            descriptions.append(play_description(note, duration))

    return statements, descriptions


def generate_variable_program():
    statements = []
    descriptions = []

    note_var = variable_name("note")
    duration_var = variable_name("duration")

    note = random.choice(NOTES)
    duration = random.choice(MELODY_DURATIONS)

    statements.append(f"LET {note_var} = {note};")
    descriptions.append(
        f"Store the note {note} in a variable called {note_var}."
    )

    statements.append(f"LET {duration_var} = {duration};")
    descriptions.append(
        f"Store the {duration} duration in a variable called {duration_var}."
    )

    statements.append(f"PLAY {note_var} {duration_var};")
    descriptions.append(
        "Play the stored note using the stored duration."
    )

    if random.random() < 0.5:
        note2 = random.choice(NOTES)

        statements.append(f"{note_var} = {note2};")
        descriptions.append(
            f"Change {note_var} to {note2}."
        )

        statements.append(f"PLAY {note_var} {duration_var};")
        descriptions.append(
            "Play the updated note using the same duration."
        )

    return statements, descriptions

def generate_repeat_program():
    statements = []
    descriptions = []

    repeat_count = random.randint(2, 6)

    if random.random() < 0.5:
        instrument = random.choice([
            "Piano",
            "Guitar",
            "Violin",
            "Flute",
            "Cello",
            "Synth"
        ])

        statements.append(f"INSTRUMENT {instrument};")
        descriptions.append(instrument_description(instrument))

    if random.random() < 0.5:
        tempo = random.choice(TEMPOS)

        statements.append(f"TEMPO {tempo};")
        descriptions.append(tempo_description(tempo))

    note = random.choice(NOTES)
    duration = random.choice(MELODY_DURATIONS)

    statements.append(f"REPEAT {repeat_count}")
    statements.append(f"    PLAY {note} {duration};")
    statements.append("ENDREPEAT")

    descriptions.append(
        random.choice([
            f"Repeat the {note} {duration} note {repeat_count} times.",
            f"Play {note} for a {duration} note, repeating it {repeat_count} times.",
            f"Repeat {note} for {repeat_count} repetitions.",
            f"Play the {note} {duration} note repeatedly {repeat_count} times."
        ])
    )

    return statements, descriptions

def generate_for_program():
    statements = []
    descriptions = []

    start = random.randint(1, 3)
    end = random.randint(start + 1, start + 6)

    if random.random() < 0.5:
        instrument = random.choice([
            "Piano",
            "Guitar",
            "Violin",
            "Flute",
            "Cello",
            "Synth"
        ])

        statements.append(f"INSTRUMENT {instrument};")
        descriptions.append(instrument_description(instrument))

    if random.random() < 0.5:
        tempo = random.choice(TEMPOS)

        statements.append(f"TEMPO {tempo};")
        descriptions.append(tempo_description(tempo))

    note = random.choice(NOTES)
    duration = random.choice(MELODY_DURATIONS)

    statements.append(f"FOR i = {start} TO {end}")
    statements.append(f"    PLAY {note} {duration};")
    statements.append("ENDFOR")

    iterations = end - start + 1

    descriptions.append(
        random.choice([
            f"Use a loop from {start} to {end} to play {note}.",
            f"Loop from {start} through {end}, playing {note} each time.",
            f"Play {note} repeatedly using a loop from {start} to {end}.",
            f"Repeat the {note} {duration} note for {iterations} iterations using a FOR loop."
        ])
    )

    return statements, descriptions


def generate_if_program():
    statements = []
    descriptions = []

    variable = variable_name("value")
    value = random.randint(1, 10)
    threshold = random.randint(1, 10)

    note_true = random.choice(NOTES)
    note_false = random.choice(NOTES)

    duration_true = random.choice(MELODY_DURATIONS)
    duration_false = random.choice(MELODY_DURATIONS)

    operator = random.choice([">", "<", ">=", "<=", "==", "!="])

    statements.append(f"LET {variable} = {value};")

    descriptions.append(
        f"Store the number {value} in a variable called {variable}."
    )

    statements.append(
        f"IF {variable} {operator} {threshold} THEN"
    )

    descriptions.append(
        f"If {variable} is {operator} {threshold}, play {note_true} "
        f"for a {duration_true} note."
    )

    statements.append(
        f"    PLAY {note_true} {duration_true};"
    )

    statements.append("ELSE")

    descriptions.append(
        f"Otherwise, play {note_false} for a {duration_false} note."
    )

    statements.append(
        f"    PLAY {note_false} {duration_false};"
    )

    statements.append("ENDIF")

    return statements, descriptions

def generate_function_program():
    statements = []
    descriptions = []

    function_name = random.choice([
        "Riff",
        "Melody",
        "NotePattern",
        "Phrase",
        "Beat"
    ])

    note1 = random.choice(NOTES)
    note2 = random.choice(NOTES)
    duration1 = random.choice(MELODY_DURATIONS)
    duration2 = random.choice(MELODY_DURATIONS)

    statements.append(
        f"FUNCTION {function_name}(note, duration)"
    )
    statements.append(
        "    PLAY note duration;"
    )
    statements.append(
        "ENDFUNCTION"
    )

    descriptions.append(
        random.choice([
            f"Create a function called {function_name} that plays a note "
            f"using a specified duration.",
            f"Define a reusable {function_name} pattern that accepts a note "
            f"and duration.",
            f"Create a {function_name} function for playing notes."
        ])
    )

    statements.append(
        f"CALL {function_name}({note1}, {duration1});"
    )

    descriptions.append(
        f"Use {function_name} to play {note1} for a {duration1} note."
    )

    statements.append(
        f"CALL {function_name}({note2}, {duration2});"
    )

    descriptions.append(
        f"Then use {function_name} to play {note2} for a {duration2} note."
    )

    return statements, descriptions

def generate_track_program():
    statements = []
    descriptions = []

    track_name = random.choice([
        "Melody",
        "Bass",
        "Lead",
        "Harmony"
    ])

    statements.append(f"TRACK {track_name}")

    descriptions.append(
        random.choice([
            f"Create a track called {track_name}.",
            f"Add a {track_name} track.",
            f"Create the {track_name} musical track."
        ])
    )

    if random.random() < 0.5:
        instrument = random.choice(INSTRUMENTS)

        statements.append(f"    INSTRUMENT {instrument};")
        descriptions.append(
            f"Use {instrument} for the {track_name} track."
        )

    count = random.randint(2, 5)

    for _ in range(count):
        note = random.choice(NOTES)
        duration = random.choice(MELODY_DURATIONS)

        statements.append(
            f"    PLAY {note} {duration};"
        )

        descriptions.append(
            f"Play {note} for a {duration} note."
        )

    statements.append("ENDTRACK")

    return statements, descriptions


def generate_parallel_program():
    statements = []
    descriptions = []

    tempo = random.choice(TEMPOS)

    statements.append(f"TEMPO {tempo};")
    descriptions.append(f"Set the tempo to {tempo} BPM.")

    tracks = [
        ("Melody", random.choice(["Piano", "Violin", "Flute", "Synth"])),
        ("Bass", random.choice(["Bass", "Cello", "Guitar"])),
    ]

    statements.append("PARALLEL")

    descriptions.append(
        "Play the following musical tracks simultaneously."
    )

    for track_name, instrument in tracks:
        statements.append(f"    TRACK {track_name}")

        statements.append(
            f"        INSTRUMENT {instrument};"
        )

        descriptions.append(
            f"Use {instrument} for the {track_name} track."
        )

        count = random.randint(2, 4)

        for _ in range(count):
            note = random.choice(NOTES)
            duration = random.choice([
                "quarter",
                "half",
                "eighth"
            ])

            statements.append(
                f"        PLAY {note} {duration};"
            )

            descriptions.append(
                f"Play {note} for a {duration} note "
                f"on the {track_name} track."
            )

        statements.append("    ENDTRACK")

    statements.append("ENDPARALLEL")

    return statements, descriptions


def generate_program():
    program_type = random.choice([
        "simple",
        "melody",
        "melody",
        "rhythm",
        "variable",
        "repeat",
        "for",
        "if",
        "function",
        "track",
        "parallel",
        "parallel"
    ])

    if program_type == "simple":
        return generate_simple()

    if program_type == "melody":
        return generate_melody()

    if program_type == "rhythm":
        return generate_rhythm()

    if program_type == "variable":
        return generate_variable_program()

    if program_type == "repeat":
        return generate_repeat_program()
    
    if program_type == "for":
        return generate_for_program()

    if program_type == "if":
        return generate_if_program()

    if program_type == "function":
        return generate_function_program()

    if program_type == "track":
        return generate_track_program()

    return generate_parallel_program()



def build_instruction(descriptions):
    return (
        "Create a SymphonyLang music program: "
        + " ".join(descriptions)
    )


def generate_example():
    statements, descriptions = generate_program()

    return {
        "instruction": build_instruction(descriptions),
        "output": "\n".join(statements)
    }


def generate_dataset(count, output_file):
    with open(output_file, "w", encoding="utf-8") as f:
        for _ in range(count):
            example = generate_example()
            f.write(json.dumps(example) + "\n")

    print(f"Generated {count} examples.")
    print(f"Saved to: {output_file}")


if __name__ == "__main__":
    count = 20
    output_file = "dataset_v3.jsonl"

    if len(sys.argv) >= 2:
        count = int(sys.argv[1])

    if len(sys.argv) >= 3:
        output_file = sys.argv[2]

    generate_dataset(count, output_file)    