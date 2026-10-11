#!/usr/bin/env python3
# Quick and dirty label-Parser for ReTi instruction set Emulator
# Author: Linus Meinders
# Inspired by Vorlesung Technische Informatik, SoSe 26
# Prof. Dr. Christoph Scholl, Universität Freiburg

import sys
import argparse
import os
import re


# Matches comments, string literals and char literals (left untouched) or any other text
_TOKEN_RE = re.compile(r"""(#.*$|"[^"]*"|'(?:\\.|[^'])')|([^#"']+|.)""", re.DOTALL)


def applyDefines(line: str, defines: dict[str, str]) -> str:
    """
    Replaces every defined name (whole word) with its value.
    Comments, "strings" and 'c' char literals are left untouched.
    """
    if not defines:
        return line
    names = sorted(defines, key=len, reverse=True)
    name_re = re.compile(r"(?<!\w)(?:" + "|".join(map(re.escape, names)) + r")(?!\w)")

    def replaceInCode(match: re.Match) -> str:
        if match.group(1) is not None:
            return match.group(1)
        return name_re.sub(lambda m: defines[m.group(0)], match.group(2))

    return _TOKEN_RE.sub(replaceInCode, line)


def getCode(file_path: str, defines: dict[str, str] | None = None) -> list[str]:
    """
    Reads a file and supports #include "filename" directives.
    Inserts the content of included files at the correct position.
    Supports plain aliases via "#define NAME VALUE" (no conditionals, no arguments);
    NAME is replaced by VALUE in all following lines (including included files).
    Also replaces characters in single quotes (e.g. 'a') with their (ASCII value + 100).
    """
    lines = []
    if defines is None:
        defines = {}
    base_dir = os.path.dirname(os.path.abspath(file_path))

    try:
        with open(file_path, "r", encoding="utf-8") as file:
            for line in file:
                stripped = line.strip()
                if stripped.startswith('#include "') and stripped.endswith('"'):
                    include_filename = stripped[10:-1]
                    include_path = os.path.join(base_dir, include_filename)
                    lines.extend(getCode(include_path, defines))
                elif re.match(r"#define\s", stripped):
                    parts = re.sub(r"\s*#.*$", "", stripped[len("#define"):]).split(None, 1)
                    if len(parts) != 2:
                        raise ValueError(
                            f"Invalid #define in {file_path}: '{stripped}' (expected '#define NAME VALUE')"
                        )
                    # Resolve earlier aliases in the value, so chains like Y -> X -> 5 work
                    defines[parts[0]] = applyDefines(parts[1], defines)
                else:
                    line = applyDefines(line, defines)
                    # 1. Match lines containing double-quoted strings (e.g., PRINTC "Hi!\n")
                    string_match = re.search(r'^(.*?)"([^"]+)"(.*)$', line)

                    if string_match:
                        prefix = string_match.group(1)   # Everything before the quote (e.g., "    PRINTC ")
                        raw_str = string_match.group(2)  # The string content (e.g., "Hi!\n")
                        suffix = string_match.group(3)   # Everything after the quote (e.g., " # print greeting")
                        
                        # Decode escape sequences like \n to real actual characters
                        decoded_str = raw_str.encode('utf-8').decode('unicode_escape')
                        
                        for char in decoded_str:
                            # Re-escape special characters so they look like '\n' for the assembler
                            if char == '\n':
                                char_repr = r"'\n'"
                            elif char == '\t':
                                char_repr = r"'\t'"
                            elif char == '\r':
                                char_repr = r"'\r'"
                            elif char == "'":
                                char_repr = r"'\''"
                            else:
                                char_repr = f"'{char}'"
                            
                            # Construct the expanded line for each character
                            expanded_line = f"{prefix}{char_repr}{suffix}"
                            
                            # 2. Translate single characters (now supporting escapes) to +100 addresses
                            processed_line = re.sub(
                                r"'(\\(?:n|t|r|')|.)'", 
                                lambda match: str(ord(match.group(1).encode('utf-8').decode('unicode_escape')) + 100), 
                                expanded_line
                            )
                            lines.append(processed_line)
                    else:
                        # Standard processing for lines without double quotes
                        processed_line = re.sub(
                            r"'(\\(?:n|t|r|')|.)'", 
                            lambda match: str(ord(match.group(1).encode('utf-8').decode('unicode_escape')) + 100), 
                            line
                        )
                        lines.append(processed_line)

    except FileNotFoundError:
        print(f"Error: File '{file_path}' does not exist.")
        sys.exit(1)
    except Exception as e:
        print(f"An unexpected error occurred while reading {file_path}: {e}")
        sys.exit(1)

    return lines


