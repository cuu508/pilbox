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

from __future__ import absolute_import, division, with_statement

import logging
import socket

import tornado.escape
import tornado.gen
import tornado.httpclient
import tornado.httpserver
import tornado.ioloop
import tornado.options
import tornado.web
from tornado.options import define, options, parse_config_file

from pilbox import errors
from pilbox.image import Image
from pilbox.signature import verify_signature

try:
    from urlparse import urlparse, urljoin
except ImportError:
    from urllib.parse import urlparse, urljoin


# general settings
define("config", help="path to configuration file",
       callback=lambda path: parse_config_file(path, final=False))
define("debug", help="run in debug mode", type=bool, default=False)
define("port", help="run on the given port", type=int, default=8888)

# security related settings
define("client_name", help="client name")
define("client_key", help="client key")
define("allowed_hosts", help="list of valid hosts", default=[], multiple=True)

# request related settings
define("max_requests", help="max concurrent requests", type=int, default=40)
define("timeout", help="request timeout in seconds", type=float, default=10)
define("implicit_base_url", help="prepend protocol/host to url paths")
define("validate_cert", help="validate certificates", type=bool, default=True)

# default image option settings
define("filter", help="default filter to use when resizing")
define("format", help="default format to use when outputting")
define("optimize", help="default to optimize when saving", type=int)
define("quality", help="default jpeg quality, 0-100", type=int)

logger = logging.getLogger("tornado.application")


class PilboxApplication(tornado.web.Application):

    def __init__(self, **kwargs):
        settings = dict(debug=options.debug,
                        client_name=options.client_name,
                        client_key=options.client_key,
                        allowed_hosts=options.allowed_hosts,
                        filter=options.filter,
                        format=options.format,
                        mode=options.mode,
                        optimize=options.optimize,
                        quality=options.quality,
                        max_requests=options.max_requests,
                        timeout=options.timeout,
                        implicit_base_url=options.implicit_base_url,
                        validate_cert=options.validate_cert)
        settings.update(kwargs)
        tornado.web.Application.__init__(self, self.get_handlers(), **settings)

    def get_handlers(self):
        return [(r"/", ImageHandler, dict(w=100, h=100))]


class ImageHandler(tornado.web.RequestHandler):
    FORWARD_HEADERS = ['Cache-Control', 'Expires', 'Last-Modified']
    OPERATIONS = ["region", "resize", "rotate", "noop"]

    _FORMAT_TO_MIME = {
        "gif": "image/gif",
        "jpeg": "image/jpeg",
        "jpg": "image/jpeg",
        "png": "image/png",
        "webp": "image/webp"}

    w = None
    h = None

    def initialize(self, w, h):
        self.w = w
        self.h = h

    @tornado.gen.coroutine
    def get(self):
        url = self.get_argument("url")

        client = tornado.httpclient.AsyncHTTPClient(
            max_clients=self.settings.get("max_requests"))
        try:
            resp = yield client.fetch(
                url,
                request_timeout=self.settings.get("timeout"),
                validate_cert=self.settings.get("validate_cert"))
        except (socket.gaierror, tornado.httpclient.HTTPError) as e:
            logger.warn("Fetch error for %s: %s"
                        % (self.get_argument("url"), str(e)))
            raise errors.FetchError()

        outfile = self._process_response(resp)
        self._forward_headers(resp.headers)
        for block in iter(lambda: outfile.read(65536), b""):
            self.write(block)
        outfile.close()

        self.finish()

    def get_argument(self, name, default=None):
        return super(ImageHandler, self).get_argument(name, default)

    def write_error(self, status_code, **kwargs):
        err = kwargs["exc_info"][1] if "exc_info" in kwargs else None
        if isinstance(err, errors.PilboxError):
            self.set_header('Content-Type', 'application/json')
            resp = dict(status_code=status_code,
                        error_code=err.get_code(),
                        error=err.log_message)
            self.finish(tornado.escape.json_encode(resp))
        else:
            super(ImageHandler, self).write_error(status_code, **kwargs)

    def _process_response(self, resp):
        image = Image(resp.buffer)

        image.resize(self.w, self.h, **self.settings)
        return image.save(**self.settings)

    def _forward_headers(self, headers):
        mime = self._FORMAT_TO_MIME.get(
            self.get_argument("fmt", self.settings.get("format")),
            headers['Content-Type'])
        self.set_header('Content-Type', mime)
        for k in ImageHandler.FORWARD_HEADERS:
            if k in headers and headers[k]:
                self.set_header(k, headers[k])

def main():
    tornado.options.parse_command_line()
    if options.debug:
        logger.setLevel(logging.DEBUG)
    server = tornado.httpserver.HTTPServer(PilboxApplication())
    logger.info("Starting server...")
    try:
        server.bind(options.port)
        server.start(1 if options.debug else 0)
        tornado.ioloop.IOLoop.instance().start()
    except KeyboardInterrupt:
        tornado.ioloop.IOLoop.instance().stop()


if __name__ == "__main__":
    main()
