import argparse
def parse(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", default="status")
    return vars(parser.parse_args(argv))
