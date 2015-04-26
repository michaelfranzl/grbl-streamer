import logging

class CallbackLogHandler(logging.StreamHandler):
    def __init__(self, cb=None):
        super(CallbackLogHandler, self).__init__()
        self.callback = cb

    def emit(self, record):
        s = self.format(record)
        #logging.StreamHandler.emit(self, record)
        #return
        
        if self.callback:
            self.callback("on_log", record.message)
        else:
            #print("NO CALLBACK", record.message)
            logging.StreamHandler.emit(self, record)