def cleanCode(code: list[str]) -> list[str]:
    """
    Removes empty lines, lines consisting only of comments (#).
    """
    cleaned_lines = []
    for line in code:
        stripped_line = line.strip()
        # Skip empty lines or lines that are strictly comments
        if not stripped_line or stripped_line.startswith("#"):
            continue

        cleaned_lines.append(stripped_line)
    return cleaned_lines


def cleanIndent(code: list[str]) -> list[str]:
    """
    Trims leading/trailing whitespace and indentations from each line.
    """
    cleaned_lines = []
    for line in code:
        stripped_line = line.strip()
        cleaned_lines.append(stripped_line)
    return cleaned_lines


def findLabels(code: list[str]) -> list[tuple[int, str, list[str]]]:
    """
    Parses code lines, assigning indices to instructions while
    ignoring labels in the count and attaching them to the next valid instruction.
    Returns the parsed result and prevents duplicates internally.
    """
    result = []
    instruction_idx = 0
    pending_labels = []

    # NEW: Keep track of all global labels to detect duplicates!
    global_label_dict = {}

    for line_idx, line in enumerate(code):
        stripped = line.strip()

        # 1. Check if it's a label (one word ending with ':')
        if stripped.endswith(":") and len(stripped.split()) == 1:
            label_name = stripped[:-1]

            # --- THE TRIPWIRE FOR DUPLICATE LABELS ---
            if label_name in global_label_dict:
                print(f"\n[ASSEMBLER ERROR] Namespace Collision!")
                print(f"Das Label '{label_name}:' wurde mehrfach definiert!")
                print(
                    f"Vorherige Definition zeigte auf Instruktion {global_label_dict[label_name]}"
                )
                print(
                    f"Neue Definition gefunden bei Zeile {line_idx} im kompilierten Code."
                )
                print(
                    "Behebung: Nutze eindeutige Präfixe für deine Labels (z.B. MAIN_LOOP: statt LOOP:)."
                )
                sys.exit(1)

            pending_labels.append(label_name)
            # Temporarily store the index it WILL point to
            global_label_dict[label_name] = instruction_idx

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
    Replaces label names with relative offsets and preserves column alignment.
    Strictly uses the legacy Python interpreter syntax (JUMP target / JUMPC cond target).
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

        # 1. Handle JUMP and JUMPC (with whitespace-separated conditions)
        command = parts[0].upper() if parts else ""
        legacy_target = None

        if command == "JUMP" and len(parts) >= 2 and not parts[1].startswith("*"):
            target_candidate = parts[1]
            # Check if it's already a raw number (relative jump)
            try:
                int(target_candidate)
                is_numeric = True
            except ValueError:
                is_numeric = False

            if not is_numeric:
                legacy_target = target_candidate

        elif command == "JUMPC" and len(parts) >= 3 and not parts[2].startswith("*"):
            target_candidate = parts[2]
            # Check if it's already a raw number (relative conditional jump)
            try:
                int(target_candidate)
                is_numeric = True
            except ValueError:
                is_numeric = False

            if not is_numeric:
                legacy_target = target_candidate

        if legacy_target:
            if legacy_target not in label_map:
                raise ValueError(
                    f"Error in line {line_num}: Label '{legacy_target}' not found."
                )

            offset = label_map[legacy_target] - instr_idx
            offset_str = str(offset)

            # Padding berechnen: Länge des Labels - Länge der Zahl
            padding = " " * max(0, len(legacy_target) - len(offset_str))
            modified_line = modified_line.replace(
                legacy_target, offset_str + padding, 1
            )

        # 2. Handle generic *LABEL syntax
        for word in parts:
            if word.startswith("*"):
                label_name = word[1:]
                if label_name not in label_map:
                    raise ValueError(
                        f"Error in line {line_num}: Referenced label '{label_name}' not found."
                    )

                offset = label_map[label_name] - instr_idx
                offset_str = str(offset)

                # Spaltenbündigkeit beibehalten (inklusive Sternchen-Länge)
                padding = " " * max(0, len(word) - len(offset_str))
                modified_line = modified_line.replace(word, offset_str + padding, 1)

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
        help="Clean comments and empty lines",
    )
    parser.add_argument(
        "-i",
        "--indentation",
        action="store_true",
        help="Clean leading whitespaces and indentations",
    )

    args = parser.parse_args()

    # Workflow
    raw_code = getCode(args.path)

    try:
        organized_code = findLabels(raw_code)
        processed_code = replaceLabels(organized_code)

        if args.clean:
            processed_code = cleanCode(processed_code)
        if args.indentation:
            processed_code = cleanIndent(processed_code)

        output_path = args.output if args.output is not None else args.path
        saveCode(processed_code, output_path)

    except ValueError as e:
        print(e)
        sys.exit(1)


if __name__ == "__main__":
    main()
