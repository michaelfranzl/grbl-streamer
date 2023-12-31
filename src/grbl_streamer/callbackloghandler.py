"""
grbl-streamer - Universal interface module for the grbl CNC firmware
Copyright (C) 2015 Michael Franzl

This file is part of grbl-streamer.

grbl-streamer is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

grbl-streamer is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with pyglpainter. If not, see <https://www.gnu.org/licenses/>.
"""

import logging

class CallbackLogHandler(logging.StreamHandler):
    def __init__(self, cb=None):
        super(CallbackLogHandler, self).__init__()
        self.callback = cb

    def emit(self, record):
        if self.callback:
            #txt = "{0} {1}".format(record.level, record.msg)
            #print(self.format(record))
            #self.callback("on_log", self.format(record))
            #self.callback("on_log", record.levelno, record.msg % record.args)
            self.callback('on_log', record)
        else:
            logging.StreamHandler.emit(self, record)