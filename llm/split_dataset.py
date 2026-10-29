import json
import random

INPUT_FILE = "final_dataset.jsonl"

TRAIN_FILE = "train.jsonl"
VAL_FILE = "validation.jsonl"
TEST_FILE = "test_generated.jsonl"

SEED = 42

TRAIN_SIZE = 2700
VAL_SIZE = 300
TEST_SIZE = 300


def load_dataset(filename):
    data = []

    with open(filename, "r", encoding="utf-8") as f:
        for line in f:
            data.append(json.loads(line))

    return data


def save_dataset(filename, data):
    with open(filename, "w", encoding="utf-8") as f:
        for example in data:
            f.write(json.dumps(example, ensure_ascii=False) + "\n")


data = load_dataset(INPUT_FILE)

if len(data) != TRAIN_SIZE + VAL_SIZE + TEST_SIZE:
    raise ValueError(
        f"Expected 3300 examples, found {len(data)}"
    )

random.seed(SEED)
random.shuffle(data)

train = data[:TRAIN_SIZE]
validation = data[TRAIN_SIZE:TRAIN_SIZE + VAL_SIZE]
test = data[TRAIN_SIZE + VAL_SIZE:]

save_dataset(TRAIN_FILE, train)
save_dataset(VAL_FILE, validation)
save_dataset(TEST_FILE, test)

print("Dataset split complete")
print("=" * 35)
print(f"Total      : {len(data)}")
print(f"Train      : {len(train)}")
print(f"Validation : {len(validation)}")
print(f"Test       : {len(test)}")
print(f"Seed       : {SEED}")
print("=" * 35)
