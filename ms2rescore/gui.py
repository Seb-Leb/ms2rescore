"""Graphical user interface for MS²Rescore using Gooey."""

import argparse
import ast
import json
import logging
import pprint
import multiprocessing


from gooey import Gooey, GooeyParser, local_resource_path
from ms2pip.ms2pipC import MODELS as ms2pip_models
from ms2rescore import MS2ReScore, package_data
from ms2rescore._exceptions import MS2RescoreError

try:
    import importlib.resources as pkg_resources
except ImportError:
    import importlib_resources as pkg_resources


logger = logging.getLogger(__name__)


with pkg_resources.path(package_data, "img") as img_dir:
    img_dir = local_resource_path(img_dir)


class MS2RescoreGUIError(MS2RescoreError):

    """MS²Rescore GUI error."""


@Gooey(
    program_name="MS²Rescore",
    program_description="Sensitive PSM rescoring with MS²PIP, DeepLC, and Percolator.",
    image_dir=img_dir,
    tabbed_groups=True,
    requires_shell=False,
    default_size=(760, 720),
)
def main():
    """Run MS²Rescore."""
    conf = _parse_arguments().__dict__
    conf = parse_settings(conf)
    rescore = MS2ReScore(parse_cli_args=False, configuration=conf, set_logger=True)
    rescore.run()


def _parse_arguments() -> argparse.Namespace:
    """Parse GUI arguments."""
    default_config = json.load(pkg_resources.open_text(package_data, "config_default.json"))
    ms2pip_mods = default_config["ms2pip"]["modifications"]

    parser = GooeyParser()
    general = parser.add_argument_group("General configuration")
    general.add_argument(
        "identification_file",
        metavar="Identification file (required)",
        type=str,
        help="Path to identification file (pin, mzid, msms.txt, tandem xml...)",
        widget="FileChooser",
        gooey_options={"full_width":True}
    )
    general.add_argument(
        "-m",
        metavar="Spectrum file directory",
        action="store",
        type=str,
        dest="mgf_path",
        help=(
            "Path to MGF file or directory with MGF files (default: derived from "
            "identification file)"
        ),
        widget="DirChooser",
    )
    general.add_argument(
        "-c",
        metavar="Configuration file",
        action="store",
        type=str,
        dest="config_file",
        help="Path to MS²Rescore configuration file (see online documentation)",
        widget="FileChooser",
    )
    general.add_argument(
        "-t",
        metavar="Temporary file directory",
        action="store",
        type=str,
        dest="tmp_path",
        help="Path to directory to place temporary files",
        widget="DirChooser",
    )
    general.add_argument(
        "-o",
        metavar="Output filename prefix",
        action="store",
        type=str,
        dest="output_filename",
        help="Name for output files (default: derive from identification file)",
        widget="FileSaver",
    )
    general.add_argument(
        "--pipeline",
        metavar="Select pipeline / search engine",
        action="store",
        type=str,
        dest="pipeline",
        help=(
            "Identification file pipeline to use, depends on the search engine used. "
            "By default, this is inferred from the input file extension."
        ),
        widget="Dropdown",
        default="infer",
        choices=["infer", "pin","maxquant", "msgfplus", "tandem", "peptideschaker", "peaks"]
    )
    general.add_argument(
        "-l",
        metavar="Logging level",
        action="store",
        type=str,
        dest="log_level",
        default="info",
        help="Controls the amount information that is logged.",
        widget="Dropdown",
        choices=["debug", "info", "warning", "error", "critical"],
    )

    maxquant_settings = parser.add_argument_group(
        "MaxQuant settings",
        (
            "MaxQuant uses two-letter labels to denote modifications in the msms.txt "
            "output. Additionally, fixed modifications are not listed at all. To "
            "correctly parse the msms.txt file, additional modification information "
            "needs to be provided below. Make sure MaxQuant was run without "
            "PSM-level FDR filtering; i.e. the FDR Threshold set at 1."
        )
    )
    maxquant_settings.add_argument(
        "--fixed_modifications",
        metavar="Fixed modifications",
        action="store",
        type=str,
        dest="fixed_modifications",
        default="C Carbamidomethyl",
        help=(
            "List all modifications set as fixed during the MaxQuant search. One "
            "modification per line, in the form of <amino acid one-letter code> "
            "<full modification name>, one per line, space-separated."
        ),
        widget="Textarea",
        gooey_options={
            "height":120
            }
    )
    maxquant_settings.add_argument(
        "--modification_mapping",
        metavar="Modification mapping",
        action="store",
        type=str,
        dest="modification_mapping",
        default=(
            "cm Carbamidomethyl\nox Oxidation\nac Acetyl\ncm Carbamidomethyl\n"
            "de Deamidated\ngl Gln->pyro-Glu"
        ),
        help=(
            "List all modification labels and their full names as listed in the "
            "MS²PIP modification definitions (see MS²PIP settings tab). One per line, "
            "space-separated."
        ),
        widget="Textarea",
        gooey_options={
            "height": 120
        },
    )

    ms2pip_settings = parser.add_argument_group(
        "MS²PIP settings"
    )
    ms2pip_settings.add_argument(
        "--ms2pip_model",
        metavar="MS²PIP model",
        type=str,
        dest="ms2pip_model",
        default="HCD2021",
        help="MS²PIP prediction model to use",
        widget="Dropdown",
        choices=ms2pip_models.keys(),
    )
    ms2pip_settings.add_argument(
        "--ms2pip_frag_error",
        metavar="MS2 error tolerance in Da",
        type=float,
        dest="ms2pip_frag_error",
        default=0.02,
        help="MS2 error tolerance in Da, for MS²PIP spectrum annotation",
        widget="DecimalField",
    )
    ms2pip_settings.add_argument(
        "--ms2pip_modifications",
        metavar="Modification definitions",
        action="store",
        type=str,
        dest="ms2pip_modifications",
        default=pprint.pformat(ms2pip_mods, compact=True, width=200),
        help=(
            "List of modification definition dictionaries for MS²PIP. See online "
            "documentation for more info."
        ),
        widget="Textarea",
        gooey_options={
            "full_width":True,
            "height": 240
        },
    )

    return parser.parse_args()

