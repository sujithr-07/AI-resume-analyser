import sys
from pathlib import Path

from resume_reader import SUPPORTED_TEXT_EXT, summarize_resume


def main() -> None:
    folder = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data/resumes")
    if not folder.is_dir():
        print(f"Folder '{folder}' not found. Run: python scripts/create_sample_resumes.py")
        return

    exts = {".pdf"} | SUPPORTED_TEXT_EXT
    files = sorted(p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in exts)
    if not files:
        print(f"No resumes found in '{folder}'.")
        return

    total_chars = total_tokens = ok = 0
    for path in files:
        r = summarize_resume(path)
        if r["error"]:
            print(f'{r["name"]}: Error - {r["error"]}')
        else:
            print(f'{r["name"]}: {r["chars"]} characters, {r["tokens"]} tokens')
            total_chars += r["chars"]
            total_tokens += r["tokens"]
            ok += 1

    print(f"\n{ok}/{len(files)} parsed | {total_chars} characters | {total_tokens} tokens")


if __name__ == "__main__":
    main()