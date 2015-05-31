import logging

class CallbackLogHandler(logging.StreamHandler):
    def __init__(self, cb=None):
        super(CallbackLogHandler, self).__init__()
        self.callback = cb

    def emit(self, record):
        if self.callback:
            self.callback("on_log", record.getMessage())
        else:
            logging.StreamHandler.emit(self, record)