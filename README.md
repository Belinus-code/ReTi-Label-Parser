# ReTi Label-Parser

A lightweight CLI tool to convert symbolic labels in ReTi assembly code into relative jump distances. Specifically designed for the ReTi instruction set emulator used in the "Technische Informatik" course at the University of Freiburg.

## Features

* **Label Resolution**: Automatically replaces labels in `JUMP` and `JUMPC` instructions with relative offsets ($Target - Current\_Line$).
* **Manual Offset Access**: Use the `*` prefix (e.g., `*Label`) to access the relative distance outside of jump instructions (e.g., in `LOADI`).
* **Preserve Formatting**: Keeps comments and indentation by default to maintain readability.
* **Code Cleaning**: Optional mode to remove empty lines, comments, and leading whitespaces for "pure" machine code output.
* **Flexible Output**: Overwrite the source file or save results to a dedicated output path.

## Installation

Ensure you have Python 3 installed. Clone this repository and optionally make the script executable:
```bash
chmod +x labels.py
```

## Usage

```bash
python3 labels.py <PATH_TO_FILE> [OPTIONS]
```

### Options

| Option | Long Form | Description | 
| ----- | ----- | ----- | 
| `-o` | `--output` | Path to the output file. If not provided, the source file will be overwritten. | 
| `-c` | `--clean` | Removes all comments, empty lines, and leading indentation for "clean" code. | 
| `-h` | `--help` | Shows the help message and exits. | 

Usage of `-c` is recomended! 

### Examples

**Basic usage (resolves labels and overwrites file):**
```bash
python3 labels.py program.reti
```

**Save to a new file and clean the code:**
```bash
python3 labels.py input.reti -o output.reti -c
```

## Label Syntax

Labels must be a single word followed by a colon (e.g., `LOOP:`, `Label1:`). They are always resolved to **relative distances** ($Target - Current\_Line$).

### Implicit Resolution (Jumps)
In jump instructions, the label name is replaced directly by the calculated offset.
```assembly
LOOP:
    SUBI 1
    JUMPC > LOOP  # Resolved to: JUMPC > -1 (Target 0 - Current 1)
```

### Explicit Resolution (`*` Operator)
To use a relative offset in other instructions, prefix the label with `*`. This is particularly useful for dynamic calls where the offset is stored first.
```assembly
    LOADI *Method # Loads relative distance to 'Method' into ACC[cite: 1]
    STORE 1024    # Store for later calculation
    ...
Method:
    ADDI 10
```

---

**Author:** Linus Meinders  
**Inspiration:** Prof. Dr. Christoph Scholl, University of Freiburg (SoSe 26)
