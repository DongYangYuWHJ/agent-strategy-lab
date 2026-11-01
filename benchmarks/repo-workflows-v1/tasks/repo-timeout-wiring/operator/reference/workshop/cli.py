import argparse
def parse(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", default="status")
    parser.add_argument("--timeout-ms", default=None)
    return vars(parser.parse_args(argv))
