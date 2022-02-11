"""

Run:
- `python3 setup.py install` to install `dietpdf` globally
- or `python3 setup.py install --home=~` to install `dietpdf` locally

You may need to run `pip3 install .` to install the package.

"""

__author__ = "Frédéric BISSON"
__copyright__ = "Copyright 2022, Frédéric BISSON"
__credits__ = ["Frédéric BISSON"]
__license__ = "mit"
__maintainer__ = "Frédéric BISSON"
__email__ = "zigazou@protonmail.com"

import argparse
import logging
import sys
import re

from dietpdf.parser.PDFParser import PDFParser
from dietpdf.processor.PDFProcessor import PDFProcessor
from dietpdf.item import PDFObject, PDFDictionary
from dietpdf.info import all_source_codes, convert_objstm
from dietpdf import __version__

_logger = logging.getLogger("dietpdf")


def diet(input_pdf_name: str):
    """Reduce PDF file size

    Args:
      input_pdf_name (str): the PDF to reduce
    """

    output_pdf_name = re.sub("\.pdf$", ".opt.pdf", input_pdf_name)

    # Read PDF.
    _logger.info("Reading %s" % input_pdf_name)
    pdf_file_content = open(input_pdf_name, "rb").read()
    processor = PDFProcessor()
    parser = PDFParser(processor)
    parser.parse(pdf_file_content)
    processor.end_parsing()
    convert_objstm(processor.tokens)

    source_codes = all_source_codes(processor.tokens)

    any_object = lambda _, item: type(item) == PDFObject
    for _, object in processor.tokens.find(any_object):
        object.source_code = object.obj_num in source_codes

    # Optimize streams.
    _logger.info("Start optimizing objects and streams")
    def any_object_with_stream(_, item):
        return type(item) == PDFObject and item.has_stream()

    for _, object in processor.tokens.find(any_object_with_stream):
        _logger.info("Optimizing object %d stream" % object.obj_num)
        object.optimize_stream()

    # Write PDF.
    _logger.info("Writing optimized PDF in %s" % output_pdf_name)
    open(output_pdf_name, "wb").write(processor.encode())

    processor.pretty_print()


def parse_args(args):
    """Parse command line parameters

    Args:
      args ([str]): command line parameters as list of strings

    Returns:
      :obj:`argparse.Namespace`: command line parameters namespace
    """
    parser = argparse.ArgumentParser(description="Aims at reducing PDF size")

    parser.add_argument(
        "--version",
        action="version",
        version="dietpdf {ver}".format(ver=__version__),
    )

    parser.add_argument(
        dest="input_pdf",
        help="the PDF for which to reduce size",
        type=str,
        metavar="<input PDF>"
    )

    parser.add_argument(
        "-v",
        "--verbose",
        dest="loglevel",
        help="set loglevel to INFO",
        action="store_const",
        const=logging.INFO,
    )

    parser.add_argument(
        "-vv",
        "--very-verbose",
        dest="loglevel",
        help="set loglevel to DEBUG",
        action="store_const",
        const=logging.DEBUG,
    )

    return parser.parse_args(args)


def setup_logging(loglevel):
    """Setup basic logging

    Args:
      loglevel (int): minimum loglevel for emitting messages
    """
    logformat = "[%(asctime)s] %(levelname)s:%(name)s:%(message)s"
    logging.basicConfig(
        level=loglevel,
        stream=sys.stdout,
        format=logformat,
        datefmt="%Y-%m-%d %H:%M:%S"
    )


def main(args):
    """Main entry point allowing external calls

    Args:
      args ([str]): command line parameter list
    """
    args = parse_args(args)
    setup_logging(args.loglevel)
    _logger.info("Start optimizing PDF %s" % args.input_pdf)

    diet(args.input_pdf)


def run():
    """Entry point for console_scripts"""
    main(sys.argv[1:])


if __name__ == "__main__":
    run()
