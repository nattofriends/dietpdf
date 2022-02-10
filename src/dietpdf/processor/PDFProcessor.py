__author__ = "Frédéric BISSON"
__copyright__ = "Copyright 2022, Frédéric BISSON"
__credits__ = ["Frédéric BISSON"]
__license__ = "mit"
__maintainer__ = "Frédéric BISSON"
__email__ = "zigazou@protonmail.com"

from logging import getLogger

from dietpdf.token import (
    PDFNumber, PDFListOpen, PDFDictOpen, PDFCommand, PDFListClose,
    PDFDictClose, PDFComment
)

from dietpdf.item import (
    PDFReference, PDFObjectID, PDFList, PDFDictionary, PDFXrefSubSection,
    PDFObject, PDFTrailer, PDFStartXref, PDFXref, PDFStream
)

from dietpdf.pdf import PDF
from .TokenProcessor import TokenProcessor


_logger = getLogger("PDFProcessor")

class PDFProcessor(TokenProcessor):
    """A PDF processor

    A PDF processor is a stack machine. It recognizes some command and executes
    them, changing the stack state.
    """
    def __init__(self):
        self.tokens = PDF()

    def _generate_reference(self):
        gen_num = int(self.tokens.pop().value)
        obj_num = int(self.tokens.pop().value)
        self.tokens.push(PDFReference(obj_num, gen_num))

    def _generate_object_id(self):
        gen_num = int(self.tokens.pop().value)
        obj_num = int(self.tokens.pop().value)
        self.tokens.push(PDFObjectID(obj_num, gen_num))

    def _generate_list(self):
        items = []
        while self.tokens.stack_size() > 0:
            current = self.tokens.pop()

            if isinstance(current, PDFListOpen):
                items.reverse()
                self.tokens.push(PDFList(items))
                return

            items.append(current)

    def _generate_dict(self):
        key_values = {}

        while self.tokens.stack_size() > 0:
            value = self.tokens.pop()

            if isinstance(value, PDFDictOpen):
                self.tokens.push(PDFDictionary(key_values))
                return

            key = self.tokens.pop()
            key_values[key] = value

    def _generate_object(self):
        stream = self.tokens.pop()

        if isinstance(stream, PDFStream):
            value = self.tokens.pop()
        else:
            value = stream
            stream = None

        object_id = self.tokens.pop()
        object = PDFObject(object_id.obj_num, object_id.gen_num, value, stream)
        self.tokens.push(object)

    def _convert_startxref(self):
        any_startxref_command = lambda _, item: (
            type(item) == PDFCommand and
            item.command == b"startxref"
        )

        for offset, _ in self.tokens.find(any_startxref_command):
            self.tokens.pop(offset)
            self.tokens.insert(
                offset,
                PDFStartXref(self.tokens.pop(offset).value)
            )

    def _convert_xref(self):
        any_xref_command = lambda _, item: (
            type(item) == PDFCommand and
            item.command == b"xref"
        )

        for offset, _ in self.tokens.find(any_xref_command):
            self.tokens.pop(offset)

            xref = PDFXref()

            while isinstance(self.tokens.stack_at(offset), PDFNumber):
                base = self.tokens.pop(offset).value
                count = self.tokens.pop(offset).value
                subsection = PDFXrefSubSection(base, count)

                for _ in range(count):
                    ref_offset = self.tokens.pop(offset).value
                    ref_new = self.tokens.pop(offset).value
                    ref_type = self.tokens.pop(offset).command.decode('ascii')

                    subsection.entries.append((ref_offset, ref_new, ref_type))

                xref.subsections.append(subsection)

            self.tokens.insert(offset, xref)

    def _convert_trailer(self):
        any_trailer_command = lambda _, item: (
            type(item) == PDFCommand and
            item.command == b"trailer"
        )

        for offset, _ in self.tokens.find(any_trailer_command):
            self.tokens.pop(offset)
            self.tokens.insert(offset, PDFTrailer(self.tokens.pop(offset)))

    def end_parsing(self):
        """Converts remaining items on the stack.
        
        The `startxref`, `xref` and `trailer` elements of a PDF file do not
        follow a stack principle. They must therefore be recognized when all the
        parsing has been done.

        Without calling this method, the processor state is inconsistent.
        """
        self._convert_startxref()
        self._convert_xref()
        self._convert_trailer()

    def push(self, item):
        """Push an item onto the processor's stack.
        
        Pushing item on stack may result in their interpretation. For example,
        pushing `1` then `0` then `R` on the stack will make the processor
        replace them by a `PDFReference` object.

        Comments other than `%PDF-*` or `%%EOF` will be completely ignored.
        """
        if type(item) == PDFCommand and item.command == b"R":
            self._generate_reference()
        elif type(item) == PDFCommand and item.command == b"obj":
            self._generate_object_id()
        elif type(item) == PDFCommand and item.command == b"endobj":
            self._generate_object()
        elif type(item) == PDFListClose:
            self._generate_list()
        elif type(item) == PDFDictClose:
            self._generate_dict()
        elif type(item) == PDFComment:
            # Discard unneeded comments
            if item.content[:5] == b"%PDF-" or item.content[:5] == b"%%EOF":
                self.tokens.push(item)
        else:
            self.tokens.push(item)

    def update_xref(self, original: bytes):
        """Update all the XRef tables.

        When changes are made on objects of a PDF, chances are that the XRef
        tables will contain wrong offsets. This method corrects them.

        :param original: The original PDF file content
        :type original: bytes
        """
        # Force calculation of actual offset for every item in the stack
        pdf = self.encode()

        # Changing offsets in an XREF table won't change its size
        any_xref_table = lambda _, item: type(item) == PDFXref
        xrefs = self.tokens.find_all(any_xref_table)

        any_startxref = lambda _, item: type(item) == PDFStartXref
        startxrefs = self.tokens.find_all(any_startxref)

        for xref in xrefs:
            for subsection in xref.subsections:
                base = subsection.base
                count = subsection.count
                for index in range(count):
                    (ref_offset, ref_new, ref_type) = subsection.entries[index]
                    object = self.tokens.get(base + index)

                    subsection.entries[index] = (
                        object.item_offset if ref_type == "n" else ref_offset,
                        ref_new,
                        ref_type
                    )

        # Update last startxref item
        if xrefs and startxrefs:
            startxrefs[-1].offset = xrefs[0].item_offset

        # Update the first object if it contains linearization information
        any_linearized = lambda _, item: (
            type(item) == PDFObject and
            type(item.value) == PDFDictionary and
            b"Linearized" in item.value
        )

        linearized = self.tokens.find_first(any_linearized)
        if linearized:
            items = linearized.value

            # Update file length
            linearized.value[b"L"] = PDFNumber(str(len(pdf)).encode('ascii'))

            # Update offset of end of first page
            old_end = int(linearized.value[b"E"])
            object_id = int(original[old_end:old_end + 10].split()[0])

            linearized.value[b"E"] = PDFNumber(
                str(self.tokens.get(object_id).item_offset).encode('ascii')
            )

            # Update offset of first entry in main xref table
            if xrefs:
                linearized.value[b"T"] = PDFNumber(
                    str(xrefs[0].item_offset +
                        xrefs[0].first_entry_offset).encode('ascii')
                )

        # Update first trailer
        any_trailer = lambda _, item: type(item) == PDFTrailer
        trailer = self.tokens.find_first(any_trailer)
        if trailer and xrefs:
            trailer.dictionary[b"Prev"] = (
                PDFNumber(str(xrefs[0].item_offset).encode('ascii'))
            )

    def encode(self) -> bytes:
        """Encode a PDF from the current state of the processor

        :return: A complete PDF file content ready to be written in a file
        :rtype: bytes
        """
        def any_item(_a, _b): return True

        output = b""
        offset = 0

        for _, item in self.tokens.find(any_item):
            item.item_offset = offset
            item_encoded = item.encode()
            offset += len(item_encoded)
            output += item_encoded

        return output
