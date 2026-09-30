"""Launch the frozen runner into a separate directory, preserving reported outputs."""
import argparse
from pathlib import Path
import sys

import run_llms


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', choices=list(run_llms.MODELS), required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    destination = args.output_dir.resolve()
    if destination == run_llms.OUT.resolve():
        parser.error('Choose a new directory; comparison/llm contains the reported run.')
    destination.mkdir(parents=True, exist_ok=True)
    run_llms.OUT = destination
    sys.argv = [str(Path(run_llms.__file__)), '--model', args.model]
    run_llms.main()


if __name__ == '__main__':
    main()
