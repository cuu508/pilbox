#!/usr/bin/env python
#
# Copyright 2013 Adam Gschwender
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

from __future__ import absolute_import, division, print_function, \
    with_statement

import logging
import re
import os.path

import PIL.Image

from pilbox import errors

try:
    from io import BytesIO
except ImportError:
    from cStringIO import StringIO as BytesIO

logger = logging.getLogger("tornado.application")

class Image(object):
    FORMATS = ("gif", "jpg", "jpeg", "png", "webp")

    def __init__(self, stream):
        self.stream = stream

        self.img = PIL.Image.open(self.stream)
        if self.img.format.lower() not in self.FORMATS:
            raise errors.ImageFormatError(
                "Unknown format: %s" % self.img.format)

    def resize(self, width, height):
        """Resizes the image to the supplied width/height. Returns the
        instance. """

        size = self._get_size(width, height)
        self._clip(size)
        return self

    def save(self):
        """Returns a buffer to the image for saving. """

        outfile = BytesIO()
        self.img.save(outfile, "JPEG", quality=85)
        outfile.seek(0)

        return outfile

    def _clip(self, size):
        self.img.thumbnail(size, PIL.Image.ANTIALIAS)

    def _get_size(self, width, height):
        aspect_ratio = self.img.size[0] / self.img.size[1]
        if not width:
            width = int((int(height) or self.img.size[1]) * aspect_ratio)
        if not height:
            height = int((int(width) or self.img.size[0]) / aspect_ratio)
        return (int(width), int(height))

