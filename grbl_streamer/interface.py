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

import serial
import threading
import logging


class Interface:
    """Implements opening, closing, writing and threaded reading from the serial port. Read data are put into a Thread Queue.
    """

    def __init__(self, name, path, baud=115200):
        """Straightforward initialization tasks.

        @param name
        An informal name of the instance. Useful if you are running
        several instances to control several serial ports at once.
        It is only used for logging output and UI messages.

        @param path
        The serial port device node living under /dev.
        e.g. /dev/ttyACM0 or /dev/ttyUSB0

        @param baud
        The baud rate. Default is 115200 for Grbl > v0.9i.
        """

        self.name = name
        self.path = path
        self.baud = baud
        self.queue = None
        self.logger = logging.getLogger('GrblStreamer.interface')

        self._buf_receive = ''
        self._do_receive = False

    def start(self, queue):
        """
        Open the device node and start a Thread for reading.

        @param queue
        An instance of Python3's `Queue()` class.
        """
        self.queue = queue

        self.logger.info(
                '%s: connecting to %s with baudrate %i',
                self.name,
                self.path,
                self.baud)

        self.serialport = serial.Serial(
                self.path,
                self.baud,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                bytesize=serial.EIGHTBITS,
                timeout=1,
                writeTimeout=0,
        )
        self.serialport.flushInput()
        self.serialport.flushOutput()
        self._do_receive = True
        self.serial_thread = threading.Thread(target=self._receiving)
        self.serial_thread.start()

    def stop(self):
        """
        Close the device node and shut down the reading Thread.
        """
        self._do_receive = False
        self.logger.info('%s: stop()', self.name)
        self.serial_thread.join()
        self.logger.info('%s: JOINED thread', self.name)
        self.logger.info('%s: Closing port', self.name)
        self.serialport.flushInput()
        self.serialport.flushOutput()
        self.serialport.close()

    def write(self, data):
        """
        Write `data` to the device node.
        If data is empty, no write is performed.
        The number of written characters is returned.
        """
        if len(data) > 0:
            num_written = self.serialport.write(bytes(data, 'ascii'))
            return num_written
        else:
            self.logger.debug('%s: nothing to write', self.name)

    def _receiving(self):
        while self._do_receive:
            data = self.serialport.read(1)
            waiting = self.serialport.inWaiting()
            data += self.serialport.read(waiting)
            self._handle_data(data)

    def _handle_data(self, data):
        try:
            asci = data.decode('ascii')
        except UnicodeDecodeError:
            self.logger.info(
                '%s: Received a non-ascii byte. Probably junk. Dropping it.',
                self.name)
            asci = ""

        for i in range(0, len(asci)):
            char = asci[i]
            self._buf_receive += char
            # not all received lines are complete (end with \n)
            if char == "\n":
                self.queue.put(self._buf_receive.strip())
                self._buf_receive = ""
