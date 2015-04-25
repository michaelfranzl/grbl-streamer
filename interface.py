import serial
import time
import threading
import logging

class Interface:
    def __init__(self, name="", path="/dev/null", baud=115200):
        self.name = name
        self.path = path
        self.baud = baud
        
        self.queue = None
        
        self._buf_receive = ""
        self._do_receive = False
        
        
    def start(self, q):
        self.queue = q
        logging.log(100, "%s: connecting to %s", self.name, self.path)
        self.serialport = serial.Serial(self.path, self.baud, timeout=1)
        
        self.serialport.flushInput()
        self.serialport.flushOutput()
        
        self._do_receive = True
        
        self.serial_thread = threading.Thread(target=self._receiving)
        self.serial_thread.start()
        
        
    def stop(self):
        self._do_receive = False
        logging.log(100, "%s: stop()", self.name)
        self.serial_thread.join()
        logging.log(100, "%s: JOINED thread", self.name)
        logging.log(100, "%s: Closing port", self.name)
        self.serialport.flushInput()
        self.serialport.flushOutput()
        self.serialport.close()
        
        
    def write(self, data):
        if len(data) > 0:
            if not "?" in data and not "$" in data:
                logging.log(200, "%s:     -----------> %ibytes %s", self.name, len(data), data.strip())
            num_written = self.serialport.write(bytes(data,"ascii"))
            return num_written
            #logging.log(100, "%s: num_written %s", self.name, num_written)
        else:
            logging.log(100, "%s: nothing to write", self.name)

    # 'private' functions

    def _receiving(self):
        while self._do_receive == True:
            data = self.serialport.read(1)
            waiting = self.serialport.inWaiting()
            #logging.log(100, "%s: READING %s %s", self.name, waiting, data)
            data += self.serialport.read(waiting)
            self._handle_data(data)


    def _handle_data(self, data):
        try:
            asci = data.decode("ascii")
        except UnicodeDecodeError:
            logging.log(100, "%s: Received a non-ascii byte. Probably junk. Dropping it.", self.name)
            asci = ""
            
        for i in range(0, len(asci)):
            char = asci[i]
            self._buf_receive += char
            if char == "\n":
                self.queue.put(self._buf_receive.strip())
                self._buf_receive = ""
