import argparse
import importlib
import os
import sys
from typing import Optional, Sequence

from cowbird import __meta__
from cowbird.cli.utils import ParserMaker, ParserRunner, get_logger_parser, subparser_help
from cowbird.utils import get_logger

LOGGER = get_logger(__name__,
                    message_format="%(asctime)s - %(levelname)s - %(message)s",
                    datetime_format="%d-%b-%y %H:%M:%S", force_stdout=False)


def main(args: Optional[Sequence[str]] = None) -> Optional[int]:
    """
    Automatically groups all sub-helper CLI listed in :py:mod:`cowbird.cli` as a common ``cowbird`` CLI entrypoint.

    Dispatches the provided arguments to the appropriate sub-helper CLI as requested. Each sub-helper CLI must implement
    functions ``make_parser`` and ``main`` to generate the arguments and dispatch them to the corresponding caller.
    """
    parser = argparse.ArgumentParser(description=f"Execute {__meta__.__package__} CLI operations.")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__meta__.__version__}",
                        help="Prints the version of the application.")
    subparsers = parser.add_subparsers(title="Helper", dest="helper", required=True,
                                       description="Name of the helper to execute.")
    helpers_dir = os.path.dirname(__file__)
    helper_mods = os.listdir(helpers_dir)
    helpers = {}
    log = get_logger_parser()
    for module_item in sorted(helper_mods):
        helper_path = os.path.join(helpers_dir, module_item)
        if os.path.isfile(helper_path) and "__init__" not in module_item and module_item.endswith(".py"):
            helper_name = module_item.replace(".py", "")
            helper_root = "cowbird.cli"
            helper_module = importlib.import_module(f"{helper_root}.{helper_name}", helper_root)
            parser_maker: ParserMaker = getattr(helper_module, "make_parser", None)
            helper_runner: ParserRunner = getattr(helper_module, "main", None)
            if parser_maker and helper_runner:
                # add help disabled otherwise conflicts with this main helper's help
                helper_parser = parser_maker([log], [parser.prog])
                subparsers.add_parser(helper_name, parents=[helper_parser], add_help=False,
                                      **subparser_help(helper_parser.description, helper_parser))
                helpers[helper_name] = {"caller": helper_runner, "parser": helper_parser}
    args = args or sys.argv[1:]         # same as was parse args does, but we must provide them to subparser
    ns = parser.parse_args(args=args)   # if 'helper' is unknown, auto prints the help message with exit(2)
    helper_name = vars(ns).pop("helper")
    if not helper_name:
        parser.print_help()
        return 0
    helper_args = args[1:]
    helper_runner = helpers[helper_name]["caller"]
    helper_parser = helpers[helper_name]["parser"]
    result = helper_runner(helper_args, helper_parser, ns)
    return 0 if result is None else result


if __name__ == "__main__":
    main()
