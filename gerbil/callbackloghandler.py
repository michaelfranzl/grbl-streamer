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
            self.callback("on_log", record)
        else:
            logging.StreamHandler.emit(self, record)