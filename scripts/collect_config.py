"""Collect an explicit config without exposing runner flags to the game SDK."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'src'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True)
    parser.add_argument('--task', required=True)
    parser.add_argument('--limit', type=int, default=5)
    parser.add_argument('--worker-index', type=int, default=0)
    parser.add_argument('--workers', type=int, default=1)
    args = parser.parse_args()
    if args.limit <= 0 or args.workers <= 0 or not 0 <= args.worker_index < args.workers:
        parser.error('Use a positive limit/workers and 0 <= worker-index < workers.')
    sys.argv = [sys.argv[0]]
    from civstudy.runner import collect
    collect(args.task, args.config, args.limit, args.worker_index, args.workers)


if __name__ == '__main__':
    main()
