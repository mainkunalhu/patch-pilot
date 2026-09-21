"""Phase 6 stub: SWE-style eval harness (DeepEval + sandbox)."""
import argparse


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--limit", type=int, default=5)
    args = p.parse_args()
    print(f"eval-quick stub: would run {args.limit} bugs (Phase 6)")


if __name__ == "__main__":
    main()
