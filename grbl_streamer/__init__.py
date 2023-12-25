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
import time
import re
import threading
import atexit

from queue import Queue

from .interface import Interface
from .callbackloghandler import CallbackLogHandler

from gcode_machine import GcodeMachine


class GrblStreamer:
    """ A universal Grbl CNC firmware interface module for Python3
    providing a convenient high-level API for scripting or integration
    into parent applications like GUI's.

    There are a number of streaming applications available for the Grbl
    CNC controller, but none of them seem to be an universal, re-usable
    standard Python module. GrblStreamer attempts to fill that gap.

    See README for usage examples.

    Features:

    * Re-usable across projects
    * Non-blocking
    * Asynchronous (event-based) callbacks for the parent application
    * Two streaming modes: Incremental or fast ("counting characters")
    * Defined shutdown
    * G-Code cleanup
    * G-Code variable expansion
    * Dynamic feed override
    * Buffer stashing
    * Job halt and resume

    Callbacks:

    After assigning your own callback function (callback = ...)
    you will receive the following signals:

    on_boot
    : Emitted whenever Grbl boots (e.g. after a soft reset).
    : No arguments.

    on_disconnected
    : Emitted whenever the serial port has been closed.
    : No arguments

    on_log
    : Emitted for informal logging or debugging messages.
    : 1 argument: LogRecord instance

    on_line_sent
    : Emitted whenever a line is actually sent to Grbl.
    : 2 arguments: job_line_number, line

    on_bufsize_change
    : Emitted whenever lines have been appended to the buffer
    : 1 argument: linecount

    on_line_number_change
    : Emitted whenever the current buffer position has been changed
    : 1 argument: line_number

    on_processed_command
    : Emitted whenever Grbl confirms a command with "ok" and is now being executed physically
    : 2 arguments: processed line number, processed line

    on_alarm
    : Emitted whenever Grbl sends an "ALARM" line
    : 1 argument: the full line Grbl sent

    on_error
    : Emitted whenever Grbl sends an "ERROR" line
    : 3 arguments: the full line Grbl sent, the line that caused the error, the line number in the buffer that caused the error

    on_rx_buffer_percent
    : Reports Grbl's serial receive buffer fill in percent. Emitted frequently while streaming.
    : 1 argument: percentage integer from 0 to 100

    on_progress_percent
    : Reports the completion of the current job/buffer in percent. Emitted frequently while streaming.
    : 1 argument: percentage integer from 0 to 100

    on_job_completed
    : Emitted when the current job/buffer has been streamed and physically executed entirely

    on_stateupdate
    : Emitted whenever Grbl's state has changed
    : 3 arguments: Grbl's mode ('Idle', 'Run' etc.), machine position tuple, working position tupe

    on_hash_stateupdate
    : Emitted after Grbl's 'hash' EEPROM settings (`$#`) have been received
    : 1 argument: dict of the settings

    on_settings_downloaded
    : Emitted after Grbl's EEPROM settings (`$$`) have been received
    : 1 argument: dict of the settings

    on_gcode_parser_stateupdate
    : Emitted after Grbl's G-Code parser state has been received
    : 1 argument: list of the state variables

    on_simulation_finished
    : Emitted when GrblStreamer's target is set to "simulator" and the job is executed.
    : 1 argument: list of all G-Code commands that would have been sent to Grbl

    on_vars_change
    : Emitted after G-Code is loaded into the buffer and variables have been detected
    : 1 argument: a dict of the detected variables

    on_preprocessor_feed_change
    : Emitted when a F keyword is parsed from the G-Code.
    : 1 argument: the feed rate in mm/min
    """

    __version__ = "0.5.0"

    def __init__(self, callback, name="mygrbl"):
        """Straightforward initialization tasks.

        @param callback
        Set your own function that will be called when a number of
        asynchronous events happen. Useful for UI's. The
        default function will just log to stdout.

        This callback function will receive two arguments. The first
        is a string giving a label of the event, and the second is a variable
        argument list `*args` containing data pertaining to the event.

        Note that this function may be called from a Thread.

        @param name
        An informal name of the instance. Useful if you are running
        several instances to control several CNC machines at once.
        It is only used for logging output and UI messages.
        """

        # @var name
        # Set an informal name of the instance. Useful if you are
        # running several instances to control several CNC machines at
        # once. It is only used for logging output and UI messages.
        self.name = name

        # @var cmode
        # Get Grbl's current mode.
        # Will be strings 'Idle', 'Check', 'Run'
        self.cmode = None

        # @var cmpos
        # Get a 3-tuple containing the current coordinates relative
        # to the machine origin.
        self.cmpos = (0, 0, 0)

        # @var cwpos
        # Get a 3-tuple containing the current working coordinates.
        # Working coordinates are relative to the currently selected
        # coordinate system.
        self.cwpos = (0, 0, 0)

        # @var gps
        # Get list of 12 elements containing the 12 Gcode Parser State
        # variables of Grbl which are obtained by sending the raw
        # command `$G`. Will be available after setting
        # `hash_state_requested` to True.
        self.gps = [
            '0',  # motion mode
            '54',  # current coordinate system
            '17',  # current plane mode
            '21',  # units
            '90',  # current distance mode
            '94',  # feed rate mode
            '0',  # program mode
            '0',  # spindle state
            '5',  # coolant state
            '0',  # tool number
            '99',  # current feed
            '0',  # spindle speed
        ]

        # @var poll_interval
        # Set an interval in seconds for polling Grbl's state via
        # the `?` command. The Grbl Wiki recommends to set this no lower
        # than 0.2 (5 per second).
        self.poll_interval = 0.2

        # @var settings
        # Get a dictionary of Grbl's EEPROM settings which can be read
        # after sending the `$$` command, or more conveniently after
        # calling the method `request_settings()` of this class.
        self.settings = {
            130: {'val': '1000', 'cmt': 'width'},
            131: {'val': '1000', 'cmt': 'height'}
        }

        # @var settings_hash
        # Get a dictionary of Grbl's 'hash' settings (also stored in the
        # EEPROM) which can be read after sending the `$#` command. It
        # contains things like coordinate system offsets. See Grbl
        # documentation for more info. Will be available shortly after
        # setting `hash_state_requested` to `True`.
        self.settings_hash = {
            'G54': (0, 0, 0),
            'G55': (0, 0, 0),
            'G56': (0, 0, 0),
            'G57': (0, 0, 0),
            'G58': (0, 0, 0),
            'G59': (0, 0, 0),
            'G28': (0, 0, 0),
            'G30': (0, 0, 0),
            'G92': (0, 0, 0),
            'TLO': 0,
            'PRB': (0, 0, 0),
        }

        # @var gcode_parser_state_requested
        # Set this variable to `True` to receive a callback with the
        # event string "on_gcode_parser_stateupdate" containing
        # data that Grbl sends after receiving the `$G` command.
        # After the callback, this variable reverts to `False`.
        self.gcode_parser_state_requested = False

        # @var hash_state_requested
        # Set this variable to `True` to receive a callback with the
        # event string "on_hash_stateupdate" containing
        # the requested data. After the callback, this variable reverts
        # to `False`.
        self.hash_state_requested = False

        # @var logger
        # The logger used by this class. The default is Python's own
        # logger module. Use `setup_logging()` to attach custom
        # log handlers.
        self.logger = logging.getLogger('GrblStreamer')
        self.logger.setLevel(logging.DEBUG)
        self.logger.propagate = False

        # @var target
        # Set this to change the output target. Default is "firmware"
        # which means the serial port. Another target is "simulator",
        # you will receive a callback with even string
        # "on_simulation_finished" and a buffer of the G-Code commands
        # that would have been sent out to Grbl.
        # TODO: Add "file" target.
        self.target = 'firmware'

        # @var connected
        # `True` when connected to Grbl (after boot), otherwise `False`
        self.connected = False

        # @var preprocessor
        # All G-code commands will go through the preprocessor
        # before they are sent out via the serial port. The preprocessor
        # keeps track of, and can dynamically change, feed rates, as well
        # as substitute variables. It has its own state and callback
        # functions.
        self.preprocessor = GcodeMachine()
        self.preprocessor.callback = self._preprocessor_callback

        # @var travel_dist_buffer
        # The total distance of all G-Codes in the buffer.
        self.travel_dist_buffer = {}

        # @var travel_dist_current
        # The currently travelled distance. Can be used to calculate ETA.
        self.travel_dist_current = {}

        # @var is_standstill
        # If the machine is currently not moving
        self.is_standstill = False

        self._ifacepath = None
        self._last_setting_number = 132

        self._last_cmode = None
        self._last_cmpos = (0, 0, 0)
        self._last_cwpos = (0, 0, 0)

        self._standstill_watchdog_increment = 0

        self._rx_buffer_size = 128
        self._rx_buffer_fill = []
        self._rx_buffer_backlog = []
        self._rx_buffer_backlog_line_number = []
        self._rx_buffer_fill_percent = 0

        self._current_line = ''
        self._current_line_sent = True
        self._streaming_mode = None
        self._wait_empty_buffer = False
        self.streaming_complete = True
        self.job_finished = True
        self._streaming_src_end_reached = True
        self._streaming_enabled = True
        self._error = False
        self._incremental_streaming = False
        self._hash_state_sent = False

        self.buffer = []
        self.buffer_size = 0
        self._current_line_nr = 0

        self.buffer_stash = []
        self.buffer_size_stash = 0
        self._current_line_nr_stash = 0

        self._poll_keep_alive = False
        self._iface_read_do = False

        self._thread_polling = None
        self._thread_read_iface = None

        self._iface = None
        self._queue = Queue()

        self._loghandler = None

        # general-purpose counter for timing tasks inside of _poll_state
        self._counter = 0

        self._callback = callback

        atexit.register(self.disconnect)

        # supply defaults to GUI to make it operational
        self._callback('on_settings_downloaded', self.settings)
        self._callback('on_hash_stateupdate', self.settings_hash)
        self.preprocessor.cs_offsets = self.settings_hash
        self._callback('on_gcode_parser_stateupdate', self.gps)

    def setup_logging(self, handler=None):
        """Assign a custom log handler.

        GrblStreamer can be used in both console applications as well as
        integrated in other projects like GUI's. Therefore, logging to
        stdout is not always useful. You can pass a custom log message
        handler to this method. If no handler is passed in, the default
        handler is an instance of class `CallbackLogHandler`
        (see file `callback_loghandler.py` included in this module).
        CallbackLogHandler will deliver logged strings as callbacks to
        the parent application, the event string will be "on_log".

        @param handler=None
        An instance of a subclass inheriting from `logging.StreamHandler`
        """

        # The default log handler shipped with this module will call
        # self._callback() with first parameter "on_log" and second
        # parameter with the logged string.
        if handler is not None:
            self._loghandler = handler
        else:
            lh = CallbackLogHandler()
            lh.callback = self._callback
            self._loghandler = lh

        self.logger.addHandler(self._loghandler)

    def cnect(self, path=None, baudrate=115200):
        """
        Connect to the RS232 port of the Grbl controller.

        @param path=None Path to the device node

        This is done by instantiating a RS232 class, included in this
        module, which by itself block-listens (in a thread) to
        asynchronous data sent by the Grbl controller.
        """
        if path is None or path.strip() == '':
            return
        else:
            self._ifacepath = path

        if self._iface is None:
            self.logger.debug('{}: Setting up interface on {}'.format(self.name, self._ifacepath))
            self._iface = Interface('iface_' + self.name, self._ifacepath, baudrate)
            self._iface.start(self._queue)
        else:
            self.logger.info('{}: Cannot start another interface. There is already an interface {}.'.format(self.name, self._iface))

        self._iface_read_do = True
        self._thread_read_iface = threading.Thread(target=self._onread)
        self._thread_read_iface.start()

        self.softreset()

    def disconnect(self):
        """
        This method provides a controlled shutdown and cleanup of this
        module.

        It stops all threads, joins them, then closes the serial
        connection. For a safe shutdown of Grbl you may also want to
        call `softreset()` before you call this method.
        """
        if not self.is_connected():
            return

        self.poll_stop()

        self._iface.stop()
        self._iface = None

        self.logger.debug('{}: Please wait until reading thread has joined...'.format(self.name))
        self._iface_read_do = False
        # The thread will not join without putting a last queue message:
        self._queue.put("dummy_msg_for_joining_thread")
        self._thread_read_iface.join()
        self.logger.debug('{}: Reading thread successfully joined.'.format(self.name))

        self.connected = False

        self._callback('on_disconnected')

    def softreset(self):
        """
        Immediately sends `Ctrl-X` to Grbl.
        """
        self._iface.write('\x18')  # Ctrl-X
        self.update_preprocessor_position()

    def abort(self):
        """
        An alias for `softreset()`.
        """
        if not self.is_connected():
            return
        self.softreset()

    def hold(self):
        """
        Immediately sends the feed hold command (exclamation mark)
        to Grbl.
        """
        if not self.is_connected():
            return
        self._iface_write('!')

    def resume(self):
        """
        Immediately send the resume command (tilde) to Grbl.
        """
        if not self.is_connected():
            return
        self._iface_write('~')

    def killalarm(self):
        """
        Immediately send the kill alarm command ($X) to Grbl.
        """
        self._iface_write('$X\n')

    def homing(self):
        """
        Immediately send the homing command ($H) to Grbl.
        """
        self._iface_write('$H\n')

    def poll_start(self):
        """
        Starts forever polling Grbl's status with the `?` command. The
        polling interval is controlled by setting `self.poll_interval`.
        You will receive callbacks with the "on_stateupdate" event
        string containing 3 data parameters self.cmode, self.cmpos,
        self.cwpos, but only when Grbl's state CHANGES.
        """
        if not self.is_connected():
            return
        self._poll_keep_alive = True
        self._last_cmode = None
        if self._thread_polling is None:
            self._thread_polling = threading.Thread(target=self._poll_state)
            self._thread_polling.start()
            self.logger.debug('{}: Polling thread started'.format(self.name))
        else:
            self.logger.debug('{}: Polling thread already running...'.format(self.name))


    def poll_stop(self):
        """
        Stops polling that has been started with `poll_start()`
        """
        if not self.is_connected():
            return
        if self._thread_polling is not None:
            self._poll_keep_alive = False
            self.logger.debug('{}: Please wait until polling thread has joined...'.format(self.name))
            self._thread_polling.join()
            self.logger.debug('{}: Polling thread has successfully  joined...'.format(self.name))
        else:
            self.logger.debug('{}: Cannot start a polling thread. Another one is already running.'.format(self.name))

        self._thread_polling = None

    def set_feed_override(self, val):
        """
        Enable or disable the feed override feature.

        @param val
        Pass `True` or `False` as argument to enable or disable dynamic
        feed override. After passing `True`, you may set the
        requested feed by calling `self.request_feed()` one or many
        times.
        """
        self.preprocessor.do_feed_override = val

    def request_feed(self, requested_feed):
        """
        Override the feed speed.
        Effecive only when you set `set_feed_override(True)`.

        @param requested_feed
        The feed speed in mm/min.
        """
        self.preprocessor.request_feed = float(requested_feed)

    @property
    def incremental_streaming(self):
        return self._incremental_streaming

    @incremental_streaming.setter
    def incremental_streaming(self, onoff):
        """
        Incremental streaming means that a new command is sent to Grbl
        only after Grbl has responded with 'ok' to the last sent
        command. This is necessary to flash $ settings to the EEPROM.

        Non-incremental streaming means that Grbl's 100-some-byte
        receive buffer will be kept as full as possible at all times,
        to give its motion planner system enough data to work with.
        This results in smoother and faster axis motion. This is also
        called 'advanced streaming protocol based on counting
        characters' -- see Grbl Wiki.

        You can dynamically change the streaming method even
        during streaming, while running a job. The buffer fill
        percentage will reflect the change even during streaming.

        @param onoff
        Set to `True` to use incremental streaming. Set to `False` to
        use non-incremental streaming. The default on module startup
        is `False`.
        """
        self._incremental_streaming = onoff
        if self._incremental_streaming:
            self._wait_empty_buffer = True
        self.logger.debug('{}: Incremental streaming set to {}'.format(self.name, self._incremental_streaming))

    def send_immediately(self, line):
        """
        G-Code command strings passed to this function will bypass
        buffer management and will be sent to Grbl immediately.
        Use this function with caution: Only send when you
        are sure Grbl's receive buffer can handle the data volume and
        when it doesn't interfere with currently running streams.
        Only send single commands at a time.

        Applications of this method: manual jogging, coordinate settings
        etc.

        @param line
        A string of a single G-Code command to be sent. Doesn't have to
        be \n terminated.
        """
        bytes_in_firmware_buffer = sum(self._rx_buffer_fill)
        if bytes_in_firmware_buffer > 0:
            self.logger.error('Firmware buffer has {:d} unprocessed bytes in it. Will not send {}'.format(bytes_in_firmware_buffer, line))
            return

        if self.cmode == 'Alarm':
            self.logger.error('Grbl is in ALARM state. Will not send {}.'.format(line))
            return

        if self.cmode == 'Hold':
            self.logger.error('Grbl is in HOLD state. Will not send {}.'.format(line))
            return

        if "$#" in line:
            # The PRB response is sent for $# as well as when probing.
            # Regular querying of the hash state needs to be done like this,
            # otherwise the PRB response would be interpreted as a probe answer
            self.hash_state_requested = True
            return

        self.preprocessor.set_line(line)
        self.preprocessor.strip()
        self.preprocessor.tidy()
        self.preprocessor.parse_state()
        self.preprocessor.override_feed()

        self._iface_write(self.preprocessor.line + '\n')

    def stream(self, lines):
        """
        A more convenient alias for `write(lines)` and `job_run()`

        @param lines
        A string of G-Code commands. Each command is \n separated.
        """
        self._load_lines_into_buffer(lines)
        self.job_run()

    def write(self, lines):
        """
        G-Code command strings passed to this function will be appended
        to the current queue buffer, however a job is not started
        automatically. You have to call `job_run()` to start streaming.

        You can call this method repeatedly, e.g. for submitting chunks
        of G-Code, even while a job is running.

        @param lines
        A string of G-Code commands. Each command is \n separated.
        """
        if type(lines) is list:
            lines = "\n".join(lines)

        self._load_lines_into_buffer(lines)

    def load_file(self, filename):
        """
        Pass a filename to this function to load its contents into the
        buffer. This only works when Grbl is Idle and the previous job
        has completed. The previous buffer will be cleared. After this
        function has completed, the buffer's contents will be identical
        to the file content. Job is not started automatically.
        Call `job_run` to start the job.

        @param filename
        A string giving the relative or absolute file path
        """
        if not self.job_finished:
            self.logger.warning('{}: Job must be finished before you can load a file'.format(self.name))
            return

        self.job_new()

        with open(filename) as f:
            self._load_lines_into_buffer(f.read())

    def job_run(self, linenr=None):
        """
        Run the current job, i.e. start streaming the current buffer
        from a specific line number.

        @param linenr
        If `linenr` is not specified, start streaming from the current
        buffer position (`self.current_line_number`).
        If `linenr` is specified, start streaming from this line.
        """
        if self.buffer_size == 0:
            self.logger.warning('{}: Cannot run job. Nothing in the buffer!'.format(self.name))
            return

        if linenr:
            self.current_line_number = linenr

        self.travel_dist_current = {}

        self._set_streaming_src_end_reached(False)
        self._set_streaming_complete(False)
        self._streaming_enabled = True
        self._current_line_sent = True
        self._set_job_finished(False)
        self._stream()

    def job_halt(self):
        """
        Stop streaming. Grbl still will continue processing
        all G-Code in its internal serial receive buffer.
        """
        self._streaming_enabled = False

    def job_new(self):
        """
        Start a new job. A "job" in our terminology means the buffer's
        contents. This function will empty the buffer, set the buffer
        position to 0, and reset internal state.
        """
        del self.buffer[:]
        self.buffer_size = 0
        self._current_line_nr = 0
        self._callback('on_line_number_change', 0)
        self._callback('on_bufsize_change', 0)
        self._set_streaming_complete(True)
        self.job_finished = True
        self._set_streaming_src_end_reached(True)
        self._error = False
        self._current_line = ''
        self._current_line_sent = True
        self.travel_dist_buffer = {}
        self.travel_dist_current = {}

        self._callback('on_vars_change', self.preprocessor.vars)

    @property
    def current_line_number(self):
        return self._current_line_nr

    @current_line_number.setter
    def current_line_number(self, linenr):
        if linenr < self.buffer_size:
            self._current_line_nr = linenr
            self._callback('on_line_number_change', self._current_line_nr)

    def request_settings(self):
        """
        This will send `$$` to Grbl and you will receive a callback with
        the argument 1 "on_settings_downloaded", and argument 2 a dict
        of the settings.
        """
        self._iface_write('$$\n')

    def do_buffer_stash(self):
        """
        Stash the current buffer and position away and initialize a
        new job. This is useful if you want to stop the current job,
        stream changed $ settings to Grbl, and then resume the job
        where you left off. See also `self.buffer_unstash()`.
        """
        self.buffer_stash = list(self.buffer)
        self.buffer_size_stash = self.buffer_size
        self._current_line_nr_stash = self._current_line_nr
        self.job_new()

    def do_buffer_unstash(self):
        """
        Restores the previous stashed buffer and position.
        """
        self.buffer = list(self.buffer_stash)
        self.buffer_size = self.buffer_size_stash
        self.current_line_number = self._current_line_nr_stash
        self._callback('on_bufsize_change', self.buffer_size)

    def update_preprocessor_position(self):
        # keep preprocessor informed about current working pos
        self.preprocessor.position_m = list(self.cmpos)
        # self.preprocessor.target = list(self.cmpos)

    def _preprocessor_callback(self, event, *data):
        if event == 'on_preprocessor_var_undefined':
            self.logger.critical(
                'HALTED JOB BECAUSE UNDEFINED VAR {}'.format(data[0])
            )
            self._set_streaming_src_end_reached(True)
            self.job_halt()
        else:
            self._callback(event, *data)

    def _stream(self):
        if self._streaming_src_end_reached:
            return

        if not self._streaming_enabled:
            return

        if self.target == 'firmware':
            if self._incremental_streaming:
                self._set_next_line()
                if not self._streaming_src_end_reached:
                    self._send_current_line()
                else:
                    self._set_job_finished(True)
            else:
                self._fill_rx_buffer_until_full()

        elif self.target == 'simulator':
            buf = []
            while not self._streaming_src_end_reached:
                self._set_next_line(True)
                if self._current_line_nr < self.buffer_size:
                    buf.append(self._current_line)

            # one line still to go
            self._set_next_line(True)
            buf.append(self._current_line)

            self._set_job_finished(True)
            self._callback('on_simulation_finished', buf)

    def _fill_rx_buffer_until_full(self):
        while True:
            if self._current_line_sent:
                self._set_next_line()

            if not self._streaming_src_end_reached and self._rx_buf_can_receive_current_line():
                self._send_current_line()
            else:
                break

    def _set_next_line(self, send_comments=False):
        progress_percent = int(100 * self._current_line_nr / self.buffer_size)
        self._callback('on_progress_percent', progress_percent)

        if self._current_line_nr < self.buffer_size:
            # still something in _buffer, pop it
            line = self.buffer[self._current_line_nr].strip()
            self.preprocessor.set_line(line)
            self.preprocessor.substitute_vars()
            self.preprocessor.parse_state()
            self.preprocessor.override_feed()
            self.preprocessor.scale_spindle()

            if send_comments:
                self._current_line = self.preprocessor.line + self.preprocessor.comment
            else:
                self._current_line = self.preprocessor.line

            self._current_line_sent = False
            self._current_line_nr += 1

            self.preprocessor.done()

        else:
            # the buffer is empty, nothing more to read
            self._set_streaming_src_end_reached(True)

    def _send_current_line(self):
        if self._error:
            self.logger.error('Firmware reported error. Halting.')
            self._set_streaming_src_end_reached(True)
            self._set_streaming_complete(True)
            return

        self._set_streaming_complete(False)

        # +1 for \n which we will append below
        line_length = len(self._current_line) + 1
        self._rx_buffer_fill.append(line_length)
        self._rx_buffer_backlog.append(self._current_line)
        self._rx_buffer_backlog_line_number.append(self._current_line_nr)
        self._iface_write(self._current_line + '\n')

        self._current_line_sent = True
        self._callback('on_line_sent', self._current_line_nr,
                       self._current_line)

    def _rx_buf_can_receive_current_line(self):
        rx_free_bytes = self._rx_buffer_size - sum(self._rx_buffer_fill)
        required_bytes = len(self._current_line) + 1  # +1 because \n
        return rx_free_bytes >= required_bytes

    def _rx_buffer_fill_pop(self):
        if len(self._rx_buffer_fill) > 0:
            self._rx_buffer_fill.pop(0)
            processed_command = self._rx_buffer_backlog.pop(0)
            ln = self._rx_buffer_backlog_line_number.pop(0) - 1
            self._callback('on_processed_command', ln, processed_command)

        if self._streaming_src_end_reached and len(self._rx_buffer_fill) == 0:
            self._set_job_finished(True)
            self._set_streaming_complete(True)

    def _iface_write(self, line):
        self._callback('on_write', line)
        if self._iface:
            num_written = self._iface.write(line)

    def _onread(self):
        while self._iface_read_do:
            line = self._queue.get()

            if len(line) > 0:
                if line[0] == '<':
                    self._update_state(line)

                elif line == 'ok':
                    self._handle_ok()

                elif re.match(r'^\[G[0123] .*', line):
                    self._update_gcode_parser_state(line)
                    self._callback("on_read", line)

                elif line == '[MSG:Caution: Unlocked]':
                    # nothing to do here
                    pass

                elif re.match(r'^\[...:.*', line):
                    self._update_hash_state(line)
                    self._callback('on_read', line)

                    if 'PRB' in line:
                        # last line
                        if self.hash_state_requested:
                            self._hash_state_sent = False
                            self.hash_state_requested = False
                            self._callback('on_hash_stateupdate', self.settings_hash)
                            self.preprocessor.cs_offsets = self.settings_hash
                        else:
                            self._callback('on_probe', self.settings_hash['PRB'])

                elif 'ALARM' in line:
                    # grbl for some reason doesn't respond to ? polling
                    # when there is an alarm due to soft limits
                    self.cmode = 'Alarm'
                    self._callback('on_stateupdate', self.cmode, self.cmpos, self.cwpos)
                    self._callback('on_read', line)
                    self._callback('on_alarm', line)

                elif 'error' in line:
                    # self.logger.debug("ERROR")
                    self._error = True
                    # self.logger.debug("%s: _rx_buffer_backlog at time of error: %s", self.name,  self._rx_buffer_backlog)
                    if len(self._rx_buffer_backlog) > 0:
                        problem_command = self._rx_buffer_backlog[0]
                        problem_line = self._rx_buffer_backlog_line_number[0]
                    else:
                        problem_command = 'unknown'
                        problem_line = -1
                    self._callback('on_error', line, problem_command, problem_line)
                    self._set_streaming_complete(True)
                    self._set_streaming_src_end_reached(True)

                elif "Grbl " in line:
                    self._callback('on_read', line)
                    self._on_bootup()
                    self.hash_state_requested = True
                    self.request_settings()
                    self.gcode_parser_state_requested = True

                else:
                    m = re.match(r'\$(.*)=(.*) \((.*)\)', line)
                    if m:
                        key = int(m.group(1))
                        val = m.group(2)
                        comment = m.group(3)
                        self.settings[key] = {
                            'val': val,
                            'cmt': comment
                        }
                        self._callback('on_read', line)
                        if key == self._last_setting_number:
                            self._callback('on_settings_downloaded', self.settings)
                    else:
                        self._callback('on_read', line)
                        # self.logger.info("{}: Could not parse settings: {}".format(self.name, line))

    def _handle_ok(self):
        if not self.streaming_complete:
            self._rx_buffer_fill_pop()
            if not (self._wait_empty_buffer and len(self._rx_buffer_fill) > 0):
                self._wait_empty_buffer = False
                self._stream()

        self._rx_buffer_fill_percent = int(100 - 100 * (self._rx_buffer_size - sum(self._rx_buffer_fill)) / self._rx_buffer_size)
        self._callback('on_rx_buffer_percent', self._rx_buffer_fill_percent)

    def _on_bootup(self):
        self._onboot_init()
        self.connected = True
        self.logger.debug('{}: Grbl has booted!'.format(self.name))
        self._callback('on_boot')

    def _update_hash_state(self, line):
        line = line.replace(']', '').replace('[', '')
        parts = line.split(':')
        key = parts[0]
        tpl_str = parts[1].split(',')
        tpl = tuple([float(x) for x in tpl_str])
        self.settings_hash[key] = tpl

    def _update_gcode_parser_state(self, line):
        m = re.match(r'\[G(\d) G(\d\d) G(\d\d) G(\d\d) G(\d\d) G(\d\d) M(\d) M(\d) M(\d) T(\d) F([\d.-]*?) S([\d.-]*?)\]', line)
        if m:
            self.gps[0] = m.group(1)  # motionmode
            self.gps[1] = m.group(2)  # current coordinate system
            self.gps[2] = m.group(3)  # plane
            self.gps[3] = m.group(4)  # units
            self.gps[4] = m.group(5)  # dist
            self.gps[5] = m.group(6)  # feed rate mode
            self.gps[6] = m.group(7)  # program mode
            self.gps[7] = m.group(8)  # spindle state
            self.gps[8] = m.group(9)  # coolant state
            self.gps[9] = m.group(10)  # tool number
            self.gps[10] = m.group(11)  # current feed
            self.gps[11] = m.group(12)  # current rpm
            self._callback('on_gcode_parser_stateupdate', self.gps)

            self.update_preprocessor_position()
        else:
            self.logger.error('{}: Could not parse gcode parser report: "{}"'.format(self.name, line))

    def _update_state(self, line):
        m = re.match(r'<(.*?),MPos:(.*?),WPos:(.*?)>', line)
        if m is not None:
            # GRBL v0.9
            # <Idle,MPos:0.000,3.000,0.000,WPos:0.000,3.000,0.000>
            self.cmode = m.group(1)
            mpos_parts = m.group(2).split(',')
            wpos_parts = m.group(3).split(',')
            self.cmpos = (float(mpos_parts[0]), float(mpos_parts[1]), float(mpos_parts[2]))
            self.cwpos = (float(wpos_parts[0]), float(wpos_parts[1]), float(wpos_parts[2]))
        else:
            # GRBL v1.1
            # <Idle|MPos:0.0000,0.0000,0.0000|Bf:15,128|FS:0.0,0|WCO:0.0000,0.0000,0.0000>
            m = re.match(r'<(.*?)\|MPos:(.*?)\|', line)
            if m is not None:
                # machine position reported (when $10=1)
                self.cmode = m.group(1)
                mpos_parts = m.group(2).split(',')
                self.cmpos = (float(mpos_parts[0]), float(mpos_parts[1]), float(mpos_parts[2]))
            else:
                m = re.match(r'<(.*?)\|WPos:(.*?)\|', line)
                if m is not None:
                    # work position reported (when $10=0)
                    self.cmode = m.group(1)
                    wpos_parts = m.group(2).split(',')
                    self.cwpos = (float(wpos_parts[0]), float(wpos_parts[1]), float(wpos_parts[2]))
                else:
                    self.logger.error('{}: Could not parse MPos or WPos: "{}"'.format(self.name, line))
                    return
        # if we made it here, we parsed MPos or WPos or both

        if (
            self.cmode != self._last_cmode or
            self.cmpos != self._last_cmpos or
            self.cwpos != self._last_cwpos
           ):
            self._callback(
                    'on_stateupdate',
                    self.cmode,
                    self.cmpos,
                    self.cwpos)
            if self.streaming_complete and self.cmode == 'Idle':
                self.update_preprocessor_position()
                self.gcode_parser_state_requested = True

        if (self.cmpos != self._last_cmpos):
            if self.is_standstill:
                self._standstill_watchdog_increment = 0
                self.is_standstill = False
                self._callback('on_movement')
        else:
            # no change in positions
            self._standstill_watchdog_increment += 1

        if not self.is_standstill and self._standstill_watchdog_increment > 10:
            # machine is not moving
            self.is_standstill = True
            self._callback('on_standstill')

        self._last_cmode = self.cmode
        self._last_cmpos = self.cmpos
        self._last_cwpos = self.cwpos

    def _load_line_into_buffer(self, line):
        self.preprocessor.set_line(line)
        split_lines = self.preprocessor.split_lines()

        for l1 in split_lines:
            self.preprocessor.set_line(l1)
            self.preprocessor.strip()
            self.preprocessor.tidy()
            self.preprocessor.parse_state()
            self.preprocessor.find_vars()
            fractionized_lines = self.preprocessor.fractionize()

            for l2 in fractionized_lines:
                self.buffer.append(l2)
                self.buffer_size += 1

            self.preprocessor.done()

    def _load_lines_into_buffer(self, string):
        lines = string.split('\n')
        for line in lines:
            self._load_line_into_buffer(line)
        self._callback('on_bufsize_change', self.buffer_size)
        self._callback('on_vars_change', self.preprocessor.vars)

    def is_connected(self):
        if not self.connected:
            # self.logger.info("{}: Not yet connected".format(self.name))
            pass
        return self.connected

    def _onboot_init(self):
        # called after boot. Mimics Grbl's initial state after boot.
        del self._rx_buffer_fill[:]
        del self._rx_buffer_backlog[:]
        del self._rx_buffer_backlog_line_number[:]
        self._set_streaming_complete(True)
        self._set_job_finished(True)
        self._set_streaming_src_end_reached(True)
        self._error = False
        self._current_line = ""
        self._current_line_sent = True
        self._clear_queue()
        self.is_standstill = False
        self.preprocessor.reset()
        self._callback('on_progress_percent', 0)
        self._callback('on_rx_buffer_percent', 0)

    def _clear_queue(self):
        try:
            junk = self._queue.get_nowait()
            self.logger.debug('Discarding junk %s', junk)
        except:
            # self.logger.debug("Queue was empty")
            pass

    def _poll_state(self):
        while self._poll_keep_alive:
            self._counter += 1

            if self.hash_state_requested:
                self.get_hash_state()

            elif self.gcode_parser_state_requested:
                self.get_gcode_parser_state()
                self.gcode_parser_state_requested = False

            else:
                self._get_state()

            time.sleep(self.poll_interval)

        self.logger.debug('{}: Polling has been stopped'.format(self.name))

    def _get_state(self):
        self._iface.write('?')

    def get_gcode_parser_state(self):
        self._iface_write('$G\n')

    def get_hash_state(self):
        if self.cmode == 'Hold':
            self.hash_state_requested = False
            self.logger.info('{}: $# command not supported in Hold mode.'.format(self.name))
            return

        if not self._hash_state_sent:
            self._iface_write('$#\n')
            self._hash_state_sent = True

    def _set_streaming_src_end_reached(self, a):
        self._streaming_src_end_reached = a

    def _set_streaming_complete(self, a):
        self.streaming_complete = a

    def _set_job_finished(self, a):
        self.job_finished = a
        if a:
            self._callback('on_job_completed')

    def _default_callback(self, status, *args):
        print('DEFAULT CALLBACK', status, args)
