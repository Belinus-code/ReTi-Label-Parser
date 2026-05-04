#!/usr/bin/env python3
# Quick and dirty label-Parser for ReTi instruction set Emulator
# Author: Linus Meinders
# Inspired by Vorlesung Technische Informatik, SoSe 26
# Prof. Dr. Christoph Scholl, Universität Freiburg

import sys
import argparse


def getCode(file_path: str) -> list[str]:
    """
    Reads a file and returns its content as a list of strings,
    preserving newline characters.
    """
    lines = []
    try:
        with open(file_path, "r", encoding="utf-8") as file:
            for line in file:
                lines.append(line)
    except FileNotFoundError:
        print(f"Error: File '{file_path}' does not exist.")
        sys.exit(1)
    except Exception as e:
        print(f"An unexpected error occurred while reading: {e}")
        sys.exit(1)

    return lines


def cleanCode(code: list[str]) -> list[str]:
    """
    Removes empty lines, lines consisting only of comments (#),
    and trims leading/trailing whitespace from each line.
    """
    cleaned_lines = []
    for line in code:
        stripped_line = line.strip()
        # Skip empty lines or lines that are strictly comments
        if not stripped_line or stripped_line.startswith("#"):
            continue

        cleaned_lines.append(stripped_line)
    return cleaned_lines


def findLabels(code: list[str]) -> list[tuple[int, str, list[str]]]:
    """
    Parses code lines, assigning indices to instructions while
    ignoring labels in the count and attaching them to the next valid instruction.
    Comments and empty lines are assigned an index of -1.
    """
    result = []
    instruction_idx = 0
    pending_labels = []

    for line in code:
        stripped = line.strip()

        # 1. Check if it's a label (one word ending with ':')
        if stripped.endswith(":") and len(stripped.split()) == 1:
            pending_labels.append(stripped[:-1])

        # 2. Check if it's a comment or an empty line
        elif not stripped or stripped.startswith("#"):
            result.append((-1, line, []))

        # 3. It's a regular code instruction
        else:
            result.append((instruction_idx, line, pending_labels))
            pending_labels = []  # Clear buffer
            instruction_idx += 1

    return result


def replaceLabels(code: list[tuple[int, str, list[str]]]) -> list[str]:
    """
    Replaces label names with relative offsets.
    Supports standard JUMP/JUMPC syntax and generic *LABEL syntax anywhere.
    """
    label_map = {}
    for instr_idx, _, labels in code:
        if instr_idx != -1:
            for lbl in labels:
                label_map[lbl] = instr_idx

    result = []

    for i, (instr_idx, original_line, _) in enumerate(code):
        line_num = i + 1
        if instr_idx == -1:
            result.append(original_line)
            continue

        modified_line = original_line
        parts = original_line.split()

        # 1. Handle legacy JUMP/JUMPC (without asterisk)
        command = parts[0].upper() if parts else ""
        legacy_target = None
        if command == "JUMP" and len(parts) >= 2 and not parts[1].startswith("*"):
            legacy_target = parts[1]
        elif command == "JUMPC" and len(parts) >= 3 and not parts[2].startswith("*"):
            legacy_target = parts[2]

        if legacy_target:
            if legacy_target not in label_map:
                raise ValueError(
                    f"Error in line {line_num}: Label '{legacy_target}' not found."
                )
            offset = label_map[legacy_target] - instr_idx
            modified_line = modified_line.replace(legacy_target, str(offset), 1)

        # 2. Handle generic *LABEL syntax (anywhere in the line)
        # We look for all words starting with '*'
        for word in parts:
            if word.startswith("*"):
                label_name = word[1:]  # Remove the '*'
                if label_name not in label_map:
                    raise ValueError(
                        f"Error in line {line_num}: Referenced label '{label_name}' not found."
                    )

                offset = label_map[label_name] - instr_idx
                # Replace the exact occurrence of *label with the numeric offset
                modified_line = modified_line.replace(word, str(offset), 1)

        result.append(modified_line)

    return result


def saveCode(code: list[str], file_path: str):
    """
    Writes the list of strings back to the disk.
    If the strings already contain newlines, they are written as-is.
    """
    try:
        with open(file_path, "w", encoding="utf-8") as file:
            for line in code:
                # Ensure we don't add extra newlines if they already exist
                if line.endswith("\n"):
                    file.write(line)
                else:
                    file.write(line + "\n")

        print(f"File successfully saved to '{file_path}'.")

    except Exception as e:
        print(f"An Error Occurred while saving: {e}")
        sys.exit(1)


def main():
    """
    Main entry point for the CLI tool. Handles argument parsing
    and orchestrates the label replacement process.
    """
    parser = argparse.ArgumentParser(description="Tool to parse ReTi-Code with Labels")

    parser.add_argument("path", help="Path to the input file")
    parser.add_argument("-o", "--output", help="Path to the output file", default=None)
    parser.add_argument(
        "-c",
        "--clean",
        action="store_true",
        help="Clean leading whitespaces and comments",
    )

    args = parser.parse_args()

    # Workflow
    raw_code = getCode(args.path)

    try:
        organized_code = findLabels(raw_code)
        processed_code = replaceLabels(organized_code)

        if args.clean:
            processed_code = cleanCode(processed_code)

        output_path = args.output if args.output is not None else args.path
        saveCode(processed_code, output_path)

    except ValueError as e:
        print(e)
        sys.exit(1)


if __name__ == "__main__":
    main()