def parse_settings(config:dict) -> dict:
    "Parse non-general settings into one dict"

    parsed_config = {
        "general" : config,
        "maxquant_to_rescore": {},
        "ms2pip": {},
    }

    # MaxQuant configuration
    for conf_item in ["modification_mapping", "fixed_modifications"]:
        parsed_conf_item = parsed_config["general"].pop(conf_item)
        try:
            if parsed_conf_item:
                parsed_conf_item = parsed_conf_item.split("\n")
                parsed_conf_item = dict([tuple(x.split(" ")) for x in parsed_conf_item])
            else:
                parsed_conf_item = {}
            parsed_config["maxquant_to_rescore"][conf_item] = parsed_conf_item
        except Exception:
            raise MS2RescoreGUIError(
                "Invalid MaxQuant modification configuration. Make sure that the "
                "modification configuration fields are formatted correctly."
            )

    # MS²PIP configuration
    parsed_config["ms2pip"] = {
        "model": parsed_config["general"].pop("ms2pip_model"),
        "frag_error": parsed_config["general"].pop("ms2pip_frag_error"),
    }

    try:
        parsed_config["ms2pip"]["modifications"] =  ast.literal_eval(
            parsed_config["general"].pop("ms2pip_modifications")
        )
    except Exception:
        raise MS2RescoreGUIError(
            "Invalid MS²PIP modification configuration. Make sure that the "
            "modification configuration field is formatted correctly."
        )

    return parsed_config


if __name__ == "__main__":
    # Required for PyInstalller package (https://github.com/pyinstaller/pyinstaller/wiki/Recipe-Multiprocessing)
    # Avoids opening new windows upon multiprocessing
    multiprocessing.freeze_support()
    main()
