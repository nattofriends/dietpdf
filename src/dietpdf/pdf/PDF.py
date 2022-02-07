__author__ = "Frédéric BISSON"
__copyright__ = "Copyright 2022, Frédéric BISSON"
__credits__ = ["Frédéric BISSON"]
__license__ = "mit"
__maintainer__ = "Frédéric BISSON"
__email__ = "zigazou@protonmail.com"

from ..item import (
    PDFReference, PDFList, PDFDictionary, PDFName, PDFObject, PDFItem
)


class DuplicateError(Exception):
    """Exception raised by the PDF object when trying to push an already
    existing PDFObject.
    """
    pass


class PDF:
    """A PDF document

    A PDF document which can be read or written.
    """

    def __init__(self):
        self.stack = []
        self.objects = {}

    def push(self, item: PDFItem):
        """Push a PDFItem.

        Any number of PDFItem may be pushed but PDFObject may only be pushed
        once.

        :param item:
        :type item: PDFItem or any subclass of PDFItem
        :raise TypeError: If `item` is not a PDFItem or any subclass of PDFItem
        :raise DuplicateError: If `item` is an object that has already been
            pushed.
        """
        if not isinstance(item, PDFItem):
            raise TypeError("expected PDFItem or any subclass")

        if type(item) == PDFObject and item.obj_num in self.objects:
            raise DuplicateError("object has already been pushed")

        self.stack.append(item)

        if isinstance(item, PDFObject):
            self.objects[item.obj_num] = item

    def pop(self, index=-1) -> PDFItem:
        """Pop the last pushed item.

        :param index: The index of the item to pop, the last one if None
        :type index: int
        :return: The last pushed item
        :rtype: PDFItem or any subclass of PDFItem
        :raise IndexError: If there is no more PDFItem to pop
        """
        try:
            item = self.stack.pop(index)
        except IndexError:
            raise IndexError("pop from empty PDF")

        # Remove the item from the objects
        if isinstance(item, PDFObject) and item.obj_num in self.objects:
            del(self.objects[item.obj_num])

        return item

    def stack_size(self) -> int:
        """Returns the stack size of the PDF

        :return: Stack size of the PDF
        :rtype: int
        """
        return len(self.stack)

    def get(self, obj_num: int, path=[]) -> PDFItem:
        """Given an object given a starting object number and a path.

        If any part of the path does not point to a valid PDFItem, it returns
        None.

        The part of the path may be either:

          - an `int` which represents an index in a `PDFList`
          - an `str` or `PDFName` which a key in a `PDFDictionary`

        Any value which would be a `PDFReference` will automatically be
        transformed into the object pointed at.

        :param obj_num: The object number.
        :type obj_num: int or PDFReference or anything convertible to int
        :param path: A path described by a sequence of subpath.
        :type path: list
        :return: The specified object (subclass of PDFItem) or None if the path
            is not valid.
        :rtype: PDFItem or any subclass of PDFItem or None

        """
        assert type(path) == list

        # Normalize the object number.
        if isinstance(obj_num, PDFReference):
            obj_num = obj_num.obj_num
        else:
            obj_num = int(obj_num)

        # Check if the object is known.
        if obj_num not in self.objects:
            return None

        object = self.objects[obj_num]

        # No more path to follow, this is the final destination.
        if path == []:
            return object

        value = None
        if isinstance(object.value, PDFDictionary):
            path_elem = PDFName(path[0])

            if path_elem in object:
                value = object[path_elem]
        elif isinstance(object.value, PDFList):
            # Index must be an int in the correct range.
            if type(path[0]) == int and \
                    path[0] >= 0 and path[0] < len(object.value):
                value = object[path[0]]

        if value == None:
            return None

        if len(path) > 1 or type(value) == PDFReference:
            return self.get(value, path[1:])
        else:
            return value

    def find(self, select:callable, start:int=0):
        """Find an item in the stack according to a predicate.

        The predicate should have the following signature:

            predicate(index: int, item: PDFItem) -> bool

        Where:

          - index is the index of the item in the stack, not its object number
          - item is a PDFItem or any subclass
          - the predicate must return True if the item meets the criteria

        :param select: The predicate
        :type select: function
        :param start: the starting index
        :type start: int
        :raise TypeError: If the predicate is not a function
        """
        if not callable(select):
            raise TypeError("select must be a function which returns a boolean")

        for index in range(start, len(self.stack)):
            item = self.stack[index]

            if select(index, item):
                yield (index, item)

    def find_all(self, select:callable, start:int=0) -> list:
        """Find an item in the stack according to a predicate.

        See the `find` method for information about the predicate.

        :param select: The predicate
        :type select: function
        :param start: the starting index
        :type start: int
        :raise TypeError: If the predicate is not a function
        :return: A list of PDFItem satisfying the predicate
        :rtype: list
        """

        return [item for _, item in self.find(select,start)]

    def find_first(self, select:callable, start:int=0) -> PDFItem:
        """Find an item in the stack according to a predicate.

        See the `find` method for information about the predicate.

        :param select: The predicate
        :type select: function
        :param start: the starting index
        :type start: int
        :raise TypeError: If the predicate is not a function
        :return: The first item satisfying the predicate
        :rtype: PDFItem or None
        """
        for index, item in self.find(select, start):
            return item

        return None
