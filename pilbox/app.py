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

import base64
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

# general settings
define("config", help="path to configuration file",
       callback=lambda path: parse_config_file(path, final=False))
define("debug", help="run in debug mode", type=bool, default=False)
define("port", help="run on the given port", type=int, default=8888)

# request related settings
define("max_requests", help="max concurrent requests", type=int, default=40)
define("timeout", help="request timeout in seconds", type=float, default=10)
define("implicit_base_url", help="prepend protocol/host to url paths")
define("validate_cert", help="validate certificates", type=bool, default=True)

define("s3_root", help="HTTP address of S3 bucket", type=str, default=None)

logger = logging.getLogger("tornado.application")

class PilboxApplication(tornado.web.Application):

    def __init__(self, **kwargs):
        settings = dict(debug=options.debug,
                        max_requests=options.max_requests,
                        timeout=options.timeout,
                        implicit_base_url=options.implicit_base_url,
                        validate_cert=options.validate_cert,
                        s3_root=options.s3_root)
        settings.update(kwargs)
        tornado.web.Application.__init__(self, self.get_handlers(), **settings)

    def get_handlers(self):
        return [(r"/a/([\w-]+)/(.*)", ImageHandler, dict(w=100, h=100)),
                (r"/b/([\w-]+)/(.*)", ImageHandler, dict(w=500, h=500)),
                (r"/c/(.*)", ImageHandler, dict(w=100, h=100, external=True)),
                (r"/d/(.*)", ImageHandler, dict(w=500, h=500, external=True))
        ]


class ImageHandler(tornado.web.RequestHandler):
    w = None
    h = None
    external = False

    def initialize(self, w, h, external=False):
        self.w = w
        self.h = h
        self.external = external

    @tornado.gen.coroutine
    def get(self, arg1, arg2=None):
        if self.external:
            url = base64.b64decode(arg1).replace(" ", "%20")
        else:
            filename = base64.b64decode(arg2).replace(" ", "%20")
            url = "%s/%s/product-pictures/%s" % (self.settings["s3_root"], arg1, filename)

        client = tornado.httpclient.AsyncHTTPClient(
            max_clients=self.settings.get("max_requests"))
        try:
            resp = yield client.fetch(
                url,
                request_timeout=self.settings.get("timeout"),
                validate_cert=self.settings.get("validate_cert"))
        except (socket.gaierror, tornado.httpclient.HTTPError) as e:
            logger.warn("Fetch error for %s: %s"
                        % (url, str(e)))
            raise errors.FetchError()

        outfile = self._process_response(resp)
        self._set_headers()

        for block in iter(lambda: outfile.read(65536), b""):
            self.write(block)
        outfile.close()

        self.finish()

    def write_error(self, status_code, **kwargs):
        err = kwargs["exc_info"][1] if "exc_info" in kwargs else None
        if isinstance(err, errors.PilboxError):
            # Don't cache error responses:
            self.set_header('Cache-Control', 'no-cache')
            self.set_header('Content-Type', 'application/json')
            resp = dict(status_code=status_code,
                        error_code=err.get_code(),
                        error=err.log_message)
            self.finish(tornado.escape.json_encode(resp))
        else:
            super(ImageHandler, self).write_error(status_code, **kwargs)

    def _process_response(self, resp):
        image = Image(resp.buffer)
        image.resize(self.w, self.h)
        return image.save()

    def _set_headers(self):
        self.set_header('Content-Type', "image/jpeg")
        self.set_header('Cache-Control', "public, max-age=31536000") # 1 year

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
