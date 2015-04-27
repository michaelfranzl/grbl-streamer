import logging
import time
import re
import threading
import atexit
import os

from queue import Queue

from interface import Interface
from preprocessor import Preprocessor
from callbackloghandler import CallbackLogHandler
from logger import Logger

class Gerbil:
    """One instance of this class manages one physically connected Grbl firmware."""
    def __init__(self, name="mygrbl", ifacepath="/dev/ttyACM0"):
        """
        Set up initial values of all properties.
        
        blah
        """
        

        # 'public' - it is safe to set these variables from outside
        self.name = name

        self.cmode = None
        self.cmpos = (0, 0, 0)
        self.cwpos = (0, 0, 0)
        
        # Grbl's Gcode parser state variables
        self.gps = [None]*12
        
        self.poll_interval = 1 # no less than 0.2 suggested by Grbl documentation
        self.poll_counter = 0
        
        # ==================================================
        # 'private' -- do not interfere with these variables
        # ==================================================
        
        # Gerbil can be used in both console applications as well as GUIs. In both cases, 
        self._logger = logging.getLogger("gerbil")
        self._loghandler = CallbackLogHandler()
        self._logger.addHandler(self._loghandler)
        self._logger.setLevel(5)
        self._logger.propagate = False
                                              
        self._ifacepath = ifacepath
        
        self._gcode_parser_state_requested = False
        
        self._last_cmode = None
        self._last_cmpos = (0, 0, 0)
        self._last_cwpos = (0, 0, 0)
        
        self._rx_buffer_size = 128
        self._rx_buffer_fill = []
        self._rx_buffer_backlog = []
        self._rx_buffer_backlog_line_number = []
        self._rx_buffer_fill_percent = 0
        
        self._gcodefilename = None
        self._gcodefilesize = 999999999
        
        self._current_line = "; cnctools_INIT" # explicit init string for debugging
        self._current_line_sent = True

        # state variables
        self._streaming_mode = None
        self._incremental_streaming = False
        
        self._wait_empty_buffer = False
        
        self._streaming_complete = True
        self._job_finished = True
        self._streaming_src_end_reached = True
        self._streaming_enabled = True
        self._error = False
        self._alarm = False
        
        self._buffer = []
        self._buffer_size = 0
        self._current_line_nr = 0

        self.connected = False
        
        # for interrupting long-running tasks in threads
        self._poll_keep_alive = False
        self._iface_read_do = False
        
        # this class maintains two threads
        self._thread_polling = None
        self._thread_read_iface = None
        
        self._iface = None
        self._queue = Queue()
        
        self.callback = self._default_callback
        
        self._preprocessor = Preprocessor()
        
        atexit.register(self.disconnect)
        
        
    ## ====== 'public' methods ======
    
    def set_callback(self, cb):
        self.callback = cb
        self._preprocessor.callback = cb
        self._loghandler.callback = cb
      
    def cnect(self,path=False):
        """
        Connect to the RS232 port of the Grbl controller. This is done by instantiating a RS232 object which by itself block-listens (in a thread) to asynchronous data sent by the Grbl controller. To read these data, the method 'self._onread' will block-run in a separate thread and fetch data via a thread queue. Once this is set up, we soft-reset the Grbl controller, after which status polling starts.
        
        The only argument to this method is `path` (e.g. /dev/ttyACM0), which you can set if you haven't given the path during object instatiation.
        """
        
        if path:
            self._ifacepath = path
            
        self._cleanup()
        
        if self._iface == None:
            self.callback("on_log", "{}: Setting up interface on {}".format(self.name, self._ifacepath))
            self._iface = Interface("iface_" + self.name, self._ifacepath, 115200)
            self._iface.start(self._queue)
        else:
            self.callback("on_log", "{}: Cannot start another interface. There is already an interface {}. This should not have happened.".format(self.name, self._iface))
            
        self._iface_read_do = True
        self._thread_read_iface = threading.Thread(target=self._onread)
        self._thread_read_iface.start()
        
        
    def disconnect(self):
        """
        This method stops all threads, joins them, then closes the serial connection.
        """
        if self.is_connected() == False: return
        
        self.poll_stop()
        
        self._iface.stop()
        self._iface = None
        
        self.callback("on_log", "{}: Please wait until reading thread has joined...".format(self.name))
        self._iface_read_do = False
        self._queue.put("dummy_msg_for_joining_thread")
        self._thread_read_iface.join()
        self.callback("on_log", "{}: Reading thread successfully joined.".format(self.name))
        
        self.connected = False
        
        self._cleanup()
        
        self.callback("on_disconnected")
        
        
    def abort(self):
        """
        An alias for `softreset()`, but also performs cleaning up.
        """
        if self.is_connected() == False: return
        self.softreset()
        self._cleanup()
        
        
    def hold(self):
        """
        An alias for sending an exclamation mark.
        """
        if self.is_connected() == False: return
        self._iface_write("!")
        
        
    def resume(self):
        """
        An alias for sending a tilde.
        """
        if self.is_connected() == False: return
        self._iface_write("~")
        
        
    def killalarm(self):
        """
        An alias for sending $X, but also performs a cleanup of data
        """
        self._iface_write("$X\n")
        #self._cleanup()
        
        
    def softreset(self):
        """
        An alias for sending Ctrl-X
        """
        self._iface.write("\x18") # Ctrl-X
        
        
    def homing(self):
        """
        An alias for sending $H
        """
        self._iface_write("$H\n")
        
        
    def poll_start(self):
        """
        Start method `_poll_state()` in a thread, which sends question marks in regular intervals forever, or until _poll_keep_alive is set to False. Grbl responds to the question marks with a status string enclosed in angle brackets < and >.
        """
        if self.is_connected() == False: return
        self._poll_keep_alive = True
        if self._thread_polling == None:
            self._thread_polling = threading.Thread(target=self._poll_state)
            self._thread_polling.start()
            self.callback("on_log", "{}: Polling thread started".format(self.name))
        else:
            self.callback("on_log", "{}: Polling thread already running...".format(self.name))
            
        
    def poll_stop(self):
        """
        Set _poll_keep_alive to False, which completes the status polling thread. This method also joins the thread to make sure it comes to a well defined end.
        """
        if self.is_connected() == False: return
        if self._thread_polling != None:
            self._poll_keep_alive = False
            self.callback("on_log", "{}: Please wait until polling thread has joined...".format(self.name))
            self._thread_polling.join()
            self.callback("on_log", "{}: Polling thread has successfully  joined...".format(self.name))
        else:
            self.callback("on_log", "{}: Cannot start a polling thread. Another one is already running. This should not have happened.".format(self.name))
            
        self._thread_polling = None
        
        
    def settings_from_file(self, filename):
        # Needs testing
        return
        if self.cmode == "Idle":
            self.callback("on_log", "{}: Stopping polling.".format(self.name))
            self.poll_stop()
            time.sleep(1)
            self.callback("on_log", "{}: Writing settings.".format(self.name))
            self.send("".join([x for x in open(filename).readlines()]))
            time.sleep(1)
            self.callback("on_log", "{}: Restarting polling.".format(self.name))
            self.poll_start()
        else:
            self.callback("on_log", "{}: Grbl has to be idle to stream settings.".format(self.name))
            
            
    def set_feed_override(self, val):
        """
        Pass True or False as argument to enable or disable feed override. If you pass True, all F gcode-commands will be stripped out from the stream. In addition, no feed override takes place until you also have set the requested feed via the method `set_feed()`.
        """
        self._preprocessor.set_feed_override(val)
        
        
    def request_feed(self, requested_feed):
        """
        Override the feed speed (in mm/min). Effecive only when you set `set_feed_override(True)`. An 'overriding' F gcode command will be inserted into the stream only when the currently requested feed differs from the last requested feed.
        """
        self._preprocessor.request_feed(float(requested_feed))
        
    def request_gcode_parser_state(self):
        self._gcode_parser_state_requested = True
        
    def set_incremental_streaming(self, a):
        """
        Pass True to enable incremental streaming. The default is False.
        
        Incremental streaming means that a new command is sent to Grbl only after Grbl has responded with 'ok' to the last sent command.
        
        Non-incremental streaming means that Grbl's 128-byte receive buffer will be kept as full as possible at all times, to give it's motion planner system enough data to work with. This results in smoother and faster axis motion.
        
        You can change the streaming method even during streaming.
        """
        self._incremental_streaming = a
        if self._incremental_streaming == True:
            self._wait_empty_buffer = True
        self.callback("on_log", "{}: Incremental streaming is {}".format(self.name, self._incremental_streaming))
        
        
    def send_immediately(self, line):
        """
        Strings passed to this function will bypass buffer management and preprocessing and will be sent to Grbl (and executed) immediately. Use this function with caution: Only send when you are sure Grbl's receive buffer can handle the data volume and when it doesn't interfere with currently running streams. Only send single commands at a time. Applications: manual jogging, coordinate settings.
        """
        line = self._preprocessor.tidy(line)
        line = self._preprocessor.handle_feed(line)
        self._iface.write(line + "\n")
        self.request_gcode_parser_state()
        
        
    def send_with_queue(self, source):
        """
        Strings passed to this function will be sent to Grbl (and executed) but WITH buffer management. If there is a currently running stream, data will be appended to the buffer, else the buffer will be reset and will only contain the data.
        """
        self._gcodefilename = None
        
        #if self._job_finished == True:
            #del self._buffer[:]
            #self._buffer_size = 0
            #self._current_line_nr = 0
            
        self._load_lines_into_buffer(source)
        self.stream_start()
        #self._set_streaming_src_end_reached(False)
        #self._set_streaming_complete(False)
        
        #self._stream() 
        #self._set_job_finished(False)
        
        
    def write(self, string):
        """
        The Compiler class requires a method "write" to be present. This just appends lines to _buffer. `stream_start()` must be called separately.
        """
        self._gcodefilename = None
        lines = string.split("\n")
        for line in lines:
            tidy_line = self._preprocessor.tidy(line)
            if tidy_line != "":
                self._buffer.append(tidy_line)
                self._buffer_size += 1
                
        self.callback("on_loaded", "string", self._buffer_size)
        

    def load_file(self, filename):
        """
        _buffer will be erased and filled with all file contents. Line numbers will become the file's line numbers.
        """
        if self._job_finished == False:
            self.callback("on_log", "{}: Job must be finished before you can load a file".format(self.name))
            return
        
        self.stream_clear()
        
        self._gcodefilename = filename # remember filename
        
        #del self._buffer[:]
        #self._buffer_size = 0
        #self._current_line_nr = 0
        
        
        with open(filename) as f:
            for line in f:
                tidy_line = self._preprocessor.tidy(line)
                self._buffer.append(tidy_line)
                self._buffer_size += 1
                
        self.callback("on_loaded", "file", self._buffer_size, self._gcodefilename)
        
    
    def stream_start(self, linenr=None):
        """
        Start stream from specific line
        """
        if self._buffer_size == 0:
            self.callback("on_log", "{}: Nothing in the buffer!".format(self.name))
            return
        
        self._set_streaming_src_end_reached(False)
        self._set_streaming_complete(False)
        
        if linenr:
            self.set_current_line_number(linenr)
            
        self._streaming_enabled = True
        self._set_job_finished(False)
        self._stream() 
        
            
        
        
        
    def stream_stop(self):
        self._streaming_enabled = False
        

    def stream_clear(self):
        del self._buffer[:]
        self._buffer_size = 0
        self._current_line_nr = 0
        self.callback("on_line_number_change", self._current_line_nr)
        self._gcodefilename = None
        self.callback("on_loaded", "string", 0)
        self._set_streaming_complete(True)
        self._set_job_finished(True)
        self._set_streaming_src_end_reached(True)
        self._error = False
        self._current_line = "; cnctools_CLEANUP" # explicit magic string for debugging
        self._current_line_sent = True
    
    def set_current_line_number(self, linenr):
        if linenr < self._buffer_size:
            self._current_line_nr = linenr
            self.callback("on_line_number_change", self._current_line_nr)
    
    def set_target(self, targetstring):
        self._target = targetstring
        
    def get_buffer(self):
        return self._buffer

    # ====== 'private' methods ======
    
    #def _log(self, level, string):
        #if self._logging_method == "callback" and level >= self._logging_level:
            #self.callback("on_log", "{}: {}".format(self.name, string))
        #else:
            #self._logger.log(level, sring)
        
    def _stream(self):
        """
        Take commands from _buffer and send them to Grbl, either one-by-one, or until
        its buffer is full.
        """
        if self._streaming_src_end_reached:
            self._logger.debug("_stream(): Nothing more in _buffer.")
            return
        
        if self._streaming_enabled == False:
            self._logger.debug("_stream(): Streaming has been stopped. Call `stream_start()` to resume.")
            return
        
        if self._incremental_streaming:
            self._set_next_line()
            if self._streaming_src_end_reached == False:
                self._send_current_line()
                
        else:
            self._fill_rx_buffer_until_full()

        
        
    def _fill_rx_buffer_until_full(self):
        """
        Does what the function name says.
        """
        while True:
            if self._current_line_sent == True:
                self._set_next_line()
            
            if self._streaming_src_end_reached == False and  self._rx_buf_can_receive_current_line():
                self._send_current_line()
            else:
                break
                
                
                
    def _set_next_line(self):
        """
        Gets next line from file or _buffer, and sets _current_gcodeblock
        """

        progress_percent = int(100 * self._current_line_nr / self._buffer_size)
        self.callback("on_progress_percent", progress_percent)

        if self._current_line_nr < self._buffer_size:
            # still something in _buffer, pop it
            line = self._buffer[self._current_line_nr].strip()
            preprocessed_line = self._preprocess(line)
            self._current_line = preprocessed_line
            self._current_line_sent = False
            self._current_line_nr += 1
                
        else:
            # the buffer is empty, nothing more to read
            self._set_streaming_src_end_reached(True)

        
    def _send_current_line(self):
        """
        Unconditionally sends the current line to Grbl.
        """
        self._set_streaming_complete(False)
        line_length = len(self._current_line) + 1 # +1 for \n which we will append below
        self._rx_buffer_fill.append(line_length) 
        self._rx_buffer_backlog.append(self._current_line)
        self._rx_buffer_backlog_line_number.append(self._current_line_nr)
        self._iface_write(self._current_line + "\n")
        self._current_line_sent = True
    
    
    def _rx_buf_can_receive_current_line(self):
        """
        Returns True or False depeding on Grbl's rx buffer can hold _current_line
        """
        rx_free_bytes = self._rx_buffer_size - sum(self._rx_buffer_fill)
        required_bytes = len(self._current_line) + 1 # +1 because \n
        return rx_free_bytes >= required_bytes
    
    
    
    def _preprocess(self, line):
        contains_setting = re.match("\$[^CXHG$#]", line)
        if contains_setting and self._incremental_streaming == False:
            self.callback("on_log", "{}: I encountered a settings command '{}' in the gcode stream but the current streaming mode is not set to incremental. Grbl cannot handle that. I will not send the $ command.".format(self.name, line))
            line = "; setting stripped"
            
        # gcode feed processing
        line = self._preprocessor.handle_feed(line)

        return line
    
        
    def _rx_buffer_fill_pop(self):
        """
        We keep a backlog (_rx_buffer_fill) of command sizes in bytes to know at any time how full Grbl's rx buffer is. Once we receive an 'ok' from Grbl, we can remove the first element in this backlog.
        """
        if len(self._rx_buffer_fill) > 0:
            self._rx_buffer_fill.pop(0)
            processed_command = self._rx_buffer_backlog.pop(0)
            self.current_line_number = self._rx_buffer_backlog_line_number.pop(0)
            self.callback("on_processed_command", self.current_line_number, processed_command)
            
        if self._streaming_src_end_reached == True and len(self._rx_buffer_fill) == 0:
            self._set_job_finished(True)
            self._set_streaming_complete(True)
            self.callback("on_log", "{}: Job completed".format(self.name))
    
    
    def _iface_write(self, data):
        """
        A convenient wrapper around _iface.write with a callback for UI's
        """
        num_written = self._iface.write(data)
        self.callback("on_send_command", data.strip())
        
        
    def _onread(self):
        """
        This method is run in a separate Thread. It blocks at the line queue.get() until the RS232 object put()'s something into this queue asynchronously. It's an endless loop, interruptable by setting _iface_read_do to False.
        """
        while self._iface_read_do == True:
            line = self._queue.get()
            
            if len(line) > 0:
                if line[0] == "<":
                    #self._logger.debug("%s <----- %s", self.name, line)
                    self._update_state(line)
                    
                elif line[0] == "[":
                    #self._logger.debug("%s <----- %s", self.name, line)
                    self._update_gcode_parser_state(line)
                    
                elif "Grbl " in line:
                    #self._logger.debug("%s <----- %s", self.name, line)
                    self._on_bootup()
                    
                elif line == "ok":
                    #self._logger.debug("OK")
                    self._handle_ok()
                    
                elif "ALARM" in line:
                    self.callback("on_alarm", line)
                    
                elif "error" in line:
                    self._logger.debug("ERROR")
                    self._error = True
                    self._logger.debug("%s: _rx_buffer_backlog at time of error: %s", self.name,  self._rx_buffer_backlog)
                    if len(self._rx_buffer_backlog) > 0:
                        problem_command = self._rx_buffer_backlog[0]
                        problem_line = self._rx_buffer_backlog_line_number[0]
                    else:
                        problem_command = "unknown"
                        problem_line = -1
                        
                    self.callback("on_error", line, problem_command, problem_line)
                        
                else:
                    self._logger.debug("%s <----- %s", self.name, line)
                    self.callback("on_read", line)
                
                
    def _handle_ok(self):
        """
        When we receive an 'ok' from Grbl, submit more.
        """
        if self._streaming_complete == False:
            self._rx_buffer_fill_pop()
            if not (self._wait_empty_buffer and len(self._rx_buffer_fill) > 0):
                self._wait_empty_buffer = False
                self._stream()
        
        self._rx_buffer_fill_percent = int(100 - 100 * (self._rx_buffer_size - sum(self._rx_buffer_fill)) / self._rx_buffer_size)
        self.callback("on_rx_buffer_percentage", self._rx_buffer_fill_percent)
                
                            
    def _on_bootup(self):
        self._cleanup()
        self.connected = True
        self.callback("on_log", "{}: Booted!".format(self.name))
        self.callback("on_boot")
        #self.poll_start()
            
    def _update_gcode_parser_state(self, line):
        """
        Parse Grbl's Gcode parser state report and inform via callback
        """
        m = re.match("\[G(\d) G(\d\d) G(\d\d) G(\d\d) G(\d\d) G(\d\d) M(\d) M(\d) M(\d) T(\d) F([\d.-]*?) S([\d.-]*?)\]", line)
        if m:
            self.gps[0] = m.group(1) # motionmode
            self.gps[1] = m.group(2) # coordinate system
            self.gps[2] = m.group(3) # plane
            self.gps[3] = m.group(4) # units
            self.gps[4] = m.group(5) # dist
            self.gps[5] = m.group(6) # feed rate mode
            self.gps[6] = m.group(7) # program mode
            self.gps[7] = m.group(8) # spindle state
            self.gps[8] = m.group(9) # coolant state
            self.gps[9] = m.group(10) # tool number
            self.gps[10] = m.group(11) # current feed
            self.gps[11] = m.group(12) # current rpm
            self.callback("on_gcode_parser_stateupdate", self.gps)
        else:
            pass
            #logging.log(300, "%s: Could not parse gcode parser report: '%s'", self.name, line)
        
            
    def _update_state(self, line):
        """
        Parse Grbl's status line and inform via callback
        """
        m = re.match("<(.*?),MPos:(.*?),WPos:(.*?)>", line)
        self.cmode = m.group(1)
        mpos_parts = m.group(2).split(",")
        wpos_parts = m.group(3).split(",")
        self.cmpos = (float(mpos_parts[0]), float(mpos_parts[1]), float(mpos_parts[2]))
        self.cwpos = (float(wpos_parts[0]), float(wpos_parts[1]), float(wpos_parts[2]))
        #self.callback("on_log", "=== STATE === %s %s %s", self.name, self.cmode, self.cmpos, self.cwpos)
        
        if (self.cmode != self._last_cmode or
            self.cmpos != self._last_cmpos or
            self.cwpos != self._last_cwpos):
            self.callback("on_stateupdate", self.cmode, self.cmpos, self.cwpos)
        
        self._last_cmode = self.cmode
        self._last_cmpos = self.cmpos
        self._last_cwpos = self.cwpos
        
        
    def _load_lines_into_buffer(self, string):
        """
        Send single lines or several lines. If sending several lines, lines must be \n terminated.
        """
        print("_load_lines_into_buffer")
        self._gcodefilename = None
        
        lines = string.split("\n")
        for line in lines:
            tidy_line = self._preprocessor.tidy(line)
            if tidy_line != "":
                # ignore all empty lines
                self._buffer.append(self._preprocess(line))
                self._buffer_size += 1
                
        self.callback("on_loaded", "string", self._buffer_size)
        
        
    def is_connected(self):
        if self.connected != True:
            self.callback("on_log", "{}: Not yet connected".format(self.name))
        return self.connected
    
    
    def _cleanup(self):
        """
        called after boot. Should mimic Grbl's initial state after boot.
        """
        del self._rx_buffer_fill[:]
        del self._rx_buffer_backlog[:]
        del self._rx_buffer_backlog_line_number[:]
        self._set_streaming_complete(True)
        self._set_job_finished(True)
        self._set_streaming_src_end_reached(True)
        self._error = False
        self._current_line = "; cnctools_CLEANUP" # explicit magic string for debugging
        self._current_line_sent = True
        self._clear_queue()
        self._preprocessor.cleanup()
        
        
    def _clear_queue(self):
        try:
            junk = self._queue.get_nowait()
            self._logger.debug("Discarding junk %s", junk)
        except:
            self._logger.debug("Queue was empty")
            
            
    def _poll_state(self):
        while self._poll_keep_alive == True:
            if self._gcode_parser_state_requested:
                self._get_gcode_parser_state()
                self._gcode_parser_state_requested = False
            else:
                self._get_state()
                
            time.sleep(self.poll_interval)
            
        self.callback("on_log", "{}: Polling has been stopped".format(self.name))
        
        
    def _get_state(self):
        self._iface.write("?")
        
        
    def _get_gcode_parser_state(self):
        self._iface.write("$G\n")
        
            
    def _set_streaming_src_end_reached(self, a):
        self._streaming_src_end_reached = a
        #self.callback("on_log", "{}: Streaming source end reached: {}".format(self.name, a))


    # The buffer has been fully written to Grbl, but Grbl is still processing the last commands.
    def _set_streaming_complete(self, a):
        self._streaming_complete = a
        #self.callback("on_log", "{}: Streaming completed: {}".format(self.name, a))
        
        
    # Grbl has finished processing everything
    def _set_job_finished(self, a):
        self._job_finished = a
        #self.callback("on_log", "{}: Job finished: {}".format(self.name, a))
        

    def _default_callback(self, status, *args):
        print("GRBL DEFAULT CALLBACK", status, args)