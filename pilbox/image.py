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
import PIL.ImageOps

from pilbox import errors

try:
    from io import BytesIO
except ImportError:
    from cStringIO import StringIO as BytesIO

logger = logging.getLogger("tornado.application")

_filters_to_pil = {
    "antialias": PIL.Image.ANTIALIAS,
    "bicubic": PIL.Image.BICUBIC,
    "bilinear": PIL.Image.BILINEAR,
    "nearest": PIL.Image.NEAREST
    }

_formats_to_pil = {
    "gif": "GIF",
    "jpg": "JPEG",
    "jpeg": "JPEG",
    "png": "PNG",
    "webp": "WEBP"
}


class Image(object):
    FILTERS = _filters_to_pil.keys()
    FORMATS = _formats_to_pil.keys()
    MODES = ["clip", "crop", "fill", "scale"]

    _DEFAULTS = dict(background="fff", expand=False, filter="antialias",
                     format=None, mode="crop", optimize=False, quality=90)

    def __init__(self, stream):
        self.stream = stream

        self.img = PIL.Image.open(self.stream)
        if self.img.format.lower() not in self.FORMATS:
            raise errors.ImageFormatError(
                "Unknown format: %s" % self.img.format)
        self._orig_format = self.img.format

    def resize(self, width, height, **kwargs):
        """Resizes the image to the supplied width/height. Returns the
        instance. Supports the following optional keyword arguments:

        filter - The filter to use: see Image.FILTERS
        """
        opts = Image._normalize_options(kwargs)
        size = self._get_size(width, height)
        self._clip(size, opts)
        return self


    def save(self, **kwargs):
        """Returns a buffer to the image for saving, supports the
        following optional keyword arguments:

        format - The format to save as: see Image.FORMATS
        optimize - The image file size should be optimized
        quality - The quality used to save JPEGs: integer from 1 - 100
        """
        opts = Image._normalize_options(kwargs)
        outfile = BytesIO()
        if opts["pil"]["format"]:
            fmt = opts["pil"]["format"]
        else:
            fmt = self._orig_format
        save_kwargs = dict(quality=int(opts["quality"]))
        if int(opts["optimize"]):
            save_kwargs["optimize"] = True
        self.img.save(outfile, fmt, **save_kwargs)
        outfile.seek(0)

        return outfile

    def _clip(self, size, opts):
        self.img.thumbnail(size, opts["pil"]["filter"])

    def _get_size(self, width, height):
        aspect_ratio = self.img.size[0] / self.img.size[1]
        if not width:
            width = int((int(height) or self.img.size[1]) * aspect_ratio)
        if not height:
            height = int((int(width) or self.img.size[0]) / aspect_ratio)
        return (int(width), int(height))

    @staticmethod
    def _normalize_options(options):
        opts = Image._DEFAULTS.copy()
        for k, v in options.items():
            if v is not None:
                opts[k] = v
        opts["pil"] = dict(
            filter=_filters_to_pil.get(opts["filter"]),
            format=_formats_to_pil.get(opts["format"]))

        if not opts["pil"]["position"]:
            opts["pil"]["position"] = _positions_to_ratios.get(
                opts["position"], None)

        return opts
