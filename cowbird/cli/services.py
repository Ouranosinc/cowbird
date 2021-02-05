#!/usr/bin/env python3
"""
Cowbird CLI helper to execute service operations.
"""
import argparse
import logging
import json
import yaml
from typing import TYPE_CHECKING

from cowbird.api.services.utils import get_services
from cowbird.constants import get_constant
from cowbird.utils import get_app_config, get_logger

if TYPE_CHECKING:
    from typing import Any, Optional, Sequence

LOGGER = get_logger(__name__,
                    message_format="%(asctime)s - %(levelname)s - %(message)s",
                    datetime_format="%d-%b-%y %H:%M:%S", force_stdout=False)


def print_format(data, fmt):
    if fmt == "yaml":
        print(yaml.safe_dump(data, allow_unicode=True, indent=2, sort_keys=False))
    else:
        print(json.dumps(data, indent=4, ensure_ascii=False))


def make_parser():
    # type: () -> argparse.ArgumentParser
    parser = argparse.ArgumentParser(description="Service commands.")
    parser.add_argument("-c", "--config", help="INI configuration file to employ.",
                        default=get_constant("COWBIRD_INI_FILE_PATH", raise_missing=False, raise_not_set=False))
    parser.add_argument("-f", "--format", choices=["json", "yaml"], help="Output format of the command.")
    parser.add_argument("-q", "--quiet", help="Suppress informative logging.")
    mode = parser.add_subparsers(title="Commands", dest="command", description="Command to run on services.")
    mode.add_parser("list")
    return parser


def main(args=None, parser=None, namespace=None):
    # type: (Optional[Sequence[str]], Optional[argparse.ArgumentParser], Optional[argparse.Namespace]) -> Any
    if not parser:
        parser = make_parser()
    args = parser.parse_args(args=args, namespace=namespace)
    LOGGER.setLevel(logging.WARNING if args.quiet else logging.DEBUG)
    LOGGER.debug("Getting configuration")
    config = get_app_config({"cowbird.ini_file_path": args.config})
    if args.command == "list":
        services = get_services(config)
        svc_json = {"services": [svc.json() for svc in services]}
        print_format(svc_json, args.format)
    return 0


if __name__ == "__main__":
    main()
